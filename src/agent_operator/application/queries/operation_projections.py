from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agent_operator.domain import (
    AgentTurnBrief,
    AttentionRequest,
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
    TaskState,
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


@dataclass(frozen=True, slots=True)
class SupervisoryProgressSummary:
    done: str | None
    doing: str | None
    next: str | None

    def to_payload(self) -> dict[str, str | None]:
        return {
            "done": self.done,
            "doing": self.doing,
            "next": self.next,
        }


@dataclass(frozen=True, slots=True)
class SupervisoryActivitySummary:
    goal: str | None
    now: str | None
    wait: str | None
    progress: SupervisoryProgressSummary
    attention: str | None
    review: str | None
    recent: str | None
    agent_activity: str | None = None
    operator_state: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "goal": self.goal,
            "now": self.now,
            "wait": self.wait,
            "progress": self.progress.to_payload(),
            "attention": self.attention,
            "review": self.review,
            "recent": self.recent,
            "agent_activity": self.agent_activity,
            "operator_state": self.operator_state,
        }


@dataclass(frozen=True, slots=True)
class FleetWorkbenchRow:
    operation_id: str
    attention_badge: str
    display_name: str
    state_label: str
    agent_cue: str
    recency_brief: str
    row_hint: str
    sort_bucket: str
    status: str
    scheduler_state: str
    project_profile_name: str | None
    runtime_alert: str | None
    focus_brief: str | None
    latest_outcome_brief: str | None
    blocker_brief: str | None
    open_attention_count: int
    open_blocking_attention_count: int
    open_nonblocking_attention_count: int
    attention_briefs: tuple[str, ...]
    attention_titles: tuple[str, ...]
    brief: SupervisoryActivitySummary

    def to_payload(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "attention_badge": self.attention_badge,
            "display_name": self.display_name,
            "state_label": self.state_label,
            "agent_cue": self.agent_cue,
            "recency_brief": self.recency_brief,
            "row_hint": self.row_hint,
            "sort_bucket": self.sort_bucket,
            "status": self.status,
            "scheduler_state": self.scheduler_state,
            "project_profile_name": self.project_profile_name,
            "runtime_alert": self.runtime_alert,
            "focus_brief": self.focus_brief,
            "latest_outcome_brief": self.latest_outcome_brief,
            "blocker_brief": self.blocker_brief,
            "open_attention_count": self.open_attention_count,
            "open_blocking_attention_count": self.open_blocking_attention_count,
            "open_nonblocking_attention_count": self.open_nonblocking_attention_count,
            "attention_briefs": list(self.attention_briefs),
            "attention_titles": list(self.attention_titles),
            "brief": self.brief.to_payload(),
            "open_attention": self.open_attention_count > 0,
        }


@dataclass(frozen=True, slots=True)
class FleetWorkbenchPayload:
    project: str | None
    total_operations: int
    header: dict[str, object]
    rows: list[dict[str, object]]
    control_hints: list[str]
    mix: dict[str, object]
    actions: list[dict[str, object]]

    def to_payload(self) -> dict[str, object]:
        return {
            "project": self.project,
            "total_operations": self.total_operations,
            "header": self.header,
            "rows": self.rows,
            "control_hints": self.control_hints,
            "mix": self.mix,
            "actions": self.actions,
        }


@dataclass(frozen=True, slots=True)
class SessionReadPayload:
    session_id: str
    adapter_key: str
    status: str
    session_name: str | None
    display_name: str
    one_shot: bool
    current_execution_id: str | None
    last_terminal_execution_id: str | None
    bound_task_ids: list[str]
    last_result_iteration: int | None
    latest_iteration: int | None
    attached_turn_started_at: str | None
    last_progress_at: str | None
    last_event_at: str | None
    waiting_reason: str | None
    cooldown_until: str | None
    cooldown_reason: str | None
    last_rate_limited_at: str | None
    recovery_summary: str | None
    recovery_count: int
    recovery_attempted_at: str | None
    last_recovered_at: str | None
    created_at: str
    updated_at: str

    def to_payload(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "adapter_key": self.adapter_key,
            "status": self.status,
            "session_name": self.session_name,
            "display_name": self.display_name,
            "one_shot": self.one_shot,
            "current_execution_id": self.current_execution_id,
            "last_terminal_execution_id": self.last_terminal_execution_id,
            "bound_task_ids": list(self.bound_task_ids),
            "last_result_iteration": self.last_result_iteration,
            "latest_iteration": self.latest_iteration,
            "attached_turn_started_at": self.attached_turn_started_at,
            "last_progress_at": self.last_progress_at,
            "last_event_at": self.last_event_at,
            "waiting_reason": self.waiting_reason,
            "cooldown_until": self.cooldown_until,
            "cooldown_reason": self.cooldown_reason,
            "last_rate_limited_at": self.last_rate_limited_at,
            "recovery_summary": self.recovery_summary,
            "recovery_count": self.recovery_count,
            "recovery_attempted_at": self.recovery_attempted_at,
            "last_recovered_at": self.last_recovered_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class FocusReadPayload:
    kind: str
    target_id: str
    mode: str
    blocking_reason: str | None
    interrupt_policy: str
    resume_policy: str
    created_at: str

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "target_id": self.target_id,
            "mode": self.mode,
            "blocking_reason": self.blocking_reason,
            "interrupt_policy": self.interrupt_policy,
            "resume_policy": self.resume_policy,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class AttentionReadPayload:
    attention_id: str
    operation_id: str
    attention_type: str
    target_scope: str
    target_id: str | None
    title: str
    question: str
    context_brief: str | None
    suggested_options: list[str]
    blocking: bool
    status: str
    answer_text: str | None
    answer_source_command_id: str | None
    created_at: str
    answered_at: str | None
    resolved_at: str | None
    resolution_summary: str | None
    metadata: dict[str, object]

    def to_payload(self) -> dict[str, object]:
        return {
            "attention_id": self.attention_id,
            "operation_id": self.operation_id,
            "attention_type": self.attention_type,
            "target_scope": self.target_scope,
            "target_id": self.target_id,
            "title": self.title,
            "question": self.question,
            "context_brief": self.context_brief,
            "suggested_options": list(self.suggested_options),
            "blocking": self.blocking,
            "status": self.status,
            "answer_text": self.answer_text,
            "answer_source_command_id": self.answer_source_command_id,
            "created_at": self.created_at,
            "answered_at": self.answered_at,
            "resolved_at": self.resolved_at,
            "resolution_summary": self.resolution_summary,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class PolicyCoverageReadPayload:
    status: str
    project_scope: str | None
    scoped_policy_count: int
    active_policy_count: int
    summary: str

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "project_scope": self.project_scope,
            "scoped_policy_count": self.scoped_policy_count,
            "active_policy_count": self.active_policy_count,
            "summary": self.summary,
        }


class OperationProjectionService:
    def _execution_profile_display_value(
        self,
        *,
        model: str | None,
        effort_value: str | None,
    ) -> str | None:
        normalized_model = model.strip() if isinstance(model, str) and model.strip() else None
        normalized_effort = (
            effort_value.strip()
            if isinstance(effort_value, str) and effort_value.strip()
            else None
        )
        if normalized_model is None:
            return None
        if normalized_effort is None:
            return normalized_model
        return f"{normalized_model} / {normalized_effort}"

    def _active_session_execution_profile_payload(
        self,
        operation: OperationState,
    ) -> dict[str, object] | None:
        active_session = operation.active_session_record
        if active_session is None:
            return None
        stamp = active_session.execution_profile_stamp
        if stamp is None:
            return {
                "session_id": active_session.session_id,
                "adapter_key": active_session.adapter_key,
                "known": False,
                "model": None,
                "effort_field_name": None,
                "effort_value": None,
                "display": "unknown",
            }
        display = self._execution_profile_display_value(
            model=stamp.model,
            effort_value=stamp.effort_value,
        )
        return {
            "session_id": active_session.session_id,
            "adapter_key": active_session.adapter_key,
            "known": display is not None,
            "model": stamp.model,
            "effort_field_name": stamp.effort_field_name,
            "effort_value": stamp.effort_value,
            "display": display or "unknown",
        }

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
        return SessionReadPayload(
            session_id=session.session_id,
            adapter_key=session.adapter_key,
            status=session.status.value,
            session_name=session.handle.session_name,
            display_name=session.handle.display_name,
            one_shot=session.handle.one_shot,
            current_execution_id=session.current_execution_id,
            last_terminal_execution_id=session.last_terminal_execution_id,
            bound_task_ids=list(session.bound_task_ids),
            last_result_iteration=session.last_result_iteration,
            latest_iteration=session.latest_iteration,
            attached_turn_started_at=(
                session.attached_turn_started_at.isoformat()
                if session.attached_turn_started_at is not None
                else None
            ),
            last_progress_at=(
                session.last_progress_at.isoformat()
                if session.last_progress_at is not None
                else None
            ),
            last_event_at=(
                session.last_event_at.isoformat() if session.last_event_at is not None else None
            ),
            waiting_reason=session.waiting_reason,
            cooldown_until=(
                session.cooldown_until.isoformat() if session.cooldown_until is not None else None
            ),
            cooldown_reason=session.cooldown_reason,
            last_rate_limited_at=(
                session.last_rate_limited_at.isoformat()
                if session.last_rate_limited_at is not None
                else None
            ),
            recovery_summary=session.recovery_summary,
            recovery_count=session.recovery_count,
            recovery_attempted_at=(
                session.recovery_attempted_at.isoformat()
                if session.recovery_attempted_at is not None
                else None
            ),
            last_recovered_at=(
                session.last_recovered_at.isoformat()
                if session.last_recovered_at is not None
                else None
            ),
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
        ).to_payload() | {
            "execution_profile_stamp": self._execution_profile_stamp_payload(
                session.execution_profile_stamp
            )
        }

    def _execution_profile_stamp_payload(self, stamp) -> dict[str, object] | None:
        if stamp is None:
            return None
        return {
            "adapter_key": stamp.adapter_key,
            "model": stamp.model,
            "effort_field_name": stamp.effort_field_name,
            "effort_value": stamp.effort_value,
        }

    def _execution_profile_override_payload(self, override) -> dict[str, object]:
        payload = {
            "adapter_key": override.adapter_key,
            "model": override.model,
            "effort_field_name": override.effort_field_name,
            "effort_value": override.effort_value,
        }
        if override.effort is not None:
            payload["effort"] = override.effort
        if override.reasoning_effort is not None:
            payload["reasoning_effort"] = override.reasoning_effort
        return payload

    def _default_execution_profile_payload(
        self,
        operation: OperationState,
        adapter_key: str,
    ) -> dict[str, object] | None:
        raw_snapshot = operation.goal.metadata.get("effective_adapter_settings")
        if not isinstance(raw_snapshot, dict):
            return None
        raw_adapter = raw_snapshot.get(adapter_key)
        if not isinstance(raw_adapter, dict):
            return None
        model = raw_adapter.get("model")
        if not isinstance(model, str) or not model.strip():
            return None
        payload: dict[str, object] = {
            "adapter_key": adapter_key,
            "model": model.strip(),
        }
        if adapter_key == "codex_acp":
            raw_effort = raw_adapter.get("reasoning_effort")
            payload["effort_field_name"] = "reasoning_effort"
            payload["effort_value"] = (
                raw_effort.strip()
                if isinstance(raw_effort, str) and raw_effort.strip()
                else None
            )
            if payload["effort_value"] is not None:
                payload["reasoning_effort"] = payload["effort_value"]
            return payload
        raw_effort = raw_adapter.get("effort")
        if adapter_key == "claude_acp":
            payload["effort_field_name"] = "effort"
            payload["effort_value"] = (
                raw_effort.strip()
                if isinstance(raw_effort, str) and raw_effort.strip()
                else None
            )
            if payload["effort_value"] is not None:
                payload["effort"] = payload["effort_value"]
            return payload
        if isinstance(raw_effort, str) and raw_effort.strip():
            payload["effort"] = raw_effort.strip()
        return payload

    def _allowed_execution_profiles_payload(
        self,
        operation: OperationState,
        adapter_key: str,
    ) -> list[dict[str, object]]:
        raw_map = operation.goal.metadata.get("allowed_execution_profiles")
        if not isinstance(raw_map, dict):
            return []
        raw_profiles = raw_map.get(adapter_key)
        if not isinstance(raw_profiles, list):
            return []
        return [item for item in raw_profiles if isinstance(item, dict)]

    def _execution_profile_view_payload(
        self,
        operation: OperationState,
        adapter_key: str,
    ) -> dict[str, object]:
        override = operation.execution_profile_overrides.get(adapter_key)
        default_payload = self._default_execution_profile_payload(operation, adapter_key)
        overlay_payload = (
            self._execution_profile_override_payload(override) if override is not None else None
        )
        return {
            "adapter_key": adapter_key,
            "default": default_payload,
            "overlay": overlay_payload,
            "effective": overlay_payload if overlay_payload is not None else default_payload,
            "allowed_models": self._allowed_execution_profiles_payload(operation, adapter_key),
        }

    def _execution_profiles_payload(self, operation: OperationState) -> dict[str, object]:
        adapter_keys = set(operation.policy.allowed_agents)
        adapter_keys.update(operation.execution_profile_overrides)
        raw_snapshot = operation.goal.metadata.get("effective_adapter_settings")
        if isinstance(raw_snapshot, dict):
            adapter_keys.update(
                key for key in raw_snapshot if isinstance(key, str) and key.strip()
            )
        raw_allowed = operation.goal.metadata.get("allowed_execution_profiles")
        if isinstance(raw_allowed, dict):
            adapter_keys.update(
                key for key in raw_allowed if isinstance(key, str) and key.strip()
            )
        return {
            adapter_key: self._execution_profile_view_payload(operation, adapter_key)
            for adapter_key in sorted(adapter_keys)
        }

    def _external_ticket_payload(self, ticket) -> dict[str, object]:
        return {
            "provider": ticket.provider,
            "project_key": ticket.project_key,
            "ticket_id": ticket.ticket_id,
            "url": ticket.url,
            "title": ticket.title,
            "reported": ticket.reported,
        }

    def _objective_payload(self, objective) -> dict[str, object]:
        return {
            "objective_id": objective.objective_id,
            "objective": objective.objective,
            "harness_instructions": objective.harness_instructions,
            "success_criteria": list(objective.success_criteria),
            "metadata": dict(objective.metadata),
            "summary": objective.summary,
            "root_task_id": objective.root_task_id,
        }

    def _task_payload(self, task: TaskState) -> dict[str, object]:
        return {
            "task_id": task.task_id,
            "task_short_id": task.task_short_id,
            "title": task.title,
            "goal": task.goal,
            "definition_of_done": task.definition_of_done,
            "status": task.status.value,
            "brain_priority": task.brain_priority,
            "effective_priority": task.effective_priority,
            "feature_id": task.feature_id,
            "dependencies": list(task.dependencies),
            "assigned_agent": task.assigned_agent,
            "linked_session_id": task.linked_session_id,
            "session_policy": task.session_policy.value,
            "memory_refs": list(task.memory_refs),
            "artifact_refs": list(task.artifact_refs),
            "attempt_count": task.attempt_count,
            "notes": list(task.notes),
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        }

    def task_payload(self, task: TaskState) -> dict[str, object]:
        return self._task_payload(task)

    def _artifact_payload(self, artifact) -> dict[str, object]:
        return {
            "artifact_id": artifact.artifact_id,
            "kind": artifact.kind,
            "producer": artifact.producer,
            "task_id": artifact.task_id,
            "session_id": artifact.session_id,
            "content": artifact.content,
            "raw_ref": artifact.raw_ref,
            "created_at": artifact.created_at.isoformat(),
        }

    def artifact_payload(self, artifact) -> dict[str, object]:
        return self._artifact_payload(artifact)

    def _feature_payload(self, feature) -> dict[str, object]:
        return {
            "feature_id": feature.feature_id,
            "title": feature.title,
            "acceptance_criteria": feature.acceptance_criteria,
            "status": feature.status.value,
            "notes": list(feature.notes),
            "created_at": feature.created_at.isoformat(),
            "updated_at": feature.updated_at.isoformat(),
        }

    def _memory_source_ref_payload(self, source_ref) -> dict[str, object]:
        return {
            "kind": source_ref.kind,
            "ref_id": source_ref.ref_id,
        }

    def _memory_entry_payload(self, entry: MemoryEntry) -> dict[str, object]:
        return {
            "memory_id": entry.memory_id,
            "scope": entry.scope.value,
            "scope_id": entry.scope_id,
            "summary": entry.summary,
            "source_refs": [self._memory_source_ref_payload(item) for item in entry.source_refs],
            "freshness": entry.freshness.value,
            "superseded_by": entry.superseded_by,
            "created_at": entry.created_at.isoformat(),
            "updated_at": entry.updated_at.isoformat(),
        }

    def memory_entry_payload(self, entry: MemoryEntry) -> dict[str, object]:
        return self._memory_entry_payload(entry)

    def _operator_message_payload(self, message) -> dict[str, object]:
        return {
            "message_id": message.message_id,
            "submitted_at": message.submitted_at.isoformat(),
            "text": message.text,
            "source_command_id": message.source_command_id,
            "applied_at": (
                message.applied_at.isoformat() if message.applied_at is not None else None
            ),
            "dropped_from_context": message.dropped_from_context,
            "planning_cycles_active": message.planning_cycles_active,
        }

    def _agenda_item_payload(self, item) -> dict[str, object]:
        return {
            "operation_id": item.operation_id,
            "bucket": item.bucket.value,
            "status": item.status.value,
            "objective_brief": item.objective_brief,
            "project_profile_name": item.project_profile_name,
            "policy_scope": item.policy_scope,
            "scheduler_state": item.scheduler_state.value,
            "involvement_level": item.involvement_level.value,
            "focus_brief": item.focus_brief,
            "latest_outcome_brief": item.latest_outcome_brief,
            "blocker_brief": item.blocker_brief,
            "runtime_alert": item.runtime_alert,
            "open_attention_count": item.open_attention_count,
            "open_blocking_attention_count": item.open_blocking_attention_count,
            "open_nonblocking_attention_count": item.open_nonblocking_attention_count,
            "attention_titles": list(item.attention_titles),
            "attention_briefs": list(item.attention_briefs),
            "blocking_attention_titles": list(item.blocking_attention_titles),
            "nonblocking_attention_titles": list(item.nonblocking_attention_titles),
            "runnable_task_count": item.runnable_task_count,
            "reusable_session_count": item.reusable_session_count,
            "updated_at": item.updated_at.isoformat(),
        }

    def _project_profile_mcp_server_payload(self, server) -> dict[str, object]:
        return {
            "name": server.name,
            "command": server.command,
            "args": list(server.args),
            "env": dict(server.env),
            "url": server.url,
            "cwd": str(server.cwd) if server.cwd is not None else None,
        }

    def _project_profile_adapter_settings_payload(self, settings) -> dict[str, object]:
        payload = {
            "timeout_seconds": settings.timeout_seconds,
            "mcp_servers": [
                self._project_profile_mcp_server_payload(item) for item in settings.mcp_servers
            ],
            "allowed_models": [
                {
                    "model": item.model,
                    "effort": item.effort,
                    "reasoning_effort": item.reasoning_effort,
                }
                for item in settings.allowed_models
            ],
        }
        extra = getattr(settings, "__pydantic_extra__", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return payload

    def _ticket_reporting_payload(self, reporting) -> dict[str, object]:
        return {
            "on_success": reporting.on_success,
            "on_failure": reporting.on_failure,
            "on_cancelled": reporting.on_cancelled,
            "webhook_url": reporting.webhook_url,
            "intake_hook": (
                str(reporting.intake_hook) if reporting.intake_hook is not None else None
            ),
        }

    def _project_profile_payload(self, profile: ProjectProfile) -> dict[str, object]:
        return {
            "name": profile.name,
            "cwd": str(profile.cwd) if profile.cwd is not None else None,
            "paths": [str(item) for item in profile.paths],
            "history_ledger": profile.history_ledger,
            "default_objective": profile.default_objective,
            "default_agents": list(profile.default_agents),
            "default_harness_instructions": profile.default_harness_instructions,
            "default_success_criteria": list(profile.default_success_criteria),
            "default_max_iterations": profile.default_max_iterations,
            "default_run_mode": (
                profile.default_run_mode.value if profile.default_run_mode is not None else None
            ),
            "default_involvement_level": (
                profile.default_involvement_level.value
                if profile.default_involvement_level is not None
                else None
            ),
            "adapter_settings": {
                key: self._project_profile_adapter_settings_payload(value)
                for key, value in profile.adapter_settings.items()
            },
            "dashboard_prefs": dict(profile.dashboard_prefs),
            "session_reuse_policy": (
                profile.session_reuse_policy.value
                if profile.session_reuse_policy is not None
                else None
            ),
            "default_message_window": profile.default_message_window,
            "ticket_reporting": self._ticket_reporting_payload(profile.ticket_reporting),
        }

    def resolved_project_run_config_payload(self, resolved) -> dict[str, object]:
        return {
            "profile_name": resolved.profile_name,
            "cwd": str(resolved.cwd) if resolved.cwd is not None else None,
            "history_ledger": resolved.history_ledger,
            "objective_text": resolved.objective_text,
            "default_agents": list(resolved.default_agents),
            "harness_instructions": resolved.harness_instructions,
            "success_criteria": list(resolved.success_criteria),
            "max_iterations": resolved.max_iterations,
            "run_mode": resolved.run_mode.value,
            "involvement_level": resolved.involvement_level.value,
            "session_reuse_policy": resolved.session_reuse_policy.value,
            "message_window": resolved.message_window,
            "overrides": list(resolved.overrides),
        }

    def _agent_turn_summary_payload(self, summary) -> dict[str, object]:
        return {
            "declared_goal": summary.declared_goal,
            "actual_work_done": summary.actual_work_done,
            "route_or_target_chosen": summary.route_or_target_chosen,
            "repo_changes": list(summary.repo_changes),
            "progress_class": summary.progress_class,
            "blocker_keys": list(summary.blocker_keys),
            "state_delta": summary.state_delta,
            "verification_status": summary.verification_status,
            "remaining_blockers": list(summary.remaining_blockers),
            "recommended_next_step": summary.recommended_next_step,
            "rationale": summary.rationale,
        }

    def _typed_refs_payload(self, refs) -> dict[str, object] | None:
        if refs is None:
            return None
        return {
            "operation_id": refs.operation_id,
            "iteration": refs.iteration,
            "task_id": refs.task_id,
            "session_id": refs.session_id,
            "artifact_id": refs.artifact_id,
            "command_id": refs.command_id,
        }

    def _operation_brief_payload(self, brief) -> dict[str, object]:
        return {
            "operation_id": brief.operation_id,
            "status": brief.status.value,
            "scheduler_state": brief.scheduler_state.value,
            "involvement_level": brief.involvement_level.value,
            "objective_brief": brief.objective_brief,
            "harness_brief": brief.harness_brief,
            "focus_brief": brief.focus_brief,
            "latest_outcome_brief": brief.latest_outcome_brief,
            "blocker_brief": brief.blocker_brief,
            "runtime_alert_brief": brief.runtime_alert_brief,
            "updated_at": brief.updated_at.isoformat(),
        }

    def operation_brief_payload(self, brief) -> dict[str, object]:
        return self._operation_brief_payload(brief)

    def _iteration_brief_payload(self, brief) -> dict[str, object]:
        return {
            "iteration": brief.iteration,
            "task_id": brief.task_id,
            "session_id": brief.session_id,
            "operator_intent_brief": brief.operator_intent_brief,
            "assignment_brief": brief.assignment_brief,
            "result_brief": brief.result_brief,
            "status_brief": brief.status_brief,
            "refs": self._typed_refs_payload(brief.refs),
            "created_at": brief.created_at.isoformat(),
        }

    def iteration_brief_payload(self, brief) -> dict[str, object]:
        return self._iteration_brief_payload(brief)

    def _execution_handle_ref_payload(self, handle_ref) -> dict[str, object]:
        return {
            "kind": handle_ref.kind,
            "value": handle_ref.value,
            "metadata": dict(handle_ref.metadata),
        }

    def _background_progress_payload(self, progress) -> dict[str, object]:
        return {
            "state": progress.state.value,
            "message": progress.message,
            "updated_at": progress.updated_at.isoformat(),
            "partial_output": progress.partial_output,
            "last_event_at": (
                progress.last_event_at.isoformat() if progress.last_event_at is not None else None
            ),
        }

    def _execution_payload(self, execution) -> dict[str, object]:
        return {
            "execution_id": execution.execution_id,
            "run_id": execution.run_id,
            "operation_id": execution.operation_id,
            "adapter_key": execution.adapter_key,
            "session_id": execution.session_id,
            "task_id": execution.task_id,
            "iteration": execution.iteration,
            "mode": execution.mode.value,
            "launch_kind": execution.launch_kind.value,
            "observed_state": execution.observed_state.value,
            "status": execution.status.value,
            "waiting_reason": execution.waiting_reason,
            "handle_ref": (
                self._execution_handle_ref_payload(execution.handle_ref)
                if execution.handle_ref is not None
                else None
            ),
            "progress": (
                self._background_progress_payload(execution.progress)
                if execution.progress is not None
                else None
            ),
            "result_ref": execution.result_ref,
            "error_ref": execution.error_ref,
            "pid": execution.pid,
            "started_at": execution.started_at.isoformat(),
            "last_heartbeat_at": (
                execution.last_heartbeat_at.isoformat()
                if execution.last_heartbeat_at is not None
                else None
            ),
            "completed_at": (
                execution.completed_at.isoformat() if execution.completed_at is not None else None
            ),
            "raw_ref": execution.raw_ref,
        }

    def _wakeup_payload(self, wakeup) -> dict[str, object]:
        return {
            "event_id": wakeup.event_id,
            "event_type": wakeup.event_type,
            "task_id": wakeup.task_id,
            "session_id": wakeup.session_id,
            "dedupe_key": wakeup.dedupe_key,
            "claimed_at": wakeup.claimed_at.isoformat() if wakeup.claimed_at is not None else None,
            "acked_at": wakeup.acked_at.isoformat() if wakeup.acked_at is not None else None,
            "created_at": wakeup.created_at.isoformat(),
        }

    def _blocking_focus_payload(self, focus) -> dict[str, object]:
        return {
            "kind": focus.kind.value,
            "target_id": focus.target_id,
            "blocking_reason": focus.blocking_reason,
            "interrupt_policy": focus.interrupt_policy.value,
            "resume_policy": focus.resume_policy.value,
        }

    def _feature_draft_payload(self, draft) -> dict[str, object]:
        return {
            "title": draft.title,
            "acceptance_criteria": draft.acceptance_criteria,
            "notes": list(draft.notes),
        }

    def _feature_patch_payload(self, patch) -> dict[str, object]:
        return {
            "feature_id": patch.feature_id,
            "title": patch.title,
            "acceptance_criteria": patch.acceptance_criteria,
            "status": patch.status.value if patch.status is not None else None,
            "append_notes": list(patch.append_notes),
        }

    def _task_draft_payload(self, draft) -> dict[str, object]:
        return {
            "title": draft.title,
            "goal": draft.goal,
            "definition_of_done": draft.definition_of_done,
            "brain_priority": draft.brain_priority,
            "feature_id": draft.feature_id,
            "assigned_agent": draft.assigned_agent,
            "session_policy": draft.session_policy.value,
            "dependencies": list(draft.dependencies),
            "notes": list(draft.notes),
        }

    def _task_patch_payload(self, patch) -> dict[str, object]:
        return {
            "task_id": patch.task_id,
            "title": patch.title,
            "goal": patch.goal,
            "definition_of_done": patch.definition_of_done,
            "status": patch.status.value if patch.status is not None else None,
            "brain_priority": patch.brain_priority,
            "assigned_agent": patch.assigned_agent,
            "linked_session_id": patch.linked_session_id,
            "session_policy": (
                patch.session_policy.value if patch.session_policy is not None else None
            ),
            "append_notes": list(patch.append_notes),
            "add_memory_refs": list(patch.add_memory_refs),
            "add_artifact_refs": list(patch.add_artifact_refs),
            "add_dependencies": list(patch.add_dependencies),
            "remove_dependencies": list(patch.remove_dependencies),
            "dependency_removal_reason": patch.dependency_removal_reason,
        }

    def _brain_decision_payload(self, decision) -> dict[str, object]:
        return {
            "action_type": decision.action_type.value,
            "target_agent": decision.target_agent,
            "session_id": decision.session_id,
            "session_name": decision.session_name,
            "one_shot": decision.one_shot,
            "workfront_key": decision.workfront_key,
            "instruction": decision.instruction,
            "rationale": decision.rationale,
            "confidence": decision.confidence,
            "assumptions": list(decision.assumptions),
            "expected_outcome": decision.expected_outcome,
            "focus_task_id": decision.focus_task_id,
            "new_features": [self._feature_draft_payload(item) for item in decision.new_features],
            "feature_updates": [
                self._feature_patch_payload(item) for item in decision.feature_updates
            ],
            "new_tasks": [self._task_draft_payload(item) for item in decision.new_tasks],
            "task_updates": [self._task_patch_payload(item) for item in decision.task_updates],
            "blocking_focus": (
                self._blocking_focus_payload(decision.blocking_focus)
                if decision.blocking_focus is not None
                else None
            ),
            "metadata": dict(decision.metadata),
        }

    def _agent_session_handle_payload(self, handle) -> dict[str, object]:
        return {
            "adapter_key": handle.adapter_key,
            "session_id": handle.session_id,
            "session_name": handle.session_name,
            "display_name": handle.display_name,
            "one_shot": handle.one_shot,
            "metadata": dict(handle.metadata),
        }

    def _agent_artifact_payload(self, artifact) -> dict[str, object]:
        return {
            "name": artifact.name,
            "kind": artifact.kind,
            "uri": artifact.uri,
            "content": artifact.content,
            "metadata": dict(artifact.metadata),
        }

    def _agent_error_payload(self, error) -> dict[str, object]:
        return {
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
            "raw": dict(error.raw) if error.raw is not None else None,
        }

    def _agent_usage_payload(self, usage) -> dict[str, object]:
        return {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "context_window_size": usage.context_window_size,
            "context_tokens_used": usage.context_tokens_used,
            "cost_amount": usage.cost_amount,
            "cost_currency": usage.cost_currency,
            "metadata": dict(usage.metadata),
        }

    def _agent_result_payload(self, result) -> dict[str, object]:
        return {
            "session_id": result.session_id,
            "status": result.status.value,
            "output_text": result.output_text,
            "artifacts": [self._agent_artifact_payload(item) for item in result.artifacts],
            "error": self._agent_error_payload(result.error) if result.error is not None else None,
            "completed_at": (
                result.completed_at.isoformat() if result.completed_at is not None else None
            ),
            "structured_output": (
                dict(result.structured_output) if result.structured_output is not None else None
            ),
            "usage": self._agent_usage_payload(result.usage) if result.usage is not None else None,
            "transcript": result.transcript,
            "raw": dict(result.raw) if result.raw is not None else None,
        }

    def _run_event_payload(self, event: RunEvent) -> dict[str, object]:
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "kind": event.kind.value,
            "category": event.category,
            "operation_id": event.operation_id,
            "iteration": event.iteration,
            "task_id": event.task_id,
            "session_id": event.session_id,
            "dedupe_key": event.dedupe_key,
            "timestamp": event.timestamp.isoformat(),
            "not_before": event.not_before.isoformat() if event.not_before is not None else None,
            "payload": dict(event.payload),
        }

    def _iteration_payload(self, iteration) -> dict[str, object]:
        return {
            "index": iteration.index,
            "decision": (
                self._brain_decision_payload(iteration.decision)
                if iteration.decision is not None
                else None
            ),
            "task_id": iteration.task_id,
            "session": (
                self._agent_session_handle_payload(iteration.session)
                if iteration.session is not None
                else None
            ),
            "result": (
                self._agent_result_payload(iteration.result)
                if iteration.result is not None
                else None
            ),
            "turn_summary": (
                self._agent_turn_summary_payload(iteration.turn_summary)
                if iteration.turn_summary is not None
                else None
            ),
            "notes": list(iteration.notes),
        }

    def _agent_turn_brief_payload(self, turn: AgentTurnBrief) -> dict[str, object]:
        return {
            "operation_id": turn.operation_id,
            "iteration": turn.iteration,
            "agent_key": turn.agent_key,
            "session_id": turn.session_id,
            "background_run_id": turn.background_run_id,
            "session_display_name": turn.session_display_name,
            "assignment_brief": turn.assignment_brief,
            "expected_outcome": turn.expected_outcome,
            "result_brief": turn.result_brief,
            "turn_summary": (
                self._agent_turn_summary_payload(turn.turn_summary)
                if turn.turn_summary is not None
                else None
            ),
            "status": turn.status,
            "artifact_refs": list(turn.artifact_refs),
            "raw_log_refs": list(turn.raw_log_refs),
            "wakeup_refs": list(turn.wakeup_refs),
            "created_at": turn.created_at.isoformat(),
        }

    def agent_turn_brief_payload(self, turn: AgentTurnBrief) -> dict[str, object]:
        return self._agent_turn_brief_payload(turn)

    def brief_bundle_payload(self, brief: TraceBriefBundle) -> dict[str, object]:
        return {
            "operation_brief": (
                self._operation_brief_payload(brief.operation_brief)
                if brief.operation_brief is not None
                else None
            ),
            "iteration_briefs": [
                self._iteration_brief_payload(item) for item in brief.iteration_briefs
            ],
            "agent_turn_briefs": [
                self._agent_turn_brief_payload(item) for item in brief.agent_turn_briefs
            ],
        }

    def outcome_payload(self, outcome: OperationOutcome) -> dict[str, object]:
        return {
            "operation_id": outcome.operation_id,
            "status": outcome.status.value,
            "summary": outcome.summary,
            "ended_at": outcome.ended_at.isoformat() if outcome.ended_at is not None else None,
        }

    def operation_payload(self, operation: OperationState) -> dict[str, object]:
        return {
            "schema_version": operation.schema_version,
            "operation_id": operation.operation_id,
            "canonical_persistence_mode": operation.canonical_persistence_mode.value,
            "goal": {
                "objective": operation.goal.objective,
                "harness_instructions": operation.goal.harness_instructions,
                "success_criteria": list(operation.goal.success_criteria),
                "metadata": dict(operation.goal.metadata),
                "external_ticket": (
                    self._external_ticket_payload(operation.goal.external_ticket)
                    if operation.goal.external_ticket is not None
                    else None
                ),
            },
            "policy": {
                "allowed_agents": list(operation.policy.allowed_agents),
                "involvement_level": operation.policy.involvement_level.value,
            },
            "execution_profiles": self._execution_profiles_payload(operation),
            "active_session_execution_profile": self._active_session_execution_profile_payload(
                operation
            ),
            "execution_budget": {
                "max_iterations": operation.execution_budget.max_iterations,
                "timeout_seconds": operation.execution_budget.timeout_seconds,
                "max_task_retries": operation.execution_budget.max_task_retries,
            },
            "runtime_hints": {
                "operator_message_window": operation.runtime_hints.operator_message_window,
                "metadata": dict(operation.runtime_hints.metadata),
            },
            "objective": (
                self._objective_payload(operation.objective_state)
                if operation.objective is not None
                else None
            ),
            "status": operation.status.value,
            "iterations": [self._iteration_payload(item) for item in operation.iterations],
            "features": [self._feature_payload(item) for item in operation.features],
            "tasks": [self._task_payload(item) for item in operation.tasks],
            "sessions": [self.session_payload(item) for item in operation.sessions],
            "executions": [self._execution_payload(item) for item in operation.executions],
            "artifacts": [self._artifact_payload(item) for item in operation.artifacts],
            "memory_entries": [
                self._memory_entry_payload(item) for item in operation.memory_entries
            ],
            "operation_brief": (
                self._operation_brief_payload(operation.operation_brief)
                if operation.operation_brief is not None
                else None
            ),
            "iteration_briefs": [
                self._iteration_brief_payload(item) for item in operation.iteration_briefs
            ],
            "agent_turn_briefs": [
                self._agent_turn_brief_payload(item) for item in operation.agent_turn_briefs
            ],
            "current_focus": (
                self._focus_payload(operation.current_focus)
                if operation.current_focus is not None
                else None
            ),
            "pending_wakeups": [self._wakeup_payload(item) for item in operation.pending_wakeups],
            "attention_requests": [
                self._attention_payload(item) for item in operation.attention_requests
            ],
            "active_policies": [self._policy_payload(item) for item in operation.active_policies],
            "policy_coverage": self._policy_coverage_payload(operation.policy_coverage),
            "involvement_level": operation.involvement_level.value,
            "scheduler_state": operation.scheduler_state.value,
            "operator_messages": [
                self._operator_message_payload(item) for item in operation.operator_messages
            ],
            "processed_command_ids": list(operation.processed_command_ids),
            "pending_replan_command_ids": list(operation.pending_replan_command_ids),
            "pending_attention_resolution_ids": list(operation.pending_attention_resolution_ids),
            "final_summary": operation.final_summary,
            "run_started_at": (
                operation.run_started_at.isoformat()
                if operation.run_started_at is not None
                else None
            ),
            "created_at": operation.created_at.isoformat(),
            "updated_at": operation.updated_at.isoformat(),
        }

    def resolve_run_mode(self, operation: OperationState) -> str:
        raw_mode = operation.runtime_hints.metadata.get("continuity_run_mode")
        if isinstance(raw_mode, str) and raw_mode.strip():
            return raw_mode.strip()
        raw_mode = operation.runtime_hints.metadata.get("run_mode")
        if isinstance(raw_mode, str) and raw_mode.strip():
            return raw_mode.strip()
        return RunMode.ATTACHED.value

    def resolve_invocation_run_mode(self, operation: OperationState) -> str:
        raw_mode = operation.runtime_hints.metadata.get("invocation_run_mode")
        if isinstance(raw_mode, str) and raw_mode.strip():
            return raw_mode.strip()
        return self.resolve_run_mode(operation)

    def resolve_background_runtime_mode(self, operation: OperationState) -> str | None:
        raw_mode = operation.runtime_hints.metadata.get("continuity_background_runtime_mode")
        if isinstance(raw_mode, str) and raw_mode.strip():
            return raw_mode.strip()
        raw_mode = operation.runtime_hints.metadata.get("background_runtime_mode")
        if isinstance(raw_mode, str) and raw_mode.strip():
            return raw_mode.strip()
        return None

    def resolve_invocation_background_runtime_mode(self, operation: OperationState) -> str | None:
        raw_mode = operation.runtime_hints.metadata.get("invocation_background_runtime_mode")
        if isinstance(raw_mode, str) and raw_mode.strip():
            return raw_mode.strip()
        return self.resolve_background_runtime_mode(operation)

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
            "tasks": [self._task_payload(task) for task in operation.tasks],
            "memory": {
                "current": [self._memory_entry_payload(entry) for entry in current_memory],
                "inactive": [
                    self._memory_entry_payload(entry)
                    for entry in all_memory
                    if entry.freshness is not MemoryFreshness.CURRENT
                ],
            },
            "artifacts": [self._artifact_payload(artifact) for artifact in operation.artifacts],
        }

    def build_operation_context_payload(self, operation: OperationState) -> dict[str, object]:
        metadata = operation.goal.metadata
        payload: dict[str, object] = {
            "operation_id": operation.operation_id,
            "status": operation.status.value,
            "scheduler_state": operation.scheduler_state.value,
            "run_mode": self.resolve_run_mode(operation),
            "invocation_run_mode": self.resolve_invocation_run_mode(operation),
            "background_runtime_mode": self.resolve_background_runtime_mode(operation),
            "invocation_background_runtime_mode": self.resolve_invocation_background_runtime_mode(
                operation
            ),
            "objective": operation.objective_state.objective,
            "harness_instructions": operation.objective_state.harness_instructions,
            "success_criteria": list(operation.objective_state.success_criteria),
            "allowed_agents": list(operation.policy.allowed_agents),
            "execution_profiles": self._execution_profiles_payload(operation),
            "active_session_execution_profile": self._active_session_execution_profile_payload(
                operation
            ),
            "available_agent_descriptors": self.available_agent_descriptors_payload(operation),
            "max_iterations": operation.execution_budget.max_iterations,
            "involvement_level": operation.involvement_level.value,
        }
        if operation.current_focus is not None:
            payload["current_focus"] = self._focus_payload(operation.current_focus)
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
            self._attention_payload(attention)
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
                metadata.get("policy_scope")
                if isinstance(metadata.get("policy_scope"), str)
                else None
            ),
            "resolved_profile": resolved_profile if isinstance(resolved_profile, dict) else None,
            "resolved_launch": resolved_launch if isinstance(resolved_launch, dict) else None,
        }
        payload["policy_coverage"] = self._policy_coverage_payload(operation.policy_coverage)
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
            "needs_attention": [
                self._agenda_item_payload(item) for item in snapshot.needs_attention
            ],
            "active": [self._agenda_item_payload(item) for item in snapshot.active],
            "recent": [self._agenda_item_payload(item) for item in snapshot.recent],
            "actions": [action.to_payload() for action in self._fleet_actions(snapshot)],
        }

    def build_fleet_workbench_payload(
        self,
        snapshot: AgendaSnapshot,
        *,
        project: str | None,
    ) -> dict[str, object]:
        items = self._ordered_fleet_workbench_items(snapshot)
        return FleetWorkbenchPayload(
            project=project,
            total_operations=snapshot.total_operations,
            header=self._fleet_workbench_header(snapshot, items),
            rows=[self._build_fleet_workbench_row(item) for item in items],
            control_hints=self._fleet_workbench_control_hints(snapshot),
            actions=[action.to_payload() for action in self._fleet_actions(snapshot)],
            mix={
                "bucket_counts": {
                    "needs_attention": len(snapshot.needs_attention),
                    "active": len(snapshot.active),
                    "recent": len(snapshot.recent),
                },
                "status_counts": self._count_items_by_key(items, lambda item: item.status.value),
                "scheduler_counts": self._count_items_by_key(
                    items,
                    lambda item: item.scheduler_state.value,
                ),
                "involvement_counts": self._count_items_by_key(
                    items,
                    lambda item: item.involvement_level.value,
                ),
            },
        ).to_payload()

    def _ordered_fleet_workbench_items(self, snapshot: AgendaSnapshot) -> list[AgendaItem]:
        return [*snapshot.needs_attention, *snapshot.active, *snapshot.recent]

    def _build_fleet_workbench_row(self, item: AgendaItem) -> dict[str, object]:
        return FleetWorkbenchRow(
            operation_id=item.operation_id,
            attention_badge=self._fleet_workbench_attention_badge(item),
            display_name=self._shorten_text(item.objective_brief, limit=120)
            or item.objective_brief,
            state_label=self._fleet_workbench_state_label(item),
            agent_cue=self._fleet_workbench_agent_cue(item),
            recency_brief=self._fleet_workbench_recency(item),
            row_hint=self._fleet_workbench_row_hint(item),
            sort_bucket=item.bucket.value,
            status=item.status.value,
            scheduler_state=item.scheduler_state.value,
            project_profile_name=item.project_profile_name,
            runtime_alert=item.runtime_alert,
            focus_brief=item.focus_brief,
            latest_outcome_brief=item.latest_outcome_brief,
            blocker_brief=item.blocker_brief,
            open_attention_count=item.open_attention_count,
            open_blocking_attention_count=item.open_blocking_attention_count,
            open_nonblocking_attention_count=item.open_nonblocking_attention_count,
            attention_briefs=tuple(item.attention_briefs),
            attention_titles=tuple(item.attention_titles),
            brief=self._fleet_workbench_brief(item),
        ).to_payload()

    def _fleet_workbench_attention_badge(self, item: AgendaItem) -> str:
        if item.runtime_alert is not None:
            return "!!"
        if item.open_blocking_attention_count > 0:
            return f"B{item.open_blocking_attention_count}"
        if item.open_attention_count > 0:
            return f"A{item.open_attention_count}"
        if item.open_nonblocking_attention_count > 0:
            return f"Q{item.open_nonblocking_attention_count}"
        return "-"

    def _fleet_workbench_state_label(self, item: AgendaItem) -> str:
        if item.scheduler_state is SchedulerState.ACTIVE:
            return item.status.value
        return f"{item.status.value}/{item.scheduler_state.value}"

    def _fleet_workbench_agent_cue(self, item: AgendaItem) -> str:
        if item.project_profile_name:
            return f"profile:{item.project_profile_name}"
        if item.policy_scope:
            return item.policy_scope
        return "-"

    def _fleet_workbench_recency(self, item: AgendaItem) -> str:
        if item.runtime_alert is not None:
            return self._shorten_text(item.runtime_alert, limit=80) or "runtime alert"
        if item.focus_brief is not None:
            return self._shorten_text(item.focus_brief, limit=80) or "focus"
        if item.latest_outcome_brief is not None:
            return self._shorten_text(item.latest_outcome_brief, limit=80) or "latest outcome"
        return "no recent activity"

    def _fleet_workbench_row_hint(self, item: AgendaItem) -> str:
        if item.runtime_alert is not None:
            return "now: runtime alert"
        if item.scheduler_state in {SchedulerState.PAUSED, SchedulerState.PAUSE_REQUESTED}:
            return "paused"
        if item.status is OperationStatus.NEEDS_HUMAN:
            return "waiting"
        if item.status is OperationStatus.FAILED:
            return "failed"
        if item.status is OperationStatus.COMPLETED:
            return "completed"
        if item.status is OperationStatus.CANCELLED:
            return "cancelled"
        return "running"

    def _fleet_workbench_brief(self, item: AgendaItem) -> SupervisoryActivitySummary:
        return SupervisoryActivitySummary(
            goal=self._shorten_text(item.objective_brief, limit=120) or item.objective_brief,
            now=self._shorten_text(item.focus_brief, limit=120),
            wait=self._shorten_text(
                item.runtime_alert if item.runtime_alert is not None else item.latest_outcome_brief,
                limit=120,
            ),
            progress=SupervisoryProgressSummary(
                done=self._shorten_text(
                    item.blocker_brief if item.status is OperationStatus.COMPLETED else None,
                    limit=120,
                ),
                doing=self._shorten_text(item.latest_outcome_brief, limit=120),
                next=self._shorten_text(
                    item.blocker_brief
                    or (item.attention_titles[0] if item.attention_titles else None),
                    limit=120,
                ),
            ),
            attention=self._shorten_text("; ".join(item.blocking_attention_titles), limit=120),
            review=self._shorten_text("; ".join(item.nonblocking_attention_titles), limit=120),
            recent=self._shorten_text(item.latest_outcome_brief, limit=120),
            agent_activity=self._fleet_workbench_agent_activity(item),
            operator_state=self._scheduler_operator_state(item.scheduler_state),
        )

    def _fleet_workbench_agent_activity(self, item: AgendaItem) -> str | None:
        if item.status is not OperationStatus.RUNNING:
            return None
        if item.reusable_session_count > 1:
            return f"{item.reusable_session_count} reusable sessions"
        if item.reusable_session_count == 1:
            return "1 reusable session"
        return None

    def _fleet_workbench_control_hints(self, snapshot: AgendaSnapshot) -> list[str]:
        hints: list[str] = []
        for action in self._fleet_actions(snapshot):
            command = action.cli_command
            if isinstance(command, str) and command not in hints:
                hints.append(command)
        return hints

    def _fleet_workbench_header(
        self,
        snapshot: AgendaSnapshot,
        rows: list[AgendaItem] | list[dict[str, object]],
    ) -> dict[str, object]:
        items = self._ordered_fleet_workbench_items(snapshot)
        all_items = [item for item in items]
        status_counts = self._count_items_by_key(all_items, lambda item: item.status.value)
        scheduler_counts = self._count_items_by_key(
            all_items, lambda item: item.scheduler_state.value
        )
        bucket_counts = {
            "needs_attention": len(snapshot.needs_attention),
            "active": len(snapshot.active),
            "recent": len(snapshot.recent),
        }
        header_rows = len(rows)
        return {
            "total_operations": snapshot.total_operations,
            "bucket_counts": bucket_counts,
            "status_counts": status_counts,
            "scheduler_counts": scheduler_counts,
            "active_count": self._count_items(
                all_items, lambda item: item.status is OperationStatus.RUNNING
            ),
            "needs_human_count": self._count_items(
                all_items, lambda item: item.status is OperationStatus.NEEDS_HUMAN
            ),
            "running_count": self._count_items(
                all_items, lambda item: item.status is OperationStatus.RUNNING
            ),
            "paused_count": self._count_items(
                all_items,
                lambda item: (
                    item.scheduler_state in {SchedulerState.PAUSED, SchedulerState.PAUSE_REQUESTED}
                ),
            ),
            "rows_count": header_rows,
            "operator_load": None,
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
            "profile": self._project_profile_payload(profile),
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
            "latest_turn": (
                self._agent_turn_brief_payload(latest_turn) if latest_turn is not None else None
            ),
            "work_summary": self._turn_work_summary(latest_turn),
            "next_step": self._turn_next_step(latest_turn),
            "verification_summary": self._turn_verification_summary(latest_turn),
            "blockers_summary": self._turn_blockers_summary(latest_turn),
            "runtime_alert": runtime_alert,
        }

    def build_operation_brief_payload(
        self,
        operation: OperationState,
        brief: TraceBriefBundle | None,
        *,
        runtime_alert: str | None,
    ) -> dict[str, object]:
        brief = brief or TraceBriefBundle()
        operation_brief = brief.operation_brief
        latest_turn = self._latest_agent_turn_brief(brief)
        open_attention = [
            attention.title
            for attention in operation.attention_requests
            if attention.status is AttentionStatus.OPEN
        ]
        blocking_attention = [
            attention.title
            for attention in operation.attention_requests
            if attention.status is AttentionStatus.OPEN and attention.blocking
        ]
        nonblocking_attention = [
            attention.title
            for attention in operation.attention_requests
            if attention.status is AttentionStatus.OPEN and not attention.blocking
        ]
        progress_done = self._turn_verification_summary(latest_turn)
        if operation.status is OperationStatus.COMPLETED:
            progress_done = (
                self._shorten_text(operation.final_summary, limit=120)
                or progress_done
                or self._shorten_text(operation.objective_state.objective, limit=120)
            )
        progress_doing = self._turn_work_summary(latest_turn)
        progress_next = self._turn_next_step(latest_turn)
        if progress_doing is None and operation_brief is not None:
            progress_doing = self._shorten_text(operation_brief.latest_outcome_brief, limit=120)
            if progress_next is None:
                progress_next = self._shorten_text(operation_brief.blocker_brief, limit=120)
        if progress_done is None and operation_brief is not None:
            progress_done = (
                self._shorten_text(operation_brief.blocker_brief, limit=120)
                if operation.status is OperationStatus.COMPLETED
                else None
            )

        wait = runtime_alert
        if not wait:
            if operation_brief is not None and operation_brief.runtime_alert_brief is not None:
                wait = self._shorten_text(operation_brief.runtime_alert_brief, limit=120)
            elif open_attention:
                wait = self._shorten_text("; ".join(open_attention[:2]), limit=120)

        summary = SupervisoryActivitySummary(
            goal=self._shorten_text(
                operation_brief.objective_brief
                if operation_brief is not None
                else operation.objective_state.objective,
                limit=120,
            ),
            now=self._shorten_text(
                operation_brief.focus_brief if operation_brief is not None else None,
                limit=120,
            )
            or self._shorten_text(operation.final_summary, limit=120)
            or self._shorten_text(operation.objective_state.objective, limit=120),
            wait=self._shorten_text(wait, limit=120),
            progress=SupervisoryProgressSummary(
                done=progress_done,
                doing=progress_doing,
                next=progress_next,
            ),
            attention=(self._shorten_text("; ".join(blocking_attention), limit=220) or ""),
            review=(self._shorten_text("; ".join(nonblocking_attention), limit=220) or ""),
            recent=self._shorten_text(
                self._turn_work_summary(latest_turn)
                or (operation_brief.latest_outcome_brief if operation_brief is not None else None)
                or self._shorten_text(operation.final_summary, limit=120),
                limit=120,
            ),
            agent_activity=self._operation_agent_activity(operation),
            operator_state=self._scheduler_operator_state(operation.scheduler_state),
        )
        return summary.to_payload()

    def build_session_brief_payload(
        self,
        *,
        session: SessionRecord,
        timeline: list[dict[str, object]],
        blocking_attention_titles: list[str],
        nonblocking_attention_titles: list[str],
    ) -> dict[str, object]:
        wait = self._shorten_text(session.waiting_reason, limit=120)
        latest_output = "-"
        for event in reversed(timeline):
            summary = event.get("summary")
            if isinstance(summary, str) and summary.strip():
                latest_output = self._shorten_text(summary, limit=160) or summary.strip()
                break
        if wait is not None:
            lowered = wait.lower()
            now = wait if "working" in lowered or "running" in lowered else session.status.value
        elif session.status.value == "running":
            now = "Agent turn running"
        else:
            now = session.status.value
        return SupervisoryActivitySummary(
            goal=None,
            now=now,
            wait=wait or session.status.value,
            progress=SupervisoryProgressSummary(done=None, doing=latest_output, next=None),
            attention="; ".join(blocking_attention_titles[:2])
            if blocking_attention_titles
            else "-",
            review=(
                "; ".join(nonblocking_attention_titles[:2])
                if nonblocking_attention_titles
                else None
            ),
            recent=latest_output,
            agent_activity=f"{session.adapter_key} session",
            operator_state=self._session_operator_state(session),
        ).to_payload() | {"latest_output": latest_output}

    def build_session_view_payload(
        self,
        *,
        operation_id: str,
        task: TaskState,
        session: SessionRecord,
        events: list[RunEvent],
        open_attention: list[AttentionRequest],
    ) -> dict[str, object]:
        timeline = [
            {
                "event_type": event.event_type,
                "iteration": event.iteration,
                "task_id": event.task_id,
                "session_id": event.session_id,
                "timestamp": event.timestamp.isoformat(),
                "summary": self._format_live_event(event) or event.event_type,
                "detail": self._build_session_event_detail(event),
            }
            for event in events
        ]
        selected_event = timeline[-1] if timeline else None
        blocking_attention_titles = [
            attention.title
            for attention in open_attention
            if attention.target_id == task.task_id and attention.blocking
        ]
        nonblocking_attention_titles = [
            attention.title
            for attention in open_attention
            if attention.target_id == task.task_id and not attention.blocking
        ]
        return {
            "task_id": task.task_id,
            "task_short_id": f"task-{task.task_short_id}",
            "task_title": task.title,
            "session": {
                "session_id": session.session_id,
                "adapter_key": session.adapter_key,
                "status": session.status.value,
                "session_name": session.handle.session_name,
                "display_name": session.handle.display_name,
                "waiting_reason": session.waiting_reason,
                "bound_task_ids": list(session.bound_task_ids),
            },
            "session_brief": self.build_session_brief_payload(
                session=session,
                timeline=timeline,
                blocking_attention_titles=blocking_attention_titles,
                nonblocking_attention_titles=nonblocking_attention_titles,
            ),
            "timeline": timeline,
            "selected_event": selected_event,
            "transcript_hint": {
                "command": (
                    f"operator log {operation_id} --agent "
                    f"{self._session_agent_hint(session.adapter_key) or 'auto'}"
                )
            },
        }

    def _build_session_event_detail(self, event: RunEvent) -> dict[str, object]:
        payload = event.payload
        if event.event_type == "agent.invocation.completed":
            artifacts = payload.get("artifacts")
            artifact_items: list[dict[str, object]] = []
            if isinstance(artifacts, list):
                for item in artifacts[:3]:
                    if not isinstance(item, dict):
                        continue
                    artifact_items.append(
                        {
                            "name": item.get("name"),
                            "kind": item.get("kind"),
                            "uri": item.get("uri"),
                            "content": self._shorten_text(
                                self._string_value(item.get("content")),
                                limit=160,
                            ),
                        }
                    )
            return {
                "status": self._string_value(payload.get("status")),
                "output_text": self._shorten_text(
                    self._string_value(payload.get("output_text")),
                    limit=220,
                ),
                "artifacts": artifact_items,
            }
        if event.event_type == "agent.invocation.started":
            return {
                "adapter_key": self._string_value(payload.get("adapter_key")),
                "session_name": self._string_value(payload.get("session_name")),
            }
        return {}

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
            "latest_turn": (
                self._agent_turn_brief_payload(latest_turn) if latest_turn is not None else None
            ),
            "runtime_alert": runtime_alert,
            "active_session_execution_profile": self._active_session_execution_profile_payload(
                operation
            ),
        }

    def _operation_agent_activity(self, operation: OperationState) -> str | None:
        running_sessions = [item for item in operation.sessions if item.status.value == "running"]
        if len(running_sessions) > 1:
            return f"{len(running_sessions)} active sessions"
        if len(running_sessions) == 1:
            return f"{running_sessions[0].adapter_key} active session"
        return None

    def _scheduler_operator_state(self, scheduler_state: SchedulerState) -> str | None:
        if scheduler_state is SchedulerState.PAUSED:
            return "paused"
        if scheduler_state is SchedulerState.PAUSE_REQUESTED:
            return "pause requested"
        if scheduler_state is SchedulerState.DRAINING:
            return "draining"
        return None

    def _session_operator_state(self, session: SessionRecord) -> str | None:
        if session.waiting_reason:
            return "observing"
        if session.status.value == "running":
            return "following"
        return None

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
        report_text: str | None,
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
        open_attention_payload = [
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
        ]
        timeline_events = [
            {
                "event_type": event.event_type,
                "iteration": event.iteration,
                "task_id": event.task_id,
                "session_id": event.session_id,
                "summary": self._format_live_event(event) or event.event_type,
            }
            for event in events[-20:]
        ]
        session_views = []
        for task in sorted(
            operation.tasks,
            key=lambda item: (-item.effective_priority, item.created_at, item.task_id),
        ):
            if task.linked_session_id is None:
                continue
            session = next(
                (item for item in operation.sessions if item.session_id == task.linked_session_id),
                None,
            )
            if session is None:
                continue
            relevant_events = [
                event
                for event in events[-20:]
                if event.session_id == session.session_id or event.task_id == task.task_id
            ]
            if not relevant_events:
                relevant_events = list(events[-20:])
            session_views.append(
                self.build_session_view_payload(
                    operation_id=operation.operation_id,
                    task=task,
                    session=session,
                    events=relevant_events,
                    open_attention=open_attention,
                )
            )
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
            "operation_brief": self.build_operation_brief_payload(
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
                    "execution_profile": self._active_session_execution_profile_payload(operation),
                }
                if active_session is not None
                else None
            ),
            "available_agent_descriptors": context_payload.get("available_agent_descriptors"),
            "project_context": context_payload.get("project_context"),
            "policy_coverage": context_payload.get("policy_coverage"),
            "active_policies": context_payload.get("active_policies"),
            "attention": open_attention_payload,
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
                    "execution_profile_stamp": self._execution_profile_stamp_payload(
                        session.execution_profile_stamp
                    ),
                }
                for session in sorted(
                    operation.sessions,
                    key=lambda item: (item.created_at, item.session_id),
                )
            ],
            "recent_events": recent_events,
            "timeline_events": timeline_events,
            "session_views": session_views,
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
            "report_text": report_text,
            "codex_log": (
                list(upstream_transcript.get("events"))
                if isinstance(upstream_transcript, dict)
                and isinstance(upstream_transcript.get("events"), list)
                and upstream_transcript.get("adapter_key") == "codex_acp"
                else []
            ),
            "actions": [action.to_payload() for action in self._dashboard_actions(operation)],
        }

    def _session_agent_hint(self, adapter_key: str) -> str | None:
        if adapter_key.startswith("claude"):
            return "claude"
        if adapter_key.startswith("opencode"):
            return "opencode"
        if adapter_key.startswith("codex"):
            return "codex"
        return None

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

    def _count_items(self, items: list[AgendaItem], predicate: Callable[[AgendaItem], bool]) -> int:
        return sum(1 for item in items if predicate(item))

    def _fleet_actions(self, snapshot: AgendaSnapshot) -> list[ProjectionAction]:
        actions: list[ProjectionAction] = []

        def add(action: ProjectionAction) -> None:
            if all(existing.cli_command != action.cli_command for existing in actions):
                actions.append(action)

        if snapshot.needs_attention:
            item = snapshot.needs_attention[0]
            add(
                ProjectionAction(
                    "dashboard",
                    "Dashboard",
                    f"operator dashboard {item.operation_id}",
                    "operation",
                    False,
                )
            )
            add(
                ProjectionAction(
                    "context",
                    "Context",
                    f"operator context {item.operation_id}",
                    "operation",
                    False,
                )
            )
            if item.runtime_alert is not None:
                add(
                    ProjectionAction(
                        "resume",
                        "Resume",
                        f"operator resume {item.operation_id}",
                        "operation",
                        False,
                    )
                )
            if item.open_attention_count > 0 or item.status is OperationStatus.NEEDS_HUMAN:
                add(
                    ProjectionAction(
                        "attention",
                        "Attention",
                        f"operator attention {item.operation_id}",
                        "operation",
                        False,
                    )
                )
            if item.scheduler_state in {SchedulerState.PAUSED, SchedulerState.PAUSE_REQUESTED}:
                add(
                    ProjectionAction(
                        "unpause",
                        "Unpause",
                        f"operator unpause {item.operation_id}",
                        "operation",
                        False,
                    )
                )
        if snapshot.active:
            item = snapshot.active[0]
            add(
                ProjectionAction(
                    "dashboard",
                    "Dashboard",
                    f"operator dashboard {item.operation_id}",
                    "operation",
                    False,
                )
            )
            add(
                ProjectionAction(
                    "watch", "Watch", f"operator watch {item.operation_id}", "operation", False
                )
            )
            add(
                ProjectionAction(
                    "context",
                    "Context",
                    f"operator context {item.operation_id}",
                    "operation",
                    False,
                )
            )
            add(
                ProjectionAction(
                    "pause", "Pause", f"operator pause {item.operation_id}", "operation", False
                )
            )
        if snapshot.recent:
            item = snapshot.recent[0]
            add(
                ProjectionAction(
                    "report", "Report", f"operator report {item.operation_id}", "operation", False
                )
            )
        return actions

    def _project_dashboard_actions(
        self,
        project_name: str,
        *,
        fleet: dict[str, object],
    ) -> list[ProjectionAction]:
        actions = [
            ProjectionAction(
                "run",
                "Run",
                f'operator run --project {project_name} "<objective>"',
                "project",
                False,
            ),
            ProjectionAction(
                "project_inspect",
                "Project Inspect",
                f"operator project inspect {project_name}",
                "project",
                False,
            ),
            ProjectionAction(
                "project_resolve",
                "Project Resolve",
                f"operator project resolve {project_name}",
                "project",
                False,
            ),
            ProjectionAction(
                "fleet",
                "Fleet",
                f"operator fleet --project {project_name} --all --once",
                "project",
                False,
            ),
            ProjectionAction(
                "policy_list",
                "Policy List",
                f"operator policy list --project profile:{project_name}",
                "project",
                False,
            ),
        ]
        fleet_actions = fleet.get("actions")
        if isinstance(fleet_actions, list):
            for item in fleet_actions:
                if isinstance(item, dict):
                    cli_command = item.get("cli_command")
                    if (
                        isinstance(cli_command, str)
                        and cli_command
                        and all(existing.cli_command != cli_command for existing in actions)
                    ):
                        actions.append(
                            ProjectionAction(
                                str(item.get("key") or "action"),
                                str(item.get("label") or cli_command),
                                cli_command,
                                str(item.get("scope") or "operation"),
                                bool(item.get("destructive", False)),
                                bool(item.get("enabled", True)),
                                str(item.get("reason"))
                                if isinstance(item.get("reason"), str)
                                else None,
                            )
                        )
        return actions

    def _dashboard_actions(self, operation: OperationState) -> list[ProjectionAction]:
        actions = [
            ProjectionAction(
                "context",
                "Context",
                f"operator context {operation.operation_id}",
                "operation",
                False,
            ),
            ProjectionAction(
                "watch", "Watch", f"operator watch {operation.operation_id}", "operation", False
            ),
        ]
        if operation.status is OperationStatus.RUNNING:
            if operation.scheduler_state in {SchedulerState.PAUSED, SchedulerState.PAUSE_REQUESTED}:
                actions.append(
                    ProjectionAction(
                        "unpause",
                        "Unpause",
                        f"operator unpause {operation.operation_id}",
                        "operation",
                        False,
                    )
                )
            else:
                actions.append(
                    ProjectionAction(
                        "pause",
                        "Pause",
                        f"operator pause {operation.operation_id}",
                        "operation",
                        False,
                    )
                )
            if (
                operation.active_session_record is not None
                and operation.scheduler_state is not SchedulerState.DRAINING
            ):
                actions.append(
                    ProjectionAction(
                        "interrupt",
                        "Interrupt",
                        f"operator interrupt {operation.operation_id}",
                        "operation",
                        False,
                    )
                )
        if any(
            session.adapter_key in {"codex_acp", "claude_acp", "opencode_acp"}
            for session in operation.sessions
        ):
            actions.append(
                ProjectionAction(
                    "log", "Log", f"operator log {operation.operation_id}", "operation", False
                )
            )
        open_attention = [
            attention
            for attention in operation.attention_requests
            if attention.status is AttentionStatus.OPEN
        ]
        if open_attention:
            actions.append(
                ProjectionAction(
                    "answer",
                    "Answer",
                    (
                        f"operator answer {operation.operation_id} "
                        f"{open_attention[0].attention_id} --text '...'"
                    ),
                    "operation",
                    False,
                )
            )
        policy_scope = operation.policy_coverage.project_scope
        if (
            operation.policy_coverage.status.value == "uncovered"
            and isinstance(policy_scope, str)
            and policy_scope.startswith("profile:")
        ):
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
        if event_type == "session.execution_profile.applied":
            adapter_key = payload.get("adapter_key") or event.session_id or "agent"
            session_id = payload.get("session_id") or event.session_id
            applied_via = payload.get("applied_via") or "started"
            display = self._execution_profile_display_value(
                model=payload.get("model") if isinstance(payload.get("model"), str) else None,
                effort_value=(
                    payload.get("effort_value")
                    if isinstance(payload.get("effort_value"), str)
                    else None
                ),
            ) or "unknown"
            verb = "reused with" if applied_via == "reuse" else "started with"
            if session_id:
                return f"session {session_id} {verb} {adapter_key} {display}"
            return f"{adapter_key} {verb} {display}"
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
        if event_type == "command.applied":
            command_type = str(payload.get("command_type") or "command").strip() or "command"
            if command_type == "set_execution_profile":
                adapter_key = str(payload.get("adapter_key") or "").strip() or "agent"
                previous_display = self._execution_profile_display_value(
                    model=(
                        payload.get("previous_model")
                        if isinstance(payload.get("previous_model"), str)
                        else None
                    ),
                    effort_value=(
                        payload.get("previous_effort_value")
                        if isinstance(payload.get("previous_effort_value"), str)
                        else None
                    ),
                ) or "unknown"
                current_display = self._execution_profile_display_value(
                    model=(
                        payload.get("current_model")
                        if isinstance(payload.get("current_model"), str)
                        else None
                    ),
                    effort_value=(
                        payload.get("current_effort_value")
                        if isinstance(payload.get("current_effort_value"), str)
                        else None
                    ),
                ) or "unknown"
                return (
                    "execution profile updated for "
                    f"{adapter_key}: {previous_display} -> {current_display}"
                )
            return f"command applied: {command_type}"
        return self._shorten_text(
            json.dumps(self._run_event_payload(event), ensure_ascii=False), limit=120
        )

    def _format_dashboard_command(self, command: OperationCommand) -> str:
        rendered = (
            f"{command.command_type.value} [{command.status.value}] "
            f"target={command.target_scope.value}:{command.target_id or '-'}"
        )
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
        payload = {
            "policy_id": policy.policy_id,
            "project_scope": policy.project_scope,
            "title": policy.title,
            "category": policy.category.value,
            "rule_text": policy.rule_text,
            "applicability": {
                "objective_keywords": list(policy.applicability.objective_keywords),
                "task_keywords": list(policy.applicability.task_keywords),
                "agent_keys": list(policy.applicability.agent_keys),
                "run_modes": [item.value for item in policy.applicability.run_modes],
                "involvement_levels": [
                    item.value for item in policy.applicability.involvement_levels
                ],
                "permission_signatures": [
                    {
                        "adapter_key": item.adapter_key,
                        "method": item.method,
                        "interaction": item.interaction,
                        "title": item.title,
                        "tool_kind": item.tool_kind,
                        "skill_name": item.skill_name,
                        "command": list(item.command),
                    }
                    for item in policy.applicability.permission_signatures
                ],
            },
            "rationale": policy.rationale,
            "source_refs": [
                {"kind": item.kind, "ref_id": item.ref_id} for item in policy.source_refs
            ],
            "status": policy.status.value,
            "created_at": policy.created_at.isoformat(),
            "revoked_at": policy.revoked_at.isoformat() if policy.revoked_at is not None else None,
            "revoked_reason": policy.revoked_reason,
            "superseded_by": policy.superseded_by,
        }
        if operation is not None:
            payload["applicability_summary"] = "active for current operation"
        return payload

    def _focus_payload(self, focus) -> dict[str, object]:
        return FocusReadPayload(
            kind=focus.kind.value,
            target_id=focus.target_id,
            mode=focus.mode.value,
            blocking_reason=focus.blocking_reason,
            interrupt_policy=focus.interrupt_policy.value,
            resume_policy=focus.resume_policy.value,
            created_at=focus.created_at.isoformat(),
        ).to_payload()

    def _attention_payload(self, attention: AttentionRequest) -> dict[str, object]:
        return AttentionReadPayload(
            attention_id=attention.attention_id,
            operation_id=attention.operation_id,
            attention_type=attention.attention_type.value,
            target_scope=attention.target_scope.value,
            target_id=attention.target_id,
            title=attention.title,
            question=attention.question,
            context_brief=attention.context_brief,
            suggested_options=list(attention.suggested_options),
            blocking=attention.blocking,
            status=attention.status.value,
            answer_text=attention.answer_text,
            answer_source_command_id=attention.answer_source_command_id,
            created_at=attention.created_at.isoformat(),
            answered_at=attention.answered_at.isoformat()
            if attention.answered_at is not None
            else None,
            resolved_at=attention.resolved_at.isoformat()
            if attention.resolved_at is not None
            else None,
            resolution_summary=attention.resolution_summary,
            metadata=dict(attention.metadata),
        ).to_payload()

    def attention_payload(self, attention: AttentionRequest) -> dict[str, object]:
        return self._attention_payload(attention)

    def _policy_coverage_payload(self, coverage) -> dict[str, object]:
        return PolicyCoverageReadPayload(
            status=coverage.status.value,
            project_scope=coverage.project_scope,
            scoped_policy_count=coverage.scoped_policy_count,
            active_policy_count=coverage.active_policy_count,
            summary=coverage.summary,
        ).to_payload()

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
        return self._shorten_text(turn.turn_summary.recommended_next_step, limit=220)

    def _turn_verification_summary(self, turn: AgentTurnBrief | None) -> str | None:
        if turn is None or turn.turn_summary is None:
            return None
        return self._shorten_text(turn.turn_summary.verification_status, limit=220)

    def _turn_blockers_summary(self, turn: AgentTurnBrief | None) -> str | None:
        if turn is None or turn.turn_summary is None or not turn.turn_summary.remaining_blockers:
            return None
        return self._shorten_text(
            "; ".join(turn.turn_summary.remaining_blockers),
            limit=220,
        )

    def _shorten_text(self, text: str | None, *, limit: int) -> str | None:
        if text is None:
            return None
        normalized = " ".join(text.split())
        if not normalized:
            return None
        if len(normalized) <= limit:
            return normalized
        return normalized[: max(0, limit - 1)].rstrip() + "…"

    def _string_value(self, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped or None

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
            str(snapshot.get("runtime_alert"))
            if snapshot.get("runtime_alert") is not None
            else None,
            limit=120,
        )
        if runtime_alert is not None:
            parts.append(f"alert={runtime_alert}")
        return " | ".join(parts)
