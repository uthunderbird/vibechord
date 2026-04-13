from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from agent_operator.domain import (
    AttentionRequest,
    AttentionStatus,
    AttentionType,
    CommandTargetScope,
    ExecutionObservedState,
    ExecutionState,
    InvolvementLevel,
    ObjectiveState,
    OperationCheckpoint,
    OperationStatus,
    OperatorMessage,
    PolicyCoverage,
    PolicyEntry,
    SchedulerState,
    SessionObservedState,
    SessionState,
    SessionTerminalState,
    StoredOperationDomainEvent,
    TaskState,
)


class DefaultOperationProjector:
    """Pure operation projector composed from deterministic reducer slices.

    Supported event families are intentionally narrow in this first slice:
    operation, task, session, execution, attention, scheduler, operator-message,
    and policy applicability updates.

    Examples:
        >>> projector = DefaultOperationProjector()
        >>> checkpoint = OperationCheckpoint.initial("op-1")
        >>> checkpoint.operation_id
        'op-1'
    """

    def apply_event(
        self,
        checkpoint: OperationCheckpoint,
        event: StoredOperationDomainEvent,
    ) -> OperationCheckpoint:
        """Apply one ordered domain event to a checkpoint.

        Args:
            checkpoint: Prior canonical checkpoint.
            event: Stored domain event to fold.

        Returns:
            Updated canonical checkpoint.
        """

        updated = checkpoint.model_copy(deep=True)
        updated = self._apply_operation_slice(updated, event)
        updated = self._apply_task_slice(updated, event)
        updated = self._apply_session_slice(updated, event)
        updated = self._apply_execution_slice(updated, event)
        updated = self._apply_attention_slice(updated, event)
        updated = self._apply_scheduler_slice(updated, event)
        updated = self._apply_operator_message_slice(updated, event)
        updated = self._apply_policy_slice(updated, event)
        updated = self._apply_active_session_slice(updated, event)
        updated.updated_at = event.timestamp
        return updated

    def project(
        self,
        checkpoint: OperationCheckpoint,
        events: list[StoredOperationDomainEvent],
    ) -> OperationCheckpoint:
        """Fold an ordered event suffix into a checkpoint.

        Args:
            checkpoint: Prior canonical checkpoint.
            events: Ordered domain event suffix.

        Returns:
            Updated canonical checkpoint after all folds.
        """

        projected = checkpoint
        for event in events:
            projected = self.apply_event(projected, event)
        return projected

    def _apply_operation_slice(
        self,
        checkpoint: OperationCheckpoint,
        event: StoredOperationDomainEvent,
    ) -> OperationCheckpoint:
        if event.event_type == "operation.created":
            checkpoint.operation_id = event.operation_id
            checkpoint.objective = self._payload_model(event.payload, ObjectiveState)
            raw_allowed_agents = event.payload.get("allowed_agents")
            if isinstance(raw_allowed_agents, list):
                checkpoint.allowed_agents = [
                    str(item).strip()
                    for item in raw_allowed_agents
                    if isinstance(item, str) and str(item).strip()
                ]
            involvement_level = event.payload.get("involvement_level")
            if involvement_level is not None:
                checkpoint.involvement_level = InvolvementLevel(involvement_level)
            checkpoint.created_at = self._payload_datetime(
                event.payload,
                "created_at",
                event.timestamp,
            )
            checkpoint.updated_at = checkpoint.created_at
        elif event.event_type == "operation.status.changed":
            checkpoint.status = OperationStatus(event.payload["status"])
            checkpoint.final_summary = self._payload_optional_string(event.payload, "final_summary")
            if checkpoint.objective is not None and checkpoint.final_summary:
                checkpoint.objective.summary = checkpoint.final_summary
        elif event.event_type == "objective.updated":
            checkpoint.objective = self._payload_model(event.payload, ObjectiveState)
        elif event.event_type == "operation.allowed_agents.updated":
            raw_allowed_agents = event.payload.get("allowed_agents", [])
            checkpoint.allowed_agents = [
                str(item).strip()
                for item in raw_allowed_agents
                if isinstance(item, str) and str(item).strip()
            ]
        elif event.event_type == "operation.involvement_level.updated":
            checkpoint.involvement_level = InvolvementLevel(event.payload["involvement_level"])
        return checkpoint

    def _apply_task_slice(
        self,
        checkpoint: OperationCheckpoint,
        event: StoredOperationDomainEvent,
    ) -> OperationCheckpoint:
        if event.event_type == "task.created":
            checkpoint.tasks.append(self._payload_model(event.payload, TaskState))
        elif event.event_type == "task.updated":
            task = self._find_by_attr(checkpoint.tasks, "task_id", event.payload["task_id"])
            if task is not None:
                if "status" in event.payload:
                    task.status = self._payload_enum(event.payload, "status", type(task.status))
                self._assign_if_present(task, event.payload, "assigned_agent")
                self._assign_if_present(task, event.payload, "linked_session_id")
                task.updated_at = self._payload_datetime(
                    event.payload,
                    "updated_at",
                    event.timestamp,
                )
        return checkpoint

    def _apply_session_slice(
        self,
        checkpoint: OperationCheckpoint,
        event: StoredOperationDomainEvent,
    ) -> OperationCheckpoint:
        if event.event_type == "session.created":
            checkpoint.sessions.append(self._payload_model(event.payload, SessionState))
        elif event.event_type == "session.observed_state.changed":
            session = self._find_by_attr(
                checkpoint.sessions,
                "session_id",
                event.payload["session_id"],
            )
            if session is not None:
                session.observed_state = SessionObservedState(event.payload["observed_state"])
                terminal_state = self._payload_optional_string(event.payload, "terminal_state")
                session.terminal_state = (
                    SessionTerminalState(terminal_state) if terminal_state is not None else None
                )
                self._assign_if_present(session, event.payload, "current_execution_id")
                self._assign_if_present(session, event.payload, "last_terminal_execution_id")
                session.updated_at = self._payload_datetime(
                    event.payload,
                    "updated_at",
                    event.timestamp,
                )
        elif event.event_type == "session.cooldown_cleared":
            session = self._find_by_attr(
                checkpoint.sessions,
                "session_id",
                event.payload["session_id"],
            )
            if session is not None:
                session.cooldown_until = None
                session.cooldown_reason = None
                session.waiting_reason = None
                if session.observed_state is SessionObservedState.WAITING:
                    session.observed_state = SessionObservedState.IDLE
                session.updated_at = self._payload_datetime(
                    event.payload,
                    "updated_at",
                    event.timestamp,
                )
        return checkpoint

    def _apply_execution_slice(
        self,
        checkpoint: OperationCheckpoint,
        event: StoredOperationDomainEvent,
    ) -> OperationCheckpoint:
        if event.event_type == "execution.registered":
            checkpoint.executions.append(self._payload_model(event.payload, ExecutionState))
        elif event.event_type == "execution.session_linked":
            execution_id = event.payload.get("execution_id")
            session_id = event.payload.get("session_id")
            if execution_id is not None and session_id is not None:
                execution = self._find_by_attr(checkpoint.executions, "execution_id", execution_id)
                if execution is not None:
                    execution.session_id = session_id
        elif event.event_type == "execution.observed_state.changed":
            execution = self._find_by_attr(
                checkpoint.executions,
                "execution_id",
                event.payload["execution_id"],
            )
            if execution is not None:
                execution.observed_state = ExecutionObservedState(event.payload["observed_state"])
                execution.waiting_reason = self._payload_optional_string(
                    event.payload,
                    "waiting_reason",
                )
                execution.completed_at = self._payload_optional_datetime(
                    event.payload,
                    "completed_at",
                )
                if execution.session_id is not None:
                    session = self._find_by_attr(
                        checkpoint.sessions,
                        "session_id",
                        execution.session_id,
                    )
                    if session is not None:
                        session.current_execution_id = (
                            execution.execution_id
                            if execution.observed_state
                            not in {
                                ExecutionObservedState.COMPLETED,
                                ExecutionObservedState.FAILED,
                                ExecutionObservedState.CANCELLED,
                                ExecutionObservedState.LOST,
                            }
                            else None
                        )
                        if session.current_execution_id is None:
                            session.last_terminal_execution_id = execution.execution_id
                            if execution.observed_state is ExecutionObservedState.COMPLETED:
                                session.terminal_state = SessionTerminalState.COMPLETED
                                session.observed_state = SessionObservedState.TERMINAL
                            elif execution.observed_state is ExecutionObservedState.FAILED:
                                session.terminal_state = SessionTerminalState.FAILED
                                session.observed_state = SessionObservedState.TERMINAL
                            elif execution.observed_state is ExecutionObservedState.CANCELLED:
                                session.terminal_state = SessionTerminalState.CANCELLED
                                session.observed_state = SessionObservedState.TERMINAL
                        session.updated_at = self._payload_datetime(
                            event.payload,
                            "updated_at",
                            event.timestamp,
                        )
        return checkpoint

    def _apply_attention_slice(
        self,
        checkpoint: OperationCheckpoint,
        event: StoredOperationDomainEvent,
    ) -> OperationCheckpoint:
        if event.event_type == "attention.request.created":
            request = AttentionRequest(
                attention_id=str(event.payload["attention_id"]),
                operation_id=str(event.payload["operation_id"]),
                attention_type=AttentionType(event.payload["attention_type"]),
                target_scope=CommandTargetScope(event.payload.get("target_scope", "operation")),
                target_id=self._payload_optional_string(event.payload, "target_id"),
                title=str(event.payload["title"]),
                question=str(event.payload["question"]),
                context_brief=self._payload_optional_string(event.payload, "context_brief"),
                suggested_options=self._payload_string_list(event.payload, "suggested_options"),
                blocking=bool(event.payload.get("blocking", True)),
                status=AttentionStatus(event.payload.get("status", AttentionStatus.OPEN.value)),
                answer_text=self._payload_optional_string(event.payload, "answer_text"),
                answer_source_command_id=self._payload_optional_string(
                    event.payload,
                    "answer_source_command_id",
                ),
                created_at=self._payload_datetime(event.payload, "created_at", event.timestamp),
                answered_at=self._payload_optional_datetime(event.payload, "answered_at"),
                resolved_at=self._payload_optional_datetime(event.payload, "resolved_at"),
                resolution_summary=self._payload_optional_string(
                    event.payload,
                    "resolution_summary",
                ),
                metadata=self._payload_dict(event.payload, "metadata"),
            )
            checkpoint.attention_requests.append(request)
            if request.blocking and checkpoint.status is OperationStatus.RUNNING:
                checkpoint.status = OperationStatus.NEEDS_HUMAN
        elif event.event_type == "attention.request.answered":
            attention = self._find_by_attr(
                checkpoint.attention_requests,
                "attention_id",
                event.payload["attention_id"],
            )
            if attention is not None:
                attention.status = AttentionStatus(event.payload["status"])
                attention.answer_text = self._payload_optional_string(event.payload, "answer_text")
                attention.answer_source_command_id = self._payload_optional_string(
                    event.payload,
                    "source_command_id",
                )
                attention.answered_at = self._payload_optional_datetime(
                    event.payload,
                    "answered_at",
                )
        elif event.event_type == "attention.request.resolved":
            attention = self._find_by_attr(
                checkpoint.attention_requests,
                "attention_id",
                event.payload["attention_id"],
            )
            if attention is not None:
                attention.status = AttentionStatus(event.payload["status"])
                attention.resolution_summary = self._payload_optional_string(
                    event.payload,
                    "resolution_summary",
                )
                attention.resolved_at = self._payload_optional_datetime(
                    event.payload,
                    "resolved_at",
                )
                blocking_open = any(
                    request.blocking and request.status is AttentionStatus.OPEN
                    for request in checkpoint.attention_requests
                )
                if not blocking_open and checkpoint.status is OperationStatus.NEEDS_HUMAN:
                    checkpoint.status = OperationStatus.RUNNING
        return checkpoint

    def _apply_scheduler_slice(
        self,
        checkpoint: OperationCheckpoint,
        event: StoredOperationDomainEvent,
    ) -> OperationCheckpoint:
        if event.event_type == "scheduler.state.changed":
            checkpoint.scheduler_state = SchedulerState(event.payload["scheduler_state"])
        return checkpoint

    def _apply_operator_message_slice(
        self,
        checkpoint: OperationCheckpoint,
        event: StoredOperationDomainEvent,
    ) -> OperationCheckpoint:
        if event.event_type == "operator_message.received":
            checkpoint.operator_messages.append(self._payload_model(event.payload, OperatorMessage))
            if len(checkpoint.operator_messages) > 50:
                checkpoint.operator_messages = checkpoint.operator_messages[-50:]
        elif event.event_type == "operator_message.dropped_from_context":
            for message in checkpoint.operator_messages:
                if message.message_id == event.payload["message_id"]:
                    message.dropped_from_context = True
                    planning_cycles_active = event.payload.get("planning_cycles_active")
                    if isinstance(planning_cycles_active, int):
                        message.planning_cycles_active = planning_cycles_active
                    break
        return checkpoint

    def _apply_policy_slice(
        self,
        checkpoint: OperationCheckpoint,
        event: StoredOperationDomainEvent,
    ) -> OperationCheckpoint:
        if event.event_type == "policy.coverage.updated":
            checkpoint.policy_coverage = self._payload_model(event.payload, PolicyCoverage)
        elif event.event_type == "policy.active_set.updated":
            checkpoint.active_policies = [
                PolicyEntry.model_validate(item) for item in event.payload["active_policies"]
            ]
        return checkpoint

    def _apply_active_session_slice(
        self,
        checkpoint: OperationCheckpoint,
        event: StoredOperationDomainEvent,
    ) -> OperationCheckpoint:
        if event.event_type == "operation.active_session_updated":
            session_id = event.payload.get("session_id")
            if session_id is None:
                checkpoint.active_session = None
            else:
                session = self._find_by_attr(checkpoint.sessions, "session_id", session_id)
                if session is not None:
                    checkpoint.active_session = session.handle.model_copy()
        return checkpoint

    def _payload_model(self, payload: dict[str, Any], model_type: type[BaseModel]) -> Any:
        return model_type.model_validate(payload)

    def _payload_datetime(
        self,
        payload: dict[str, Any],
        key: str,
        default: datetime,
    ) -> datetime:
        raw = payload.get(key)
        if raw is None:
            return default
        if isinstance(raw, datetime):
            return raw
        return datetime.fromisoformat(str(raw)).astimezone(UTC)

    def _payload_optional_datetime(self, payload: dict[str, Any], key: str) -> datetime | None:
        raw = payload.get(key)
        if raw is None:
            return None
        if isinstance(raw, datetime):
            return raw
        return datetime.fromisoformat(str(raw)).astimezone(UTC)

    def _payload_optional_string(self, payload: dict[str, Any], key: str) -> str | None:
        raw = payload.get(key)
        if raw is None:
            return None
        return str(raw)

    def _payload_string_list(self, payload: dict[str, Any], key: str) -> list[str]:
        raw = payload.get(key)
        if not isinstance(raw, list):
            return []
        return [str(item) for item in raw]

    def _payload_dict(self, payload: dict[str, Any], key: str) -> dict[str, Any]:
        raw = payload.get(key)
        if not isinstance(raw, dict):
            return {}
        return dict(raw)

    def _payload_enum(self, payload: dict[str, Any], key: str, enum_type: type[Any]) -> Any:
        return enum_type(payload[key])

    def _assign_if_present(self, target: Any, payload: dict[str, Any], key: str) -> None:
        if key in payload:
            setattr(target, key, payload[key])

    def _find_by_attr(self, items: list[Any], attr_name: str, attr_value: str) -> Any | None:
        for item in items:
            if getattr(item, attr_name) == attr_value:
                return item
        return None
