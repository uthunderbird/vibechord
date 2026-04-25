from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from agent_operator.application.queries.operation_state_views import OperationStateViewService
from agent_operator.domain import OperationState


@dataclass(frozen=True, slots=True)
class OperationResolutionError(RuntimeError):
    """Failure to resolve an operation reference.

    Args:
        code: Stable machine-readable resolution failure code.
        message: Human-readable failure message.

    Examples:
        ```python
        raise OperationResolutionError(
            code="ambiguous",
            message="Operation reference 'op' is ambiguous.",
        )
        ```
    """

    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class ReplayServiceLike(Protocol):
    async def load(self, operation_id: str) -> object: ...


class OperationSummaryLike(Protocol):
    operation_id: str


class OperationStoreLike(Protocol):
    async def list_operations(self) -> Sequence[OperationSummaryLike]: ...

    async def load_operation(self, operation_id: str) -> OperationState | None: ...


@dataclass(slots=True)
class OperationResolutionService:
    """Resolve operation references against legacy and event-sourced truth."""

    store: OperationStoreLike
    replay_service: ReplayServiceLike
    event_root: Path
    state_view_service: OperationStateViewService = field(
        default_factory=OperationStateViewService
    )

    async def resolve_operation_id(self, operation_ref: str) -> str:
        states = await self.list_canonical_operation_states()
        event_sourced_ids = self.list_event_sourced_operation_ids()
        if operation_ref == "last":
            if not states:
                raise OperationResolutionError(
                    code="not_found",
                    message="No persisted operations were found.",
                )
            latest = max(states, key=lambda item: item.created_at)
            return latest.operation_id
        exact = next(
            (item.operation_id for item in states if item.operation_id == operation_ref),
            None,
        )
        if exact is not None:
            return exact
        if operation_ref in event_sourced_ids:
            return operation_ref
        matches = sorted(
            {
                item.operation_id
                for item in states
                if item.operation_id.startswith(operation_ref)
            }
        )
        matches.extend(item for item in event_sourced_ids if item.startswith(operation_ref))
        deduped = sorted(set(matches))
        if len(deduped) == 1:
            return deduped[0]
        if len(deduped) > 1:
            rendered_matches = ", ".join(deduped)
            raise OperationResolutionError(
                code="ambiguous",
                message=(
                    f"Operation reference {operation_ref!r} is ambiguous. Matches: "
                    f"{rendered_matches}"
                ),
            )
        raise OperationResolutionError(
            code="not_found",
            message=f"Operation {operation_ref!r} was not found.",
        )

    async def load_canonical_operation_state(self, operation_id: str) -> OperationState | None:
        operation = await self._load_event_sourced_operation_state(operation_id)
        if operation is not None:
            return operation
        operation = await self.store.load_operation(operation_id)
        if operation is not None:
            return operation
        return None

    async def list_canonical_operation_states(self) -> list[OperationState]:
        states: list[OperationState] = []
        seen_operation_ids: set[str] = set()
        for operation_id in self.list_event_sourced_operation_ids():
            operation = await self._load_event_sourced_operation_state(operation_id)
            if operation is None:
                continue
            states.append(operation)
            seen_operation_ids.add(operation.operation_id)
        for summary in await self.store.list_operations():
            if summary.operation_id in seen_operation_ids:
                continue
            operation = await self.store.load_operation(summary.operation_id)
            if operation is None:
                continue
            states.append(operation)
            seen_operation_ids.add(operation.operation_id)
        return states

    def list_event_sourced_operation_ids(self) -> list[str]:
        if not self.event_root.exists():
            return []
        paths = [path for path in self.event_root.glob("*.jsonl") if path.is_file()]
        paths.sort(key=lambda path: (path.stat().st_mtime, path.name))
        return [path.stem for path in paths]

    async def _load_event_sourced_operation_state(self, operation_id: str) -> OperationState | None:
        replay_state = await self.replay_service.load(operation_id)
        if (
            getattr(replay_state, "stored_checkpoint", None) is None
            and getattr(replay_state, "last_applied_sequence", 0) == 0
            and not getattr(replay_state, "suffix_events", [])
        ):
            return None
        checkpoint = getattr(replay_state, "checkpoint", None)
        if checkpoint is None:
            return None
        return self.state_view_service.from_checkpoint(checkpoint)
