"""OperationReadModelProjector — builds OperationReadModel from event stream (ADR 0193).

v2-native query entry point: no OperationState dependency.
"""
from __future__ import annotations

from datetime import UTC, datetime

from agent_operator.domain import StoredOperationDomainEvent
from agent_operator.domain.enums import OperationStatus, SchedulerState
from agent_operator.domain.read_model import DecisionRecord, OperationReadModel
from agent_operator.domain.traceability import AgentTurnBrief, IterationBrief, OperationBrief


class OperationReadModelProjector:
    """Build OperationReadModel from a stored event stream.

    Called by DriveService after each iteration to keep the read model current.
    Not persisted — always reconstructible from events.
    """

    def project(
        self,
        operation_id: str,
        events: list[StoredOperationDomainEvent],
    ) -> OperationReadModel:
        read_model = OperationReadModel.empty(operation_id)
        for event in events:
            read_model = self._apply_one(read_model, event)
        return read_model

    def _apply_one(
        self,
        model: OperationReadModel,
        event: StoredOperationDomainEvent,
    ) -> OperationReadModel:
        payload = event.payload
        timestamp = event.timestamp or datetime.now(UTC)

        if event.event_type == "operation.created":
            objective_brief = ""
            objective = payload.get("objective")
            if isinstance(objective, str):
                objective_brief = objective
            elif isinstance(objective, dict):
                nested_objective = objective.get("objective")
                if isinstance(nested_objective, str):
                    objective_brief = nested_objective

            brief = OperationBrief(
                operation_id=model.operation_id,
                status=OperationStatus.RUNNING,
                scheduler_state=SchedulerState.ACTIVE,
                objective_brief=objective_brief,
                updated_at=timestamp,
            )
            return OperationReadModel(
                operation_id=model.operation_id,
                operation_brief=brief,
                iteration_briefs=model.iteration_briefs,
                decision_records=model.decision_records,
                agent_turn_briefs=model.agent_turn_briefs,
            )

        if event.event_type == "brain.decision.made":
            record = DecisionRecord(
                action_type=payload.get("action_type", ""),
                more_actions=bool(payload.get("more_actions", False)),
                wake_cycle_id=payload.get("wake_cycle_id", ""),
                timestamp=timestamp,
            )
            iteration = IterationBrief(
                iteration=len(model.iteration_briefs) + 1,
                task_id=payload.get("task_id"),
                session_id=payload.get("session_id"),
                operator_intent_brief=payload.get("rationale") or payload.get("action_type", ""),
                assignment_brief=payload.get("target_agent"),
                status_brief=payload.get("action_type", ""),
                created_at=timestamp,
            )
            return OperationReadModel(
                operation_id=model.operation_id,
                operation_brief=model.operation_brief,
                iteration_briefs=[*model.iteration_briefs, iteration],
                decision_records=[*model.decision_records, record],
                agent_turn_briefs=model.agent_turn_briefs,
            )

        if event.event_type == "agent.turn.completed":
            iteration = len(model.agent_turn_briefs) + 1
            brief = AgentTurnBrief(
                operation_id=model.operation_id,
                iteration=iteration,
                agent_key=payload.get("adapter_key", ""),
                session_id=payload.get("session_id", ""),
                assignment_brief=payload.get("assignment_brief")
                or payload.get("adapter_key", ""),
                result_brief=payload.get("output_text"),
                status=payload.get("status", ""),
                created_at=timestamp,
            )
            return OperationReadModel(
                operation_id=model.operation_id,
                operation_brief=model.operation_brief,
                iteration_briefs=model.iteration_briefs,
                decision_records=model.decision_records,
                agent_turn_briefs=[*model.agent_turn_briefs, brief],
            )

        if event.event_type == "operation.status.changed" and model.operation_brief is not None:
            status_raw = payload.get("status")
            if isinstance(status_raw, str):
                status = OperationStatus(status_raw)
            else:
                status = model.operation_brief.status
            brief = model.operation_brief.model_copy(
                update={
                    "status": status,
                    "latest_outcome_brief": payload.get("final_summary"),
                    "updated_at": timestamp,
                }
            )
            return OperationReadModel(
                operation_id=model.operation_id,
                operation_brief=brief,
                iteration_briefs=model.iteration_briefs,
                decision_records=model.decision_records,
                agent_turn_briefs=model.agent_turn_briefs,
            )

        # All other event types are noop for now
        return model
