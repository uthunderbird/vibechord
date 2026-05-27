"""Public local Python SDK surface."""

from __future__ import annotations

import uuid
from pathlib import Path

from vibechord.command import CommandApplication
from vibechord.domain import (
    CommandName,
    CommandResult,
    FleetRowDTO,
    LiveFeedEnvelope,
    OperationCommand,
    StatusDTO,
)
from vibechord.driver import OperationDriver
from vibechord.projection import ProjectionService
from vibechord.workspace import AppContext, build_context


class VibechordClient:
    """Local Python SDK over the same application contracts as CLI/REST/TUI.

    Example:
        >>> from tempfile import TemporaryDirectory
        >>> with TemporaryDirectory() as tmp:
        ...     client = VibechordClient(tmp)
        ...     result = client.run("example")
        ...     client.status(result.operation_id or "").status
        'completed'
    """

    def __init__(self, root: str | Path) -> None:
        """Create a local SDK client for a workspace root."""

        self.context: AppContext = build_context(Path(root))

    @property
    def commands(self) -> CommandApplication:
        """Return the shared command application."""

        return self.context.command_application

    @property
    def projections(self) -> ProjectionService:
        """Return the shared projection service."""

        return self.context.projection_service

    @property
    def driver(self) -> OperationDriver:
        """Return the shared operation driver."""

        return self.context.operation_driver

    def run(self, goal: str) -> CommandResult:
        """Start an operation and drive it until blocked or terminal."""

        result = self.commands.apply(
            OperationCommand(
                name=CommandName.START,
                command_id=str(uuid.uuid4()),
                payload={"goal": goal},
            )
        )
        if result.accepted and result.operation_id is not None:
            self.driver.run_until_blocked_or_terminal(result.operation_id)
        return result

    def status(self, operation_id: str) -> StatusDTO:
        """Return shared operation status."""

        return self.projections.status(operation_id)

    def fleet(self) -> tuple[FleetRowDTO, ...]:
        """Return shared fleet rows."""

        return self.projections.fleet()

    def live(self, operation_id: str) -> tuple[LiveFeedEnvelope, ...]:
        """Return live-feed envelopes for one operation."""

        return self.projections.live_feed(operation_id)

    def message(self, operation_id: str, text: str) -> CommandResult:
        """Post a live operator message through shared command authority."""

        return self.commands.apply(
            OperationCommand(
                name=CommandName.POST_MESSAGE,
                command_id=str(uuid.uuid4()),
                operation_id=operation_id,
                payload={"text": text},
            )
        )
