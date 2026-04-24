from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agent_operator.protocols import OperationEventStore, OperationStore


class ReplayServiceLike(Protocol):
    async def load(self, operation_id: str) -> object: ...


@dataclass(slots=True)
class OperationLifecycleEntrypointGuard:
    """Enforce create-only and continue-only lifecycle entrypoint rules."""

    store: OperationStore | None = None
    replay_service: ReplayServiceLike | None = None
    event_store: OperationEventStore | None = None

    async def ensure_new_operation_id(self, operation_id: str) -> None:
        """Reject `run()` when the supplied operation id already exists."""
        if await self.operation_exists(operation_id):
            raise RuntimeError(
                f"Operation {operation_id!r} already exists. "
                "Use resume, recover, or tick to continue an existing operation."
            )

    async def ensure_existing_operation_id(self, operation_id: str) -> None:
        """Reject continue-only entrypoints when the target operation does not exist."""
        if not await self.operation_exists(operation_id):
            raise RuntimeError(f"Operation {operation_id!r} was not found.")

    async def operation_exists(self, operation_id: str) -> bool:
        """Return whether the operation exists in any configured authority."""
        if self.store is not None and await self.store.load_operation(operation_id) is not None:
            return True
        if self.replay_service is not None:
            replay_state = await self.replay_service.load(operation_id)
            if (
                getattr(replay_state, "stored_checkpoint", None) is not None
                or getattr(replay_state, "last_applied_sequence", 0) > 0
                or bool(getattr(replay_state, "suffix_events", []))
            ):
                return True
        return (
            self.event_store is not None
            and await self.event_store.load_last_sequence(operation_id) > 0
        )
