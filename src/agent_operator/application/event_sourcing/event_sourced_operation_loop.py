from __future__ import annotations

from dataclasses import dataclass

from agent_operator.application.event_sourcing.event_sourced_replay import EventSourcedReplayService
from agent_operator.application.process_signals import ProcessManagerSignal
from agent_operator.application.queries.operation_state_views import OperationStateViewService
from agent_operator.domain import (
    OperationCheckpointRecord,
    OperationState,
    PlanningTrigger,
    StoredFact,
    TechnicalFactDraft,
)
from agent_operator.protocols import (
    FactStore,
    FactTranslator,
    OperationCheckpointStore,
    OperationEventStore,
    OperationProjector,
    PlanningTriggerBus,
    ProcessManager,
)


@dataclass(slots=True)
class EventSourcedOperationLoopResult:
    """Result of one canonical technical-fact ingestion pass.

    Attributes:
        checkpoint: Canonical checkpoint after replay, translation, append, and materialization.
        stored_facts: Persisted technical facts ingested in this pass.
        stored_events: Persisted domain events emitted in this pass.
        planning_triggers: Planning triggers enqueued from process-manager reactions.
    """

    checkpoint: object
    stored_facts: list[StoredFact]
    stored_events: list
    planning_triggers: list[PlanningTrigger]


class EventSourcedOperationLoopService:
    """Canonical loop authority for technical-fact ingestion in one operation.

    This service owns the event-sourced orchestration path for:
    replay, technical-fact persistence, deterministic translation, canonical domain-event append,
    checkpoint materialization, and process-manager follow-up emission.

    Examples:
        >>> service = EventSourcedOperationLoopService(  # doctest: +SKIP
        ...     event_store=None,
        ...     checkpoint_store=None,
        ...     projector=None,
        ...     fact_store=None,
        ...     translator=None,
        ... )
    """

    def __init__(
        self,
        *,
        event_store: OperationEventStore,
        checkpoint_store: OperationCheckpointStore,
        projector: OperationProjector,
        fact_store: FactStore,
        translator: FactTranslator,
        planning_trigger_bus: PlanningTriggerBus | None = None,
        process_managers: list[ProcessManager] | None = None,
    ) -> None:
        self._event_store = event_store
        self._replay = EventSourcedReplayService(
            event_store=event_store,
            checkpoint_store=checkpoint_store,
            projector=projector,
        )
        self._fact_store = fact_store
        self._translator = translator
        self._planning_trigger_bus = planning_trigger_bus
        self._process_managers = process_managers or []
        self._state_views = OperationStateViewService()

    async def ingest_technical_facts(
        self,
        *,
        operation_id: str,
        technical_facts: list[TechnicalFactDraft],
        process_signal: ProcessManagerSignal | None = None,
    ) -> EventSourcedOperationLoopResult:
        """Run one canonical ingestion pass for technical facts.

        Args:
            operation_id: Owning operation identifier.
            technical_facts: Technical facts to persist and translate.
            process_signal: Optional signal that should be forwarded into process managers after
                canonical append and checkpoint refresh.

        Returns:
            Result of the canonical ingestion pass.
        """
        replay_state = await self._replay.load(operation_id)
        fact_sequence = await self._fact_store.load_last_sequence(operation_id)
        stored_facts = await self._fact_store.append_technical_facts(
            operation_id,
            fact_sequence,
            technical_facts,
        )
        checkpoint_record = OperationCheckpointRecord(
            operation_id=operation_id,
            checkpoint_payload=replay_state.checkpoint.model_dump(mode="json"),
            last_applied_sequence=replay_state.last_applied_sequence,
            checkpoint_format_version=1,
        )
        event_drafts = await self._translator.translate(
            checkpoint=checkpoint_record,
            technical_facts=stored_facts,
        )
        stored_events = await self._event_store.append(
            operation_id,
            replay_state.last_applied_sequence,
            event_drafts,
        )
        updated_replay_state = self._replay.advance(replay_state, stored_events)
        await self._replay.materialize(updated_replay_state)
        if stored_facts:
            await self._fact_store.mark_translated_through(
                operation_id,
                max(fact.sequence for fact in stored_facts),
            )
        planning_triggers = await self._dispatch_process_managers(
            signal=process_signal,
            state=self._checkpoint_to_operation_state(updated_replay_state.checkpoint),
        )
        return EventSourcedOperationLoopResult(
            checkpoint=updated_replay_state.checkpoint,
            stored_facts=stored_facts,
            stored_events=stored_events,
            planning_triggers=planning_triggers,
        )

    async def _dispatch_process_managers(
        self,
        *,
        signal: ProcessManagerSignal | None,
        state: OperationState,
    ) -> list[PlanningTrigger]:
        if signal is None or self._planning_trigger_bus is None or not self._process_managers:
            return []
        applied: list[PlanningTrigger] = []
        for manager in self._process_managers:
            triggers = await manager.react(signal, state)
            for trigger in triggers:
                await self._planning_trigger_bus.enqueue_planning_trigger(trigger)
                applied.append(trigger)
        return applied

    def _checkpoint_to_operation_state(self, checkpoint: object) -> OperationState:
        return self._state_views.from_checkpoint(checkpoint)
