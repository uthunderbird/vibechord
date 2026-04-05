from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agent_operator.application.agent_results import AgentResultService
from agent_operator.application.loaded_operation import LoadedOperation
from agent_operator.application.operation_event_relay import OperationEventRelay
from agent_operator.application.operation_lifecycle import OperationLifecycleCoordinator
from agent_operator.application.operation_runtime_context import OperationRuntimeContext
from agent_operator.application.operation_traceability import OperationTraceabilityService
from agent_operator.domain import (
    AgentError,
    AgentResult,
    AgentResultStatus,
    BackgroundRunStatus,
    FocusKind,
    FocusMode,
    FocusState,
    InterruptPolicy,
    OperationState,
    OperationStatus,
    ResumePolicy,
    RunEvent,
    SchedulerState,
    SessionRecordStatus,
    TaskStatus,
    WakeupRef,
)
from agent_operator.protocols import OperationRuntime, WakeupInbox


class OperationRuntimeReconciliationService:
    def __init__(
        self,
        *,
        loaded_operation: LoadedOperation,
        operation_runtime: OperationRuntime | None,
        wakeup_inbox: WakeupInbox | None,
        event_relay: OperationEventRelay,
        stale_background_run_threshold: timedelta,
        lifecycle_coordinator: OperationLifecycleCoordinator,
        runtime_context: OperationRuntimeContext,
        agent_result_service: AgentResultService,
        traceability_service: OperationTraceabilityService,
    ) -> None:
        self._loaded_operation = loaded_operation
        self._operation_runtime = operation_runtime
        self._wakeup_inbox = wakeup_inbox
        self._event_relay = event_relay
        self._stale_background_run_threshold = stale_background_run_threshold
        self._lifecycle_coordinator = lifecycle_coordinator
        self._runtime_context = runtime_context
        self._agent_result_service = agent_result_service
        self._traceability_service = traceability_service

    def materialize_pause_if_ready(self, state: OperationState) -> None:
        if (
            state.scheduler_state is SchedulerState.PAUSE_REQUESTED
            and not self._runtime_context.is_waiting_on_attached_turn(state)
        ):
            state.scheduler_state = SchedulerState.PAUSED

    def is_scheduler_paused(self, state: OperationState) -> bool:
        return state.scheduler_state is SchedulerState.PAUSED

    def reconcile_state(self, state: OperationState) -> None:
        state.objective_state.status = state.status
        if state.final_summary:
            state.objective_state.summary = state.final_summary
        task_map = {task.task_id: task for task in state.tasks}
        for task in state.tasks:
            if task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
                task.effective_priority = 0
                continue
            blocked = any(
                dependency not in task_map
                or task_map[dependency].status is not TaskStatus.COMPLETED
                for dependency in task.dependencies
            )
            if blocked:
                task.status = TaskStatus.BLOCKED
                task.effective_priority = 0
            elif task.status not in {TaskStatus.RUNNING, TaskStatus.COMPLETED}:
                task.status = TaskStatus.READY
                task.effective_priority = max(task.brain_priority - task.attempt_count * 5, 1)
            task.updated_at = datetime.now(UTC)
        active = self._loaded_operation.highest_priority_task(
            state,
            statuses={TaskStatus.READY, TaskStatus.RUNNING},
        )
        if active is not None and (
            state.current_focus is None or state.current_focus.mode is not FocusMode.BLOCKING
        ):
            state.current_focus = FocusState(
                kind=FocusKind.TASK,
                target_id=active.task_id,
                mode=FocusMode.ADVISORY,
            )
        self.sync_legacy_active_session(state)

    async def reconcile_background_wakeups(self, state: OperationState) -> None:
        if self._wakeup_inbox is None or self._operation_runtime is None:
            return
        await self._wakeup_inbox.requeue_stale_claims()
        claimed = await self._wakeup_inbox.claim(state.operation_id)
        state.pending_wakeups = [
            WakeupRef(
                event_id=event.event_id,
                event_type=event.event_type,
                task_id=event.task_id,
                session_id=event.session_id,
                dedupe_key=event.dedupe_key,
                claimed_at=datetime.now(UTC),
            )
            for event in claimed
        ]
        ack_ids: list[str] = []
        for event in claimed:
            await self.apply_wakeup_event(state, event)
            ack_ids.append(event.event_id)
        if ack_ids:
            await self._wakeup_inbox.ack(ack_ids)
            for ref in state.pending_wakeups:
                if ref.event_id in ack_ids:
                    ref.acked_at = datetime.now(UTC)
        state.pending_wakeups = [
            ref for ref in state.pending_wakeups if ref.event_id not in ack_ids
        ]

    async def reconcile_stale_background_runs(self, state: OperationState) -> None:
        if self._operation_runtime is None:
            return
        now = datetime.now(UTC)
        for existing in list(state.background_runs):
            existing_session_id = existing.session_id
            existing_task_id = existing.task_id
            if existing.status not in {BackgroundRunStatus.PENDING, BackgroundRunStatus.RUNNING}:
                continue
            run = await self._operation_runtime.poll_background_turn(existing.run_id)
            if run is not None:
                reconciled_session_id = run.session_id or existing_session_id
                reconciled_task_id = run.task_id or existing_task_id
                self._loaded_operation.upsert_background_run(
                    state,
                    run,
                    reconciled_session_id,
                    reconciled_task_id,
                )
                existing = run
                if run.status in {
                    BackgroundRunStatus.COMPLETED,
                    BackgroundRunStatus.FAILED,
                    BackgroundRunStatus.CANCELLED,
                    BackgroundRunStatus.DISCONNECTED,
                }:
                    await self.reconcile_terminal_background_run_from_supervisor(
                        state,
                        run,
                        session_id=reconciled_session_id,
                        task_id=reconciled_task_id,
                    )
                    continue
            if not self.background_run_is_stale(existing, now):
                continue
            await self.handle_stale_background_run(state, existing, now)

    async def clear_expired_session_cooldowns(self, state: OperationState) -> None:
        now = datetime.now(UTC)
        changed = False
        still_waiting = False
        for record in state.sessions:
            if record.cooldown_until is None:
                continue
            if record.cooldown_until > now:
                still_waiting = True
                continue
            record.cooldown_until = None
            record.cooldown_reason = None
            record.waiting_reason = None
            changed = True
            if record.status is SessionRecordStatus.WAITING:
                record.status = SessionRecordStatus.IDLE
            if (
                state.current_focus is not None
                and state.current_focus.kind is FocusKind.SESSION
                and state.current_focus.target_id == record.session_id
                and state.current_focus.interrupt_policy is InterruptPolicy.MATERIAL_WAKEUP
            ):
                state.current_focus = None
        if changed:
            if (
                state.status is OperationStatus.NEEDS_HUMAN
                and state.current_focus is None
                and not still_waiting
                and not state.pending_attention_resolution_ids
                and not state.pending_wakeups
            ):
                self._lifecycle_coordinator.mark_running(state)
            state.updated_at = datetime.now(UTC)

    async def migrate_legacy_rate_limit_failures(self, state: OperationState) -> None:
        if state.status is not OperationStatus.FAILED:
            return
        for record in state.sessions:
            if record.cooldown_until is not None or record.status is not SessionRecordStatus.FAILED:
                continue
            if record.latest_iteration is None:
                continue
            iteration = self._loaded_operation.find_iteration_for_session(
                state,
                record.handle.session_id,
                record.latest_iteration,
            )
            result = iteration.result if iteration is not None else None
            if result is None or result.error is None:
                continue
            error = result.error
            if not self._agent_result_service.is_legacy_rate_limit_error(error):
                continue
            retry_after_seconds = (
                self._agent_result_service.retry_after_seconds_from_raw(error.raw)
                if error.raw is not None
                else None
            )
            cooldown = self._agent_result_service.normalize_rate_limit_cooldown(
                retry_after_seconds
            )
            reason = (
                "Rate limit encountered on background/attached run and operator "
                "input is needed before retrying."
            )
            record.cooldown_until = cooldown
            record.cooldown_reason = reason
            record.status = SessionRecordStatus.WAITING
            record.waiting_reason = reason
            self._lifecycle_coordinator.mark_needs_human(state, summary=reason)
            if state.current_focus is None or state.current_focus.target_id != record.session_id:
                state.current_focus = FocusState(
                    kind=FocusKind.SESSION,
                    target_id=record.session_id,
                    mode=FocusMode.BLOCKING,
                    blocking_reason=reason,
                    interrupt_policy=InterruptPolicy.MATERIAL_WAKEUP,
                    resume_policy=ResumePolicy.REPLAN,
                )
            await self._agent_result_service.schedule_session_cooldown_expiry_wakeup(
                state,
                record.session_id,
                cooldown,
            )

    async def reconcile_terminal_background_run_from_supervisor(
        self,
        state: OperationState,
        run,
        *,
        session_id: str | None,
        task_id: str | None,
    ) -> None:
        if self._operation_runtime is None:
            return
        result = await self._operation_runtime.collect_background_turn(run.run_id)
        if result is None:
            return
        record = self._loaded_operation.find_session_record(state, session_id)
        if record is None or not self._loaded_operation.session_has_pending_result_slot(record):
            return
        iteration = self._loaded_operation.find_iteration_for_session(
            state,
            record.handle.session_id,
            record.latest_iteration,
        )
        if iteration is None:
            return
        task = self._loaded_operation.find_task(state, task_id) if task_id is not None else None
        await self._lifecycle_coordinator.fold_reconciled_terminal_result(
            state,
            iteration=iteration,
            task=task,
            session=record.handle,
            result=result,
            handle_agent_result=self._agent_result_service.handle_agent_result,
            record_iteration_brief=self._traceability_service.record_iteration_brief,
            clear_blocking_focus=True,
        )
        await self._event_relay.emit(
            "background_run.reconciled_from_supervisor",
            state,
            iteration.index,
            {
                "run_id": run.run_id,
                "session_id": session_id,
                "task_id": task_id,
                "status": run.status.value,
            },
            task_id=task_id,
            session_id=session_id,
        )

    async def sync_terminal_background_runs(self, state: OperationState) -> None:
        if self._operation_runtime is None:
            return
        for existing in state.background_runs:
            if existing.status not in {
                BackgroundRunStatus.COMPLETED,
                BackgroundRunStatus.FAILED,
                BackgroundRunStatus.CANCELLED,
            }:
                continue
            run = await self._operation_runtime.poll_background_turn(existing.run_id)
            if run is None or run.status in {
                BackgroundRunStatus.COMPLETED,
                BackgroundRunStatus.FAILED,
                BackgroundRunStatus.CANCELLED,
            }:
                continue
            await self._operation_runtime.finalize_background_turn(
                existing.run_id,
                existing.status,
                error=f"state_reconciled_{existing.status.value}",
            )

    async def handle_stale_background_run(self, state: OperationState, run, now: datetime) -> None:
        record = self._loaded_operation.find_session_record(state, run.session_id)
        if record is None or not self._loaded_operation.session_has_pending_result_slot(record):
            return
        result = None
        if self._operation_runtime is not None:
            try:
                result = await self._operation_runtime.collect_background_turn(run.run_id)
            except KeyError:
                result = None
        if result is None:
            result = AgentResult(
                session_id=run.session_id or f"background-{run.run_id}",
                status=AgentResultStatus.FAILED,
                output_text="",
                error=AgentError(
                    code="background_run_stale",
                    message=(
                        "Background agent turn lost heartbeat before delivering a "
                        "wakeup or result."
                    ),
                    retryable=False,
                    raw={
                        "run_id": run.run_id,
                        "pid": run.pid,
                        "last_heartbeat_at": (
                            run.last_heartbeat_at.isoformat()
                            if run.last_heartbeat_at is not None
                            else None
                        ),
                    },
                ),
                completed_at=now,
                raw={"run_id": run.run_id, "stale": True},
            )
        run.status = BackgroundRunStatus.FAILED
        run.completed_at = now
        run.last_heartbeat_at = now
        if self._operation_runtime is not None:
            await self._operation_runtime.finalize_background_turn(
                run.run_id,
                BackgroundRunStatus.FAILED,
                error="background_run_stale",
            )
        self._loaded_operation.upsert_background_run(state, run, run.session_id, run.task_id)
        iteration = self._loaded_operation.find_iteration_for_session(
            state,
            record.handle.session_id,
            record.latest_iteration,
        )
        if iteration is None:
            return
        task = (
            self._loaded_operation.find_task(state, iteration.task_id)
            if iteration.task_id is not None
            else None
        )
        await self._lifecycle_coordinator.fold_reconciled_terminal_result(
            state,
            iteration=iteration,
            task=task,
            session=record.handle,
            result=result,
            handle_agent_result=self._agent_result_service.handle_agent_result,
            record_iteration_brief=self._traceability_service.record_iteration_brief,
            clear_blocking_focus=True,
        )
        await self._event_relay.emit(
            "background_run.stale_detected",
            state,
            iteration.index,
            {
                "run_id": run.run_id,
                "session_id": run.session_id,
                "pid": run.pid,
                "last_heartbeat_at": (
                    run.last_heartbeat_at.isoformat()
                    if run.last_heartbeat_at is not None
                    else None
                ),
            },
            task_id=run.task_id,
            session_id=run.session_id,
        )

    def background_run_is_stale(self, run, now: datetime) -> bool:
        if run.status not in {BackgroundRunStatus.PENDING, BackgroundRunStatus.RUNNING}:
            return False
        if run.last_heartbeat_at is None:
            return False
        return now - run.last_heartbeat_at > self._stale_background_run_threshold

    async def apply_wakeup_event(self, state: OperationState, event: RunEvent) -> None:
        run_id = event.payload.get("run_id") if isinstance(event.payload, dict) else None
        if not isinstance(run_id, str) or self._operation_runtime is None:
            return
        run = await self._operation_runtime.poll_background_turn(run_id)
        if run is None:
            return
        self._loaded_operation.upsert_background_run(
            state,
            run,
            event.session_id,
            event.task_id,
        )
        if event.event_type.endswith("completed"):
            run.status = BackgroundRunStatus.COMPLETED
        elif event.event_type.endswith("failed"):
            run.status = BackgroundRunStatus.FAILED
        elif event.event_type.endswith("cancelled"):
            run.status = BackgroundRunStatus.CANCELLED
        if run.status not in {
            BackgroundRunStatus.COMPLETED,
            BackgroundRunStatus.FAILED,
            BackgroundRunStatus.CANCELLED,
        }:
            return
        result = await self._operation_runtime.collect_background_turn(run_id)
        if result is None:
            return
        record = self._loaded_operation.find_session_record(state, event.session_id)
        if record is None or not self._loaded_operation.session_has_pending_result_slot(record):
            return
        iteration = self._loaded_operation.find_iteration_for_session(
            state,
            record.handle.session_id,
            record.latest_iteration,
        )
        if iteration is None:
            return
        task = (
            self._loaded_operation.find_task(state, iteration.task_id)
            if iteration.task_id is not None
            else None
        )
        await self._lifecycle_coordinator.fold_reconciled_terminal_result(
            state,
            iteration=iteration,
            task=task,
            session=record.handle,
            result=result,
            handle_agent_result=self._agent_result_service.handle_agent_result,
            record_iteration_brief=self._traceability_service.record_iteration_brief,
            clear_blocking_focus=self.focus_should_preempt(state, event),
            wakeup_event_id=event.event_id,
        )
        await self._event_relay.emit(
            "background_wakeup.reconciled",
            state,
            iteration.index,
            event.payload,
            task_id=event.task_id,
            session_id=event.session_id,
        )

    def focus_should_preempt(self, state: OperationState, event: RunEvent) -> bool:
        focus = state.current_focus
        if focus is None or focus.mode is not FocusMode.BLOCKING:
            return False
        if focus.interrupt_policy is InterruptPolicy.TERMINAL_ONLY:
            return event.event_type.endswith(("completed", "failed", "cancelled"))
        return True

    async def cleanup_orphaned_background_runs(self, state: OperationState) -> None:
        active_run_ids = {
            record.current_execution_id
            for record in state.sessions
            if record.current_execution_id is not None
        }
        now = datetime.now(UTC)
        for run in state.background_runs:
            if run.status not in {BackgroundRunStatus.PENDING, BackgroundRunStatus.RUNNING}:
                continue
            if run.run_id in active_run_ids:
                continue
            run.status = BackgroundRunStatus.CANCELLED
            run.completed_at = now
            run.last_heartbeat_at = now
            if self._operation_runtime is not None:
                await self._operation_runtime.finalize_background_turn(
                    run.run_id,
                    BackgroundRunStatus.CANCELLED,
                    error="orphaned_background_run",
                )

    async def reconcile_orphaned_recoverable_background_runs(
        self,
        state: OperationState,
    ) -> None:
        if self._operation_runtime is None:
            return
        for run in list(state.background_runs):
            polled = await self._operation_runtime.poll_background_turn(run.run_id)
            if polled is None:
                continue
            if polled.status not in {
                BackgroundRunStatus.COMPLETED,
                BackgroundRunStatus.FAILED,
                BackgroundRunStatus.CANCELLED,
                BackgroundRunStatus.DISCONNECTED,
            }:
                continue
            self._loaded_operation.upsert_background_run(
                state,
                polled,
                run.session_id,
                run.task_id,
            )
            record = self._loaded_operation.find_session_record(state, polled.session_id)
            if record is None or not self._loaded_operation.session_has_pending_result_slot(record):
                continue
            iteration = self._loaded_operation.find_iteration_for_session(
                state,
                record.handle.session_id,
                record.latest_iteration,
            )
            if iteration is None:
                continue
            task = (
                self._loaded_operation.find_task(state, polled.task_id)
                if polled.task_id
                else None
            )
            result = await self._operation_runtime.collect_background_turn(polled.run_id)
            if result is None:
                continue
            await self._lifecycle_coordinator.fold_reconciled_terminal_result(
                state,
                iteration=iteration,
                task=task,
                session=record.handle,
                result=result,
                handle_agent_result=self._agent_result_service.handle_agent_result,
                record_iteration_brief=self._traceability_service.record_iteration_brief,
                clear_blocking_focus=True,
            )
            await self._event_relay.emit(
                "session.force_recovered",
                state,
                iteration.index,
                {
                    "run_id": run.run_id,
                    "session_id": record.handle.session_id,
                    "task_id": task.task_id if task is not None else None,
                },
                task_id=task.task_id if task is not None else None,
                session_id=record.handle.session_id,
            )

    def sync_legacy_active_session(self, state: OperationState) -> None:
        if state.active_session is None:
            active = next(
                (
                    record.handle
                    for record in state.sessions
                    if record.status is SessionRecordStatus.RUNNING
                ),
                None,
            )
            if active is not None:
                state.active_session = active
