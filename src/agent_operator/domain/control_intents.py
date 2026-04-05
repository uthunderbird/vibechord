from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from agent_operator.domain.control import OperationCommand
from agent_operator.domain.enums import ControlIntentKind, ControlIntentStatus


class PlanningTrigger(BaseModel):
    """Durable internal intent requesting a new planning cycle.

    Attributes:
        trigger_id: Stable trigger identifier.
        operation_id: Owning operation identifier.
        reason: Control-plane-safe trigger reason.
        source_kind: Kind of upstream cause.
        source_id: Upstream cause identifier.
        source_event_type: Optional upstream event or signal type.
        task_id: Optional linked task identifier.
        session_id: Optional linked session identifier.
        execution_id: Optional linked execution identifier.
        dedupe_key: Coalescing key for equivalent triggers.
        submitted_at: Trigger creation timestamp.

    Examples:
        >>> trigger = PlanningTrigger(
        ...     operation_id="op-1",
        ...     reason="objective_updated",
        ...     source_kind="command",
        ...     source_id="cmd-1",
        ...     dedupe_key="planning:op-1",
        ... )
        >>> trigger.reason
        'objective_updated'
    """

    trigger_id: str = Field(default_factory=lambda: str(uuid4()))
    operation_id: str
    reason: str
    source_kind: Literal["command", "signal", "event", "runtime"]
    source_id: str
    source_event_type: str | None = None
    task_id: str | None = None
    session_id: str | None = None
    execution_id: str | None = None
    dedupe_key: str | None = None
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _validate_reason(self) -> PlanningTrigger:
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("PlanningTrigger.reason must not be empty.")
        return self


class StoredControlIntent(BaseModel):
    """Durable envelope for user commands and internal planning triggers.

    Attributes:
        intent_id: Stable envelope identifier.
        operation_id: Owning operation identifier.
        intent_kind: Envelope kind discriminator.
        status: Intent lifecycle status.
        submitted_at: Envelope creation timestamp.
        command: User command payload when `intent_kind=user_command`.
        planning_trigger: Internal planning trigger payload when
            `intent_kind=planning_trigger`.
        rejection_reason: Optional rejection reason.
        applied_at: Optional application timestamp.
        superseded_at: Optional supersession timestamp.
        superseded_by_intent_id: Optional superseding envelope identifier.

    Examples:
        >>> command = OperationCommand(
        ...     operation_id="op-1",
        ...     command_type="pause_operator",
        ...     target_scope="operation",
        ... )
        >>> record = StoredControlIntent.for_command(command)
        >>> record.intent_kind
        <ControlIntentKind.USER_COMMAND: 'user_command'>
    """

    intent_id: str = Field(default_factory=lambda: str(uuid4()))
    operation_id: str
    intent_kind: ControlIntentKind
    status: ControlIntentStatus = ControlIntentStatus.PENDING
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    command: OperationCommand | None = None
    planning_trigger: PlanningTrigger | None = None
    rejection_reason: str | None = None
    applied_at: datetime | None = None
    superseded_at: datetime | None = None
    superseded_by_intent_id: str | None = None

    @classmethod
    def for_command(cls, command: OperationCommand) -> StoredControlIntent:
        return cls(
            intent_id=command.command_id,
            operation_id=command.operation_id,
            intent_kind=ControlIntentKind.USER_COMMAND,
            submitted_at=command.submitted_at,
            command=command,
        )

    @classmethod
    def for_planning_trigger(cls, trigger: PlanningTrigger) -> StoredControlIntent:
        return cls(
            intent_id=trigger.trigger_id,
            operation_id=trigger.operation_id,
            intent_kind=ControlIntentKind.PLANNING_TRIGGER,
            submitted_at=trigger.submitted_at,
            planning_trigger=trigger,
        )

    @model_validator(mode="after")
    def _validate_payload(self) -> StoredControlIntent:
        if (
            self.intent_kind is ControlIntentKind.USER_COMMAND
            and (self.command is None or self.planning_trigger is not None)
        ):
            raise ValueError("User-command intent must contain exactly one command payload.")
        if (
            self.intent_kind is ControlIntentKind.PLANNING_TRIGGER
            and (self.planning_trigger is None or self.command is not None)
        ):
            raise ValueError(
                "Planning-trigger intent must contain exactly one planning trigger payload."
            )
        return self
