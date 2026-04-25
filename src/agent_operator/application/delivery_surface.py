from __future__ import annotations

from dataclasses import dataclass

from agent_operator.application.commands.operation_delivery_commands import (
    OperationDeliveryCommandService,
)
from agent_operator.application.queries.operation_resolution import OperationResolutionService
from agent_operator.application.queries.operation_status_queries import (
    OperationReadPayload,
    OperationStatusQueryService,
)
from agent_operator.domain import (
    CommandTargetScope,
    OperationCommand,
    OperationCommandType,
    OperationOutcome,
    OperationState,
)


@dataclass(slots=True)
class DeliverySurfaceService:
    """Shared application-facing contract for delivery surfaces.

    The service is intentionally thin: operation identity, status reads, and
    command application remain owned by the existing application services.

    Examples:
        ```python
        surface = DeliverySurfaceService(
            resolver=resolver,
            status_queries=status_queries,
            commands=commands,
        )
        operation_id = await surface.resolve_operation_id("last")
        ```
    """

    resolver: OperationResolutionService
    status_queries: OperationStatusQueryService
    commands: OperationDeliveryCommandService

    async def resolve_operation_id(self, operation_ref: str) -> str:
        """Resolve an operation reference through the shared resolver."""

        return await self.resolver.resolve_operation_id(operation_ref)

    async def list_operation_states(self) -> list[OperationState]:
        """List canonical operation states through the shared resolver."""

        return await self.resolver.list_canonical_operation_states()

    async def load_operation_state(self, operation_ref: str) -> OperationState:
        """Load canonical operation state after shared reference resolution."""

        operation_id = await self.resolve_operation_id(operation_ref)
        operation = await self.resolver.load_canonical_operation_state(operation_id)
        if operation is None:
            raise RuntimeError(f"Operation {operation_id!r} was not found.")
        return operation

    async def build_read_payload(self, operation_ref: str) -> OperationReadPayload:
        """Build the shared status/read payload for a resolved operation."""

        operation_id = await self.resolve_operation_id(operation_ref)
        return await self.status_queries.build_read_payload(operation_id)

    async def answer_attention(
        self,
        operation_ref: str,
        *,
        attention_id: str | None,
        text: str,
        promote: bool = False,
        policy_payload: dict[str, object] | None = None,
    ) -> tuple[OperationCommand, OperationCommand | None, OperationOutcome | None]:
        """Answer an attention request through the shared command facade."""

        answer_text = text.strip()
        if not answer_text:
            raise ValueError("text must not be empty.")
        operation_id = await self.resolve_operation_id(operation_ref)
        return await self.commands.answer_attention(
            operation_id,
            attention_id=attention_id,
            text=answer_text,
            promote=promote,
            policy_payload=policy_payload or {},
        )

    async def cancel_operation(
        self,
        operation_ref: str,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        reason: str | None = None,
    ) -> OperationOutcome:
        """Cancel an operation through the shared command facade."""

        operation_id = await self.resolve_operation_id(operation_ref)
        return await self.commands.cancel(
            operation_id,
            session_id=session_id,
            run_id=run_id,
            reason=reason,
        )

    async def interrupt_operation(
        self,
        operation_ref: str,
        *,
        task_id: str | None = None,
    ) -> OperationCommand:
        """Request active-turn interruption through the shared command facade."""

        operation_id = await self.resolve_operation_id(operation_ref)
        return await self.commands.enqueue_stop_turn(operation_id, task_id=task_id)

    async def message_operation(
        self,
        operation_ref: str,
        *,
        text: str,
    ) -> OperationCommand:
        """Queue a free-form operator message through the shared command facade."""

        message_text = text.strip()
        if not message_text:
            raise ValueError("text must not be empty.")
        operation_id = await self.resolve_operation_id(operation_ref)
        command, _, _ = await self.commands.enqueue_command(
            operation_id,
            OperationCommandType.INJECT_OPERATOR_MESSAGE,
            {"text": message_text},
            target_scope=CommandTargetScope.OPERATION,
            target_id=operation_id,
        )
        return command

    async def pause_operation(self, operation_ref: str) -> OperationCommand:
        """Queue a pause command through the shared command facade."""

        operation_id = await self.resolve_operation_id(operation_ref)
        command, _, _ = await self.commands.enqueue_command(
            operation_id,
            OperationCommandType.PAUSE_OPERATOR,
            {},
            target_scope=CommandTargetScope.OPERATION,
            target_id=operation_id,
        )
        return command

    async def unpause_operation(
        self,
        operation_ref: str,
    ) -> tuple[OperationCommand, OperationOutcome | None, str | None]:
        """Queue an unpause command and resume attached work when applicable."""

        operation_id = await self.resolve_operation_id(operation_ref)
        return await self.commands.enqueue_command(
            operation_id,
            OperationCommandType.RESUME_OPERATOR,
            {},
            target_scope=CommandTargetScope.OPERATION,
            target_id=operation_id,
            auto_resume_when_paused=True,
        )
