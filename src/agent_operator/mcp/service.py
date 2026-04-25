from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, cast
from uuid import uuid4

import anyio

from agent_operator.application import (
    OperationDeliveryCommandService,
    OperationStatusQueryService,
)
from agent_operator.application.queries.operation_resolution import (
    OperationResolutionError,
    OperationResolutionService,
    OperationStoreLike,
)
from agent_operator.application.queries.operation_state_views import OperationStateViewService
from agent_operator.bootstrap import (
    build_event_sink,
    build_replay_service,
    build_service,
    build_store,
)
from agent_operator.config import OperatorSettings
from agent_operator.domain import (
    AttentionStatus,
    BackgroundRuntimeMode,
    ExecutionBudget,
    OperationGoal,
    OperationOutcome,
    OperationPolicy,
    OperationState,
    OperationStatus,
    RunMode,
    RunOptions,
    RuntimeHints,
    TaskStatus,
)
from agent_operator.runtime import (
    apply_project_profile_settings,
    discover_local_project_profile,
    resolve_project_run_config,
)


class McpToolError(RuntimeError):
    """Structured MCP tool failure.

    Args:
        code: Stable string error kind exposed in JSON-RPC `error.data.code`.
        message: Human-readable error message.
        operation_id: Optional operation identifier for operation-scoped failures.
    """

    def __init__(self, code: str, message: str, *, operation_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.operation_id = operation_id

class OperationSummaryLike(Protocol):
    operation_id: str
    status: OperationStatus


class OperatorServiceLike(Protocol):
    async def run(
        self,
        goal: OperationGoal,
        options: RunOptions | None = None,
        *,
        operation_id: str | None = None,
        attached_sessions: list[object] | None = None,
        policy: OperationPolicy | None = None,
        budget: ExecutionBudget | None = None,
        runtime_hints: RuntimeHints | None = None,
    ) -> OperationOutcome: ...


@dataclass(slots=True)
class OperatorMcpService:
    """MCP tool surface over the existing operator runtime and query layer."""

    status_service_factory: Callable[[OperatorSettings], OperationStatusQueryService]
    delivery_service_factory: Callable[[OperatorSettings], OperationDeliveryCommandService]
    settings_loader: Callable[[], OperatorSettings]
    settings_loader_with_data_dir: Callable[[], tuple[OperatorSettings, str]]
    service_builder: Callable[..., Any]
    store_builder: Callable[[OperatorSettings], OperationStoreLike]
    event_sink_builder: Callable[[OperatorSettings, str], object]

    async def list_operations(
        self,
        *,
        status_filter: OperationStatus | None,
    ) -> list[dict[str, object]]:
        settings = self.settings_loader()
        store = self.store_builder(settings)
        resolver = OperationResolutionService(
            store=store,
            replay_service=build_replay_service(settings),
            event_root=settings.data_dir / "operation_events",
            state_view_service=OperationStateViewService(),
        )
        items: list[dict[str, object]] = []
        for operation in await resolver.list_canonical_operation_states():
            if status_filter is not None and operation.status is not status_filter:
                continue
            items.append(self._list_item(operation))
        return items

    async def run_operation(
        self,
        *,
        goal: str,
        agent: str | None,
        wait: bool,
        timeout_seconds: int | None,
    ) -> dict[str, object]:
        settings, data_dir_source = self.settings_loader_with_data_dir()
        selection = discover_local_project_profile(settings)
        if selection.profile is None:
            raise McpToolError(
                "invalid_state",
                "No local operator-profile.yaml was found for MCP run_operation.",
            )
        if timeout_seconds is not None and not wait:
            raise McpToolError(
                "invalid_state",
                "timeout_seconds is supported only when wait=true.",
            )
        profile = selection.profile
        apply_project_profile_settings(settings, profile)
        resolved = resolve_project_run_config(
            settings,
            profile=profile,
            objective=goal,
            harness=None,
            success_criteria=None,
            allowed_agents=[agent] if agent is not None else None,
            max_iterations=None,
            run_mode=RunMode.RESUMABLE,
            involvement_level=None,
        )
        assert resolved.objective_text is not None
        operation_id = str(uuid4())
        service = cast(
            OperatorServiceLike,
            self.service_builder(
                settings,
                event_sink=self.event_sink_builder(settings, operation_id),
            ),
        )
        outcome = await service.run(
            OperationGoal(
                objective=resolved.objective_text,
                harness_instructions=resolved.harness_instructions,
                success_criteria=resolved.success_criteria,
                metadata={
                    "project_profile_name": profile.name,
                    "policy_scope": f"profile:{profile.name}",
                    "resolved_operator_launch": {
                        "data_dir": str(settings.data_dir),
                        "data_dir_source": data_dir_source,
                        "profile_source": selection.source,
                        "profile_path": str(selection.path) if selection.path else None,
                    },
                },
            ),
            policy=OperationPolicy(
                allowed_agents=resolved.default_agents,
                involvement_level=resolved.involvement_level,
            ),
            budget=ExecutionBudget(max_iterations=resolved.max_iterations),
            runtime_hints=RuntimeHints(operator_message_window=resolved.message_window),
            options=RunOptions(
                run_mode=RunMode.RESUMABLE,
                background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
            ),
            operation_id=operation_id,
        )
        if not wait:
            return {"operation_id": operation_id, "status": outcome.status.value}
        waited = await self._wait_for_outcome(
            operation_id=operation_id,
            timeout_seconds=timeout_seconds,
        )
        return {
            "operation_id": operation_id,
            "status": waited.status.value,
            "outcome": {"status": waited.status.value, "summary": waited.summary},
        }

    async def get_status(self, *, operation_id: str) -> dict[str, object]:
        resolved_operation_id = await self._resolve_operation_id(operation_id)
        settings = self.settings_loader()
        service = self.status_service_factory(settings)
        operation, outcome, _, _ = await self._build_status_payload(service, resolved_operation_id)
        assert operation is not None
        blocking_attention = [
            attention
            for attention in operation.attention_requests
            if attention.status is AttentionStatus.OPEN and attention.blocking
        ]
        return {
            "operation_id": resolved_operation_id,
            "status": operation.status.value,
            "goal": operation.goal.objective_text,
            "iteration": len(operation.iterations),
            "task_summary": self._summarize_task_counts(operation),
            "attention_requests": [
                {
                    "id": attention.attention_id,
                    "question": attention.question,
                    "created_at": self._iso(attention.created_at),
                }
                for attention in blocking_attention
            ],
            "started_at": self._iso(operation.run_started_at or operation.created_at),
            "ended_at": (
                self._iso(operation.updated_at)
                if operation.status is not OperationStatus.RUNNING
                else None
            ),
            "outcome_summary": outcome.summary if outcome is not None else operation.final_summary,
        }

    async def answer_attention(
        self,
        *,
        operation_id: str,
        attention_id: str | None,
        answer: str,
    ) -> dict[str, object]:
        resolved_operation_id = await self._resolve_operation_id(operation_id)
        service = self.delivery_service_factory(self.settings_loader())
        try:
            answer_command, _, _ = await service.answer_attention(
                resolved_operation_id,
                attention_id=attention_id,
                text=answer,
                promote=False,
                policy_payload={},
            )
        except RuntimeError as exc:
            raise self._map_runtime_error(exc, operation_id=resolved_operation_id) from exc
        return {"attention_id": answer_command.target_id, "status": "answered"}

    async def cancel_operation(
        self,
        *,
        operation_id: str,
        reason: str | None,
    ) -> dict[str, object]:
        resolved_operation_id = await self._resolve_operation_id(operation_id)
        del reason
        service = self.delivery_service_factory(self.settings_loader())
        try:
            outcome = await service.cancel(
                resolved_operation_id,
                session_id=None,
                run_id=None,
            )
        except RuntimeError as exc:
            raise self._map_runtime_error(exc, operation_id=resolved_operation_id) from exc
        return {"operation_id": resolved_operation_id, "status": outcome.status.value}

    async def interrupt_operation(self, *, operation_id: str) -> dict[str, object]:
        resolved_operation_id = await self._resolve_operation_id(operation_id)
        service = self.delivery_service_factory(self.settings_loader())
        try:
            await service.enqueue_stop_turn(resolved_operation_id, task_id=None)
        except RuntimeError as exc:
            raise self._map_runtime_error(exc, operation_id=resolved_operation_id) from exc
        return {"operation_id": resolved_operation_id, "acknowledged": True}

    async def _wait_for_outcome(
        self,
        *,
        operation_id: str,
        timeout_seconds: int | None,
    ) -> OperationOutcome:
        service = self.status_service_factory(self.settings_loader())
        deadline = anyio.current_time() + timeout_seconds if timeout_seconds is not None else None
        while True:
            _, outcome, _, _ = await self._build_status_payload(service, operation_id)
            if outcome is not None and outcome.status is not OperationStatus.RUNNING:
                return outcome
            if deadline is not None and anyio.current_time() >= deadline:
                raise McpToolError(
                    "timeout",
                    "Timed out while waiting for operation.",
                    operation_id=operation_id,
                )
            await anyio.sleep(0.1)

    async def _resolve_operation_id(self, operation_ref: str) -> str:
        settings = self.settings_loader()
        resolver = OperationResolutionService(
            store=self.store_builder(settings),
            replay_service=build_replay_service(settings),
            event_root=settings.data_dir / "operation_events",
            state_view_service=OperationStateViewService(),
        )
        try:
            return await resolver.resolve_operation_id(operation_ref)
        except OperationResolutionError as exc:
            code = "invalid_state" if exc.code == "ambiguous" else "not_found"
            raise McpToolError(code, str(exc)) from exc

    async def _build_status_payload(
        self,
        service: OperationStatusQueryService,
        operation_id: str,
    ) -> tuple[OperationState | None, OperationOutcome | None, object | None, str | None]:
        try:
            return await service.build_status_payload(operation_id)
        except RuntimeError as exc:
            raise McpToolError("not_found", str(exc), operation_id=operation_id) from exc

    def _list_item(self, operation: OperationState) -> dict[str, object]:
        return {
            "operation_id": operation.operation_id,
            "status": operation.status.value,
            "goal": operation.goal.objective_text,
            "started_at": self._iso(operation.run_started_at or operation.created_at),
            "attention_count": sum(
                1
                for attention in operation.attention_requests
                if attention.status is AttentionStatus.OPEN and attention.blocking
            ),
        }

    def _map_runtime_error(self, exc: RuntimeError, *, operation_id: str) -> McpToolError:
        message = str(exc)
        lowered = message.lower()
        if "not found" in lowered:
            return McpToolError("not_found", message, operation_id=operation_id)
        if "timed out" in lowered:
            return McpToolError("timeout", message, operation_id=operation_id)
        return McpToolError("invalid_state", message, operation_id=operation_id)

    def _summarize_task_counts(self, operation: OperationState) -> str:
        counts = {
            "running": 0,
            "queued": 0,
            "blocked": 0,
            "completed": 0,
            "failed": 0,
        }
        for task in operation.tasks:
            if task.status is TaskStatus.RUNNING:
                counts["running"] += 1
            elif task.status is TaskStatus.READY:
                counts["queued"] += 1
            elif task.status in {TaskStatus.PENDING, TaskStatus.BLOCKED}:
                counts["blocked"] += 1
            elif task.status is TaskStatus.COMPLETED:
                counts["completed"] += 1
            elif task.status is TaskStatus.FAILED:
                counts["failed"] += 1
        return (
            f"running={counts['running']} queued={counts['queued']} blocked={counts['blocked']} "
            f"completed={counts['completed']} failed={counts['failed']}"
        )

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None


def build_operator_mcp_service() -> OperatorMcpService:
    """Build the MCP service façade from existing repository services."""
    from agent_operator.cli.helpers.services import (
        build_delivery_commands_service,
        build_status_query_service,
        load_settings,
        load_settings_with_data_dir,
    )

    return OperatorMcpService(
        status_service_factory=build_status_query_service,
        delivery_service_factory=build_delivery_commands_service,
        settings_loader=load_settings,
        settings_loader_with_data_dir=load_settings_with_data_dir,
        service_builder=build_service,
        store_builder=build_store,
        event_sink_builder=build_event_sink,
    )
