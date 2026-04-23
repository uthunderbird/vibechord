"""OperationAggregate — v2 domain aggregate with explicit field classification.

ADR 0193 classifies fields into three categories:
- Domain canonical: business facts produced by domain events
- Coordination state: drive-loop bookkeeping that must survive crashes (event-sourced)
- Read model: derived projection, lives in OperationReadModel (not here)

The only write path is apply_events(), which returns a NEW immutable instance.
"""
from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agent_operator.domain.agent import AgentSessionHandle
from agent_operator.domain.attention import AttentionRequest
from agent_operator.domain.control import OperatorMessage
from agent_operator.domain.enums import (
    InvolvementLevel,
    OperationStatus,
    SchedulerState,
)
from agent_operator.domain.operation import (
    ArtifactRecord,
    ExecutionBudget,
    ExecutionProfileOverride,
    ExecutionState,
    ExternalTicketLink,
    FeatureState,
    FocusState,
    MemoryEntry,
    ObjectiveState,
    OperationGoal,
    OperationPolicy,
    RuntimeHints,
    SessionState,
    TaskState,
)
from agent_operator.domain.policy import PolicyCoverage, PolicyEntry


@dataclasses.dataclass(frozen=True)
class OperationAggregate:
    """Immutable v2 operation aggregate.

    Write path: apply_events() only — returns a new instance via dataclasses.replace().
    All fields are either domain canonical or coordination state (ADR 0193).
    Read-model fields (iteration_briefs, decision_records, etc.) live in OperationReadModel.
    """

    # ── Domain canonical ──────────────────────────────────────────────────────
    operation_id: str
    goal: OperationGoal
    policy: OperationPolicy
    execution_budget: ExecutionBudget
    runtime_hints: RuntimeHints
    execution_profile_overrides: dict[str, ExecutionProfileOverride]
    status: OperationStatus
    objective: ObjectiveState | None
    tasks: list[TaskState]
    features: list[FeatureState]
    sessions: list[SessionState]
    executions: list[ExecutionState]
    artifacts: list[ArtifactRecord]
    memory_entries: list[MemoryEntry]
    external_ticket: ExternalTicketLink | None
    final_summary: str | None
    allowed_agents: list[str]
    involvement_level: InvolvementLevel
    created_at: datetime
    updated_at: datetime

    # ── Coordination state (event-sourced, crash-safe) ────────────────────────
    current_focus: FocusState | None
    scheduler_state: SchedulerState
    operator_messages: list[OperatorMessage]
    attention_requests: list[AttentionRequest]
    active_policies: list[PolicyEntry]
    policy_coverage: PolicyCoverage
    processed_command_ids: list[str]
    pending_replan_command_ids: list[str]
    pending_attention_resolution_ids: list[str]

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def create(
        cls,
        goal: OperationGoal,
        *,
        policy: OperationPolicy | None = None,
        execution_budget: ExecutionBudget | None = None,
        runtime_hints: RuntimeHints | None = None,
        operation_id: str | None = None,
        created_at: datetime | None = None,
    ) -> OperationAggregate:
        """Construct a new operation aggregate with sensible defaults."""
        now = created_at or datetime.now(UTC)
        resolved_policy = policy or OperationPolicy()
        return cls(
            operation_id=operation_id or str(uuid4()),
            goal=goal,
            policy=resolved_policy,
            execution_budget=execution_budget or ExecutionBudget(),
            runtime_hints=runtime_hints or RuntimeHints(),
            execution_profile_overrides={},
            status=OperationStatus.RUNNING,
            objective=ObjectiveState(objective=goal.objective_text),
            tasks=[],
            features=[],
            sessions=[],
            executions=[],
            artifacts=[],
            memory_entries=[],
            external_ticket=None,
            final_summary=None,
            allowed_agents=list(resolved_policy.allowed_agents),
            involvement_level=resolved_policy.involvement_level,
            created_at=now,
            updated_at=now,
            current_focus=None,
            scheduler_state=SchedulerState.ACTIVE,
            operator_messages=[],
            attention_requests=[],
            active_policies=[],
            policy_coverage=PolicyCoverage(),
            processed_command_ids=[],
            pending_replan_command_ids=[],
            pending_attention_resolution_ids=[],
        )

    def apply_events(self, events: list[Any]) -> OperationAggregate:
        """Apply a sequence of domain events, returning a new aggregate instance.

        Each event must have an `event_type` attribute (str) and a `payload` attribute
        (dict[str, Any]), matching the StoredOperationDomainEvent wire format.
        Unknown event types are silently ignored (forward-compatibility).
        """
        agg = self
        for event in events:
            agg = agg._apply_one(event)
        return agg

    def _apply_one(self, event: Any) -> OperationAggregate:
        event_type: str = getattr(event, "event_type", "")
        payload: dict[str, Any] = getattr(event, "payload", {})
        now = datetime.now(UTC)

        # ── Operation slice ───────────────────────────────────────────────────
        if event_type == "operation.created":
            objective_raw = payload.get("objective")
            if isinstance(objective_raw, dict):
                # nested dict shape (legacy)
                new_objective = ObjectiveState(**objective_raw) if objective_raw else self.objective
            elif isinstance(objective_raw, str):
                # flat string shape — extract remaining ObjectiveState fields from payload
                new_objective = ObjectiveState(
                    objective=objective_raw,
                    harness_instructions=payload.get("harness_instructions"),
                    success_criteria=list(payload.get("success_criteria") or []),
                    metadata=dict(payload.get("metadata") or {}),
                )
            else:
                new_objective = self.objective
            allowed = payload.get("allowed_agents", list(self.allowed_agents))
            involvement_raw = payload.get("involvement_level", self.involvement_level.value)
            involvement = (
                InvolvementLevel(involvement_raw)
                if isinstance(involvement_raw, str)
                else self.involvement_level
            )
            policy_payload = payload.get("policy")
            if isinstance(policy_payload, dict):
                new_policy = OperationPolicy(**policy_payload)
            else:
                new_policy = self.policy.model_copy(
                    update={
                        "allowed_agents": list(allowed),
                        "involvement_level": involvement,
                    }
                )
            execution_budget_payload = payload.get("execution_budget")
            new_execution_budget = (
                ExecutionBudget(**execution_budget_payload)
                if isinstance(execution_budget_payload, dict)
                else self.execution_budget
            )
            runtime_hints_payload = payload.get("runtime_hints")
            new_runtime_hints = (
                RuntimeHints(**runtime_hints_payload)
                if isinstance(runtime_hints_payload, dict)
                else self.runtime_hints
            )
            return dataclasses.replace(
                self,
                policy=new_policy,
                execution_budget=new_execution_budget,
                runtime_hints=new_runtime_hints,
                objective=new_objective,
                allowed_agents=allowed,
                involvement_level=involvement,
                updated_at=now,
            )

        if event_type == "operation.status.changed":
            raw_status = payload.get("status", self.status.value)
            new_status = OperationStatus(raw_status) if isinstance(raw_status, str) else self.status
            return dataclasses.replace(
                self,
                status=new_status,
                final_summary=payload.get("final_summary", self.final_summary),
                updated_at=now,
            )

        if event_type == "operation.ticket_linked":
            ticket_data = payload.get("ticket")
            ticket = ExternalTicketLink(**ticket_data) if ticket_data else self.external_ticket
            return dataclasses.replace(self, external_ticket=ticket, updated_at=now)

        if event_type == "objective.updated":
            objective_data = payload.get("objective", {})
            new_objective = ObjectiveState(**objective_data) if objective_data else self.objective
            return dataclasses.replace(self, objective=new_objective, updated_at=now)

        if event_type == "operation.allowed_agents.updated":
            return dataclasses.replace(
                self,
                allowed_agents=payload.get("allowed_agents", self.allowed_agents),
                updated_at=now,
            )

        if event_type == "operation.involvement_level.updated":
            raw = payload.get("involvement_level", self.involvement_level.value)
            level = InvolvementLevel(raw) if isinstance(raw, str) else self.involvement_level
            return dataclasses.replace(self, involvement_level=level, updated_at=now)

        if event_type == "operation.execution_profile.updated":
            overrides = dict(self.execution_profile_overrides)
            adapter_key = payload.get("adapter_key", "")
            if adapter_key:
                overrides[adapter_key] = ExecutionProfileOverride(**payload)
            return dataclasses.replace(self, execution_profile_overrides=overrides, updated_at=now)

        # ── Task slice ────────────────────────────────────────────────────────
        if event_type == "task.created":
            new_task = TaskState(**payload)
            return dataclasses.replace(self, tasks=[*self.tasks, new_task], updated_at=now)

        if event_type == "task.updated":
            task_id = payload.get("task_id")
            updated_tasks = []
            for t in self.tasks:
                if t.task_id == task_id:
                    task_updates = {
                        key: value
                        for key, value in payload.items()
                        if key != "task_id" and value is not None
                    }
                    t = t.model_copy(update=task_updates)
                updated_tasks.append(t)
            return dataclasses.replace(self, tasks=updated_tasks, updated_at=now)

        # ── Session slice ─────────────────────────────────────────────────────
        if event_type == "session.created":
            if "handle" in payload:
                new_session = SessionState(**payload)
            else:
                # Minimal shape from PolicyExecutor (Layer 2): adapter_key only
                adapter_key = payload.get("adapter_key", "unknown")
                session_id = payload.get("session_id") or str(uuid4())
                handle = AgentSessionHandle(adapter_key=adapter_key, session_id=session_id)
                new_session = SessionState(handle=handle)
            return dataclasses.replace(self, sessions=[*self.sessions, new_session], updated_at=now)

        if event_type == "session.observed_state.changed":
            session_id = payload.get("session_id")
            updated_sessions = []
            for s in self.sessions:
                if s.handle and s.handle.session_id == session_id:
                    session_updates = {
                        key: value
                        for key, value in payload.items()
                        if key != "session_id" and value is not None
                    }
                    s = s.model_copy(update=session_updates)
                updated_sessions.append(s)
            return dataclasses.replace(self, sessions=updated_sessions, updated_at=now)

        if event_type == "session.cooldown_cleared":
            session_id = payload.get("session_id")
            updated_sessions = []
            for s in self.sessions:
                if s.handle and s.handle.session_id == session_id:
                    s = s.model_copy(update={"cooldown_until": None, "waiting_reason": None})
                updated_sessions.append(s)
            return dataclasses.replace(self, sessions=updated_sessions, updated_at=now)

        # ── Execution slice ───────────────────────────────────────────────────
        if event_type == "execution.registered":
            new_exec = ExecutionState(**payload)
            return dataclasses.replace(
                self,
                executions=[*self.executions, new_exec],
                updated_at=now,
            )

        if event_type in ("execution.session_linked", "execution.observed_state.changed"):
            exec_id = payload.get("execution_id")
            updated_execs = []
            for e in self.executions:
                if e.execution_id == exec_id:
                    execution_updates = {
                        key: value
                        for key, value in payload.items()
                        if key != "execution_id" and value is not None
                    }
                    e = e.model_copy(update=execution_updates)
                updated_execs.append(e)
            return dataclasses.replace(self, executions=updated_execs, updated_at=now)

        # ── Attention slice ───────────────────────────────────────────────────
        if event_type == "attention.request.created":
            new_req = AttentionRequest(**payload)
            new_reqs = [*self.attention_requests, new_req]
            # If blocking, set status to NEEDS_HUMAN
            new_status = self.status
            if payload.get("blocking") and self.status == OperationStatus.RUNNING:
                new_status = OperationStatus.NEEDS_HUMAN
            return dataclasses.replace(
                self, attention_requests=new_reqs, status=new_status, updated_at=now
            )

        if event_type in ("attention.request.answered", "attention.request.resolved"):
            req_id = payload.get("request_id") or payload.get("attention_id")
            updated_reqs = []
            for r in self.attention_requests:
                if r.attention_id == req_id:
                    request_updates = {
                        key: value
                        for key, value in payload.items()
                        if key != "request_id" and value is not None
                    }
                    r = r.model_copy(update=request_updates)
                updated_reqs.append(r)
            # If no more open blocking requests, restore status
            new_status = self.status
            if self.status == OperationStatus.NEEDS_HUMAN:
                still_blocking = any(
                    r.blocking and r.status.value == "open"
                    for r in updated_reqs
                )
                if not still_blocking:
                    new_status = OperationStatus.RUNNING
            return dataclasses.replace(
                self, attention_requests=updated_reqs, status=new_status, updated_at=now
            )

        # ── Scheduler slice ───────────────────────────────────────────────────
        if event_type == "scheduler.state.changed":
            raw = payload.get("scheduler_state", self.scheduler_state.value)
            new_sched = SchedulerState(raw) if isinstance(raw, str) else self.scheduler_state
            return dataclasses.replace(self, scheduler_state=new_sched, updated_at=now)

        # ── Operator message slice ────────────────────────────────────────────
        if event_type == "operator_message.received":
            new_msg = OperatorMessage(**payload)
            msgs = [*self.operator_messages, new_msg]
            if len(msgs) > 50:
                msgs = msgs[-50:]
            return dataclasses.replace(self, operator_messages=msgs, updated_at=now)

        if event_type == "operator_message.dropped_from_context":
            msg_id = payload.get("message_id")
            updated_msgs = []
            for m in self.operator_messages:
                if m.message_id == msg_id:
                    m = m.model_copy(update={"dropped_from_context": True})
                updated_msgs.append(m)
            return dataclasses.replace(self, operator_messages=updated_msgs, updated_at=now)

        # ── Policy slice ──────────────────────────────────────────────────────
        if event_type == "policy.coverage.updated":
            new_coverage = PolicyCoverage(**payload)
            return dataclasses.replace(self, policy_coverage=new_coverage, updated_at=now)

        if event_type == "policy.active_set.updated":
            new_policies = [PolicyEntry(**p) for p in payload.get("policies", [])]
            return dataclasses.replace(self, active_policies=new_policies, updated_at=now)

        # ── Focus slice ───────────────────────────────────────────────────────
        if event_type == "operation.focus.updated":
            focus_data = payload.get("focus")
            new_focus = FocusState(**focus_data) if focus_data else None
            return dataclasses.replace(self, current_focus=new_focus, updated_at=now)

        if event_type == "session.waiting_reason.updated":
            session_id = payload.get("session_id")
            waiting_reason = payload.get("waiting_reason")
            updated_sessions = []
            for s in self.sessions:
                if s.handle and s.handle.session_id == session_id:
                    s = s.model_copy(update={"waiting_reason": waiting_reason})
                updated_sessions.append(s)
            return dataclasses.replace(self, sessions=updated_sessions, updated_at=now)

        # ── Coordination state events ─────────────────────────────────────────
        if event_type == "command.processed":
            cmd_id = payload.get("command_id", "")
            if cmd_id and cmd_id not in self.processed_command_ids:
                return dataclasses.replace(
                    self,
                    processed_command_ids=[*self.processed_command_ids, cmd_id],
                    updated_at=now,
                )
            return self

        if event_type == "replan.scheduled":
            cmd_id = payload.get("command_id", "")
            if cmd_id and cmd_id not in self.pending_replan_command_ids:
                return dataclasses.replace(
                    self,
                    pending_replan_command_ids=[*self.pending_replan_command_ids, cmd_id],
                    updated_at=now,
                )
            return self

        if event_type == "replan.consumed":
            cmd_id = payload.get("command_id", "")
            return dataclasses.replace(
                self,
                pending_replan_command_ids=[
                    command_id
                    for command_id in self.pending_replan_command_ids
                    if command_id != cmd_id
                ],
                updated_at=now,
            )

        if event_type == "attention.answer.queued":
            req_id = payload.get("request_id", "")
            if req_id and req_id not in self.pending_attention_resolution_ids:
                return dataclasses.replace(
                    self,
                    pending_attention_resolution_ids=[
                        *self.pending_attention_resolution_ids,
                        req_id,
                    ],
                    updated_at=now,
                )
            return self

        if event_type == "attention.answer.consumed":
            req_id = payload.get("request_id", "")
            return dataclasses.replace(
                self,
                pending_attention_resolution_ids=[
                    r for r in self.pending_attention_resolution_ids if r != req_id
                ],
                updated_at=now,
            )

        # Unknown event_type — forward-compatible noop
        return self
