from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from agent_operator.domain import (
    AttentionStatus,
    BackgroundRuntimeMode,
    CommandTargetScope,
    FocusKind,
    InvolvementLevel,
    OperationCommand,
    OperationCommandType,
    OperationOutcome,
    OperationState,
    OperationStatus,
    RunMode,
    RunOptions,
    SchedulerState,
    SessionStatus,
    TaskStatus,
)
from agent_operator.protocols import OperationCommandInbox, OperationStore


class OperatorServiceLike(Protocol):
    async def resume(
        self,
        operation_id: str,
        *,
        options: RunOptions | None = None,
        session_id: str | None = None,
    ) -> OperationOutcome: ...

    async def cancel(
        self,
        operation_id: str,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        reason: str | None = None,
    ) -> OperationOutcome: ...

    async def tick(
        self,
        operation_id: str,
        *,
        options: RunOptions | None = None,
    ) -> OperationOutcome: ...

    async def recover(
        self,
        operation_id: str,
        *,
        session_id: str | None = None,
        options: RunOptions | None = None,
    ) -> OperationOutcome: ...


class OperationStateLoaderLike(Protocol):
    async def load_canonical_operation_state(self, operation_id: str) -> OperationState | None: ...


@dataclass(slots=True)
class OperationDeliveryCommandService:
    store: OperationStore
    command_inbox: OperationCommandInbox
    service_factory: Callable[[], OperatorServiceLike]
    find_task_by_display_id: Callable[[OperationState, str], object | None]
    state_loader: OperationStateLoaderLike | None = None

    async def cancel(
        self,
        operation_id: str,
        *,
        session_id: str | None,
        run_id: str | None,
        reason: str | None = None,
    ) -> OperationOutcome:
        service = self.service_factory()
        if reason is None:
            return await service.cancel(
                operation_id,
                session_id=session_id,
                run_id=run_id,
            )
        return await service.cancel(
            operation_id,
            session_id=session_id,
            run_id=run_id,
            reason=reason,
        )

    async def resume(
        self,
        operation_id: str,
        *,
        max_cycles: int,
    ) -> OperationOutcome:
        service = self.service_factory()
        return await service.resume(
            operation_id,
            options=RunOptions(
                run_mode=RunMode.RESUMABLE,
                max_cycles=max_cycles,
                background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
            ),
        )

    async def tick(
        self,
        operation_id: str,
    ) -> OperationOutcome:
        service = self.service_factory()
        return await service.tick(
            operation_id,
            options=RunOptions(
                run_mode=RunMode.RESUMABLE,
                background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
            ),
        )

    async def recover(
        self,
        operation_id: str,
        *,
        session_id: str | None,
        max_cycles: int,
    ) -> OperationOutcome:
        service = self.service_factory()
        return await service.recover(
            operation_id,
            session_id=session_id,
            options=RunOptions(
                run_mode=RunMode.RESUMABLE,
                max_cycles=max_cycles,
                background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
            ),
        )

    async def daemon_sweep(
        self,
        *,
        ready_operation_ids: list[str],
        max_cycles_per_operation: int,
        emit_operation: Callable[[str], None] | None = None,
        emit_outcome: Callable[[OperationOutcome], None] | None = None,
    ) -> int:
        resumed = 0
        for operation_id in ready_operation_ids:
            if emit_operation is not None:
                emit_operation(operation_id)
            service = self.service_factory()
            outcome = await service.resume(
                operation_id,
                options=RunOptions(
                    run_mode=RunMode.RESUMABLE,
                    max_cycles=max_cycles_per_operation,
                    background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
                ),
            )
            if emit_outcome is not None:
                emit_outcome(outcome)
            resumed += 1
        return resumed

    async def enqueue_command(
        self,
        operation_id: str,
        command_type: OperationCommandType,
        payload: dict[str, object],
        *,
        target_scope: CommandTargetScope,
        target_id: str,
        auto_resume_when_paused: bool = False,
        auto_resume_blocked_attention_id: str | None = None,
    ) -> tuple[OperationCommand, OperationOutcome | None, str | None]:
        command = OperationCommand(
            operation_id=operation_id,
            command_type=command_type,
            target_scope=target_scope,
            target_id=target_id,
            payload={key: value for key, value in payload.items() if value is not None},
        )
        await self.command_inbox.enqueue(command)
        operation = await self._load_operation(operation_id)
        if operation is None:
            return command, None, None
        if auto_resume_when_paused and command_type is OperationCommandType.RESUME_OPERATOR:
            if operation.scheduler_state is not SchedulerState.PAUSED:
                if operation.scheduler_state is SchedulerState.PAUSE_REQUESTED:
                    return (
                        command,
                        None,
                        "resume queued: waiting for the current attached turn to yield.",
                    )
                return command, None, None
            service = self.service_factory()
            outcome = await service.resume(
                operation_id,
                options=RunOptions(run_mode=RunMode.ATTACHED),
            )
            return command, outcome, None
        if (
            auto_resume_blocked_attention_id is not None
            and operation.status is OperationStatus.NEEDS_HUMAN
            and operation.current_focus is not None
            and operation.current_focus.kind is FocusKind.ATTENTION_REQUEST
            and operation.current_focus.target_id == auto_resume_blocked_attention_id
        ):
            service = self.service_factory()
            outcome = await service.resume(
                operation_id,
                options=RunOptions(run_mode=RunMode.ATTACHED),
            )
            return command, outcome, None
        return command, None, None

    def build_command_payload(
        self,
        command_type: OperationCommandType,
        text: str | None,
        success_criteria: list[str] | None = None,
        clear_success_criteria: bool = False,
        allowed_agents: list[str] | None = None,
        max_iterations: int | None = None,
        model: str | None = None,
        effort: str | None = None,
    ) -> dict[str, object]:
        if command_type in {
            OperationCommandType.PATCH_OBJECTIVE,
            OperationCommandType.PATCH_HARNESS,
            OperationCommandType.INJECT_OPERATOR_MESSAGE,
            OperationCommandType.ANSWER_ATTENTION_REQUEST,
        }:
            if text is None or not text.strip():
                raise RuntimeError("--text is required for this command type.")
            return {"text": text.strip()}
        if command_type is OperationCommandType.PATCH_SUCCESS_CRITERIA:
            if text is not None:
                raise RuntimeError("--text is not supported for this command type.")
            if clear_success_criteria:
                if success_criteria:
                    raise RuntimeError(
                        "--success-criterion cannot be combined with --clear-success-criteria."
                    )
                return {"success_criteria": []}
            normalized = [item.strip() for item in success_criteria or [] if item.strip()]
            if not normalized:
                raise RuntimeError(
                    "--success-criterion or --clear-success-criteria "
                    "is required for this command type."
                )
            return {"success_criteria": normalized}
        if command_type is OperationCommandType.SET_ALLOWED_AGENTS:
            if text is not None:
                raise RuntimeError("--text is not supported for this command type.")
            if success_criteria or clear_success_criteria:
                raise RuntimeError(
                    "--success-criterion and --clear-success-criteria "
                    "are not supported for this command type."
                )
            if max_iterations is not None:
                raise RuntimeError("--max-iterations is not supported for this command type.")
            if allowed_agents is None:
                raise RuntimeError("--agent is required for this command type.")
            allowed_agents_payload = [item.strip() for item in allowed_agents if item.strip()]
            if not allowed_agents_payload:
                raise RuntimeError("--agent cannot be empty.")
            return {"allowed_agents": allowed_agents_payload}
        if command_type is OperationCommandType.SET_EXECUTION_PROFILE:
            if text is not None:
                raise RuntimeError("--text is not supported for this command type.")
            if success_criteria or clear_success_criteria:
                raise RuntimeError(
                    "--success-criterion and --clear-success-criteria "
                    "are not supported for this command type."
                )
            if max_iterations is not None:
                raise RuntimeError("--max-iterations is not supported for this command type.")
            if allowed_agents is None or len(allowed_agents) != 1:
                raise RuntimeError("--agent is required exactly once for this command type.")
            adapter_key = allowed_agents[0].strip()
            if not adapter_key:
                raise RuntimeError("--agent cannot be empty.")
            if model is None or not model.strip():
                raise RuntimeError("--model is required for this command type.")
            payload: dict[str, object] = {"adapter_key": adapter_key, "model": model.strip()}
            if effort is not None and effort.strip():
                payload["effort"] = effort.strip()
            return payload
        if command_type is OperationCommandType.SET_INVOLVEMENT_LEVEL:
            if text is None or not text.strip():
                raise RuntimeError("--text is required for this command type.")
            return {"level": text.strip()}
        if success_criteria or clear_success_criteria:
            raise RuntimeError("--success-criterion is not supported for this command type.")
        if text is not None:
            raise RuntimeError("--text is not supported for this command type.")
        return {}

    def build_policy_decision_payload(
        self,
        *,
        promote: bool,
        category: str,
        title: str | None,
        text: str | None,
        objective_keyword: list[str] | None,
        task_keyword: list[str] | None,
        agent: list[str] | None,
        run_mode: list[RunMode] | None,
        involvement: list[InvolvementLevel] | None,
        rationale: str | None,
    ) -> dict[str, object]:
        if not promote and any(
            item is not None
            for item in (
                title,
                text,
                rationale,
                objective_keyword,
                task_keyword,
                agent,
                run_mode,
                involvement,
            )
        ):
            raise RuntimeError("Policy options require --promote.")
        payload: dict[str, object] = {"category": category}
        if objective_keyword:
            payload["objective_keywords"] = [
                item.strip() for item in objective_keyword if item.strip()
            ]
        if task_keyword:
            payload["task_keywords"] = [item.strip() for item in task_keyword if item.strip()]
        if agent:
            payload["agent_keys"] = [item.strip() for item in agent if item.strip()]
        if run_mode:
            payload["run_modes"] = [item.value for item in run_mode]
        if involvement:
            payload["involvement_levels"] = [item.value for item in involvement]
        if title is not None:
            payload["title"] = title
        if text is not None:
            payload["text"] = text
        if rationale is not None:
            payload["rationale"] = rationale
        return payload

    async def enqueue_stop_turn(
        self,
        operation_id: str,
        *,
        task_id: str | None = None,
    ) -> OperationCommand:
        operation = await self._load_operation(operation_id)
        if operation is None:
            raise RuntimeError(f"Operation {operation_id!r} was not found.")
        if operation.scheduler_state is SchedulerState.DRAINING:
            raise RuntimeError("The active attached turn is already stopping.")
        if task_id is not None:
            task = self.find_task_by_display_id(operation, task_id)
            if task is None:
                raise RuntimeError(f"Task {task_id!r} was not found in operation {operation_id!r}.")
            if task.status is not TaskStatus.RUNNING:
                raise RuntimeError(
                    "stop_turn_invalid_state: "
                    f"task {task_id!r} is in state {task.status.value!r}, not 'running'."
                )
            target_session = None
            for record in operation.sessions:
                if task.task_id in record.bound_task_ids and record.status is SessionStatus.RUNNING:
                    target_session = record
                    break
            if target_session is None:
                raise RuntimeError(
                    f"Task {task_id!r} is running but has no active session bound to it."
                )
        else:
            target_session = operation.active_session_record
            if target_session is None:
                raise RuntimeError("This operation has no active session to stop.")
        command, _, _ = await self.enqueue_command(
            operation_id,
            OperationCommandType.STOP_AGENT_TURN,
            {},
            target_scope=CommandTargetScope.SESSION,
            target_id=target_session.session_id,
        )
        return command

    async def answer_attention(
        self,
        operation_id: str,
        *,
        attention_id: str | None,
        text: str,
        promote: bool,
        policy_payload: dict[str, object],
    ) -> tuple[OperationCommand, OperationCommand | None, OperationOutcome | None]:
        operation = await self._load_operation(operation_id)
        if operation is None:
            raise RuntimeError(f"Operation {operation_id!r} was not found.")
        resolved_attention_id = attention_id
        if resolved_attention_id is None:
            blocking = sorted(
                (
                    item
                    for item in operation.attention_requests
                    if item.status is AttentionStatus.OPEN and item.blocking
                ),
                key=lambda item: item.created_at,
            )
            if not blocking:
                raise RuntimeError(
                    f"Operation {operation_id!r} has no open blocking attention requests."
                )
            resolved_attention_id = blocking[0].attention_id
        answer_command, _, _ = await self.enqueue_command(
            operation_id,
            OperationCommandType.ANSWER_ATTENTION_REQUEST,
            {"text": text.strip()},
            target_scope=CommandTargetScope.ATTENTION_REQUEST,
            target_id=resolved_attention_id,
            auto_resume_blocked_attention_id=resolved_attention_id,
        )
        policy_command = None
        if promote:
            policy_command, _, _ = await self.enqueue_command(
                operation_id,
                OperationCommandType.RECORD_POLICY_DECISION,
                policy_payload,
                target_scope=CommandTargetScope.ATTENTION_REQUEST,
                target_id=resolved_attention_id,
            )
        operation = await self._load_operation(operation_id)
        if (
            operation is not None
            and operation.status is OperationStatus.NEEDS_HUMAN
            and operation.current_focus is not None
            and operation.current_focus.kind is FocusKind.ATTENTION_REQUEST
            and operation.current_focus.target_id == resolved_attention_id
        ):
            service = self.service_factory()
            outcome = await service.resume(
                operation_id,
                options=RunOptions(run_mode=RunMode.ATTACHED),
            )
            return answer_command, policy_command, outcome
        return answer_command, policy_command, None

    async def _load_operation(self, operation_id: str) -> OperationState | None:
        if self.state_loader is not None:
            operation = await self.state_loader.load_canonical_operation_state(operation_id)
            if operation is not None:
                return operation
        return await self.store.load_operation(operation_id)
