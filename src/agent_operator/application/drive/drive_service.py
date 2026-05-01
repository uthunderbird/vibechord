"""DriveService — v2 operation orchestration loop (ADR 0195).

Owns the while loop, checkpoint writes, and coordination of LifecycleGate,
RuntimeReconciler, and PolicyExecutor. The aggregate is never mutated in-place —
all changes flow through apply_events() which returns a new instance.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from agent_operator.application.drive.lifecycle_gate import LifecycleGate
from agent_operator.application.drive.policy_executor import PolicyExecutor
from agent_operator.application.drive.process_manager_context import (
    ProcessManagerContext,
    build_pm_context,
)
from agent_operator.application.drive.runtime_reconciler import RuntimeReconciler
from agent_operator.domain.aggregate import OperationAggregate
from agent_operator.domain.enums import OperationStatus, SchedulerState
from agent_operator.domain.event_sourcing import (
    OperationDomainEventDraft,
    StoredOperationDomainEvent,
)
from agent_operator.domain.events import RunEvent
from agent_operator.domain.operation import (
    OperationGoal,
    OperationOutcome,
    OperationPolicy,
    OperationState,
    RunOptions,
)
from agent_operator.domain.read_model import DecisionRecord
from agent_operator.protocols import EventSink, OperationEventStore
from agent_operator.protocols.event_sourcing import OperationCheckpointStore

if TYPE_CHECKING:
    from agent_operator.domain.checkpoints import OperationCheckpoint


class HistoryLedger(Protocol):
    async def append(self, state: OperationState, outcome: OperationOutcome) -> None: ...


class ReplayService(Protocol):
    async def load(self, operation_id: str) -> ReplayState: ...


class ReplayState(Protocol):
    checkpoint: OperationCheckpoint
    last_applied_sequence: int
    suffix_events: list[StoredOperationDomainEvent]


class DriveService:
    """v2 drive loop — coordinates LifecycleGate, RuntimeReconciler, PolicyExecutor.

    Replaces OperationDriveService and its 25 mixin services (ADR 0195).
    Not yet called by OperatorService — wired in Layer 4.
    """

    def __init__(
        self,
        *,
        lifecycle_gate: LifecycleGate,
        reconciler: RuntimeReconciler,
        executor: PolicyExecutor,
        event_store: OperationEventStore,
        checkpoint_store: OperationCheckpointStore,
        replay_service: ReplayService,
        policy_store: object | None = None,
        adapter_registry: object | None = None,
        event_sink: EventSink | None = None,
        history_ledger: HistoryLedger | None = None,
        max_cycles: int = 1000,
        max_consecutive_actions: int = 10,
    ) -> None:
        self._gate = lifecycle_gate
        self._reconciler = reconciler
        self._executor = executor
        self._event_store = event_store
        self._checkpoint_store = checkpoint_store
        self._replay_service = replay_service
        self._policy_store = policy_store
        self._adapter_registry = adapter_registry
        self._event_sink = event_sink
        self._history_ledger = history_ledger
        self._max_cycles = max_cycles
        self._max_consecutive_actions = max_consecutive_actions

    async def drive(
        self,
        operation_id: str,
        options: RunOptions,
        *,
        context_ready: Callable[[ProcessManagerContext], None] | None = None,
    ) -> OperationOutcome:
        """Execute the v2 orchestration loop for one operation.

        1. Load aggregate from event log via replay service.
        2. Build ephemeral ProcessManagerContext.
        3. Check pre-run conditions (timeout, budget).
        4. While should_continue: reconcile → apply → decide_and_execute → apply → persist.
        5. Return OperationOutcome.
        """
        # ── Step 1: Load aggregate ────────────────────────────────────────────
        agg, last_sequence, epoch_id, suffix_events = await self._load_aggregate(operation_id)

        # ── Step 2: Build ephemeral context ───────────────────────────────────
        ctx = await self._build_context(agg, suffix_events=suffix_events)
        if context_ready is not None:
            context_ready(ctx)

        cycle_budget = options.max_cycles or self._max_cycles
        cycles_executed = 0
        consecutive_actions = 0
        wake_cycle_id = f"wc-{uuid4()}"

        # ── Step 3: Pre-run timeout check ─────────────────────────────────────
        if self._gate.check_timeout(agg):
            timeout_events = [
                OperationDomainEventDraft(
                    event_type="operation.status.changed",
                    payload={
                        "status": OperationStatus.FAILED.value,
                        "final_summary": (
                            "Time limit of "
                            f"{agg.execution_budget.timeout_seconds} seconds exceeded."
                        ),
                    },
                )
            ]
            stored = await self._event_store.append(operation_id, last_sequence, timeout_events)
            await self._emit_run_events(stored)
            agg = agg.apply_events(stored)
            last_sequence = stored[-1].sequence if stored else last_sequence
            await self._save_checkpoint(agg, last_sequence, epoch_id)
            return self._make_outcome(agg)

        # ── Step 4: Main loop ─────────────────────────────────────────────────
        while self._gate.should_continue(
            agg, ctx=ctx, cycles_executed=cycles_executed, cycle_budget=cycle_budget
        ):
            async def append_live_events(
                drafts: list[OperationDomainEventDraft],
            ) -> None:
                nonlocal agg, last_sequence
                if not drafts:
                    return
                stored_live = await self._event_store.append(operation_id, last_sequence, drafts)
                await self._emit_run_events(stored_live)
                agg = agg.apply_events(stored_live)
                last_sequence = stored_live[-1].sequence if stored_live else last_sequence

            # Materialize PAUSE_REQUESTED → PAUSED when safe
            if self._gate.should_pause_materialize(agg):
                pause_events = [
                    OperationDomainEventDraft(
                        event_type="scheduler.state.changed",
                        payload={"scheduler_state": SchedulerState.PAUSED.value},
                    )
                ]
                stored = await self._event_store.append(operation_id, last_sequence, pause_events)
                await self._emit_run_events(stored)
                agg = agg.apply_events(stored)
                last_sequence = stored[-1].sequence if stored else last_sequence
                break

            # Reconcile inboxes and background runs
            reconcile_drafts = await self._reconciler.reconcile(agg, ctx)
            if reconcile_drafts:
                stored = await self._event_store.append(
                    operation_id, last_sequence, reconcile_drafts
                )
                await self._emit_run_events(stored)
                agg = agg.apply_events(stored)
                last_sequence = stored[-1].sequence if stored else last_sequence
            if ctx.canonical_replay_advanced:
                agg, last_sequence, epoch_id, suffix_events = await self._load_aggregate(
                    operation_id
                )
                ctx.canonical_replay_advanced = False

            # Re-check after reconciliation
            if self._gate.should_break_for_status(agg) and not (
                agg.pending_attention_resolution_ids or agg.pending_replan_command_ids
            ):
                break

            # Execute one brain decision
            executor_result = await self._executor.decide_and_execute(
                agg,
                ctx,
                options,
                wake_cycle_id=wake_cycle_id,
                append_domain_events=append_live_events,
            )
            cycles_executed += 1

            deferred_events = executor_result.events[executor_result.persisted_event_count :]
            if deferred_events:
                stored = await self._event_store.append(
                    operation_id, last_sequence, deferred_events
                )
                await self._emit_run_events(stored)
                agg = agg.apply_events(stored)
                last_sequence = stored[-1].sequence if stored else last_sequence

            if (
                executor_result.more_actions
                and not executor_result.should_break
                and consecutive_actions < self._max_consecutive_actions
            ):
                consecutive_actions += 1
                continue

            consecutive_actions = 0

            # Checkpoint after each iteration
            await self._save_checkpoint(agg, last_sequence, epoch_id)
            wake_cycle_id = f"wc-{uuid4()}"

            if executor_result.should_break:
                break

        if ctx.draining and agg.status is OperationStatus.RUNNING:
            now = datetime.now(UTC)
            drain_events = [
                OperationDomainEventDraft(
                    event_type="operation.parked.updated",
                    payload={
                        "parked_execution": {
                            "kind": "runtime_drained",
                            "fingerprint": f"runtime_drained:{operation_id}",
                            "reason": (
                                "Attached drive call drained before the operation "
                                "reached a terminal state."
                            ),
                            "wake_predicates": ["runtime_reentered", "operator_resumed"],
                            "created_at": now.isoformat(),
                            "last_confirmed_at": now.isoformat(),
                        }
                    },
                )
            ]
            stored = await self._event_store.append(operation_id, last_sequence, drain_events)
            await self._emit_run_events(stored)
            agg = agg.apply_events(stored)
            last_sequence = stored[-1].sequence if stored else last_sequence
            await self._save_checkpoint(agg, last_sequence, epoch_id)

        # ── Step 5: Budget exhaustion check ───────────────────────────────────
        if agg.status is OperationStatus.RUNNING and cycles_executed >= cycle_budget:
            budget_events = [
                OperationDomainEventDraft(
                    event_type="operation.status.changed",
                    payload={
                        "status": OperationStatus.FAILED.value,
                        "final_summary": "Maximum iterations reached.",
                    },
                )
            ]
            stored = await self._event_store.append(operation_id, last_sequence, budget_events)
            await self._emit_run_events(stored)
            agg = agg.apply_events(stored)
            last_sequence = stored[-1].sequence if stored else last_sequence
            await self._save_checkpoint(agg, last_sequence, epoch_id)

        outcome = self._make_outcome(agg)

        if self._history_ledger is not None and agg.status in {
            OperationStatus.COMPLETED,
            OperationStatus.FAILED,
            OperationStatus.CANCELLED,
        }:
            await self._history_ledger.append(self._history_state_from_aggregate(agg), outcome)

        return outcome

    async def _load_aggregate(
        self, operation_id: str
    ) -> tuple[OperationAggregate, int, int, list[StoredOperationDomainEvent]]:
        """Load aggregate via replay service.

        Returns:
            Aggregate, last applied sequence, checkpoint epoch, and replayed suffix events.
        """
        replay_state = await self._replay_service.load(operation_id)
        epoch_id = 0

        # Try epoch-fenced load if checkpoint store supports it
        with suppress(AttributeError, NotImplementedError):
            _checkpoint, epoch_id = await self._checkpoint_store.load(operation_id)

        checkpoint: OperationCheckpoint = replay_state.checkpoint
        agg = self._aggregate_from_checkpoint(checkpoint)
        agg = agg.apply_events(replay_state.suffix_events)
        return agg, replay_state.last_applied_sequence, epoch_id, replay_state.suffix_events

    def _aggregate_from_checkpoint(self, checkpoint: OperationCheckpoint) -> OperationAggregate:
        """Build the drive aggregate from canonical replay checkpoint truth."""
        goal = OperationGoal(
            objective=(
                checkpoint.objective.objective if checkpoint.objective is not None else ""
            ),
            harness_instructions=(
                checkpoint.objective.harness_instructions
                if checkpoint.objective is not None
                else None
            ),
            success_criteria=(
                list(checkpoint.objective.success_criteria)
                if checkpoint.objective is not None
                else []
            ),
            metadata=(
                dict(checkpoint.objective.metadata)
                if checkpoint.objective is not None
                else {}
            ),
            external_ticket=(
                checkpoint.external_ticket.model_copy(deep=True)
                if checkpoint.external_ticket is not None
                else None
            ),
        )
        policy = OperationPolicy(
            allowed_agents=list(checkpoint.allowed_agents),
            involvement_level=checkpoint.involvement_level,
        )
        defaults = OperationAggregate.create(goal)
        return OperationAggregate(
            operation_id=checkpoint.operation_id,
            goal=goal,
            policy=policy,
            execution_budget=defaults.execution_budget,
            runtime_hints=defaults.runtime_hints,
            execution_profile_overrides={
                key: value.model_copy(deep=True)
                for key, value in checkpoint.execution_profile_overrides.items()
            },
            status=checkpoint.status,
            objective=(
                checkpoint.objective.model_copy(deep=True)
                if checkpoint.objective is not None
                else None
            ),
            tasks=[task.model_copy(deep=True) for task in checkpoint.tasks],
            features=[],
            sessions=[session.model_copy(deep=True) for session in checkpoint.sessions],
            executions=[execution.model_copy(deep=True) for execution in checkpoint.executions],
            artifacts=[],
            memory_entries=[],
            permission_events=[dict(event) for event in checkpoint.permission_events],
            external_ticket=(
                checkpoint.external_ticket.model_copy(deep=True)
                if checkpoint.external_ticket is not None
                else None
            ),
            final_summary=checkpoint.final_summary,
            allowed_agents=list(checkpoint.allowed_agents),
            created_at=checkpoint.created_at,
            updated_at=checkpoint.updated_at,
            current_focus=(
                checkpoint.current_focus.model_copy(deep=True)
                if checkpoint.current_focus is not None
                else None
            ),
            parked_execution=(
                checkpoint.parked_execution.model_copy(deep=True)
                if checkpoint.parked_execution is not None
                else None
            ),
            scheduler_state=checkpoint.scheduler_state,
            operator_messages=[
                message.model_copy(deep=True)
                for message in checkpoint.operator_messages
            ],
            attention_requests=[
                request.model_copy(deep=True)
                for request in checkpoint.attention_requests
            ],
            processed_command_ids=list(checkpoint.processed_command_ids),
            pending_replan_command_ids=[],
            pending_attention_resolution_ids=[],
        )

    async def _build_context(
        self,
        agg: OperationAggregate,
        *,
        suffix_events: Sequence[StoredOperationDomainEvent],
    ) -> ProcessManagerContext:
        if self._policy_store is not None and self._adapter_registry is not None:
            ctx = await build_pm_context(
                agg,
                policy_store=self._policy_store,
                adapter_registry=self._adapter_registry,
            )
        else:
            ctx = ProcessManagerContext()
        ctx.recent_decisions = self._recent_decisions_from_events(suffix_events)
        return ctx

    def _recent_decisions_from_events(
        self,
        events: Sequence[StoredOperationDomainEvent],
        *,
        limit: int = 10,
    ) -> list[DecisionRecord]:
        records: list[DecisionRecord] = []
        for event in events:
            if event.event_type != "brain.decision.made":
                continue
            payload = event.payload
            if not isinstance(payload, dict):
                continue
            action_type = payload.get("action_type")
            wake_cycle_id = payload.get("wake_cycle_id")
            if not isinstance(action_type, str) or not isinstance(wake_cycle_id, str):
                continue
            records.append(
                DecisionRecord(
                    action_type=action_type,
                    more_actions=bool(payload.get("more_actions", False)),
                    wake_cycle_id=wake_cycle_id,
                    timestamp=event.timestamp,
                )
            )
        return records[-limit:]

    async def _save_checkpoint(
        self, agg: OperationAggregate, last_sequence: int, epoch_id: int
    ) -> None:
        from agent_operator.domain.event_sourcing import OperationCheckpointRecord
        record = OperationCheckpointRecord(
            operation_id=agg.operation_id,
            checkpoint_payload={"status": agg.status.value, "operation_id": agg.operation_id},
            last_applied_sequence=last_sequence,
            checkpoint_format_version=2,
        )
        try:
            await self._checkpoint_store.save_with_epoch(record, epoch_id=epoch_id)
        except (AttributeError, NotImplementedError):
            await self._checkpoint_store.save(record)

    def _make_outcome(self, agg: OperationAggregate) -> OperationOutcome:
        from agent_operator.domain.operation import OperationOutcome
        return OperationOutcome(
            operation_id=agg.operation_id,
            status=agg.status,
            summary=agg.final_summary or "",
            ended_at=datetime.now(UTC),
        )

    def _history_state_from_aggregate(self, agg: OperationAggregate) -> OperationState:
        return OperationState(
            operation_id=agg.operation_id,
            goal=agg.goal,
            policy=agg.policy,
            execution_budget=agg.execution_budget,
            runtime_hints=agg.runtime_hints,
            execution_profile_overrides=dict(agg.execution_profile_overrides),
            status=agg.status,
            objective=agg.objective,
            tasks=list(agg.tasks),
            sessions=list(agg.sessions),
            executions=list(agg.executions),
            artifacts=list(agg.artifacts),
            memory_entries=list(agg.memory_entries),
            permission_events=[dict(event) for event in agg.permission_events],
            current_focus=agg.current_focus,
            attention_requests=list(agg.attention_requests),
            involvement_level=agg.policy.involvement_level,
            scheduler_state=agg.scheduler_state,
            operator_messages=list(agg.operator_messages),
            final_summary=agg.final_summary,
            created_at=agg.created_at,
            updated_at=agg.updated_at,
            run_started_at=agg.created_at,
        )

    async def _emit_run_events(
        self, stored_events: Sequence[StoredOperationDomainEvent]
    ) -> None:
        if self._event_sink is None:
            return
        for stored in stored_events:
            if not hasattr(stored, "event_type") or not hasattr(stored, "operation_id"):
                continue
            payload = getattr(stored, "payload", {})
            session_id = payload.get("session_id") if isinstance(payload, dict) else None
            task_id = payload.get("task_id") if isinstance(payload, dict) else None
            iteration = payload.get("iteration") if isinstance(payload, dict) else None
            await self._event_sink.emit(
                RunEvent(
                    event_type=stored.event_type,
                    category="domain",
                    operation_id=stored.operation_id,
                    iteration=iteration if isinstance(iteration, int) else 0,
                    task_id=task_id if isinstance(task_id, str) else None,
                    session_id=session_id if isinstance(session_id, str) else None,
                    timestamp=stored.timestamp,
                    payload=payload if isinstance(payload, dict) else {},
                )
            )
