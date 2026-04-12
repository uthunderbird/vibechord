from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import anyio

from agent_operator.application.attached_session_registry import AttachedSessionRuntimeRegistry
from agent_operator.application.process_signals import ProcessManagerSignal
from agent_operator.domain import (
    AgentError,
    AgentProgress,
    AgentProgressState,
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    IterationState,
    OperationState,
    SessionRecord,
    SessionRecordStatus,
    TaskState,
    TaskStatus,
)
from agent_operator.dtos.requests import AgentRunRequest


class AttachedTurnService:
    """Own attached-turn lifecycle mechanics outside the public service facade."""

    def __init__(self, *, attached_turn_timeout: timedelta) -> None:
        self._attached_turn_timeout = attached_turn_timeout

    async def start_turn(
        self,
        *,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        adapter_key: str,
        registry: AttachedSessionRuntimeRegistry,
        resolve_instruction: Callable[[], str],
        resolve_working_directory: Callable[
            [TaskState | None, AgentSessionHandle | None], Path
        ],
        background_request_metadata: Callable[[], dict[str, str]],
        decorate_session_handle: Callable[
            [AgentSessionHandle, str | None, bool, bool], AgentSessionHandle
        ],
        upsert_session_record: Callable[[AgentSessionHandle, TaskState | None], SessionRecord],
        emit: Callable[..., Awaitable[None]],
        allowed_adapter_count: int,
    ) -> AgentSessionHandle:
        """Start a new attached turn."""
        decision = iteration.decision
        assert decision is not None
        request = AgentRunRequest(
            goal=state.objective_state.objective,
            instruction=resolve_instruction(),
            session_name=decision.session_name,
            one_shot=decision.one_shot,
            working_directory=resolve_working_directory(task, None),
            metadata=background_request_metadata(),
        )
        session = decorate_session_handle(
            await registry.start(adapter_key, request),
            decision.session_name,
            allowed_adapter_count > 1,
            decision.one_shot,
        )
        iteration.session = session
        record = upsert_session_record(session, task)
        record.status = SessionRecordStatus.RUNNING
        record.latest_iteration = iteration.index
        if task is not None:
            if task.status is not TaskStatus.COMPLETED:
                task.status = TaskStatus.RUNNING
                task.assigned_agent = adapter_key
                task.linked_session_id = session.session_id
            task.attempt_count += 1
            task.updated_at = datetime.now(UTC)
        state.active_session = session if not session.one_shot else None
        await emit(
            "operation.active_session_updated",
            state,
            iteration.index,
            {"session_id": state.active_session.session_id if state.active_session else None},
            session_id=state.active_session.session_id if state.active_session else None,
        )
        await emit(
            "agent.invocation.started",
            state,
            iteration.index,
            session.model_dump(mode="json"),
            task_id=iteration.task_id,
            session_id=session.session_id,
        )
        return session

    async def continue_turn(
        self,
        *,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        adapter_key: str,
        registry: AttachedSessionRuntimeRegistry,
        resolve_record: Callable[[str | None, TaskState | None], SessionRecord | None],
        build_restart_instruction: Callable[[str], str],
        resolve_working_directory: Callable[
            [TaskState | None, AgentSessionHandle | None], Path
        ],
        background_request_metadata: Callable[[], dict[str, str]],
        decorate_session_handle: Callable[
            [AgentSessionHandle, str | None, bool, bool], AgentSessionHandle
        ],
        upsert_session_record: Callable[[AgentSessionHandle, TaskState | None], SessionRecord],
        emit: Callable[..., Awaitable[None]],
        allowed_adapter_count: int,
    ) -> AgentSessionHandle:
        """Continue an attached turn, restarting only when follow-up is unsupported."""
        decision = iteration.decision
        assert decision is not None
        record = resolve_record(decision.session_id, task)
        if record is None:
            raise RuntimeError("Brain requested session continuation without reusable session.")
        if adapter_key != record.adapter_key:
            raise RuntimeError(
                "Brain requested session continuation through a different adapter than the "
                f"active session: requested {adapter_key!r}, active {record.adapter_key!r}."
            )
        descriptor = await registry.describe(adapter_key)
        if descriptor.supports_follow_up:
            await registry.send(record.handle, decision.instruction or "")
            session = record.handle
        else:
            await registry.close(record.handle)
            request = AgentRunRequest(
                goal=state.objective_state.objective,
                instruction=build_restart_instruction(
                    decision.instruction
                    or (
                        task.goal if task is not None else state.objective_state.objective
                    )
                ),
                session_name=decision.session_name or record.handle.session_name,
                one_shot=decision.one_shot,
                working_directory=resolve_working_directory(task, record.handle),
                metadata=background_request_metadata(),
            )
            session = decorate_session_handle(
                await registry.start(adapter_key, request),
                request.session_name,
                allowed_adapter_count > 1,
                decision.one_shot,
            )
            record = upsert_session_record(session, task)
            await emit(
                "agent.invocation.started",
                state,
                iteration.index,
                session.model_dump(mode="json"),
                task_id=iteration.task_id,
                session_id=session.session_id,
            )
        record.status = SessionRecordStatus.RUNNING
        record.latest_iteration = iteration.index
        record.updated_at = datetime.now(UTC)
        if task is not None:
            if task.status is not TaskStatus.COMPLETED:
                task.status = TaskStatus.RUNNING
                task.linked_session_id = session.session_id
                task.attempt_count += 1
            task.updated_at = datetime.now(UTC)
        iteration.session = session
        state.active_session = session if not session.one_shot else None
        await emit(
            "operation.active_session_updated",
            state,
            iteration.index,
            {"session_id": state.active_session.session_id if state.active_session else None},
            session_id=state.active_session.session_id if state.active_session else None,
        )
        return session

    async def record_turn_started(
        self,
        *,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        session: AgentSessionHandle,
        record_agent_turn_brief: Callable[..., Awaitable[None]],
        record_iteration_brief: Callable[
            [OperationState, IterationState, TaskState | None], Awaitable[None]
        ],
        sync_traceability_artifacts: Callable[[OperationState], Awaitable[None]],
        save_operation: Callable[[OperationState], Awaitable[None]],
    ) -> None:
        """Persist trace artifacts for a newly started attached turn."""
        await record_agent_turn_brief(
            state,
            iteration,
            task,
            session,
            None,
            None,
        )
        await record_iteration_brief(state, iteration, task)
        await sync_traceability_artifacts(state)
        await save_operation(state)

    async def collect_turn(
        self,
        *,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        registry: AttachedSessionRuntimeRegistry,
        session: AgentSessionHandle,
        ensure_session_record: Callable[[OperationState, AgentSessionHandle], SessionRecord],
        save_operation: Callable[[OperationState], Awaitable[None]],
        sync_traceability_artifacts: Callable[[OperationState], Awaitable[None]],
        drain_commands: Callable[
            [OperationState, IterationState, AgentSessionHandle], Awaitable[None]
        ],
        reconcile_timeout: Callable[
            [
                IterationState,
                TaskState | None,
                AgentSessionHandle,
                SessionRecord,
                AgentProgress,
            ],
            Awaitable[AgentResult],
        ],
        dispatch_process_manager_signal: Callable[
            [OperationState, int, ProcessManagerSignal], Awaitable[None]
        ],
        scheduler_is_draining: bool,
    ) -> AgentResult:
        """Poll and collect one attached turn to completion or interruption."""
        while True:
            progress = await registry.poll(session)
            record = ensure_session_record(state, session)
            record.last_progress_at = progress.updated_at
            record.last_event_at = self.extract_last_event_time(progress)
            record.updated_at = progress.updated_at
            record.attached_turn_started_at = record.attached_turn_started_at or datetime.now(UTC)
            record.waiting_reason = progress.message
            timeout_origin = record.last_event_at or progress.updated_at
            if progress.state in {AgentProgressState.PENDING, AgentProgressState.RUNNING}:
                if datetime.now(UTC) - timeout_origin >= self._attached_turn_timeout:
                    return await reconcile_timeout(
                        iteration,
                        task,
                        session,
                        record,
                        progress,
                    )
                record.status = SessionRecordStatus.RUNNING
                await save_operation(state)
                await sync_traceability_artifacts(state)
                await drain_commands(state, iteration, session)
                await anyio.sleep(1.0)
                continue
            if progress.state is AgentProgressState.WAITING_INPUT:
                return AgentResult(
                    session_id=session.session_id,
                    status=AgentResultStatus.INCOMPLETE,
                    output_text=progress.partial_output or "",
                    error=AgentError(
                        code="agent_waiting_input",
                        message=progress.message,
                        retryable=False,
                        raw=progress.raw,
                    ),
                    completed_at=progress.updated_at,
                    raw={"progress": progress.model_dump(mode="json")},
                )
            result = await registry.collect(session)
            if scheduler_is_draining:
                await dispatch_process_manager_signal(
                    state,
                    iteration.index,
                    ProcessManagerSignal(
                        operation_id=state.operation_id,
                        signal_type="attached_turn_stopped",
                        session_id=session.session_id,
                        metadata={"session_id": session.session_id},
                    ),
                )
            return result

    async def reconcile_timeout(
        self,
        *,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        session: AgentSessionHandle,
        record: SessionRecord,
        progress: AgentProgress,
        emit: Callable[..., Awaitable[None]],
    ) -> AgentResult:
        """Convert an attached-turn timeout into a recovered synthetic result."""
        timeout_output = self.extract_latest_recovery_output(session)
        partial_output = progress.partial_output.strip() if progress.partial_output else ""
        recovery_output = timeout_output or partial_output
        record.recovery_count += 1
        record.last_recovered_at = datetime.now(UTC)
        record.recovery_summary = (
            f"Attached turn timed out after {self._attached_turn_timeout.total_seconds()} seconds."
        )
        record.waiting_reason = "Attached turn timed out and was recovered."
        await emit(
            "attached_turn.recovered",
            state,
            iteration.index,
            {
                "session_id": session.session_id,
                "adapter_key": session.adapter_key,
            },
            task_id=task.task_id if task is not None else None,
            session_id=session.session_id,
        )
        return AgentResult(
            session_id=session.session_id,
            status=AgentResultStatus.SUCCESS,
            output_text=recovery_output
            or "Attached turn timed out; continuing with partial recovery output.",
            completed_at=progress.updated_at,
            artifacts=progress.artifacts,
            raw={
                "attached_turn_recovered": True,
                "used_log_tail_recovery": timeout_output is not None,
                "raw_output": progress.raw,
            },
        )

    def extract_last_event_time(self, progress: AgentProgress) -> datetime | None:
        """Extract best-effort last-event timestamp from progress raw payload."""
        raw = progress.raw
        if not isinstance(raw, dict):
            return None
        raw_value = raw.get("last_event_at")
        if raw_value is None:
            return None
        if isinstance(raw_value, datetime):
            return raw_value
        if isinstance(raw_value, str):
            try:
                return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    def extract_latest_recovery_output(self, session: AgentSessionHandle) -> str | None:
        """Read the latest recoverable output from the attached session log, if any."""
        log_path = session.metadata.get("log_path")
        if not isinstance(log_path, str):
            return None
        path = Path(log_path)
        if not path.exists():
            return None
        collected_lines: list[str] = []
        try:
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                if not raw_line.strip():
                    continue
                try:
                    record = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                message = record.get("message", {})
                event_type = record.get("type")
                if event_type == "assistant":
                    for item in message.get("content", []):
                        if item.get("type") == "text" and item.get("text"):
                            collected_lines.append(str(item["text"]))
                elif event_type == "tool_use":
                    command = ""
                    command_source = message
                    if not isinstance(command_source, dict):
                        command_source = {}
                    if isinstance(record.get("input"), dict):
                        command_source = record
                    command = (
                        command_source.get("input", {}).get("command")
                        if isinstance(command_source.get("input"), dict)
                        else ""
                    )
                    if command:
                        collected_lines.append(str(command))
                elif event_type == "result":
                    result_text = record.get("result")
                    if isinstance(result_text, str):
                        collected_lines.append(result_text)
        except OSError:
            return None
        if not collected_lines:
            return None
        return "\n".join(collected_lines)
