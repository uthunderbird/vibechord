"""PolicyExecutor — calls brain and executes decisions, returns domain events (ADR 0195).

Contract: async, calls brain.decide(), executes decision via session manager,
returns PolicyExecutorResult with events and agent_result. Never mutates aggregate.

Brain protocol bridge: OperatorBrain currently takes OperationState (v1). PolicyExecutor
builds a minimal OperationState view from the aggregate for the brain call. This bridge
is removed in Layer 3 when the brain protocol is updated to accept OperationAggregate.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime

from agent_operator.application.commands.operation_attention import OperationAttentionCoordinator
from agent_operator.application.drive.process_manager_context import ProcessManagerContext
from agent_operator.domain import AgentResult, AgentSessionHandle, TechnicalFactDraft
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
from agent_operator.domain.execution_profiles import execution_profile_request_metadata
from agent_operator.domain.operation import OperationState, RunOptions
from agent_operator.domain.policy import PolicyCoverage
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
    persisted_fact_count: int = 0
    more_actions: bool = False
    technical_facts: list[TechnicalFactDraft] = field(default_factory=list)


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
        attention_coordinator: OperationAttentionCoordinator | None = None,
    ) -> None:
        self._brain = brain
        self._supervisor = supervisor
        self._session_manager = session_manager
        self._event_store = event_store
        self._command_inbox = command_inbox
        self._planning_trigger_bus = planning_trigger_bus
        self._attention_coordinator = attention_coordinator or OperationAttentionCoordinator()

    async def decide_and_execute(
        self,
        agg: OperationAggregate,
        ctx: ProcessManagerContext,
        options: RunOptions,
        *,
        wake_cycle_id: str,
        append_domain_events: (
            Callable[
                [list[OperationDomainEventDraft], list[TechnicalFactDraft]],
                Awaitable[None],
            ]
            | None
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
            pending_facts = result.technical_facts[result.persisted_fact_count :]
            await append_domain_events(pending, pending_facts)
            result.persisted_event_count = len(result.events)
            result.persisted_fact_count = len(result.technical_facts)

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

        if decision.action_type is BrainActionType.WAIT_FOR_MATERIAL_CHANGE:
            barrier_kind = (
                decision.blocking_focus.kind.value
                if decision.blocking_focus is not None
                else "unknown"
            )
            related_task_id = decision.focus_task_id
            fingerprint = (
                f"{barrier_kind}:{related_task_id or '-'}:"
                f"{decision.target_agent or '-'}:{decision.rationale}"
            )
            wake_predicates = decision.metadata.get("wake_predicates")
            if not isinstance(wake_predicates, list):
                wake_predicates = []
            result.events.append(
                OperationDomainEventDraft(
                    event_type="operation.parked.updated",
                    payload={
                        "parked_execution": {
                            "kind": barrier_kind,
                            "fingerprint": fingerprint,
                            "reason": decision.rationale,
                            "wake_predicates": [
                                str(item) for item in wake_predicates if isinstance(item, str)
                            ],
                            "related_task_id": related_task_id,
                            "related_agent": decision.target_agent,
                            "created_at": now.isoformat(),
                            "last_confirmed_at": now.isoformat(),
                        }
                    },
                )
            )
            await flush_events()
            result.should_break = True
            return result

        if decision.action_type is BrainActionType.APPLY_POLICY:
            if decision.blocking_focus is not None:
                result.should_break = True
            return result

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
                    **execution_profile_request_metadata(
                        goal_metadata=agg.goal.metadata,
                        execution_profile_overrides=agg.execution_profile_overrides,
                        adapter_key=adapter_key,
                    ),
                    "operation_id": agg.operation_id,
                    "adapter_key": adapter_key,
                },
            )

            handle = await self._session_manager.start(adapter_key, request)
            session_id = handle.session_id

            result.technical_facts.append(
                TechnicalFactDraft(
                    fact_type="session.started",
                    payload={
                        "session_id": session_id,
                        "adapter_key": adapter_key,
                        "handle": handle.model_dump(mode="json"),
                        "requested_at": now.isoformat(),
                    },
                    observed_at=now,
                    session_id=session_id,
                )
            )
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

            agent_result = await self._session_manager.collect(handle)
            result.agent_result = agent_result
            completed_at = datetime.now(UTC)

            turn_status = self._turn_status_from_agent_result(agent_result.status)
            result.technical_facts.append(
                TechnicalFactDraft(
                    fact_type=self._terminal_fact_type_from_agent_result(agent_result.status),
                    payload={
                        "session_id": session_id,
                        "adapter_key": adapter_key,
                        "status": turn_status,
                        "output_text": agent_result.output_text or "",
                        "completed_at": completed_at.isoformat(),
                    },
                    observed_at=completed_at,
                    session_id=session_id,
                )
            )
            result.events.append(
                OperationDomainEventDraft(
                    event_type="agent.turn.completed",
                    payload={
                        "iteration": result.iteration_index,
                        "task_id": decision.focus_task_id,
                        "session_id": session_id,
                        "adapter_key": adapter_key,
                        "status": turn_status,
                        "output_text": agent_result.output_text or "",
                        "completed_at": completed_at.isoformat(),
                    },
                )
            )
            attention_event = self._attention_event_from_agent_result(
                agg=agg,
                ctx=ctx,
                session_handle=handle,
                agent_result=agent_result,
            )
            result.events.extend(
                self._permission_events_from_agent_result(
                    session_handle=handle,
                    agent_result=agent_result,
                    completed_at=completed_at,
                    involvement_level=agg.policy.involvement_level.value,
                    attention_event=attention_event,
                )
            )
            result.technical_facts.extend(
                self._permission_facts_from_events(
                    result.events,
                    session_id=session_id,
                    completed_at=completed_at,
                )
            )
            if attention_event is not None:
                result.events.append(attention_event)
            result.events.append(
                OperationDomainEventDraft(
                    event_type="session.observed_state.changed",
                    payload={
                        "iteration": result.iteration_index,
                        "task_id": decision.focus_task_id,
                        "session_id": session_id,
                        **self._session_observed_state_payload(agent_result.status),
                        "updated_at": completed_at.isoformat(),
                    },
                )
            )
            if (
                decision.one_shot
                and agent_result.status is AgentResultStatus.SUCCESS
                and not decision.more_actions
            ):
                result.events.append(
                    OperationDomainEventDraft(
                        event_type="operation.status.changed",
                        payload={
                            "status": OperationStatus.COMPLETED.value,
                            "final_summary": (
                                agent_result.output_text or "One-shot agent turn completed."
                            ),
                        },
                    )
                )
                result.should_break = True
            self._close_session_nonblocking(handle)

        return result

    def _close_session_nonblocking(self, handle: AgentSessionHandle) -> None:
        session_manager = self._session_manager
        if session_manager is None:
            return

        async def _close() -> None:
            with suppress(Exception):
                await session_manager.close(handle)

        asyncio.create_task(_close())

    def _session_observed_state_payload(
        self,
        status: AgentResultStatus,
    ) -> dict[str, str]:
        if status is AgentResultStatus.SUCCESS:
            return {"status": "completed"}
        if status is AgentResultStatus.CANCELLED:
            return {"status": "cancelled"}
        if status is AgentResultStatus.DISCONNECTED:
            return {"status": "disconnected"}
        if status is AgentResultStatus.INCOMPLETE:
            return {"status": "waiting"}
        return {"status": "failed"}

    def _turn_status_from_agent_result(self, status: AgentResultStatus) -> str:
        if status is AgentResultStatus.SUCCESS:
            return "completed"
        if status is AgentResultStatus.CANCELLED:
            return "cancelled"
        if status is AgentResultStatus.DISCONNECTED:
            return "disconnected"
        if status is AgentResultStatus.INCOMPLETE:
            return "interrupted"
        return "failed"

    def _terminal_fact_type_from_agent_result(self, status: AgentResultStatus) -> str:
        if status is AgentResultStatus.SUCCESS:
            return "session.completed"
        if status is AgentResultStatus.CANCELLED:
            return "session.cancelled"
        if status is AgentResultStatus.DISCONNECTED:
            return "session.discontinuity_observed"
        if status is AgentResultStatus.INCOMPLETE:
            return "session.waiting_input_observed"
        return "session.failed"

    def _permission_facts_from_events(
        self,
        events: list[OperationDomainEventDraft],
        *,
        session_id: str,
        completed_at: datetime,
    ) -> list[TechnicalFactDraft]:
        facts: list[TechnicalFactDraft] = []
        for event in events:
            if not event.event_type.startswith("permission.request."):
                continue
            facts.append(
                TechnicalFactDraft(
                    fact_type=event.event_type,
                    payload=dict(event.payload),
                    observed_at=completed_at,
                    session_id=session_id,
                )
            )
        return facts

    def _permission_events_from_agent_result(
        self,
        *,
        session_handle: AgentSessionHandle,
        agent_result: AgentResult,
        completed_at: datetime,
        involvement_level: str,
        attention_event: OperationDomainEventDraft | None,
    ) -> list[OperationDomainEventDraft]:
        raw_result = agent_result.raw if isinstance(agent_result.raw, dict) else {}
        linked_attention_id = self._linked_attention_id(attention_event)
        raw_permission_events = raw_result.get("permission_events")
        if isinstance(raw_permission_events, list):
            events: list[OperationDomainEventDraft] = []
            for event in raw_permission_events:
                if not isinstance(event, dict) or not isinstance(event.get("event_type"), str):
                    continue
                event_type = str(event["event_type"])
                payload = {
                    key: value
                    for key, value in dict(event).items()
                    if key != "event_type"
                }
                if event_type == "permission.request.escalated":
                    payload.setdefault("involvement_level", involvement_level)
                    if linked_attention_id is not None:
                        payload.setdefault("linked_attention_id", linked_attention_id)
                events.append(
                    OperationDomainEventDraft(
                        event_type=event_type,
                        payload=payload,
                    )
                )
            return events
        if agent_result.status is not AgentResultStatus.INCOMPLETE:
            return []
        if agent_result.error is None or not isinstance(agent_result.error.raw, dict):
            return []
        raw = agent_result.error.raw
        if raw.get("kind") != "permission_escalation":
            return []
        request = raw.get("request")
        signature = raw.get("signature")
        observed_payload = {
            "adapter_key": session_handle.adapter_key,
            "session_id": session_handle.session_id,
            "request": request if isinstance(request, dict) else None,
            "signature": signature if isinstance(signature, dict) else None,
            "observed_at": completed_at.isoformat(),
        }
        events = [
            OperationDomainEventDraft(
                event_type="permission.request.observed",
                payload=observed_payload,
            ),
            OperationDomainEventDraft(
                event_type="permission.request.escalated",
                payload={
                    **observed_payload,
                    "rationale": raw.get("rationale"),
                    "suggested_options": self._list_payload(raw.get("suggested_options")),
                    "policy_title": raw.get("policy_title"),
                    "policy_rule_text": raw.get("policy_rule_text"),
                    "involvement_level": involvement_level,
                    "linked_attention_id": linked_attention_id,
                },
            ),
        ]
        if session_handle.adapter_key in {"codex_acp", "opencode_acp"}:
            events.append(
                OperationDomainEventDraft(
                    event_type="permission.request.followup_required",
                    payload={
                        **observed_payload,
                        "required_followup_reason": (
                            f"{session_handle.adapter_key} requires explicit replacement "
                            "instructions after a rejected or escalated permission request."
                        ),
                        "recommended_instruction": (
                            "Decide whether to give the agent a safe alternative instruction, "
                            "skip the blocked action, or escalate to the human."
                        ),
                    },
                )
            )
        return events

    def _linked_attention_id(
        self,
        attention_event: OperationDomainEventDraft | None,
    ) -> str | None:
        if attention_event is None:
            return None
        raw = attention_event.payload.get("attention_id")
        return raw if isinstance(raw, str) else None

    def _attention_event_from_agent_result(
        self,
        *,
        agg: OperationAggregate,
        ctx: ProcessManagerContext,
        session_handle: AgentSessionHandle,
        agent_result: AgentResult,
    ) -> OperationDomainEventDraft | None:
        if agent_result.status is not AgentResultStatus.INCOMPLETE:
            return None
        attention = self._attention_coordinator.attention_from_incomplete_result(
            self._build_brain_state(agg, ctx),
            session_handle,
            None,
            agent_result,
        )
        if attention is None:
            return None
        return OperationDomainEventDraft(
            event_type="attention.request.created",
            payload=self._attention_coordinator.event_payload(attention),
        )

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
            permission_events=[dict(event) for event in agg.permission_events],
            current_focus=agg.current_focus,
            attention_requests=list(agg.attention_requests),
            active_policies=[],
            policy_coverage=ctx.policy_context or PolicyCoverage(),
            involvement_level=agg.policy.involvement_level,
            scheduler_state=agg.scheduler_state,
            operator_messages=list(agg.operator_messages),
        )
        return state

    @staticmethod
    def _list_payload(value: object) -> list[object]:
        return list(value) if isinstance(value, list) else []
