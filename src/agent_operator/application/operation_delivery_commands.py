from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from agent_operator.application.operation_projections import OperationProjectionService
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
    TraceBriefBundle,
)
from agent_operator.protocols import OperationCommandInbox, OperationStore


class TraceStoreLike(Protocol):
    async def load_brief_bundle(self, operation_id: str) -> TraceBriefBundle | None: ...


class BackgroundInspectionStoreLike(Protocol):
    async def list_runs(self, operation_id: str) -> list: ...


class WakeupInspectionStoreLike(Protocol):
    def read_all(self, operation_id: str | None = None) -> list[dict[str, object]]: ...


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


@dataclass(slots=True)
class OperationDeliveryCommandService:
    store: OperationStore
    command_inbox: OperationCommandInbox
    projection_service: OperationProjectionService
    trace_store: TraceStoreLike
    background_inspection_store: BackgroundInspectionStoreLike
    wakeup_inspection_store: WakeupInspectionStoreLike | None
    service_factory: Callable[[], OperatorServiceLike]
    overlay_live_background_progress: Callable[[OperationState, list], OperationState]
    build_runtime_alert: Callable[..., str | None]
    render_status_brief: Callable[[OperationState], str]
    render_inspect_summary: Callable[[OperationState, TraceBriefBundle | None], str]
    find_task_by_display_id: Callable[[OperationState, str], object | None]

    async def build_status_payload(
        self,
        operation_id: str,
    ) -> tuple[OperationState | None, OperationOutcome | None, TraceBriefBundle | None, str | None]:
        operation = await self.store.load_operation(operation_id)
        outcome = await self.store.load_outcome(operation_id)
        if operation is None and outcome is None:
            raise RuntimeError(f"Operation {operation_id!r} was not found.")
        if operation is None:
            return None, outcome, None, None
        wakeups = (
            self.wakeup_inspection_store.read_all(operation_id)
            if self.wakeup_inspection_store is not None
            else []
        )
        runs = await self.background_inspection_store.list_runs(operation_id)
        operation = self.overlay_live_background_progress(operation, runs)
        brief_bundle = await self.trace_store.load_brief_bundle(operation_id)
        runtime_alert = self.build_runtime_alert(
            status=operation.status,
            wakeups=wakeups,
            background_runs=[item.model_dump(mode="json") for item in runs],
        )
        return operation, outcome, brief_bundle, runtime_alert

    async def render_status_output(
        self,
        operation_id: str,
        *,
        json_mode: bool,
        brief: bool,
    ) -> str:
        operation, outcome, brief_bundle, runtime_alert = await self.build_status_payload(operation_id)
        if operation is None:
            assert outcome is not None
            if json_mode:
                return json.dumps(
                    {
                        "operation_id": operation_id,
                        "status": outcome.status.value,
                        "summary": outcome.summary,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            return f"{operation_id} {outcome.status.value.upper()} {outcome.summary}"

        if json_mode:
            payload = {
                "operation_id": operation_id,
                "status": operation.status.value,
                "summary": self.build_live_snapshot(operation_id, operation, outcome),
                "action_hint": self.build_status_action_hint(operation),
                "durable_truth": self.projection_service.build_durable_truth_payload(
                    operation,
                    include_inactive_memory=True,
                ),
            }
            return json.dumps(payload, indent=2, ensure_ascii=False)
        if brief:
            return self.render_status_brief(operation)
        rendered = self.render_inspect_summary(operation, brief_bundle, runtime_alert=runtime_alert)
        action_hint = self.build_status_action_hint(operation)
        if action_hint is not None:
            rendered += f"\n→ Action required: {action_hint}"
        return rendered

    async def cancel(
        self,
        operation_id: str,
        *,
        session_id: str | None,
        run_id: str | None,
    ) -> OperationOutcome:
        service = self.service_factory()
        return await service.cancel(operation_id, session_id=session_id, run_id=run_id)

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
        operation = await self.store.load_operation(operation_id)
        if operation is None:
            return command, None, None
        if auto_resume_when_paused and command_type is OperationCommandType.RESUME_OPERATOR:
            if operation.scheduler_state is not SchedulerState.PAUSED:
                if operation.scheduler_state is SchedulerState.PAUSE_REQUESTED:
                    return command, None, "resume queued: waiting for the current attached turn to yield."
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
                    "--success-criterion or --clear-success-criteria is required for this command type."
                )
            return {"success_criteria": normalized}
        if command_type is OperationCommandType.SET_ALLOWED_AGENTS:
            if text is not None:
                raise RuntimeError("--text is not supported for this command type.")
            if success_criteria or clear_success_criteria:
                raise RuntimeError(
                    "--success-criterion and --clear-success-criteria are not supported for this command type."
                )
            if max_iterations is not None:
                raise RuntimeError("--max-iterations is not supported for this command type.")
            if allowed_agents is None:
                raise RuntimeError("--allowed-agent is required for this command type.")
            allowed_agents_payload = [item.strip() for item in allowed_agents if item.strip()]
            if not allowed_agents_payload:
                raise RuntimeError("--allowed-agent cannot be empty.")
            return {"allowed_agents": allowed_agents_payload}
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
            payload["objective_keywords"] = [item.strip() for item in objective_keyword if item.strip()]
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

    def build_status_action_hint(self, operation: OperationState) -> str | None:
        open_attention = [
            attention
            for attention in operation.attention_requests
            if attention.status is AttentionStatus.OPEN
        ]
        if open_attention:
            return (
                f"operator answer {operation.operation_id} "
                f"{open_attention[0].attention_id} --text '...'"
            )
        if (
            operation.active_session_record is not None
            and operation.scheduler_state is not SchedulerState.DRAINING
        ):
            return f"operator interrupt {operation.operation_id}"
        if operation.scheduler_state in {SchedulerState.PAUSED, SchedulerState.PAUSE_REQUESTED}:
            return f"operator unpause {operation.operation_id}"
        return None

    async def enqueue_stop_turn(
        self,
        operation_id: str,
        *,
        task_id: str | None = None,
    ) -> OperationCommand:
        operation = await self.store.load_operation(operation_id)
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
        operation = await self.store.load_operation(operation_id)
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
        operation = await self.store.load_operation(operation_id)
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

    def build_live_snapshot(
        self,
        operation_id: str,
        operation: OperationState | None,
        outcome: OperationOutcome | None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {"operation_id": operation_id}
        if operation is None:
            payload["status"] = outcome.status.value if outcome is not None else "unknown"
            payload["summary"] = outcome.summary if outcome is not None else "Operation not found."
            return payload
        payload.update(self.projection_service.build_live_snapshot(operation, None, runtime_alert=None))
        payload["involvement_level"] = operation.involvement_level.value
        payload["updated_at"] = operation.updated_at.isoformat()
        active_session = operation.active_session_record
        if active_session is not None:
            payload["session_id"] = active_session.session_id
            payload["adapter_key"] = active_session.adapter_key
            payload["session_status"] = active_session.status.value
            if active_session.waiting_reason:
                payload["waiting_reason"] = active_session.waiting_reason
        if operation.attention_requests:
            open_attention = [
                item for item in operation.attention_requests if item.status is AttentionStatus.OPEN
            ]
            if open_attention:
                payload["open_attention_count"] = len(open_attention)
                payload["attention_title"] = open_attention[0].title
                payload["attention_brief"] = (
                    f"[{open_attention[0].attention_type.value}] {open_attention[0].title}"
                )
        summary = outcome.summary if outcome is not None else operation.final_summary
        if summary:
            payload["summary"] = summary
        return payload
