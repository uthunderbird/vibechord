"""Forensic payload serializers for debug CLI surfaces."""

from __future__ import annotations

from agent_operator.domain.attention import AttentionRequest
from agent_operator.domain.control import OperationCommand
from agent_operator.domain.events import RunEvent
from agent_operator.domain.operation import ExecutionState, OperationOutcome, WakeupRef
from agent_operator.domain.traceability import DecisionMemo, TraceBriefBundle, TraceRecord


def wakeup_ref_payload(item: WakeupRef) -> dict[str, object]:
    return {
        "event_id": item.event_id,
        "event_type": item.event_type,
        "task_id": item.task_id,
        "session_id": item.session_id,
        "dedupe_key": item.dedupe_key,
        "claimed_at": item.claimed_at.isoformat() if item.claimed_at is not None else None,
        "acked_at": item.acked_at.isoformat() if item.acked_at is not None else None,
        "created_at": item.created_at.isoformat(),
    }


def run_event_payload(event: RunEvent) -> dict[str, object]:
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


def execution_payload(execution: ExecutionState) -> dict[str, object]:
    return {
        "run_id": execution.run_id,
        "operation_id": execution.operation_id,
        "adapter_key": execution.adapter_key,
        "session_id": execution.session_id,
        "task_id": execution.task_id,
        "iteration": execution.iteration,
        "mode": execution.mode.value,
        "launch_kind": execution.launch_kind.value,
        "status": execution.status.value,
        "observed_state": execution.observed_state.value,
        "waiting_reason": execution.waiting_reason,
        "handle_ref": (
            {
                "kind": execution.handle_ref.kind,
                "value": execution.handle_ref.value,
                "metadata": dict(execution.handle_ref.metadata),
            }
            if execution.handle_ref is not None
            else None
        ),
        "progress": (
            {
                "state": execution.progress.state.value,
                "message": execution.progress.message,
                "updated_at": execution.progress.updated_at.isoformat(),
                "partial_output": execution.progress.partial_output,
                "last_event_at": (
                    execution.progress.last_event_at.isoformat()
                    if execution.progress.last_event_at is not None
                    else None
                ),
            }
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
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
        "raw_ref": execution.raw_ref,
    }


def operation_command_payload(command: OperationCommand) -> dict[str, object]:
    return {
        "command_id": command.command_id,
        "operation_id": command.operation_id,
        "command_type": command.command_type.value,
        "target_scope": command.target_scope.value,
        "target_id": command.target_id,
        "payload": dict(command.payload),
        "submitted_by": command.submitted_by,
        "submitted_at": command.submitted_at.isoformat(),
        "status": command.status.value,
        "rejection_reason": command.rejection_reason,
        "applied_at": command.applied_at.isoformat() if command.applied_at is not None else None,
    }


def attention_request_payload(attention: AttentionRequest) -> dict[str, object]:
    return {
        "attention_id": attention.attention_id,
        "operation_id": attention.operation_id,
        "attention_type": attention.attention_type.value,
        "target_scope": attention.target_scope.value,
        "target_id": attention.target_id,
        "title": attention.title,
        "question": attention.question,
        "context_brief": attention.context_brief,
        "suggested_options": list(attention.suggested_options),
        "blocking": attention.blocking,
        "status": attention.status.value,
        "answer_text": attention.answer_text,
        "answer_source_command_id": attention.answer_source_command_id,
        "created_at": attention.created_at.isoformat(),
        "answered_at": (
            attention.answered_at.isoformat() if attention.answered_at is not None else None
        ),
        "resolved_at": attention.resolved_at.isoformat()
        if attention.resolved_at is not None
        else None,
        "resolution_summary": attention.resolution_summary,
        "metadata": dict(attention.metadata),
    }


def operation_outcome_payload(outcome: OperationOutcome) -> dict[str, object]:
    return {
        "operation_id": outcome.operation_id,
        "status": outcome.status.value,
        "summary": outcome.summary,
        "ended_at": outcome.ended_at.isoformat() if outcome.ended_at is not None else None,
    }


def trace_brief_bundle_payload(brief: TraceBriefBundle) -> dict[str, object]:
    return {
        "operation_brief": (
            {
                "operation_id": brief.operation_brief.operation_id,
                "status": brief.operation_brief.status.value,
                "scheduler_state": brief.operation_brief.scheduler_state.value,
                "involvement_level": brief.operation_brief.involvement_level.value,
                "objective_brief": brief.operation_brief.objective_brief,
                "harness_brief": brief.operation_brief.harness_brief,
                "focus_brief": brief.operation_brief.focus_brief,
                "latest_outcome_brief": brief.operation_brief.latest_outcome_brief,
                "blocker_brief": brief.operation_brief.blocker_brief,
                "runtime_alert_brief": brief.operation_brief.runtime_alert_brief,
                "updated_at": brief.operation_brief.updated_at.isoformat(),
            }
            if brief.operation_brief is not None
            else None
        ),
        "iteration_briefs": [
            {
                "iteration": item.iteration,
                "task_id": item.task_id,
                "session_id": item.session_id,
                "operator_intent_brief": item.operator_intent_brief,
                "assignment_brief": item.assignment_brief,
                "result_brief": item.result_brief,
                "status_brief": item.status_brief,
                "refs": item.refs.to_dict() if item.refs is not None else None,
                "created_at": item.created_at.isoformat(),
            }
            for item in brief.iteration_briefs
        ],
        "agent_turn_briefs": [
            {
                "operation_id": item.operation_id,
                "iteration": item.iteration,
                "agent_key": item.agent_key,
                "session_id": item.session_id,
                "background_run_id": item.background_run_id,
                "session_display_name": item.session_display_name,
                "assignment_brief": item.assignment_brief,
                "expected_outcome": item.expected_outcome,
                "result_brief": item.result_brief,
                "turn_summary": (
                    {
                        "declared_goal": item.turn_summary.declared_goal,
                        "actual_work_done": item.turn_summary.actual_work_done,
                        "route_or_target_chosen": item.turn_summary.route_or_target_chosen,
                        "repo_changes": list(item.turn_summary.repo_changes),
                        "progress_class": item.turn_summary.progress_class,
                        "blocker_keys": list(item.turn_summary.blocker_keys),
                        "state_delta": item.turn_summary.state_delta,
                        "verification_status": item.turn_summary.verification_status,
                        "remaining_blockers": list(item.turn_summary.remaining_blockers),
                        "recommended_next_step": item.turn_summary.recommended_next_step,
                        "rationale": item.turn_summary.rationale,
                    }
                    if item.turn_summary is not None
                    else None
                ),
                "status": item.status,
                "artifact_refs": list(item.artifact_refs),
                "raw_log_refs": list(item.raw_log_refs),
                "wakeup_refs": list(item.wakeup_refs),
                "created_at": item.created_at.isoformat(),
            }
            for item in brief.agent_turn_briefs
        ],
        "command_briefs": [
            {
                "operation_id": item.operation_id,
                "command_id": item.command_id,
                "command_type": item.command_type,
                "status": item.status,
                "iteration": item.iteration,
                "applied_at": item.applied_at.isoformat() if item.applied_at is not None else None,
                "rejected_at": (
                    item.rejected_at.isoformat() if item.rejected_at is not None else None
                ),
                "rejection_reason": item.rejection_reason,
            }
            for item in brief.command_briefs
        ],
        "evaluation_briefs": [
            {
                "operation_id": item.operation_id,
                "iteration": item.iteration,
                "goal_satisfied": item.goal_satisfied,
                "should_continue": item.should_continue,
                "summary": item.summary,
                "blocker": item.blocker,
            }
            for item in brief.evaluation_briefs
        ],
    }


def trace_record_payload(record: TraceRecord) -> dict[str, object]:
    return {
        "operation_id": record.operation_id,
        "iteration": record.iteration,
        "category": record.category,
        "title": record.title,
        "summary": record.summary,
        "task_id": record.task_id,
        "session_id": record.session_id,
        "refs": dict(record.refs),
        "payload": dict(record.payload),
        "created_at": record.created_at.isoformat(),
    }


def decision_memo_payload(memo: DecisionMemo) -> dict[str, object]:
    return {
        "operation_id": memo.operation_id,
        "iteration": memo.iteration,
        "task_id": memo.task_id,
        "session_id": memo.session_id,
        "decision_context_summary": memo.decision_context_summary,
        "chosen_action": memo.chosen_action,
        "rationale": memo.rationale,
        "alternatives_considered": list(memo.alternatives_considered),
        "why_not_chosen": list(memo.why_not_chosen),
        "expected_outcome": memo.expected_outcome,
        "refs": memo.refs.to_dict() if memo.refs is not None else None,
        "created_at": memo.created_at.isoformat(),
    }
