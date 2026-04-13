from __future__ import annotations

from datetime import UTC, datetime

from agent_operator.application.attached_turns import AttachedTurnService
from agent_operator.application.commands.operation_commands import OperationCommandService
from agent_operator.application.loaded_operation import LoadedOperation
from agent_operator.application.queries.operation_traceability import OperationTraceabilityService
from agent_operator.application.runtime.operation_event_relay import OperationEventRelay
from agent_operator.application.runtime.operation_process_dispatch import (
    OperationProcessSignalDispatcher,
)
from agent_operator.domain import (
    AgentDescriptor,
    AgentProgress,
    AgentResult,
    AgentSessionHandle,
    FocusKind,
    FocusMode,
    FocusState,
    InterruptPolicy,
    IterationState,
    OperationState,
    ResumePolicy,
    SchedulerState,
    SessionRecord,
    SessionRecordStatus,
    TaskState,
    TaskStatus,
)
from agent_operator.dtos.requests import AgentRunRequest
from agent_operator.protocols import AgentSessionManager, OperationRuntime, OperationStore


class OperationTurnExecutionService:
    """Own attached/background agent-turn execution bridges for one operation."""

    def __init__(
        self,
        *,
        loaded_operation: LoadedOperation,
        attached_session_registry: AgentSessionManager,
        attached_turn_service: AttachedTurnService,
        operation_runtime: OperationRuntime | None,
        store: OperationStore,
        event_relay: OperationEventRelay,
        process_signal_dispatcher: OperationProcessSignalDispatcher,
        traceability_service: OperationTraceabilityService,
        command_service: OperationCommandService,
    ) -> None:
        self._loaded_operation = loaded_operation
        self._attached_session_registry = attached_session_registry
        self._attached_turn_service = attached_turn_service
        self._operation_runtime = operation_runtime
        self._store = store
        self._event_relay = event_relay
        self._process_signal_dispatcher = process_signal_dispatcher
        self._traceability_service = traceability_service
        self._command_service = command_service

    async def collect_attached_turn(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        session: AgentSessionHandle,
    ) -> AgentResult:
        async def _reconcile_timeout(
            active_iteration: IterationState,
            active_task: TaskState | None,
            active_session: AgentSessionHandle,
            record: SessionRecord,
            progress: AgentProgress | None,
        ) -> AgentResult:
            return await self.reconcile_attached_turn_timeout(
                state,
                active_iteration,
                active_task,
                active_session,
                record,
                progress,
            )

        return await self._attached_turn_service.collect_turn(
            state=state,
            iteration=iteration,
            task=task,
            registry=self._attached_session_registry,
            session=session,
            ensure_session_record=self._loaded_operation.ensure_session_record,
            sync_traceability_artifacts=self._traceability_service.sync_traceability_artifacts,
            drain_commands=lambda operation_state, active_iteration, active_session: (
                self._command_service.drain_commands(
                    operation_state,
                    iteration=active_iteration,
                    attached_session=active_session,
                )
            ),
            reconcile_timeout=_reconcile_timeout,
            dispatch_process_manager_signal=self._process_signal_dispatcher.dispatch,
            scheduler_is_draining=state.scheduler_state is SchedulerState.DRAINING,
        )

    async def reconcile_attached_turn_timeout(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        session: AgentSessionHandle,
        record: SessionRecord,
        progress: AgentProgress,
    ) -> AgentResult:
        return await self._attached_turn_service.reconcile_timeout(
            state=state,
            iteration=iteration,
            task=task,
            session=session,
            record=record,
            progress=progress,
            emit=self._event_relay.emit,
        )

    async def record_attached_turn_started(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        session: AgentSessionHandle,
    ) -> None:
        await self._attached_turn_service.record_turn_started(
            state=state,
            iteration=iteration,
            task=task,
            session=session,
            record_agent_turn_brief=self._traceability_service.record_agent_turn_brief,
            record_iteration_brief=self._traceability_service.record_iteration_brief,
            sync_traceability_artifacts=self._traceability_service.sync_traceability_artifacts,
        )

    async def start_agent_turn(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        adapter_key: str,
    ) -> AgentSessionHandle:
        return await self._attached_turn_service.start_turn(
            state=state,
            iteration=iteration,
            task=task,
            adapter_key=adapter_key,
            registry=self._attached_session_registry,
            resolve_instruction=lambda: (
                iteration.decision.instruction
                or (task.goal if task is not None else state.objective_state.objective)
            ),
            resolve_working_directory=lambda active_task, handle: (
                self._loaded_operation.resolve_working_directory(
                    state,
                    active_task,
                    handle,
                )
            ),
            background_request_metadata=lambda: self._background_request_metadata(state),
            decorate_session_handle=self._loaded_operation.decorate_session_handle,
            upsert_session_record=lambda session_handle, active_task: (
                self._loaded_operation.upsert_session_record(
                    state,
                    session_handle,
                    active_task,
                )
            ),
            emit=self._event_relay.emit,
            allowed_adapter_count=len(self._loaded_operation.allowed_adapters(state)),
        )

    async def continue_agent_turn(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        adapter_key: str,
    ) -> AgentSessionHandle:
        return await self._attached_turn_service.continue_turn(
            state=state,
            iteration=iteration,
            task=task,
            adapter_key=adapter_key,
            registry=self._attached_session_registry,
            resolve_record=lambda session_id, active_task: (
                self._loaded_operation.resolve_session_for_continuation(
                    state,
                    session_id,
                    active_task,
                )
            ),
            build_restart_instruction=lambda instruction: (
                self._loaded_operation.build_restart_instruction(
                    state,
                    instruction,
                )
            ),
            resolve_working_directory=lambda active_task, handle: (
                self._loaded_operation.resolve_working_directory(
                    state,
                    active_task,
                    handle,
                )
            ),
            background_request_metadata=lambda: self._background_request_metadata(state),
            decorate_session_handle=self._loaded_operation.decorate_session_handle,
            upsert_session_record=lambda session_handle, active_task: (
                self._loaded_operation.upsert_session_record(
                    state,
                    session_handle,
                    active_task,
                )
            ),
            emit=self._event_relay.emit,
            allowed_adapter_count=len(self._loaded_operation.allowed_adapters(state)),
        )

    async def start_background_agent_turn(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        adapter_key: str,
    ) -> None:
        if self._operation_runtime is None:
            raise RuntimeError("Operation runtime is not configured.")
        decision = iteration.decision
        assert decision is not None
        request = AgentRunRequest(
            goal=state.objective_state.objective,
            instruction=decision.instruction
            or (task.goal if task is not None else state.objective_state.objective),
            session_name=decision.session_name,
            one_shot=decision.one_shot,
            session_reuse_policy=self._loaded_operation.resolved_session_reuse_policy(state),
            working_directory=self._loaded_operation.resolve_working_directory(state, task),
            metadata=self._background_request_metadata(state),
        )
        run = await self._operation_runtime.dispatch_background_turn(
            operation_id=state.operation_id,
            iteration=iteration.index,
            adapter_key=adapter_key,
            request=request,
            task_id=task.task_id if task is not None else None,
        )
        session = self._loaded_operation.decorate_background_session(
            run,
            decision.session_name,
            state,
            one_shot=decision.one_shot,
        )
        iteration.session = session
        record = self._loaded_operation.upsert_session_record(state, session, task)
        record.status = SessionRecordStatus.RUNNING
        record.current_execution_id = run.run_id
        record.latest_iteration = iteration.index
        record.last_progress_at = datetime.now(UTC)
        if task is not None:
            if task.status is not TaskStatus.COMPLETED:
                task.status = TaskStatus.RUNNING
                task.assigned_agent = adapter_key
                task.linked_session_id = session.session_id
            task.attempt_count += 1
            task.updated_at = datetime.now(UTC)
        state.current_focus = FocusState(
            kind=FocusKind.SESSION,
            target_id=session.session_id,
            mode=FocusMode.BLOCKING,
            blocking_reason="Waiting for the background agent turn to complete.",
            interrupt_policy=InterruptPolicy.TERMINAL_ONLY,
            resume_policy=ResumePolicy.REPLAN,
        )
        self._loaded_operation.upsert_background_run(
            state,
            run,
            session.session_id,
            task.task_id if task else None,
        )
        await self._event_relay.emit(
            "execution.session_linked",
            state,
            iteration.index,
            {"execution_id": run.run_id, "session_id": session.session_id},
            session_id=session.session_id,
        )
        await self._record_agent_turn_brief(
            state,
            iteration,
            task,
            session,
            None,
            None,
            background_run_id=run.run_id,
        )
        await self._event_relay.emit(
            "agent.invocation.background_started",
            state,
            iteration.index,
            {"run_id": run.run_id, "adapter_key": adapter_key},
            task_id=iteration.task_id,
            session_id=session.session_id,
        )

    async def continue_background_agent_turn(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        adapter_key: str,
        descriptor: AgentDescriptor,
    ) -> None:
        if self._operation_runtime is None:
            raise RuntimeError("Operation runtime is not configured.")
        decision = iteration.decision
        assert decision is not None
        record = self._loaded_operation.resolve_session_for_continuation(
            state,
            decision.session_id,
            task,
        )
        if record is None:
            raise RuntimeError("Brain requested session continuation without reusable session.")
        if adapter_key != record.adapter_key:
            raise RuntimeError(
                "Brain requested session continuation through a different adapter than the "
                f"active session: requested {adapter_key!r}, active {record.adapter_key!r}."
            )
        if not descriptor.supports_follow_up:
            request = AgentRunRequest(
                goal=state.objective_state.objective,
                instruction=self._loaded_operation.build_restart_instruction(
                    state,
                    decision.instruction
                    or (task.goal if task is not None else state.objective_state.objective),
                ),
                session_name=decision.session_name or record.handle.session_name,
                one_shot=decision.one_shot,
                session_reuse_policy=self._loaded_operation.resolved_session_reuse_policy(state),
                working_directory=self._loaded_operation.resolve_working_directory(
                    state,
                    task,
                    record.handle,
                ),
                metadata=self._background_request_metadata(state),
            )
            run = await self._operation_runtime.dispatch_background_turn(
                operation_id=state.operation_id,
                iteration=iteration.index,
                adapter_key=adapter_key,
                request=request,
                task_id=task.task_id if task is not None else None,
            )
            session = self._loaded_operation.decorate_background_session(
                run,
                request.session_name,
                state,
                one_shot=request.one_shot,
            )
            record = self._loaded_operation.upsert_session_record(state, session, task)
        else:
            request = AgentRunRequest(
                goal=state.objective_state.objective,
                instruction=decision.instruction or "",
                session_name=decision.session_name or record.handle.session_name,
                one_shot=decision.one_shot,
                session_reuse_policy=self._loaded_operation.resolved_session_reuse_policy(state),
                working_directory=self._loaded_operation.resolve_working_directory(
                    state,
                    task,
                    record.handle,
                ),
                metadata=self._background_request_metadata(state),
            )
            run = await self._operation_runtime.dispatch_background_turn(
                operation_id=state.operation_id,
                iteration=iteration.index,
                adapter_key=adapter_key,
                request=request,
                existing_session=record.handle,
                task_id=task.task_id if task is not None else None,
            )
            session = self._loaded_operation.decorate_background_session(
                run,
                request.session_name,
                state,
                fallback=record.handle,
                one_shot=request.one_shot,
            )
            record.handle = session
        record.status = SessionRecordStatus.RUNNING
        record.current_execution_id = run.run_id
        record.latest_iteration = iteration.index
        record.last_progress_at = datetime.now(UTC)
        record.updated_at = datetime.now(UTC)
        if task is not None:
            task.status = TaskStatus.RUNNING
            task.linked_session_id = session.session_id
            task.attempt_count += 1
            task.updated_at = datetime.now(UTC)
        iteration.session = session
        state.current_focus = FocusState(
            kind=FocusKind.SESSION,
            target_id=session.session_id,
            mode=FocusMode.BLOCKING,
            blocking_reason="Waiting for the background agent turn to complete.",
            interrupt_policy=InterruptPolicy.TERMINAL_ONLY,
            resume_policy=ResumePolicy.REPLAN,
        )
        self._loaded_operation.upsert_background_run(
            state,
            run,
            session.session_id,
            task.task_id if task else None,
        )
        await self._event_relay.emit(
            "execution.session_linked",
            state,
            iteration.index,
            {"execution_id": run.run_id, "session_id": session.session_id},
            session_id=session.session_id,
        )
        await self._traceability_service.record_agent_turn_brief(
            state,
            iteration,
            task,
            session,
            None,
            None,
            background_run_id=run.run_id,
        )
        await self._event_relay.emit(
            "agent.invocation.background_started",
            state,
            iteration.index,
            {"run_id": run.run_id, "adapter_key": adapter_key, "continued": True},
            task_id=iteration.task_id,
            session_id=session.session_id,
        )

    def background_request_metadata(self, state: OperationState) -> dict[str, str]:
        return self._background_request_metadata(state)

    async def _record_agent_turn_brief(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        session: AgentSessionHandle,
        result: AgentResult | None,
        artifact,
        *,
        background_run_id: str | None = None,
        turn_summary=None,
        wakeup_event_id: str | None = None,
    ) -> None:
        await self._traceability_service.record_agent_turn_brief(
            state,
            iteration,
            task,
            session,
            result,
            artifact,
            background_run_id=background_run_id,
            turn_summary=turn_summary,
            wakeup_event_id=wakeup_event_id,
        )

    def _background_request_metadata(self, state: OperationState) -> dict[str, str]:
        metadata: dict[str, str] = {}
        for key in ("project_profile_name", "project_profile_path"):
            value = state.goal.metadata.get(key)
            if isinstance(value, str) and value:
                metadata[key] = value
        return metadata
