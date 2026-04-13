from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from agent_operator.application.event_sourcing.event_sourced_replay import EventSourcedReplayService
from agent_operator.domain import (
    InvolvementLevel,
    OperationCheckpoint,
    OperationCommand,
    OperationCommandType,
    OperationDomainEventDraft,
    OperationStatus,
    OperatorMessage,
    SchedulerState,
    StoredOperationDomainEvent,
)
from agent_operator.protocols import (
    OperationCheckpointStore,
    OperationEventStore,
    OperationProjector,
)


@dataclass(slots=True)
class EventSourcedCommandApplicationResult:
    """Result of one event-sourced command application attempt.

    Attributes:
        applied: Whether the command was accepted and produced business mutation events.
        checkpoint: Canonical checkpoint after appending and projecting outcome events.
        stored_events: Persisted domain events emitted for this command.
        rejection_reason: Rejection reason for rejected commands, if any.
    """

    applied: bool
    checkpoint: OperationCheckpoint
    stored_events: list[StoredOperationDomainEvent]
    rejection_reason: str | None = None


class EventSourcedCommandApplicationService:
    """Single-writer command application boundary for event-sourced operations.

    This service validates one command against canonical replay state, appends explicit command
    outcome events, projects the new checkpoint, and persists the updated checkpoint record.

    Examples:
        >>> service = EventSourcedCommandApplicationService(
        ...     event_store=None,  # doctest: +SKIP
        ...     checkpoint_store=None,  # doctest: +SKIP
        ...     projector=None,  # doctest: +SKIP
        ... )
    """

    def __init__(
        self,
        *,
        event_store: OperationEventStore,
        checkpoint_store: OperationCheckpointStore,
        projector: OperationProjector,
    ) -> None:
        self._event_store = event_store
        self._replay = EventSourcedReplayService(
            event_store=event_store,
            checkpoint_store=checkpoint_store,
            projector=projector,
        )

    async def apply(
        self,
        command: OperationCommand,
    ) -> EventSourcedCommandApplicationResult:
        """Apply one command through canonical domain-event append.

        Args:
            command: User command to validate and append.

        Returns:
            Canonical application result after append and projection.
        """
        replay_state = await self._replay.load(command.operation_id)
        drafts, rejection_reason = self._build_domain_event_drafts(command, replay_state.checkpoint)
        stored_events = await self._event_store.append(
            command.operation_id,
            replay_state.last_applied_sequence,
            drafts,
        )
        updated_replay_state = self._replay.advance(replay_state, stored_events)
        await self._replay.materialize(updated_replay_state)
        return EventSourcedCommandApplicationResult(
            applied=rejection_reason is None,
            checkpoint=updated_replay_state.checkpoint,
            stored_events=stored_events,
            rejection_reason=rejection_reason,
        )

    def _build_domain_event_drafts(
        self,
        command: OperationCommand,
        checkpoint: OperationCheckpoint,
    ) -> tuple[list[OperationDomainEventDraft], str | None]:
        """Validate one command and build outcome event drafts."""
        accepted = self._accepted_event(command)
        patch_command_types = {
            OperationCommandType.PATCH_OBJECTIVE,
            OperationCommandType.PATCH_HARNESS,
            OperationCommandType.PATCH_SUCCESS_CRITERIA,
        }

        if command.command_type in patch_command_types and checkpoint.status in {
            OperationStatus.COMPLETED,
            OperationStatus.FAILED,
            OperationStatus.CANCELLED,
        }:
            reason = (
                "operation_terminal: operation is already "
                f"{checkpoint.status.value}."
            )
            return [self._rejected_event(command, reason)], reason

        if command.command_type is OperationCommandType.PATCH_OBJECTIVE:
            text = str(command.payload.get("text", "")).strip()
            if not text:
                reason = "invalid_payload: PATCH_OBJECTIVE requires non-empty payload.text."
                return [self._rejected_event(command, reason)], reason
            if checkpoint.objective is None:
                reason = "Operation checkpoint does not contain objective state."
                return [self._rejected_event(command, reason)], reason
            payload = checkpoint.objective.model_copy(
                update={
                    "objective": text,
                    "updated_at": datetime.now(UTC),
                },
                deep=True,
            ).model_dump(mode="json")
            return [
                accepted,
                OperationDomainEventDraft(
                    event_type="objective.updated",
                    payload=payload,
                ),
            ], None

        if command.command_type is OperationCommandType.PATCH_HARNESS:
            text = str(command.payload.get("text", "")).strip()
            if not text:
                reason = "invalid_payload: PATCH_HARNESS requires non-empty payload.text."
                return [self._rejected_event(command, reason)], reason
            if checkpoint.objective is None:
                reason = "Operation checkpoint does not contain objective state."
                return [self._rejected_event(command, reason)], reason
            payload = checkpoint.objective.model_copy(
                update={"harness_instructions": text, "updated_at": datetime.now(UTC)},
                deep=True,
            ).model_dump(mode="json")
            return [
                accepted,
                OperationDomainEventDraft(
                    event_type="objective.updated",
                    payload=payload,
                ),
            ], None

        if command.command_type is OperationCommandType.PATCH_SUCCESS_CRITERIA:
            raw_criteria = command.payload.get("success_criteria", [])
            if not isinstance(raw_criteria, list):
                reason = (
                    "invalid_payload: PATCH_SUCCESS_CRITERIA requires "
                    "payload.success_criteria to be a list."
                )
                return [self._rejected_event(command, reason)], reason
            if checkpoint.objective is None:
                reason = "Operation checkpoint does not contain objective state."
                return [self._rejected_event(command, reason)], reason
            success_criteria = [
                str(item).strip()
                for item in raw_criteria
                if isinstance(item, str) and str(item).strip()
            ]
            payload = checkpoint.objective.model_copy(
                update={"success_criteria": success_criteria, "updated_at": datetime.now(UTC)},
                deep=True,
            ).model_dump(mode="json")
            return [
                accepted,
                OperationDomainEventDraft(
                    event_type="objective.updated",
                    payload=payload,
                ),
            ], None

        if command.command_type is OperationCommandType.INJECT_OPERATOR_MESSAGE:
            text = str(command.payload.get("text", "")).strip()
            if not text:
                reason = "INJECT_OPERATOR_MESSAGE requires non-empty payload.text."
                return [self._rejected_event(command, reason)], reason
            message = OperatorMessage(
                text=text,
                source_command_id=command.command_id,
                applied_at=datetime.now(UTC),
            )
            return [
                accepted,
                OperationDomainEventDraft(
                    event_type="operator_message.received",
                    payload=message.model_dump(mode="json"),
                ),
            ], None

        if command.command_type is OperationCommandType.SET_INVOLVEMENT_LEVEL:
            raw_level = str(command.payload.get("level", "")).strip()
            if not raw_level:
                reason = "SET_INVOLVEMENT_LEVEL requires non-empty payload.level."
                return [self._rejected_event(command, reason)], reason
            try:
                level = InvolvementLevel(raw_level)
            except ValueError:
                reason = f"Unsupported involvement level: {raw_level}."
                return [self._rejected_event(command, reason)], reason
            return [
                accepted,
                OperationDomainEventDraft(
                    event_type="operation.involvement_level.updated",
                    payload={"involvement_level": level.value},
                ),
            ], None

        if command.command_type is OperationCommandType.SET_ALLOWED_AGENTS:
            raw_allowed_agents = command.payload.get("allowed_agents")
            if not isinstance(raw_allowed_agents, list):
                reason = "SET_ALLOWED_AGENTS requires payload.allowed_agents to be a list."
                return [self._rejected_event(command, reason)], reason
            allowed_agents = [
                str(item).strip()
                for item in raw_allowed_agents
                if isinstance(item, str) and str(item).strip()
            ]
            if not allowed_agents:
                reason = "SET_ALLOWED_AGENTS requires non-empty payload.allowed_agents."
                return [self._rejected_event(command, reason)], reason
            return [
                accepted,
                OperationDomainEventDraft(
                    event_type="operation.allowed_agents.updated",
                    payload={"allowed_agents": allowed_agents},
                ),
            ], None

        if command.command_type is OperationCommandType.PAUSE_OPERATOR:
            if checkpoint.scheduler_state in {
                SchedulerState.PAUSED,
                SchedulerState.PAUSE_REQUESTED,
            }:
                reason = f"Operator is already {checkpoint.scheduler_state.value}."
                return [self._rejected_event(command, reason)], reason
            return [
                accepted,
                OperationDomainEventDraft(
                    event_type="scheduler.state.changed",
                    payload={"scheduler_state": SchedulerState.PAUSED.value},
                ),
            ], None

        if command.command_type is OperationCommandType.RESUME_OPERATOR:
            if checkpoint.scheduler_state not in {
                SchedulerState.PAUSED,
                SchedulerState.PAUSE_REQUESTED,
            }:
                reason = "Operator is not paused."
                return [self._rejected_event(command, reason)], reason
            return [
                accepted,
                OperationDomainEventDraft(
                    event_type="scheduler.state.changed",
                    payload={"scheduler_state": SchedulerState.ACTIVE.value},
                ),
            ], None

        reason = f"Unsupported event-sourced command type: {command.command_type.value}."
        return [self._rejected_event(command, reason)], reason

    def _accepted_event(self, command: OperationCommand) -> OperationDomainEventDraft:
        return OperationDomainEventDraft(
            event_type="command.accepted",
            payload={
                "command_id": command.command_id,
                "command_type": command.command_type.value,
                "target_scope": command.target_scope.value,
                "target_id": command.target_id,
                "submitted_by": command.submitted_by,
                "submitted_at": command.submitted_at.isoformat(),
            },
            causation_id=command.command_id,
            correlation_id=command.command_id,
        )

    def _rejected_event(
        self,
        command: OperationCommand,
        reason: str,
    ) -> OperationDomainEventDraft:
        return OperationDomainEventDraft(
            event_type="command.rejected",
            payload={
                "command_id": command.command_id,
                "command_type": command.command_type.value,
                "target_scope": command.target_scope.value,
                "target_id": command.target_id,
                "submitted_by": command.submitted_by,
                "submitted_at": command.submitted_at.isoformat(),
                "rejection_reason": reason,
            },
            causation_id=command.command_id,
            correlation_id=command.command_id,
        )
