"""PolicyExecutor — calls brain and executes decisions, returns domain events (ADR 0195).

Contract: async, calls brain.decide(), executes decision via session manager,
returns PolicyExecutorResult with events and agent_result. Never mutates aggregate.

Brain protocol bridge: OperatorBrain currently takes OperationState (v1). PolicyExecutor
builds a minimal OperationState view from the aggregate for the brain call. This bridge
is removed in Layer 3 when the brain protocol is updated to accept OperationAggregate.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime

from agent_operator.application.drive.process_manager_context import ProcessManagerContext
from agent_operator.domain.aggregate import OperationAggregate
from agent_operator.domain.enums import (
    AgentResultStatus,
    BrainActionType,
    FocusKind,
    FocusMode,
    OperationStatus,
    SessionReusePolicy,
)
from agent_operator.domain.event_sourcing import OperationDomainEventDraft
from agent_operator.domain.operation import OperationState, RunOptions
from agent_operator.domain.read_model import DecisionRecord
from agent_operator.dtos.requests import AgentRunRequest
from agent_operator.protocols import OperatorBrain
from agent_operator.protocols.session_manager import AgentSessionManager


@dataclass
class PolicyExecutorResult:
    """Output of one decide_and_execute() call.

    Mutations are expressed as domain events — the drive loop applies them
    to the aggregate. agent_result carries the turn output (if any).
    """

    events: list[OperationDomainEventDraft] = field(default_factory=list)
    agent_result: object | None = None
    should_break: bool = False
    iteration_index: int = 0
    persisted_event_count: int = 0
    more_actions: bool = False


class PolicyExecutor:
    """Call brain, execute decision, return events.

    Replaces DecisionExecutionService + OperationDriveDecisionExecutorService.
    All state changes are expressed as domain events — no direct aggregate mutation.
    """

    def __init__(
        self,
        *,
        brain: OperatorBrain,
        supervisor: object | None = None,
        session_manager: AgentSessionManager | None = None,
        event_store: object | None = None,
        command_inbox: object | None = None,
        planning_trigger_bus: object | None = None,
    ) -> None:
        self._brain = brain
        self._supervisor = supervisor
        self._session_manager = session_manager
        self._event_store = event_store
        self._command_inbox = command_inbox
        self._planning_trigger_bus = planning_trigger_bus

    async def decide_and_execute(
        self,
        agg: OperationAggregate,
        ctx: ProcessManagerContext,
        options: RunOptions,
        *,
        wake_cycle_id: str,
        append_domain_events: (
            Callable[[list[OperationDomainEventDraft]], Awaitable[None]] | None
        ) = None,
    ) -> PolicyExecutorResult:
        """Call brain.decide_next_action() and execute the returned decision.

        Returns PolicyExecutorResult with events representing all state changes.
        The caller (DriveService) applies events to the aggregate.
        """
        now = datetime.now(UTC)
        result = PolicyExecutorResult(iteration_index=len(agg.tasks))

        async def flush_events() -> None:
            if append_domain_events is None:
                return
            pending = result.events[result.persisted_event_count :]
            if not pending:
                return
            await append_domain_events(pending)
            result.persisted_event_count = len(result.events)

        # Build a minimal OperationState bridge for the brain call (Layer 2 bridge).
        # This is bounded to PolicyExecutor and removed in Layer 3.
        brain_state = self._build_brain_state(agg, ctx)

        decision = await self._brain.decide_next_action(brain_state)
        result.more_actions = decision.more_actions
        ctx.recent_decisions.append(
            DecisionRecord(
                action_type=decision.action_type.value,
                more_actions=decision.more_actions,
                wake_cycle_id=wake_cycle_id,
                timestamp=now,
            )
        )
        ctx.recent_decisions = ctx.recent_decisions[-10:]

        # Record the decision as a domain event
        result.events.append(
            OperationDomainEventDraft(
                event_type="brain.decision.made",
                payload={
                    "action_type": decision.action_type.value,
                    "more_actions": decision.more_actions,
                    "wake_cycle_id": wake_cycle_id,
                    "rationale": decision.rationale,
                    "target_agent": decision.target_agent,
                    "focus_task_id": decision.focus_task_id,
                    "decided_at": now.isoformat(),
                },
            )
        )
        await flush_events()

        # ── Handle terminal decisions ─────────────────────────────────────────

        if decision.action_type is BrainActionType.STOP:
            result.events.append(
                OperationDomainEventDraft(
                    event_type="operation.status.changed",
                    payload={
                        "status": OperationStatus.COMPLETED.value,
                        "final_summary": decision.rationale,
                    },
                )
            )
            result.should_break = True
            return result

        if decision.action_type is BrainActionType.FAIL:
            result.events.append(
                OperationDomainEventDraft(
                    event_type="operation.status.changed",
                    payload={
                        "status": OperationStatus.FAILED.value,
                        "final_summary": decision.rationale,
                    },
                )
            )
            result.should_break = True
            return result

        if decision.action_type is BrainActionType.REQUEST_CLARIFICATION:
            result.events.append(
                OperationDomainEventDraft(
                    event_type="attention.request.created",
                    payload={
                        "request_id": f"attn-{now.timestamp():.0f}",
                        "title": decision.rationale or "Clarification needed",
                        "question": decision.rationale or "",
                        "blocking": True,
                        "created_at": now.isoformat(),
                    },
                )
            )
            result.events.append(
                OperationDomainEventDraft(
                    event_type="operation.status.changed",
                    payload={
                        "status": OperationStatus.NEEDS_HUMAN.value,
                        "final_summary": f"Blocked on attention request: {decision.rationale}.",
                    },
                )
            )
            result.should_break = True
            return result

        if decision.action_type is BrainActionType.APPLY_POLICY:
            return result

        # ── Focus update ──────────────────────────────────────────────────────

        if decision.blocking_focus is not None:
            result.events.append(
                OperationDomainEventDraft(
                    event_type="operation.focus.updated",
                    payload={
                        "focus": {
                            "kind": decision.blocking_focus.kind.value,
                            "target_id": decision.blocking_focus.target_id,
                            "mode": FocusMode.BLOCKING.value,
                            "blocking_reason": decision.blocking_focus.blocking_reason,
                            "interrupt_policy": decision.blocking_focus.interrupt_policy.value,
                            "resume_policy": decision.blocking_focus.resume_policy.value,
                        }
                    },
                )
            )
            await flush_events()
        elif decision.focus_task_id is not None:
            result.events.append(
                OperationDomainEventDraft(
                    event_type="operation.focus.updated",
                    payload={
                        "focus": {
                            "kind": FocusKind.TASK.value,
                            "target_id": decision.focus_task_id,
                            "mode": FocusMode.ADVISORY.value,
                        }
                    },
                )
            )
            await flush_events()

        # ── Agent actions ─────────────────────────────────────────────────────

        if decision.action_type in {
            BrainActionType.START_AGENT,
            BrainActionType.CONTINUE_AGENT,
        }:
            adapter_key = decision.target_agent
            if adapter_key is None:
                result.events.append(
                    OperationDomainEventDraft(
                        event_type="operation.status.changed",
                        payload={
                            "status": OperationStatus.FAILED.value,
                            "final_summary": "Brain requested agent action with no target_agent.",
                        },
                    )
                )
                result.should_break = True
                return result

            if self._session_manager is None:
                # Stub path — no session manager wired (tests / early bootstrap)
                result.events.append(
                    OperationDomainEventDraft(
                        event_type="session.created",
                        payload={
                            "adapter_key": adapter_key,
                            "action_type": decision.action_type.value,
                            "requested_at": now.isoformat(),
                        },
                    )
                )
                return result

            # ── Real session launch ───────────────────────────────────────────
            objective_text = agg.objective.objective if agg.objective else ""
            instruction = decision.instruction or objective_text
            working_dir = ctx.working_directory if hasattr(ctx, "working_directory") else None

            request = AgentRunRequest(
                goal=objective_text,
                instruction=instruction,
                session_name=decision.session_name,
                one_shot=getattr(decision, "one_shot", False),
                session_reuse_policy=SessionReusePolicy.ALWAYS_NEW,
                **({"working_directory": working_dir} if working_dir is not None else {}),
                metadata={
                    "operation_id": agg.operation_id,
                    "adapter_key": adapter_key,
                },
            )

            handle = await self._session_manager.start(adapter_key, request)
            session_id = handle.session_id

            result.events.append(
                OperationDomainEventDraft(
                    event_type="session.created",
                    payload={
                        "handle": handle.model_dump(mode="json"),
                        "adapter_key": adapter_key,
                        "requested_at": now.isoformat(),
                    },
                )
            )
            await flush_events()

            # Register with supervisor if available (ADR 0200)
            if hasattr(self._supervisor, "spawn"):
                pass  # Background spawning handled by DriveService for resumable runs

            try:
                agent_result = await self._session_manager.collect(handle)
            finally:
                with suppress(Exception):
                    await self._session_manager.close(handle)
            result.agent_result = agent_result
            completed_at = datetime.now(UTC)

            turn_status = (
                "completed"
                if agent_result.status is AgentResultStatus.SUCCESS
                else (
                    "interrupted"
                    if agent_result.status is AgentResultStatus.INCOMPLETE
                    else "failed"
                )
            )
            result.events.append(
                OperationDomainEventDraft(
                    event_type="agent.turn.completed",
                    payload={
                        "session_id": session_id,
                        "adapter_key": adapter_key,
                        "status": turn_status,
                        "output_text": agent_result.output_text or "",
                        "completed_at": completed_at.isoformat(),
                    },
                )
            )
            result.events.append(
                OperationDomainEventDraft(
                    event_type="session.observed_state.changed",
                    payload={
                        "session_id": session_id,
                        "observed_state": turn_status,
                        "updated_at": completed_at.isoformat(),
                    },
                )
            )

        return result

    def _build_brain_state(
        self,
        agg: OperationAggregate,
        ctx: ProcessManagerContext,
    ) -> OperationState:
        """Construct a minimal OperationState bridge for the brain protocol.

        This is the Layer 2 bridge — removed in Layer 3 when brain protocol is updated.
        Only fields that brain.decide_next_action() actually reads are populated.
        """
        state = OperationState(
            operation_id=agg.operation_id,
            goal=agg.goal,
            policy=agg.policy,
            execution_budget=agg.execution_budget,
            runtime_hints=agg.runtime_hints,
            execution_profile_overrides=dict(agg.execution_profile_overrides),
            status=agg.status,
            objective=agg.objective,
            tasks=list(agg.tasks),
            features=list(agg.features),
            sessions=list(agg.sessions),
            executions=list(agg.executions),
            artifacts=list(agg.artifacts),
            recent_decisions=list(ctx.recent_decisions),
            memory_entries=list(agg.memory_entries),
            current_focus=agg.current_focus,
            attention_requests=list(agg.attention_requests),
            active_policies=list(agg.active_policies),
            policy_coverage=agg.policy_coverage,
            involvement_level=agg.involvement_level,
            scheduler_state=agg.scheduler_state,
            operator_messages=list(agg.operator_messages),
        )
        return state
