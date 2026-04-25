from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from agent_operator.application.queries.operation_resolution import (
    OperationResolutionError,
    OperationResolutionService,
)
from agent_operator.domain import OperationGoal, OperationState
from agent_operator.testing.operator_service_support import state_settings


class _Summary:
    def __init__(self, operation_id: str) -> None:
        self.operation_id = operation_id


class _Store:
    def __init__(self, states: list[OperationState]) -> None:
        self._states = {state.operation_id: state for state in states}

    async def list_operations(self) -> list[_Summary]:
        return [_Summary(operation_id) for operation_id in self._states]

    async def load_operation(self, operation_id: str) -> OperationState | None:
        return self._states.get(operation_id)


class _ReplayService:
    async def load(self, operation_id: str) -> object:
        del operation_id
        return SimpleNamespace(
            stored_checkpoint=None,
            last_applied_sequence=0,
            suffix_events=[],
            checkpoint=None,
        )


def _operation(operation_id: str, *, created_at: datetime) -> OperationState:
    settings = cast(Any, state_settings())
    return OperationState(
        operation_id=operation_id,
        goal=OperationGoal(objective=f"Operate {operation_id}"),
        created_at=created_at,
        **settings,
    )


@pytest.mark.anyio
async def test_operation_resolution_rejects_ambiguous_prefix_with_code(
    tmp_path: Path,
) -> None:
    service = OperationResolutionService(
        store=_Store(
            [
                _operation("op-resolution-alpha", created_at=datetime(2026, 4, 23, tzinfo=UTC)),
                _operation("op-resolution-beta", created_at=datetime(2026, 4, 24, tzinfo=UTC)),
            ]
        ),
        replay_service=_ReplayService(),
        event_root=tmp_path / "operation_events",
    )

    with pytest.raises(OperationResolutionError) as exc_info:
        await service.resolve_operation_id("op-resolution")

    assert exc_info.value.code == "ambiguous"
    assert "op-resolution-alpha" in str(exc_info.value)
    assert "op-resolution-beta" in str(exc_info.value)


@pytest.mark.anyio
async def test_operation_resolution_does_not_match_profile_name(
    tmp_path: Path,
) -> None:
    state = _operation("op-profile-explicit-only", created_at=datetime(2026, 4, 24, tzinfo=UTC))
    state.goal.metadata["project_profile_name"] = "femtobot"
    service = OperationResolutionService(
        store=_Store([state]),
        replay_service=_ReplayService(),
        event_root=tmp_path / "operation_events",
    )

    with pytest.raises(OperationResolutionError) as exc_info:
        await service.resolve_operation_id("femtobot")

    assert exc_info.value.code == "not_found"
    assert str(exc_info.value) == "Operation 'femtobot' was not found."
