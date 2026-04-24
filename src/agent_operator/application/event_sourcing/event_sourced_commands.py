from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from agent_operator.application.event_sourcing.event_sourced_replay import EventSourcedReplayService
from agent_operator.domain import (
    AttentionRequest,
    CommandTargetScope,
    ExecutionProfileOverride,
    InvolvementLevel,
    OperationCheckpoint,
    OperationCommand,
    OperationCommandType,
    OperationDomainEventDraft,
    OperationState,
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

    async def append_domain_events(
        self,
        operation_id: str,
        drafts: list[OperationDomainEventDraft],
    ) -> EventSourcedCommandApplicationResult:
        """Append prevalidated domain events through the canonical replay path."""
        replay_state = await self._replay.load(operation_id)
        stored_events = await self._event_store.append(
            operation_id,
            replay_state.last_applied_sequence,
            drafts,
        )
        updated_replay_state = self._replay.advance(replay_state, stored_events)
        await self._replay.materialize(updated_replay_state)
        return EventSourcedCommandApplicationResult(
            applied=True,
            checkpoint=updated_replay_state.checkpoint,
            stored_events=stored_events,
            rejection_reason=None,
        )

    async def seed_attention_request_from_state(
        self,
        state: OperationState,
        attention: AttentionRequest,
    ) -> OperationCheckpoint:
        """Seed one snapshot-era attention request into canonical event-sourced state."""
        replay_state = await self._replay.load(state.operation_id)
        checkpoint = replay_state.checkpoint
        existing_attention = next(
            (
                item
                for item in checkpoint.attention_requests
                if item.attention_id == attention.attention_id
            ),
            None,
        )
        drafts: list[OperationDomainEventDraft] = []
        if (
            attention.blocking
            and state.status is OperationStatus.NEEDS_HUMAN
            and checkpoint.status is not OperationStatus.NEEDS_HUMAN
        ):
            drafts.append(
                OperationDomainEventDraft(
                    event_type="operation.status.changed",
                    payload={"status": OperationStatus.NEEDS_HUMAN.value},
                )
            )
        if existing_attention is None:
            drafts.append(
                OperationDomainEventDraft(
                    event_type="attention.request.created",
                    payload=attention.model_dump(mode="json"),
                )
            )
        if not drafts:
            return checkpoint
        stored_events = await self._event_store.append(
            state.operation_id,
            replay_state.last_applied_sequence,
            drafts,
        )
        updated_replay_state = self._replay.advance(replay_state, stored_events)
        await self._replay.materialize(updated_replay_state)
        return updated_replay_state.checkpoint

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

        if command.command_type is OperationCommandType.STOP_OPERATION:
            if command.target_scope is not CommandTargetScope.OPERATION:
                reason = "STOP_OPERATION requires operation target scope."
                return [self._rejected_event(command, reason)], reason
            if command.target_id not in {"", checkpoint.operation_id}:
                reason = "STOP_OPERATION target does not match the current operation."
                return [self._rejected_event(command, reason)], reason
            if checkpoint.status in {
                OperationStatus.COMPLETED,
                OperationStatus.FAILED,
                OperationStatus.CANCELLED,
            }:
                reason = (
                    "operation_terminal: operation is already "
                    f"{checkpoint.status.value}."
                )
                return [self._rejected_event(command, reason)], reason
            summary = str(command.payload.get("reason", "")).strip()
            final_summary = (
                f"Operation cancelled: {summary}." if summary else "Operation cancelled."
            )
            return [
                accepted,
                OperationDomainEventDraft(
                    event_type="operation.status.changed",
                    payload={
                        "status": OperationStatus.CANCELLED.value,
                        "final_summary": final_summary,
                    },
                ),
                OperationDomainEventDraft(
                    event_type="operation.focus.updated",
                    payload={"focus": None},
                ),
                OperationDomainEventDraft(
                    event_type="scheduler.state.changed",
                    payload={"scheduler_state": SchedulerState.ACTIVE.value},
                ),
            ], None

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

        if command.command_type is OperationCommandType.ANSWER_ATTENTION_REQUEST:
            if command.target_scope is not CommandTargetScope.ATTENTION_REQUEST:
                reason = (
                    "ANSWER_ATTENTION_REQUEST requires attention_request target scope."
                )
                return [self._rejected_event(command, reason)], reason
            attention_id = command.target_id
            attention = next(
                (
                    item
                    for item in checkpoint.attention_requests
                    if item.attention_id == attention_id
                ),
                None,
            )
            if attention is None:
                reason = "Target attention request was not found."
                return [self._rejected_event(command, reason)], reason
            if attention.status.value != "open":
                reason = "Target attention request is not open."
                return [self._rejected_event(command, reason)], reason
            text = str(command.payload.get("text", "")).strip()
            if not text:
                reason = "ANSWER_ATTENTION_REQUEST requires non-empty payload.text."
                return [self._rejected_event(command, reason)], reason
            answered_at = datetime.now(UTC)
            events = [
                accepted,
                OperationDomainEventDraft(
                    event_type="attention.request.answered",
                    payload={
                        "attention_id": attention.attention_id,
                        "attention_type": attention.attention_type.value,
                        "status": "answered",
                        "answer_text": text,
                        "source_command_id": command.command_id,
                        "answered_at": answered_at.isoformat(),
                    },
                ),
            ]
            remaining_blocking_open = any(
                item.blocking
                and item.status.value == "open"
                and item.attention_id != attention.attention_id
                for item in checkpoint.attention_requests
            )
            if (
                attention.blocking
                and checkpoint.status is OperationStatus.NEEDS_HUMAN
                and not remaining_blocking_open
            ):
                events.append(
                    OperationDomainEventDraft(
                        event_type="operation.status.changed",
                        payload={"status": OperationStatus.RUNNING.value},
                    )
                )
            return events, None

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

        if command.command_type is OperationCommandType.SET_EXECUTION_PROFILE:
            adapter_key = str(command.payload.get("adapter_key", "")).strip()
            model = str(command.payload.get("model", "")).strip()
            effort = command.payload.get("effort")
            if not adapter_key:
                reason = "SET_EXECUTION_PROFILE requires non-empty payload.adapter_key."
                return [self._rejected_event(command, reason)], reason
            if not model:
                reason = "SET_EXECUTION_PROFILE requires non-empty payload.model."
                return [self._rejected_event(command, reason)], reason
            if effort is not None and (not isinstance(effort, str) or not effort.strip()):
                reason = "SET_EXECUTION_PROFILE payload.effort must be a non-empty string."
                return [self._rejected_event(command, reason)], reason
            payload = ExecutionProfileOverride(
                adapter_key=adapter_key,
                model=model,
                reasoning_effort=(
                    effort.strip()
                    if adapter_key == "codex_acp" and isinstance(effort, str)
                    else None
                ),
                effort=(
                    effort.strip()
                    if adapter_key == "claude_acp" and isinstance(effort, str)
                    else None
                ),
            ).model_dump(mode="json")
            return [
                accepted,
                OperationDomainEventDraft(
                    event_type="operation.execution_profile.updated",
                    payload=payload,
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
