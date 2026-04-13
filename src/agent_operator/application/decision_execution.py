from __future__ import annotations

from datetime import UTC, datetime

from agent_operator.application.agent_results import AgentResultService
from agent_operator.application.commands.operation_attention import OperationAttentionCoordinator
from agent_operator.application.loaded_operation import LoadedOperation
from agent_operator.application.operation_lifecycle import OperationLifecycleCoordinator
from agent_operator.application.operation_turn_execution import OperationTurnExecutionService
from agent_operator.application.runtime.operation_event_relay import OperationEventRelay
from agent_operator.application.runtime.operation_runtime_context import OperationRuntimeContext
from agent_operator.domain import (
    AttentionRequest,
    AttentionType,
    BrainActionType,
    BrainDecision,
    CommandTargetScope,
    FocusKind,
    FocusMode,
    FocusState,
    InterruptPolicy,
    IterationState,
    OperationState,
    ResumePolicy,
    RunMode,
    RunOptions,
    SessionRecordStatus,
    SessionReusePolicy,
    TaskState,
    TaskStatus,
)


class DecisionExecutionService:
    def __init__(
        self,
        *,
        loaded_operation: LoadedOperation,
        attached_session_registry: object,
        attention_coordinator: OperationAttentionCoordinator,
        event_relay: OperationEventRelay,
        lifecycle_coordinator: OperationLifecycleCoordinator,
        runtime_context: OperationRuntimeContext,
        turn_execution_service: OperationTurnExecutionService,
        agent_result_service: AgentResultService,
    ) -> None:
        self._loaded_operation = loaded_operation
        self._attached_session_registry = attached_session_registry
        self._attention_coordinator = attention_coordinator
        self._event_relay = event_relay
        self._lifecycle_coordinator = lifecycle_coordinator
        self._runtime_context = runtime_context
        self._turn_execution_service = turn_execution_service
        self._agent_result_service = agent_result_service

    async def execute_decision(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        options: RunOptions,
        *,
        supervisor_available: bool,
    ) -> bool:
        decision = iteration.decision
        assert decision is not None

        self._loaded_operation.apply_task_mutations(
            state,
            decision.new_tasks,
            decision.task_updates,
        )

        if (
            decision.action_type is BrainActionType.START_AGENT
            and options.run_mode is RunMode.ATTACHED
            and self._runtime_context.should_retry_from_recoverable_block(state)
        ):
            recoverable_record = self._runtime_context.resolve_recoverable_session_for_retry(state)
            if recoverable_record is not None:
                decision = decision.model_copy(
                    update={
                        "action_type": BrainActionType.CONTINUE_AGENT,
                        "session_id": recoverable_record.session_id,
                    }
                )
                iteration.decision = decision

        if decision.action_type is BrainActionType.STOP:
            self._lifecycle_coordinator.mark_completed(state, summary=decision.rationale)
            if task is not None:
                task.status = TaskStatus.COMPLETED
                task.updated_at = datetime.now(UTC)
            return True

        if decision.action_type is BrainActionType.FAIL:
            self._lifecycle_coordinator.mark_failed(state, summary=decision.rationale)
            if task is not None:
                task.status = TaskStatus.FAILED
                task.updated_at = datetime.now(UTC)
            return True

        if (
            decision.action_type is not BrainActionType.REQUEST_CLARIFICATION
            and self._attention_coordinator.decision_requires_policy_gap(state, decision)
        ):
            return await self._block_or_defer_attention(
                state,
                iteration,
                task,
                self._attention_coordinator.open_policy_gap_attention(state, decision, task),
                "Deferred policy-shaped action until attention request ",
            )

        if (
            decision.action_type is not BrainActionType.REQUEST_CLARIFICATION
            and self._attention_coordinator.decision_requires_novel_strategic_fork(decision)
        ):
            return await self._block_or_defer_attention(
                state,
                iteration,
                task,
                self._attention_coordinator.open_novel_strategic_fork_attention(
                    state, decision, task
                ),
                "Deferred strategic fork until attention request ",
            )

        if decision.action_type is BrainActionType.REQUEST_CLARIFICATION:
            attention_type = (
                AttentionType.POLICY_GAP
                if self._attention_coordinator.decision_requires_policy_gap(state, decision)
                else (
                    AttentionType.NOVEL_STRATEGIC_FORK
                    if self._attention_coordinator.decision_requires_novel_strategic_fork(decision)
                    else self._attention_coordinator.attention_type_from_decision(decision)
                )
            )
            attention = self._attention_coordinator.open_attention_request(
                state,
                attention_type=attention_type,
                title=self._attention_coordinator.attention_title_from_decision(
                    decision, attention_type
                ),
                question=self._attention_coordinator.attention_question_from_decision(
                    decision, attention_type
                ),
                context_brief=self._attention_coordinator.attention_context_from_decision(
                    decision, task
                ),
                target_scope=CommandTargetScope.OPERATION,
                target_id=state.operation_id,
                blocking=True,
                suggested_options=self._attention_coordinator.attention_options_from_decision(decision),
            )
            return await self._block_or_defer_attention(
                state,
                iteration,
                task,
                attention,
                "Recorded non-blocking attention request ",
            )

        if decision.action_type is BrainActionType.APPLY_POLICY or options.dry_run:
            iteration.notes.append("No side-effectful action executed.")
            return False

        adapter_key = decision.target_agent
        if (
            adapter_key is None
            or adapter_key not in self._loaded_operation.allowed_adapters(state)
        ):
            self._lifecycle_coordinator.mark_failed(
                state,
                summary=(
                    "Adapter requested by brain is unavailable or not allowed: "
                    f"{adapter_key!r}"
                ),
            )
            return True

        if decision.action_type is BrainActionType.START_AGENT:
            return await self._execute_start_agent(
                state,
                iteration,
                task,
                options,
                adapter_key,
                supervisor_available=supervisor_available,
            )

        if decision.action_type is BrainActionType.CONTINUE_AGENT:
            return await self._execute_continue_agent(
                state,
                iteration,
                task,
                options,
                adapter_key,
                supervisor_available=supervisor_available,
            )

        if decision.action_type is BrainActionType.WAIT_FOR_AGENT:
            return self._execute_wait_for_agent(state, iteration, task, options, decision)

        self._lifecycle_coordinator.mark_failed(
            state,
            summary=f"Unsupported action type: {decision.action_type}",
        )
        return True

    async def _block_or_defer_attention(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        attention: AttentionRequest,
        deferred_prefix: str,
    ) -> bool:
        await self._event_relay.emit(
            "attention.request.created",
            state,
            iteration.index,
            self._attention_coordinator.event_payload(attention),
            task_id=task.task_id if task is not None else None,
        )
        if not attention.blocking:
            iteration.notes.append(f"{deferred_prefix}{attention.attention_id}.")
            return False
        self._lifecycle_coordinator.mark_needs_human(
            state,
            summary=f"Blocked on attention request: {attention.title}.",
        )
        state.current_focus = FocusState(
            kind=FocusKind.ATTENTION_REQUEST,
            target_id=attention.attention_id,
            mode=FocusMode.BLOCKING,
            blocking_reason=attention.question,
            interrupt_policy=InterruptPolicy.MATERIAL_WAKEUP,
            resume_policy=ResumePolicy.REPLAN,
        )
        if task is not None:
            task.status = TaskStatus.BLOCKED
            task.updated_at = datetime.now(UTC)
        return True

    async def _execute_start_agent(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        options: RunOptions,
        adapter_key: str,
        *,
        supervisor_available: bool,
    ) -> bool:
        if (
            self._loaded_operation.resolved_session_reuse_policy(state)
            is SessionReusePolicy.REUSE_IF_IDLE
        ):
            reusable_record = self._loaded_operation.resolve_reusable_idle_session(
                state,
                adapter_key,
                task,
            )
            if reusable_record is not None:
                iteration.decision = iteration.decision.model_copy(
                    update={"session_id": reusable_record.session_id}
                )
                return await self._execute_continue_agent(
                    state,
                    iteration,
                    task,
                    options,
                    adapter_key,
                    supervisor_available=supervisor_available,
                )
        if (
            self._runtime_context.should_use_background_runtime(options)
            and supervisor_available
            and not (
                options.run_mode is RunMode.ATTACHED
                and self._runtime_context.should_retry_from_recoverable_block(state)
            )
        ):
            await self._turn_execution_service.start_background_agent_turn(
                state,
                iteration,
                task,
                adapter_key,
            )
            return options.run_mode is not RunMode.ATTACHED
        session = await self._turn_execution_service.start_agent_turn(
            state,
            iteration,
            task,
            adapter_key,
        )
        await self._turn_execution_service.record_attached_turn_started(
            state,
            iteration,
            task,
            session,
        )
        result = await self._turn_execution_service.collect_attached_turn(
            state,
            iteration,
            task,
            session,
        )
        await self._agent_result_service.handle_agent_result(
            state, iteration, task, session, result
        )
        return False

    async def _execute_continue_agent(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        options: RunOptions,
        adapter_key: str,
        *,
        supervisor_available: bool,
    ) -> bool:
        if (
            self._runtime_context.should_use_background_runtime(options)
            and supervisor_available
            and not (
                options.run_mode is RunMode.ATTACHED
                and self._runtime_context.should_retry_from_recoverable_block(state)
            )
        ):
            descriptor = await self._attached_session_registry.describe(adapter_key)
            await self._turn_execution_service.continue_background_agent_turn(
                state,
                iteration,
                task,
                adapter_key,
                descriptor,
            )
            return options.run_mode is not RunMode.ATTACHED
        session = await self._turn_execution_service.continue_agent_turn(
            state,
            iteration,
            task,
            adapter_key,
        )
        await self._turn_execution_service.record_attached_turn_started(
            state,
            iteration,
            task,
            session,
        )
        result = await self._turn_execution_service.collect_attached_turn(
            state,
            iteration,
            task,
            session,
        )
        await self._agent_result_service.handle_agent_result(
            state, iteration, task, session, result
        )
        return False

    def _execute_wait_for_agent(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        options: RunOptions,
        decision: BrainDecision,
    ) -> bool:
        latest_result = self._loaded_operation.latest_result_for_session(
            state,
            decision.session_id or (task.linked_session_id if task is not None else None),
        )
        if latest_result is not None:
            iteration.result = latest_result
            iteration.notes.append(
                "WAIT_FOR_AGENT ignored because the target session already has a "
                "collected terminal result."
            )
            return False
        if (
            options.run_mode is not RunMode.ATTACHED
            and options.background_runtime_mode.value != "resumable_wakeup"
        ):
            self._lifecycle_coordinator.mark_failed(
                state,
                summary=(
                    "WAIT_FOR_AGENT is unavailable in resumable CLI mode until "
                    "the background wakeup runtime is implemented."
                ),
            )
            return True
        if decision.blocking_focus is None:
            self._lifecycle_coordinator.mark_failed(
                state,
                summary="WAIT_FOR_AGENT requires blocking focus metadata in background-wait mode.",
            )
            return True
        target_session_id = decision.session_id or (
            task.linked_session_id if task is not None else None
        )
        if target_session_id is None:
            self._lifecycle_coordinator.mark_failed(
                state,
                summary="WAIT_FOR_AGENT requires a target session.",
            )
            return True
        state.current_focus = FocusState(
            kind=decision.blocking_focus.kind,
            target_id=decision.blocking_focus.target_id,
            mode=FocusMode.BLOCKING,
            blocking_reason=decision.blocking_focus.blocking_reason,
            interrupt_policy=decision.blocking_focus.interrupt_policy,
            resume_policy=decision.blocking_focus.resume_policy,
        )
        session_record = self._loaded_operation.find_session_record(state, target_session_id)
        if session_record is not None:
            session_record.status = SessionRecordStatus.WAITING
            session_record.waiting_reason = decision.blocking_focus.blocking_reason
            session_record.updated_at = datetime.now(UTC)
        if options.run_mode is RunMode.ATTACHED:
            iteration.notes.append(
                "Blocking focus established; attached run entered reconciliation-only wait."
            )
            self._lifecycle_coordinator.mark_running(state)
            return False
        iteration.notes.append("Blocking focus established; waiting for background wakeup.")
        return True
