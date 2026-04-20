from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

import anyio

from agent_operator.application.loaded_operation import LoadedOperation
from agent_operator.application.operation_lifecycle import OperationLifecycleCoordinator
from agent_operator.domain import (
    BrainActionType,
    FocusKind,
    FocusMode,
    FocusState,
    InterruptPolicy,
    IterationState,
    OperationOutcome,
    OperationState,
    OperationStatus,
    PlanningTrigger,
    RunMode,
    RunOptions,
    TaskState,
    TaskStatus,
)
from agent_operator.protocols import OperationStore, OperatorPolicy


class HistoryLedger(Protocol):
    async def append(self, state: OperationState, outcome: OperationOutcome) -> None: ...


class OperationDriveRuntime(Protocol):
    """Runtime reconciliation and gating surface required by the drive loop."""

    async def _refresh_policy_context(self, state: OperationState) -> None: ...

    async def _refresh_available_agent_descriptors(self, state: OperationState) -> None: ...

    async def _cleanup_orphaned_background_runs(self, state: OperationState) -> None: ...

    async def _clear_expired_session_cooldowns(self, state: OperationState) -> None: ...

    async def _migrate_legacy_rate_limit_failures(self, state: OperationState) -> None: ...

    def _should_use_background_runtime(self, options: RunOptions) -> bool: ...

    async def _sync_terminal_background_runs(self, state: OperationState) -> None: ...

    async def _reconcile_stale_background_runs(self, state: OperationState) -> None: ...

    async def _reconcile_background_wakeups(self, state: OperationState) -> None: ...

    def _is_blocked_on_background_wait(self, state: OperationState) -> bool: ...

    def _materialize_pause_if_ready(self, state: OperationState) -> None: ...

    def _is_scheduler_paused(self, state: OperationState) -> bool: ...

    def _should_retry_from_recoverable_block(self, state: OperationState) -> bool: ...

    def _reconcile_state(self, state: OperationState) -> None: ...


class OperationDriveControl(Protocol):
    """Command and planning-trigger control surface required by the drive loop."""

    async def _drain_commands(self, state: OperationState) -> None: ...

    async def _has_pending_planning_triggers(self, state: OperationState) -> bool: ...

    async def _drain_pending_planning_triggers(
        self,
        state: OperationState,
        *,
        iteration: int,
    ) -> list[PlanningTrigger]: ...

    async def _finalize_pending_attention_resolutions(self, state: OperationState) -> None: ...


class OperationDriveTrace(Protocol):
    """Traceability and event emission surface required by the drive loop."""

    async def _emit(
        self,
        event_type: str,
        state: OperationState,
        iteration: int,
        payload: dict[str, object],
        *,
        task_id: str | None = None,
        session_id: str | None = None,
    ) -> None: ...

    async def _record_decision_memo(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
    ) -> None: ...

    async def _record_iteration_brief(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
    ) -> None: ...

    async def _sync_traceability_artifacts(self, state: OperationState) -> None: ...

    def _default_outcome_summary(self, state: OperationState) -> str: ...


class OperationDecisionExecutor(Protocol):
    """Decision execution surface required by the drive loop."""

    async def _execute_decision(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        options: RunOptions,
    ) -> bool: ...


class OperationDriveService:
    """Run the main operation orchestration loop outside the public facade."""

    def __init__(
        self,
        *,
        operator_policy: OperatorPolicy,
        store: OperationStore,
        loaded_operation: LoadedOperation,
        runtime: OperationDriveRuntime,
        control: OperationDriveControl,
        trace: OperationDriveTrace,
        decision_executor: OperationDecisionExecutor,
        lifecycle_coordinator: OperationLifecycleCoordinator,
    ) -> None:
        self._operator_policy = operator_policy
        self._store = store
        self._loaded_operation = loaded_operation
        self._runtime = runtime
        self._control = control
        self._trace = trace
        self._decision_executor = decision_executor
        self._lifecycle_coordinator = lifecycle_coordinator

    @staticmethod
    def _message_is_active_this_cycle(message: object, *, window: int) -> bool:
        planning_cycles_active = getattr(message, "planning_cycles_active", None)
        dropped_from_context = getattr(message, "dropped_from_context", None)
        if not isinstance(planning_cycles_active, int) or dropped_from_context is not False:
            return False
        return planning_cycles_active == 0 or planning_cycles_active < window

    async def _age_operator_messages_after_planning_cycle(
        self,
        state: OperationState,
        *,
        iteration: int,
    ) -> None:
        """Advance operator-message planning age and emit explicit drop events."""
        window = state.runtime_hints.operator_message_window
        for message in state.operator_messages:
            if not self._message_is_active_this_cycle(message, window=window):
                continue
            message.planning_cycles_active += 1
            if message.planning_cycles_active < window:
                continue
            message.dropped_from_context = True
            await self._trace._emit(
                "operator_message.dropped_from_context",
                state,
                iteration,
                {
                    "message_id": message.message_id,
                    "text_preview": message.text[:120],
                    "planning_cycles_active": message.planning_cycles_active,
                    "operator_message_window": window,
                },
            )

    async def _advance_checkpoint(self, state: OperationState) -> None:
        """Persist a durable snapshot of event-sourced state for fast resume.

        This is a read-path checkpoint helper. It does not mutate state and is
        not the canonical write path — the event log is. Callers must not add
        new mutation logic immediately before this call; mutations must go
        through event emission first.
        """
        await self._store.save_operation(state)

    async def drive(
        self,
        state: OperationState,
        options: RunOptions,
    ) -> OperationOutcome:
        """Execute the orchestration loop for one operation state."""
        cycle_budget = options.max_cycles or state.execution_budget.max_iterations
        cycles_executed = 0

        await self._runtime._refresh_policy_context(state)
        await self._runtime._refresh_available_agent_descriptors(state)
        await self._runtime._cleanup_orphaned_background_runs(state)
        await self._runtime._clear_expired_session_cooldowns(state)
        await self._runtime._migrate_legacy_rate_limit_failures(state)
        if (
            state.execution_budget.timeout_seconds is not None
            and state.run_started_at is not None
            and (
                datetime.now(UTC) - state.run_started_at
            ).total_seconds()
            >= float(state.execution_budget.timeout_seconds)
        ):
            previous_status = state.status
            self._lifecycle_coordinator.mark_failed(
                state,
                summary=f"Time limit of {state.execution_budget.timeout_seconds} seconds exceeded.",
            )
            await self._trace._emit(
                "operation.status.changed",
                state,
                0,
                {
                    "previous_status": previous_status.value,
                    "new_status": state.status.value,
                    "reason": "timeout_seconds",
                },
            )
            outcome = await self._lifecycle_coordinator.finalize_outcome(
                state,
                final_result=self._loaded_operation.find_latest_result(state),
            )
            await self._trace._sync_traceability_artifacts(state)
            return outcome
        if self._runtime._should_use_background_runtime(options):
            await self._runtime._sync_terminal_background_runs(state)
        await self._runtime._reconcile_stale_background_runs(state)
        await self._runtime._reconcile_background_wakeups(state)
        await self._trace._sync_traceability_artifacts(state)
        await self._advance_checkpoint(state)
        await self._control._drain_commands(state)

        while (
            (
                state.status is OperationStatus.RUNNING
                or state.status is OperationStatus.NEEDS_HUMAN
                and self._runtime._should_retry_from_recoverable_block(state)
                or await self._control._has_pending_planning_triggers(state)
                or bool(state.pending_attention_resolution_ids)
            )
            and len(state.iterations) < state.execution_budget.max_iterations
            and cycles_executed < cycle_budget
        ):
            self._runtime._materialize_pause_if_ready(state)
            if self._runtime._is_scheduler_paused(state):
                break
            if (
                state.status is OperationStatus.NEEDS_HUMAN
                and self._runtime._should_retry_from_recoverable_block(state)
            ):
                self._lifecycle_coordinator.mark_running(state)
            await self._control._drain_commands(state)
            await self._runtime._reconcile_stale_background_runs(state)
            await self._runtime._reconcile_background_wakeups(state)
            await self._runtime._clear_expired_session_cooldowns(state)
            self._runtime._materialize_pause_if_ready(state)
            if self._runtime._is_scheduler_paused(state):
                break
            if (
                options.run_mode is RunMode.ATTACHED
                and self._runtime._is_blocked_on_background_wait(state)
            ):
                await self._advance_checkpoint(state)
                await anyio.sleep(1.0)
                continue
            if (
                self._runtime._is_blocked_on_background_wait(state)
                and state.current_focus is not None
                and state.current_focus.interrupt_policy is InterruptPolicy.MATERIAL_WAKEUP
            ):
                has_active_operator_messages = any(
                    self._message_is_active_this_cycle(
                        m, window=state.runtime_hints.operator_message_window
                    )
                    for m in state.operator_messages
                )
                if not has_active_operator_messages and not state.pending_attention_resolution_ids:
                    await self._advance_checkpoint(state)
                    break
            await self._control._drain_pending_planning_triggers(
                state,
                iteration=len(state.iterations),
            )
            cycles_executed += 1
            self._runtime._reconcile_state(state)
            await self._runtime._refresh_policy_context(state)
            await self._runtime._refresh_available_agent_descriptors(state)
            planning_state = state.model_copy(deep=True)
            window = state.runtime_hints.operator_message_window
            planning_state.operator_messages = [
                message.model_copy(deep=True)
                for message in state.operator_messages
                if self._message_is_active_this_cycle(message, window=window)
            ]
            decision = await self._operator_policy.decide_next_action(planning_state)
            await self._age_operator_messages_after_planning_cycle(
                state,
                iteration=len(state.iterations) + 1,
            )
            self._loaded_operation.apply_task_mutations(
                state,
                decision.new_tasks,
                decision.task_updates,
            )
            task = self._loaded_operation.resolve_focus_task(state, decision.focus_task_id)
            if (
                decision.action_type is BrainActionType.START_AGENT
                and task is not None
                and task.status in {
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                }
            ):
                task = None
            iteration = IterationState(
                index=len(state.iterations) + 1,
                decision=decision,
                task_id=task.task_id if task is not None else None,
            )
            state.iterations.append(iteration)
            state.updated_at = datetime.now(UTC)

            await self._trace._emit(
                "brain.decision.made",
                state,
                iteration.index,
                decision.model_dump(mode="json"),
                task_id=iteration.task_id,
            )
            await self._trace._record_decision_memo(state, iteration, task)
            await self._control._finalize_pending_attention_resolutions(state)

            if decision.blocking_focus is not None:
                state.current_focus = FocusState(
                    kind=decision.blocking_focus.kind,
                    target_id=decision.blocking_focus.target_id,
                    mode=FocusMode.BLOCKING,
                    blocking_reason=decision.blocking_focus.blocking_reason,
                    interrupt_policy=decision.blocking_focus.interrupt_policy,
                    resume_policy=decision.blocking_focus.resume_policy,
                )
            elif task is not None:
                state.current_focus = FocusState(
                    kind=FocusKind.TASK,
                    target_id=task.task_id,
                    mode=FocusMode.ADVISORY,
                )

            try:
                should_break = await self._decision_executor._execute_decision(
                    state,
                    iteration,
                    task,
                    options,
                )
            except anyio.get_cancelled_exc_class():
                raise
            except Exception as exc:
                self._lifecycle_coordinator.mark_failed(state, summary=str(exc))
                if task is not None and task.status not in {
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                }:
                    task.status = TaskStatus.FAILED
                    task.updated_at = datetime.now(UTC)
                else:
                    self._loaded_operation.mark_root_task_terminal(
                        state,
                        TaskStatus.FAILED,
                    )
                await self._trace._record_iteration_brief(state, iteration, task)
                await self._trace._sync_traceability_artifacts(state)
                await self._advance_checkpoint(state)
                break
            await self._advance_checkpoint(state)
            if should_break:
                await self._trace._record_iteration_brief(state, iteration, task)
                await self._trace._sync_traceability_artifacts(state)
                await self._advance_checkpoint(state)
                if (
                    options.run_mode is RunMode.ATTACHED
                    and state.status is OperationStatus.NEEDS_HUMAN
                    and state.current_focus is not None
                    and state.current_focus.kind is FocusKind.ATTENTION_REQUEST
                ):
                    while state.status is OperationStatus.NEEDS_HUMAN:
                        await self._control._drain_commands(state)
                        if state.status is not OperationStatus.NEEDS_HUMAN:
                            break
                        await self._advance_checkpoint(state)
                        await anyio.sleep(1.0)
                    continue
                break
            self._runtime._materialize_pause_if_ready(state)
            if self._runtime._is_scheduler_paused(state):
                await self._trace._record_iteration_brief(state, iteration, task)
                await self._trace._sync_traceability_artifacts(state)
                await self._advance_checkpoint(state)
                break
            if state.status is OperationStatus.NEEDS_HUMAN:
                await self._trace._record_iteration_brief(state, iteration, task)
                await self._trace._sync_traceability_artifacts(state)
                await self._advance_checkpoint(state)
                break
            if state.status in {
                OperationStatus.COMPLETED,
                OperationStatus.FAILED,
                OperationStatus.CANCELLED,
            }:
                await self._trace._record_iteration_brief(state, iteration, task)
                await self._trace._sync_traceability_artifacts(state)
                await self._advance_checkpoint(state)
                break
            if iteration.result is None:
                await self._trace._record_iteration_brief(state, iteration, task)
                await self._trace._sync_traceability_artifacts(state)
                continue
            evaluation = await self._operator_policy.evaluate_result(state)
            await self._trace._emit(
                "evaluation.completed",
                state,
                iteration.index,
                evaluation.model_dump(mode="json"),
                task_id=iteration.task_id,
            )
            if not evaluation.should_continue:
                summary = evaluation.summary
                if evaluation.goal_satisfied:
                    self._lifecycle_coordinator.mark_completed(state, summary=summary)
                else:
                    self._lifecycle_coordinator.mark_needs_human(state, summary=summary)
                if evaluation.goal_satisfied:
                    self._loaded_operation.mark_root_task_terminal(
                        state,
                        TaskStatus.COMPLETED,
                    )
                elif task is not None and task.status not in {
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                }:
                    task.status = TaskStatus.BLOCKED
                    task.updated_at = datetime.now(UTC)
                await self._trace._record_iteration_brief(state, iteration, task)
                await self._trace._sync_traceability_artifacts(state)
                break
            await self._trace._record_iteration_brief(state, iteration, task)
            await self._trace._sync_traceability_artifacts(state)

        await self._control._finalize_pending_attention_resolutions(state)
        if (
            state.status is OperationStatus.RUNNING
            and len(state.iterations) >= state.execution_budget.max_iterations
        ):
            self._lifecycle_coordinator.mark_failed(
                state,
                summary="Maximum iterations reached.",
            )
            self._loaded_operation.mark_root_task_terminal(state, TaskStatus.FAILED)

        outcome = await self._lifecycle_coordinator.finalize_outcome(
            state,
            summary=state.final_summary or self._trace._default_outcome_summary(state),
            final_result=self._loaded_operation.find_latest_result(state),
        )
        await self._trace._sync_traceability_artifacts(state)
        await self._trace._emit(
            "operation.cycle_finished",
            state,
            len(state.iterations),
            outcome.model_dump(mode="json"),
        )
        return outcome
