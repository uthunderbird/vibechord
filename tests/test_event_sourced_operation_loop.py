from __future__ import annotations

from dataclasses import dataclass

import pytest

from agent_operator.application import EventSourcedOperationBirthService
from agent_operator.application.event_sourcing.event_sourced_operation_loop import (
    EventSourcedOperationLoopService,
)
from agent_operator.application.process_managers import CodeProcessManagerBuilder
from agent_operator.application.process_signals import ProcessManagerSignal
from agent_operator.domain import (
    OperationCommandType,
    OperationDomainEventDraft,
    OperationGoal,
    OperationPolicy,
    OperationState,
    PlanningTrigger,
    StoredControlIntent,
    StoredFact,
    TechnicalFactDraft,
)
from agent_operator.projectors import DefaultOperationProjector
from agent_operator.runtime import (
    FileFactStore,
    FileOperationCheckpointStore,
    FileOperationEventStore,
)


class StubFactTranslator:
    """Narrow deterministic translator for loop-service tests."""

    async def translate(
        self,
        *,
        checkpoint,
        technical_facts: list[StoredFact],
    ) -> list[OperationDomainEventDraft]:
        drafts: list[OperationDomainEventDraft] = []
        for fact in technical_facts:
            if fact.fact_type != "objective.refresh_requested":
                continue
            objective_payload = dict(checkpoint.checkpoint_payload["objective"])
            objective_payload["objective"] = str(fact.payload["objective"])
            drafts.append(
                OperationDomainEventDraft(
                    event_type="objective.updated",
                    payload=objective_payload,
                    causation_id=fact.fact_id,
                    correlation_id=fact.fact_id,
                )
            )
        return drafts


@dataclass
class MemoryPlanningTriggerBus:
    """In-memory planning-trigger sink for loop-service tests."""

    triggers: list[PlanningTrigger]

    def __init__(self) -> None:
        self.triggers = []

    async def enqueue_planning_trigger(self, trigger: PlanningTrigger) -> StoredControlIntent:
        self.triggers.append(trigger.model_copy(deep=True))
        return StoredControlIntent.for_planning_trigger(trigger)

    async def list_planning_triggers(self, operation_id: str) -> list[PlanningTrigger]:
        return [item for item in self.triggers if item.operation_id == operation_id]

    async def list_pending_planning_triggers(self, operation_id: str) -> list[PlanningTrigger]:
        return await self.list_planning_triggers(operation_id)

    async def mark_planning_trigger_applied(
        self, trigger_id: str, *, applied_at=None
    ) -> PlanningTrigger | None:
        return next((item for item in self.triggers if item.trigger_id == trigger_id), None)

    async def mark_planning_trigger_superseded(
        self,
        trigger_id: str,
        *,
        superseded_by_trigger_id: str | None = None,
    ) -> PlanningTrigger | None:
        return next((item for item in self.triggers if item.trigger_id == trigger_id), None)


@pytest.mark.anyio
async def test_event_sourced_operation_loop_persists_facts_translates_and_materializes_checkpoint(
    tmp_path,
) -> None:
    """Canonical loop persists technical facts and appends translated domain events."""
    operation_id = "op-1"
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    fact_store = FileFactStore(tmp_path / "facts")
    projector = DefaultOperationProjector()
    birth = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    state = OperationState(
        operation_id=operation_id,
        goal=OperationGoal(objective="Initial objective"),
        policy=OperationPolicy(),
    )
    await birth.birth(state)
    service = EventSourcedOperationLoopService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
        fact_store=fact_store,
        translator=StubFactTranslator(),
    )

    result = await service.ingest_technical_facts(
        operation_id=operation_id,
        technical_facts=[
            TechnicalFactDraft(
                fact_type="objective.refresh_requested",
                payload={"objective": "Updated objective"},
                source_fact_ids=["fact-source-1"],
            )
        ],
    )

    assert [fact.fact_type for fact in result.stored_facts] == ["objective.refresh_requested"]
    assert [event.event_type for event in result.stored_events] == ["objective.updated"]
    assert result.checkpoint.objective is not None
    assert result.checkpoint.objective.objective == "Updated objective"
    persisted = await checkpoint_store.load_latest(operation_id)
    assert persisted is not None
    assert persisted.checkpoint_payload["objective"]["objective"] == "Updated objective"


@pytest.mark.anyio
async def test_event_sourced_operation_loop_emits_planning_trigger_from_process_managers(
    tmp_path,
) -> None:
    """Canonical loop emits process-manager follow-ups after checkpoint refresh."""
    operation_id = "op-2"
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    fact_store = FileFactStore(tmp_path / "facts")
    projector = DefaultOperationProjector()
    birth = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    state = OperationState(
        operation_id=operation_id,
        goal=OperationGoal(objective="Initial objective"),
        policy=OperationPolicy(),
    )
    await birth.birth(state)
    bus = MemoryPlanningTriggerBus()
    service = EventSourcedOperationLoopService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
        fact_store=fact_store,
        translator=StubFactTranslator(),
        planning_trigger_bus=bus,
        process_managers=CodeProcessManagerBuilder().build(),
    )

    result = await service.ingest_technical_facts(
        operation_id=operation_id,
        technical_facts=[
            TechnicalFactDraft(
                fact_type="objective.refresh_requested",
                payload={"objective": "Updated objective"},
                source_fact_ids=["fact-source-1"],
            )
        ],
        process_signal=ProcessManagerSignal(
            operation_id=operation_id,
            signal_type="planning_context_changed",
            source_command_id="cmd-1",
            metadata={"reason": OperationCommandType.PATCH_OBJECTIVE.value},
        ),
    )

    assert len(result.planning_triggers) == 1
    assert result.planning_triggers[0].reason == OperationCommandType.PATCH_OBJECTIVE.value
    assert len(bus.triggers) == 1
