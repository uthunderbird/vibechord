from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agent_operator.domain import (
    AgentTurnBrief,
    AttentionStatus,
    DecisionMemo,
    MemoryEntry,
    MemoryFreshness,
    OperationCommand,
    OperationOutcome,
    OperationState,
    OperationStatus,
    PolicyEntry,
    ProjectProfile,
    RunEvent,
    RunMode,
    SchedulerState,
    SessionRecord,
    TraceBriefBundle,
)
from agent_operator.runtime import AgendaItem, AgendaSnapshot


@dataclass(frozen=True, slots=True)
class ProjectionAction:
    key: str
    label: str
    cli_command: str
    scope: str
    destructive: bool
    enabled: bool = True
    reason: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "cli_command": self.cli_command,
            "scope": self.scope,
            "destructive": self.destructive,
            "enabled": self.enabled,
            "reason": self.reason,
        }


class OperationProjectionService:
    def memory_entries(
        self,
        operation: OperationState,
        *,
        include_inactive: bool,
    ) -> list[MemoryEntry]:
        entries = sorted(operation.memory_entries, key=lambda item: item.created_at)
        if include_inactive:
            return entries
        return [entry for entry in entries if entry.freshness is MemoryFreshness.CURRENT]

    def session_payload(self, session: SessionRecord) -> dict[str, object]:
        payload = session.model_dump(mode="json")
        payload["session_id"] = session.session_id
        payload["adapter_key"] = session.adapter_key
        payload["status"] = session.status.value
        payload["session_name"] = session.handle.session_name
        payload["display_name"] = session.handle.display_name
        return payload

    def operation_payload(self, operation: OperationState) -> dict[str, object]:
        payload = operation.model_dump(mode="json")
        payload["sessions"] = [self.session_payload(item) for item in operation.sessions]
        return payload

    def resolve_run_mode(self, operation: OperationState) -> str:
        raw_mode = operation.runtime_hints.metadata.get("run_mode")
        if isinstance(raw_mode, str) and raw_mode.strip():
            return raw_mode.strip()
        return RunMode.ATTACHED.value

    def available_agent_descriptors_payload(
        self, operation: OperationState
    ) -> list[dict[str, object]]:
        raw = operation.runtime_hints.metadata.get("available_agent_descriptors")
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, dict)]

    def build_durable_truth_payload(
        self,
        operation: OperationState,
        *,
        include_inactive_memory: bool = False,
    ) -> dict[str, object]:
        current_memory = self.memory_entries(operation, include_inactive=False)
        all_memory = self.memory_entries(operation, include_inactive=include_inactive_memory)
        return {
            "task_counts": self._summarize_task_counts(operation),
            "tasks": [task.model_dump(mode="json") for task in operation.tasks],
            "memory": {
                "current": [entry.model_dump(mode="json") for entry in current_memory],
                "inactive": [
                    entry.model_dump(mode="json")
                    for entry in all_memory
                    if entry.freshness is not MemoryFreshness.CURRENT
                ],
            },
            "artifacts": [artifact.model_dump(mode="json") for artifact in operation.artifacts],
        }

    def build_operation_context_payload(self, operation: OperationState) -> dict[str, object]:
        metadata = operation.goal.metadata
        payload: dict[str, object] = {
            "operation_id": operation.operation_id,
            "status": operation.status.value,
            "scheduler_state": operation.scheduler_state.value,
            "run_mode": self.resolve_run_mode(operation),
            "objective": operation.objective_state.objective,
            "harness_instructions": operation.objective_state.harness_instructions,
            "success_criteria": list(operation.objective_state.success_criteria),
            "allowed_agents": list(operation.policy.allowed_agents),
            "available_agent_descriptors": self.available_agent_descriptors_payload(operation),
            "max_iterations": operation.execution_budget.max_iterations,
            "involvement_level": operation.involvement_level.value,
        }
        if operation.current_focus is not None:
            payload["current_focus"] = operation.current_focus.model_dump(mode="json")
        active_session = operation.active_session_record
        if active_session is not None:
            payload["active_session"] = {
                "session_id": active_session.session_id,
                "adapter_key": active_session.adapter_key,
                "session_name": active_session.handle.session_name,
                "status": active_session.status.value,
                "waiting_reason": active_session.waiting_reason,
            }
        payload["open_attention"] = [
            attention.model_dump(mode="json")
            for attention in operation.attention_requests
            if attention.status is AttentionStatus.OPEN
        ]
        resolved_profile = metadata.get("resolved_project_profile")
        resolved_launch = metadata.get("resolved_operator_launch")
        payload["project_context"] = {
            "profile_name": (
                metadata.get("project_profile_name")
                if isinstance(metadata.get("project_profile_name"), str)
                else None
            ),
            "policy_scope": (
                metadata.get("policy_scope") if isinstance(metadata.get("policy_scope"), str) else None
            ),
            "resolved_profile": resolved_profile if isinstance(resolved_profile, dict) else None,
            "resolved_launch": resolved_launch if isinstance(resolved_launch, dict) else None,
        }
        payload["policy_coverage"] = operation.policy_coverage.model_dump(mode="json")
        payload["active_policies"] = [
            self._policy_payload(policy, operation) for policy in operation.active_policies
        ]
        return payload

    def build_fleet_payload(
        self,
        snapshot: AgendaSnapshot,
        *,
        project: str | None,
    ) -> dict[str, object]:
        items = [*snapshot.needs_attention, *snapshot.active, *snapshot.recent]
        return {
            "project": project,
            "total_operations": snapshot.total_operations,
            "mix": {
                "bucket_counts": {
                    "needs_attention": len(snapshot.needs_attention),
                    "active": len(snapshot.active),
                    "recent": len(snapshot.recent),
                },
                "status_counts": self._count_items_by_key(items, lambda item: item.status.value),
                "scheduler_counts": self._count_items_by_key(
                    items, lambda item: item.scheduler_state.value
                ),
                "involvement_counts": self._count_items_by_key(
                    items, lambda item: item.involvement_level.value
                ),
            },
            "needs_attention": [item.model_dump(mode="json") for item in snapshot.needs_attention],
            "active": [item.model_dump(mode="json") for item in snapshot.active],
            "recent": [item.model_dump(mode="json") for item in snapshot.recent],
            "actions": [action.to_payload() for action in self._fleet_actions(snapshot)],
        }

    def build_project_dashboard_payload(
        self,
        *,
        profile: ProjectProfile,
        resolved: dict[str, object],
        profile_path: Path,
        fleet: dict[str, object],
        active_policies: list[PolicyEntry],
    ) -> dict[str, object]:
        active_policy_payloads = [self._policy_payload(item) for item in active_policies]
        category_counts: dict[str, int] = {}
        for policy in active_policies:
            key = policy.category.value
            category_counts[key] = category_counts.get(key, 0) + 1
        return {
            "project": profile.name,
            "profile_path": str(profile_path),
            "profile": profile.model_dump(mode="json"),
            "resolved": resolved,
            "policy_scope": f"profile:{profile.name}",
            "active_policies": active_policy_payloads,
            "policy_summary": {
                "active_count": len(active_policy_payloads),
                "category_counts": category_counts,
            },
            "fleet": fleet,
            "actions": [
                action.to_payload()
                for action in self._project_dashboard_actions(profile.name, fleet=fleet)
            ],
        }

    def build_brief_summary_payload(
        self,
        operation: OperationState,
        brief: TraceBriefBundle | None,
        *,
        runtime_alert: str | None,
    ) -> dict[str, object]:
        brief = brief or TraceBriefBundle()
        latest_turn = self._latest_agent_turn_brief(brief)
        return {
            "objective": self._shorten_text(operation.objective_state.objective, limit=120),
            "harness": self._shorten_text(
                operation.objective_state.harness_instructions,
                limit=120,
            ),
            "task_counts": self._summarize_task_counts(operation),
            "latest_turn": latest_turn.model_dump(mode="json") if latest_turn is not None else None,
            "work_summary": self._turn_work_summary(latest_turn),
            "next_step": self._turn_next_step(latest_turn),
            "verification_summary": self._turn_verification_summary(latest_turn),
            "blockers_summary": self._turn_blockers_summary(latest_turn),
            "runtime_alert": runtime_alert,
        }

    def build_live_snapshot(
        self,
        operation: OperationState,
        brief: TraceBriefBundle | None,
        *,
        runtime_alert: str | None,
    ) -> dict[str, object]:
        latest_turn = self._latest_agent_turn_brief(brief)
        return {
            "operation_id": operation.operation_id,
            "status": operation.status.value,
            "scheduler_state": operation.scheduler_state.value,
            "focus": (
                f"{operation.current_focus.kind.value}:{operation.current_focus.target_id}"
                if operation.current_focus is not None
                else None
            ),
            "summary": self.build_brief_summary_payload(
                operation,
                brief,
                runtime_alert=runtime_alert,
            ),
            "latest_turn": latest_turn.model_dump(mode="json") if latest_turn is not None else None,
            "runtime_alert": runtime_alert,
        }

    def build_inspect_summary_payload(
        self,
        operation: OperationState,
        brief: TraceBriefBundle | None,
        *,
        runtime_alert: str | None,
    ) -> dict[str, object]:
        summary = self.build_brief_summary_payload(
            operation,
            brief,
            runtime_alert=runtime_alert,
        )
        return {
            "status": operation.status.value,
            "scheduler_state": operation.scheduler_state.value,
            "objective": summary.get("objective"),
            "task_counts": summary.get("task_counts"),
            "runtime_alert": runtime_alert,
            "latest_turn": summary.get("latest_turn"),
            "work_summary": summary.get("work_summary"),
            "verification_summary": summary.get("verification_summary"),
            "blockers_summary": summary.get("blockers_summary"),
            "next_step": summary.get("next_step"),
        }

    def build_dashboard_payload(
        self,
        operation: OperationState,
        *,
        brief: TraceBriefBundle | None,
        outcome: OperationOutcome | None,
        runtime_alert: str | None,
        commands: list[OperationCommand],
        events: list[RunEvent],
        decision_memos: list[DecisionMemo],
        upstream_transcript: dict[str, object] | None,
    ) -> dict[str, object]:
        active_session = operation.active_session_record
        context_payload = self.build_operation_context_payload(operation)
        open_attention = [
            attention
            for attention in operation.attention_requests
            if attention.status is AttentionStatus.OPEN
        ]
        recent_events = [
            rendered
            for rendered in (self._format_live_event(event) for event in events[-8:])
            if rendered is not None
        ]
        return {
            "operation_id": operation.operation_id,
            "status": operation.status.value,
            "scheduler_state": operation.scheduler_state.value,
            "run_mode": self.resolve_run_mode(operation),
            "involvement_level": operation.involvement_level.value,
            "objective": operation.objective_state.objective,
            "harness_instructions": operation.objective_state.harness_instructions,
            "summary": outcome.summary if outcome is not None else operation.final_summary,
            "focus": (
                f"{operation.current_focus.kind.value}:{operation.current_focus.target_id}"
                if operation.current_focus is not None
                else None
            ),
            "brief_summary": self.build_brief_summary_payload(
                operation,
                brief,
                runtime_alert=runtime_alert,
            ),
            "task_counts": self._summarize_task_counts(operation),
            "runtime_alert": runtime_alert,
            "active_session": (
                {
                    "session_id": active_session.session_id,
                    "adapter_key": active_session.adapter_key,
                    "status": active_session.status.value,
                    "session_name": active_session.handle.session_name,
                    "waiting_reason": active_session.waiting_reason,
                }
                if active_session is not None
                else None
            ),
            "available_agent_descriptors": context_payload.get("available_agent_descriptors"),
            "project_context": context_payload.get("project_context"),
            "policy_coverage": context_payload.get("policy_coverage"),
            "active_policies": context_payload.get("active_policies"),
            "attention": [
                {
                    "attention_id": attention.attention_id,
                    "attention_type": attention.attention_type.value,
                    "blocking": attention.blocking,
                    "target_scope": attention.target_scope.value,
                    "target_id": attention.target_id,
                    "title": attention.title,
                    "question": attention.question,
                    "context_brief": attention.context_brief,
                    "suggested_options": list(attention.suggested_options),
                }
                for attention in open_attention
            ],
            "tasks": [
                {
                    "task_id": task.task_id,
                    "task_short_id": f"task-{task.task_short_id}",
                    "title": task.title,
                    "goal": task.goal,
                    "definition_of_done": task.definition_of_done,
                    "status": task.status.value,
                    "priority": task.effective_priority,
                    "dependencies": list(task.dependencies),
                    "assigned_agent": task.assigned_agent,
                    "linked_session_id": task.linked_session_id,
                    "memory_refs": list(task.memory_refs),
                    "artifact_refs": list(task.artifact_refs),
                    "notes": list(task.notes),
                }
                for task in sorted(
                    operation.tasks,
                    key=lambda item: (-item.effective_priority, item.created_at, item.task_id),
                )[:8]
            ],
            "memory_entries": [
                {
                    "memory_id": entry.memory_id,
                    "scope": entry.scope.value,
                    "scope_id": entry.scope_id,
                    "summary": entry.summary,
                    "freshness": entry.freshness.value,
                }
                for entry in self.memory_entries(operation, include_inactive=True)
            ],
            "decision_memos": [
                {
                    "iteration": memo.iteration,
                    "task_id": memo.task_id,
                    "session_id": memo.session_id,
                    "decision_context_summary": memo.decision_context_summary,
                    "chosen_action": memo.chosen_action,
                    "rationale": memo.rationale,
                    "expected_outcome": memo.expected_outcome,
                }
                for memo in sorted(
                    decision_memos,
                    key=lambda item: (item.iteration, item.created_at),
                    reverse=True,
                )[:8]
            ],
            "sessions": [
                {
                    "session_id": session.session_id,
                    "adapter_key": session.adapter_key,
                    "status": session.status.value,
                    "session_name": session.handle.session_name,
                    "waiting_reason": session.waiting_reason,
                    "bound_task_ids": list(session.bound_task_ids),
                }
                for session in sorted(
                    operation.sessions,
                    key=lambda item: (item.created_at, item.session_id),
                )
            ],
            "recent_events": recent_events,
            "recent_commands": [
                {
                    "command_id": command.command_id,
                    "command_type": command.command_type.value,
                    "status": command.status.value,
                    "target_scope": command.target_scope.value,
                    "target_id": command.target_id,
                    "payload": command.payload,
                    "rejection_reason": command.rejection_reason,
                    "summary": self._format_dashboard_command(command),
                }
                for command in sorted(commands, key=lambda item: item.submitted_at)[-6:]
            ],
            "upstream_transcript": upstream_transcript,
            "codex_log": (
                list(upstream_transcript.get("events"))
                if isinstance(upstream_transcript, dict)
                and isinstance(upstream_transcript.get("events"), list)
                and upstream_transcript.get("adapter_key") == "codex_acp"
                else []
            ),
            "actions": [action.to_payload() for action in self._dashboard_actions(operation)],
        }

    def _count_items_by_key(
        self,
        items: list[AgendaItem],
        key_fn: Callable[[AgendaItem], str],
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            key = key_fn(item)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _fleet_actions(self, snapshot: AgendaSnapshot) -> list[ProjectionAction]:
        actions: list[ProjectionAction] = []

        def add(action: ProjectionAction) -> None:
            if all(existing.cli_command != action.cli_command for existing in actions):
                actions.append(action)

        if snapshot.needs_attention:
            item = snapshot.needs_attention[0]
            add(ProjectionAction("dashboard", "Dashboard", f"operator dashboard {item.operation_id}", "operation", False))
            add(ProjectionAction("context", "Context", f"operator context {item.operation_id}", "operation", False))
            if item.runtime_alert is not None:
                add(ProjectionAction("resume", "Resume", f"operator resume {item.operation_id}", "operation", False))
            if item.open_attention_count > 0 or item.status is OperationStatus.NEEDS_HUMAN:
                add(ProjectionAction("attention", "Attention", f"operator attention {item.operation_id}", "operation", False))
            if item.scheduler_state in {SchedulerState.PAUSED, SchedulerState.PAUSE_REQUESTED}:
                add(ProjectionAction("unpause", "Unpause", f"operator unpause {item.operation_id}", "operation", False))
        if snapshot.active:
            item = snapshot.active[0]
            add(ProjectionAction("dashboard", "Dashboard", f"operator dashboard {item.operation_id}", "operation", False))
            add(ProjectionAction("watch", "Watch", f"operator watch {item.operation_id}", "operation", False))
            add(ProjectionAction("context", "Context", f"operator context {item.operation_id}", "operation", False))
            add(ProjectionAction("pause", "Pause", f"operator pause {item.operation_id}", "operation", False))
        if snapshot.recent:
            item = snapshot.recent[0]
            add(ProjectionAction("report", "Report", f"operator report {item.operation_id}", "operation", False))
        return actions

    def _project_dashboard_actions(
        self,
        project_name: str,
        *,
        fleet: dict[str, object],
    ) -> list[ProjectionAction]:
        actions = [
            ProjectionAction("run", "Run", f'operator run --project {project_name} "<objective>"', "project", False),
            ProjectionAction("project_inspect", "Project Inspect", f"operator project inspect {project_name}", "project", False),
            ProjectionAction("project_resolve", "Project Resolve", f"operator project resolve {project_name}", "project", False),
            ProjectionAction("fleet", "Fleet", f"operator fleet --project {project_name} --all --once", "project", False),
            ProjectionAction("policy_list", "Policy List", f"operator policy list --project profile:{project_name}", "project", False),
        ]
        fleet_actions = fleet.get("actions")
        if isinstance(fleet_actions, list):
            for item in fleet_actions:
                if isinstance(item, dict):
                    cli_command = item.get("cli_command")
                    if isinstance(cli_command, str) and cli_command and all(existing.cli_command != cli_command for existing in actions):
                        actions.append(
                            ProjectionAction(
                                str(item.get("key") or "action"),
                                str(item.get("label") or cli_command),
                                cli_command,
                                str(item.get("scope") or "operation"),
                                bool(item.get("destructive", False)),
                                bool(item.get("enabled", True)),
                                str(item.get("reason")) if isinstance(item.get("reason"), str) else None,
                            )
                        )
        return actions

    def _dashboard_actions(self, operation: OperationState) -> list[ProjectionAction]:
        actions = [
            ProjectionAction("context", "Context", f"operator context {operation.operation_id}", "operation", False),
            ProjectionAction("watch", "Watch", f"operator watch {operation.operation_id}", "operation", False),
        ]
        if operation.status is OperationStatus.RUNNING:
            if operation.scheduler_state in {SchedulerState.PAUSED, SchedulerState.PAUSE_REQUESTED}:
                actions.append(ProjectionAction("unpause", "Unpause", f"operator unpause {operation.operation_id}", "operation", False))
            else:
                actions.append(ProjectionAction("pause", "Pause", f"operator pause {operation.operation_id}", "operation", False))
            if operation.active_session_record is not None and operation.scheduler_state is not SchedulerState.DRAINING:
                actions.append(ProjectionAction("interrupt", "Interrupt", f"operator interrupt {operation.operation_id}", "operation", False))
        if any(session.adapter_key in {"codex_acp", "claude_acp", "opencode_acp"} for session in operation.sessions):
            actions.append(ProjectionAction("log", "Log", f"operator log {operation.operation_id}", "operation", False))
        open_attention = [attention for attention in operation.attention_requests if attention.status is AttentionStatus.OPEN]
        if open_attention:
            actions.append(
                ProjectionAction(
                    "answer",
                    "Answer",
                    f"operator answer {operation.operation_id} {open_attention[0].attention_id} --text '...'",
                    "operation",
                    False,
                )
            )
        policy_scope = operation.policy_coverage.project_scope
        if operation.policy_coverage.status.value == "uncovered" and isinstance(policy_scope, str) and policy_scope.startswith("profile:"):
            actions.append(
                ProjectionAction(
                    "policy_list",
                    "Policy List",
                    f"operator policy list --project {policy_scope.removeprefix('profile:')}",
                    "project",
                    False,
                )
            )
        return actions

    def _format_live_event(self, event: RunEvent) -> str | None:
        event_type = event.event_type
        payload = event.payload
        if event_type == "brain.decision.made":
            action_type = payload.get("action_type")
            rationale = payload.get("rationale")
            suffix = f": {rationale}" if isinstance(rationale, str) and rationale else ""
            return f"decision {action_type}{suffix}"
        if event_type == "agent.invocation.started":
            adapter_key = payload.get("adapter_key") or event.session_id or "agent"
            session_name = payload.get("session_name")
            if isinstance(session_name, str) and session_name:
                return f"started {adapter_key} ({session_name})"
            return f"started {adapter_key}"
        if event_type == "agent.result.received":
            status = payload.get("status") or "result"
            summary = payload.get("summary")
            suffix = f": {summary}" if isinstance(summary, str) and summary else ""
            return f"result {status}{suffix}"
        if event_type == "attention.requested":
            title = payload.get("title") or payload.get("question") or "attention requested"
            return f"attention: {title}"
        if event_type == "operation.command.enqueued":
            command_type = payload.get("command_type") or "command"
            return f"command queued: {command_type}"
        return self._shorten_text(json.dumps(event.model_dump(mode="json"), ensure_ascii=False), limit=120)

    def _format_dashboard_command(self, command: OperationCommand) -> str:
        rendered = f"{command.command_type.value} [{command.status.value}] target={command.target_scope.value}:{command.target_id or '-'}"
        payload_text = self._shorten_text(json.dumps(command.payload, ensure_ascii=False), limit=80)
        if payload_text is not None and payload_text != "{}":
            rendered += f" | payload={payload_text}"
        if command.rejection_reason:
            rendered += f" | reason={command.rejection_reason}"
        return rendered

    def _policy_payload(
        self,
        policy: PolicyEntry,
        operation: OperationState | None = None,
    ) -> dict[str, object]:
        payload = policy.model_dump(mode="json")
        payload["category"] = policy.category.value
        if operation is not None:
            payload["applicability_summary"] = "active for current operation"
        return payload

    def _latest_agent_turn_brief(
        self,
        brief: TraceBriefBundle | None,
    ) -> AgentTurnBrief | None:
        if brief is None or not brief.agent_turn_briefs:
            return None
        return max(brief.agent_turn_briefs, key=lambda item: (item.iteration, item.session_id))

    def _turn_work_summary(self, turn: AgentTurnBrief | None) -> str | None:
        if turn is None:
            return None
        return self._shorten_text(turn.assignment_brief or turn.result_brief, limit=220)

    def _turn_next_step(self, turn: AgentTurnBrief | None) -> str | None:
        if turn is None or turn.turn_summary is None:
            return None
        return self._shorten_text(turn.turn_summary.next_step, limit=220)

    def _turn_verification_summary(self, turn: AgentTurnBrief | None) -> str | None:
        if turn is None or turn.turn_summary is None:
            return None
        return self._shorten_text(turn.turn_summary.verification_summary, limit=220)

    def _turn_blockers_summary(self, turn: AgentTurnBrief | None) -> str | None:
        if turn is None or turn.turn_summary is None:
            return None
        return self._shorten_text(turn.turn_summary.blockers_summary, limit=220)

    def _shorten_text(self, text: str | None, *, limit: int) -> str | None:
        if text is None:
            return None
        normalized = " ".join(text.split())
        if not normalized:
            return None
        if len(normalized) <= limit:
            return normalized
        return normalized[: max(0, limit - 1)].rstrip() + "…"

    def _summarize_task_counts(self, operation: OperationState) -> str:
        counts: dict[str, int] = {}
        for task in operation.tasks:
            key = task.status.value
            counts[key] = counts.get(key, 0) + 1
        if not counts:
            return ""
        return ", ".join(f"{status}:{count}" for status, count in sorted(counts.items()))

    def format_live_snapshot(self, snapshot: dict[str, object]) -> str:
        parts = [f"state: {snapshot.get('status', 'unknown')}"]
        scheduler_state = snapshot.get("scheduler_state")
        if isinstance(scheduler_state, str) and scheduler_state:
            parts.append(f"scheduler={scheduler_state}")
        focus = snapshot.get("focus")
        if isinstance(focus, str) and focus:
            parts.append(f"focus={focus}")
        summary = snapshot.get("summary")
        if isinstance(summary, dict):
            objective = self._shorten_text(
                str(summary.get("objective")) if summary.get("objective") is not None else None,
                limit=120,
            )
            if objective is not None:
                parts.append(f"objective={objective}")
            work_summary = self._shorten_text(
                str(summary.get("work_summary"))
                if summary.get("work_summary") is not None
                else None,
                limit=120,
            )
            if work_summary is not None:
                parts.append(f"work={work_summary}")
            next_step = self._shorten_text(
                str(summary.get("next_step")) if summary.get("next_step") is not None else None,
                limit=120,
            )
            if next_step is not None:
                parts.append(f"next={next_step}")
        runtime_alert = self._shorten_text(
            str(snapshot.get("runtime_alert")) if snapshot.get("runtime_alert") is not None else None,
            limit=120,
        )
        if runtime_alert is not None:
            parts.append(f"alert={runtime_alert}")
        return " | ".join(parts)
