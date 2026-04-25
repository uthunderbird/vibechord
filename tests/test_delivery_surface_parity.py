from __future__ import annotations

from dataclasses import dataclass

import pytest

from agent_operator.application import DeliverySurfaceService
from agent_operator.application.queries.operation_status_queries import OperationReadPayload
from agent_operator.domain import (
    CommandTargetScope,
    OperationCommand,
    OperationCommandType,
    OperationGoal,
    OperationOutcome,
    OperationState,
    OperationStatus,
)

pytestmark = pytest.mark.anyio


@dataclass(slots=True)
class _Resolver:
    resolved: list[str]

    async def resolve_operation_id(self, operation_ref: str) -> str:
        self.resolved.append(operation_ref)
        return "op-canonical"

    async def list_canonical_operation_states(self) -> list[OperationState]:
        return [
            OperationState(
                operation_id="op-canonical",
                goal=OperationGoal(objective="Shared surface"),
            )
        ]

    async def load_canonical_operation_state(self, operation_id: str) -> OperationState | None:
        return OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Shared surface"),
        )


@dataclass(slots=True)
class _StatusQueries:
    requested: list[str]

    async def build_read_payload(self, operation_id: str) -> OperationReadPayload:
        self.requested.append(operation_id)
        return OperationReadPayload(
            operation_id=operation_id,
            operation=OperationState(
                operation_id=operation_id,
                goal=OperationGoal(objective="Shared read"),
            ),
            outcome=None,
            source="event_sourced",
        )


@dataclass(slots=True)
class _Commands:
    answered: list[tuple[str, str | None, str]]
    cancelled: list[str]
    interrupted: list[tuple[str, str | None]]

    async def answer_attention(
        self,
        operation_id: str,
        *,
        attention_id: str | None,
        text: str,
        promote: bool,
        policy_payload: dict[str, object],
    ) -> tuple[OperationCommand, OperationCommand | None, OperationOutcome | None]:
        del promote, policy_payload
        self.answered.append((operation_id, attention_id, text))
        return (
            OperationCommand(
                operation_id=operation_id,
                command_type=OperationCommandType.ANSWER_ATTENTION_REQUEST,
                target_scope=CommandTargetScope.ATTENTION_REQUEST,
                target_id=attention_id or "att-1",
                payload={"text": text},
            ),
            None,
            None,
        )

    async def cancel(
        self,
        operation_id: str,
        *,
        session_id: str | None,
        run_id: str | None,
        reason: str | None = None,
    ) -> OperationOutcome:
        del session_id, run_id, reason
        self.cancelled.append(operation_id)
        return OperationOutcome(
            operation_id=operation_id,
            status=OperationStatus.CANCELLED,
            summary="cancelled",
        )

    async def enqueue_stop_turn(
        self,
        operation_id: str,
        *,
        task_id: str | None = None,
    ) -> OperationCommand:
        self.interrupted.append((operation_id, task_id))
        return OperationCommand(
            operation_id=operation_id,
            command_type=OperationCommandType.STOP_AGENT_TURN,
            target_scope=CommandTargetScope.SESSION,
            target_id="session-1",
            payload={},
        )


def _surface() -> tuple[DeliverySurfaceService, _Resolver, _StatusQueries, _Commands]:
    resolver = _Resolver(resolved=[])
    status_queries = _StatusQueries(requested=[])
    commands = _Commands(answered=[], cancelled=[], interrupted=[])
    return (
        DeliverySurfaceService(
            resolver=resolver,  # type: ignore[arg-type]
            status_queries=status_queries,  # type: ignore[arg-type]
            commands=commands,  # type: ignore[arg-type]
        ),
        resolver,
        status_queries,
        commands,
    )


async def test_delivery_surface_resolves_before_status_reads() -> None:
    """Catches bypassing the shared resolver and querying status with raw refs."""
    surface, resolver, status_queries, _ = _surface()

    payload = await surface.build_read_payload("op")

    assert payload.operation_id == "op-canonical"
    assert resolver.resolved == ["op"]
    assert status_queries.requested == ["op-canonical"]


async def test_delivery_surface_resolves_before_command_application() -> None:
    """Catches SDK/MCP/TUI command paths applying commands to unresolved refs."""
    surface, resolver, _, commands = _surface()

    await surface.answer_attention("last", attention_id="att", text="  approved  ")
    await surface.cancel_operation("last")
    await surface.interrupt_operation("last", task_id="task-1")

    assert resolver.resolved == ["last", "last", "last"]
    assert commands.answered == [("op-canonical", "att", "approved")]
    assert commands.cancelled == ["op-canonical"]
    assert commands.interrupted == [("op-canonical", "task-1")]
