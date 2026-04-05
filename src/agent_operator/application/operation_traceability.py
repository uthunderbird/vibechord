from __future__ import annotations

from agent_operator.application.loaded_operation import LoadedOperation
from agent_operator.application.operation_runtime_context import OperationRuntimeContext
from agent_operator.domain import (
    AgentResult,
    AgentSessionHandle,
    AgentTurnBrief,
    AgentTurnSummary,
    ArtifactRecord,
    AttentionStatus,
    BackgroundRunStatus,
    DecisionMemo,
    FocusKind,
    IterationBrief,
    IterationState,
    MemoryFreshness,
    OperationBrief,
    OperationState,
    OperationStatus,
    SchedulerState,
    TaskState,
    TaskStatus,
    TraceRecord,
)
from agent_operator.protocols import TraceStore


class OperationTraceabilityService:
    """Own trace, brief, and report projection outside the public facade."""

    def __init__(
        self,
        *,
        loaded_operation: LoadedOperation,
        trace_store: TraceStore,
        runtime_context: OperationRuntimeContext,
    ) -> None:
        self._loaded_operation = loaded_operation
        self._trace_store = trace_store
        self._runtime_context = runtime_context

    async def record_decision_memo(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
    ) -> None:
        decision = iteration.decision
        if decision is None:
            return
        memo = DecisionMemo(
            operation_id=state.operation_id,
            iteration=iteration.index,
            task_id=task.task_id if task is not None else None,
            session_id=decision.session_id,
            decision_context_summary=self._build_decision_context_summary(state, task),
            chosen_action=decision.action_type.value,
            rationale=decision.rationale,
            alternatives_considered=list(decision.assumptions),
            why_not_chosen=[],
            expected_outcome=decision.expected_outcome,
            refs=self._build_refs(state, iteration, task, decision.session_id),
        )
        await self._trace_store.save_decision_memo(state.operation_id, memo)
        await self._trace_store.append_trace_record(
            state.operation_id,
            TraceRecord(
                operation_id=state.operation_id,
                iteration=iteration.index,
                category="decision",
                title=f"Decision {decision.action_type.value}",
                summary=decision.rationale,
                task_id=task.task_id if task is not None else None,
                session_id=decision.session_id,
                refs=memo.refs,
                payload={"action_type": decision.action_type.value},
            ),
        )

    async def record_agent_turn_brief(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        session: AgentSessionHandle,
        result: AgentResult | None,
        artifact: ArtifactRecord | None,
        *,
        background_run_id: str | None = None,
        turn_summary: AgentTurnSummary | None = None,
        wakeup_event_id: str | None = None,
    ) -> None:
        raw_log_refs: list[str] = []
        log_path = session.metadata.get("log_path")
        if isinstance(log_path, str) and log_path:
            raw_log_refs.append(log_path)
        background_log_path = session.metadata.get("background_log_path")
        if isinstance(background_log_path, str) and background_log_path:
            raw_log_refs.append(background_log_path)
        result_brief = (
            self._shorten(result.output_text)
            if result is not None and result.output_text
            else (
                result.status.value
                if result is not None
                else (
                    "background turn started"
                    if background_run_id is not None
                    else "agent turn started"
                )
            )
        )
        if turn_summary is not None:
            result_brief = self._shorten(turn_summary.state_delta) or result_brief
        brief = AgentTurnBrief(
            operation_id=state.operation_id,
            iteration=iteration.index,
            agent_key=session.adapter_key,
            session_id=session.session_id,
            background_run_id=background_run_id,
            session_display_name=session.display_name,
            assignment_brief=(
                self._build_assignment_brief(iteration, task, session)
                or f"Asked {session.adapter_key} to continue task execution."
            ),
            expected_outcome=iteration.decision.expected_outcome if iteration.decision else None,
            result_brief=result_brief,
            status=result.status.value if result is not None else "running",
            artifact_refs=[artifact.artifact_id] if artifact is not None else [],
            raw_log_refs=raw_log_refs,
            turn_summary=turn_summary,
            wakeup_refs=[wakeup_event_id] if wakeup_event_id is not None else [],
        )
        state.agent_turn_briefs = [
            item
            for item in state.agent_turn_briefs
            if not (item.iteration == brief.iteration and item.session_id == brief.session_id)
        ]
        state.agent_turn_briefs.append(brief)
        await self._trace_store.append_agent_turn_brief(state.operation_id, brief)
        await self._trace_store.append_trace_record(
            state.operation_id,
            TraceRecord(
                operation_id=state.operation_id,
                iteration=iteration.index,
                category="agent_turn",
                title=(
                    f"{session.adapter_key} turn completed"
                    if result is not None
                    else f"{session.adapter_key} turn started"
                ),
                summary=brief.result_brief or brief.status,
                task_id=task.task_id if task is not None else None,
                session_id=session.session_id,
                refs=self._build_refs(
                    state,
                    iteration,
                    task,
                    session.session_id,
                    artifact.artifact_id if artifact is not None else None,
                ),
                payload={
                    "status": result.status.value if result is not None else "running",
                    "background_run_id": background_run_id,
                },
            ),
        )

    async def record_iteration_brief(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
    ) -> None:
        result = iteration.result
        session_id = iteration.session.session_id if iteration.session is not None else None
        brief = IterationBrief(
            iteration=iteration.index,
            task_id=task.task_id if task is not None else None,
            session_id=session_id,
            operator_intent_brief=self._build_operator_intent_brief(iteration, task),
            assignment_brief=self._build_assignment_brief(iteration, task, iteration.session),
            result_brief=self._build_result_brief(result),
            status_brief=self._build_status_brief(state, iteration, task),
            refs=self._build_refs(state, iteration, task, session_id),
        )
        state.iteration_briefs = [
            item for item in state.iteration_briefs if item.iteration != brief.iteration
        ]
        state.iteration_briefs.append(brief)
        state.iteration_briefs.sort(key=lambda item: item.iteration)
        await self._trace_store.append_iteration_brief(state.operation_id, brief)
        await self._trace_store.append_trace_record(
            state.operation_id,
            TraceRecord(
                operation_id=state.operation_id,
                iteration=iteration.index,
                category="iteration",
                title=f"Iteration {iteration.index}",
                summary=brief.status_brief,
                task_id=task.task_id if task is not None else None,
                session_id=session_id,
                refs=brief.refs,
                payload={
                    "operator_intent_brief": brief.operator_intent_brief,
                    "assignment_brief": brief.assignment_brief,
                    "result_brief": brief.result_brief,
                },
            ),
        )

    async def sync_traceability_artifacts(self, state: OperationState) -> None:
        state.operation_brief = self.build_operation_brief(state)
        await self._trace_store.save_operation_brief(state.operation_brief)
        await self._trace_store.write_report(state.operation_id, self.render_report(state))

    def build_operation_brief(self, state: OperationState) -> OperationBrief:
        latest_result = self._loaded_operation.find_latest_result(state)
        focus_brief = None
        if state.current_focus is not None:
            focus_brief = f"{state.current_focus.kind.value}:{state.current_focus.target_id}"
        blocker_brief = None
        if state.status is OperationStatus.NEEDS_HUMAN:
            blocker_brief = state.final_summary
        elif self._runtime_context.is_blocked_on_background_wait(state):
            blocker_brief = "Waiting on a background agent turn."
        elif self._runtime_context.is_waiting_on_attached_turn(state):
            blocker_brief = "Waiting on an attached agent turn."
        if state.scheduler_state is SchedulerState.PAUSED:
            blocker_brief = "Operator is paused."
        elif state.scheduler_state is SchedulerState.PAUSE_REQUESTED:
            blocker_brief = "Pause requested; waiting for the current attached turn to yield."
        elif state.scheduler_state is SchedulerState.DRAINING:
            blocker_brief = "Stopping the active attached agent turn."
        return OperationBrief(
            operation_id=state.operation_id,
            status=state.status,
            scheduler_state=state.scheduler_state,
            involvement_level=state.involvement_level,
            objective_brief=self._shorten(state.objective_state.objective),
            harness_brief=self._shorten(state.objective_state.harness_instructions)
            if state.objective_state.harness_instructions
            else None,
            focus_brief=focus_brief,
            latest_outcome_brief=(
                self._shorten(latest_result.output_text)
                if latest_result is not None and latest_result.output_text
                else state.final_summary
            ),
            blocker_brief=blocker_brief,
            runtime_alert_brief=self.build_runtime_alert_brief(state),
        )

    def build_runtime_alert_brief(self, state: OperationState) -> str | None:
        timed_out_recovery = next(
            (
                session.recovery_summary
                for session in state.sessions
                if session.recovery_summary
                and "timed out" in session.recovery_summary.lower()
            ),
            None,
        )
        if timed_out_recovery is not None:
            return timed_out_recovery
        if state.pending_wakeups:
            return (
                f"{len(state.pending_wakeups)} wakeup(s) have been claimed and are waiting "
                "to be reconciled."
            )
        if state.status is not OperationStatus.RUNNING:
            return None
        if not self._runtime_context.is_blocked_on_background_wait(state):
            return None
        if any(
            run.status
            in {
                BackgroundRunStatus.COMPLETED,
                BackgroundRunStatus.FAILED,
                BackgroundRunStatus.CANCELLED,
            }
            for run in state.background_runs
        ):
            return (
                "A background run is already terminal, but the operation still appears to be "
                "waiting. Run `operator resume <operation-id>` to reconcile persisted results."
            )
        return None

    def render_report(self, state: OperationState) -> str:
        lines = [
            f"# Operation {state.operation_id}",
            "",
            f"Status: {state.status.value}",
            f"Scheduler State: {state.scheduler_state.value}",
            f"Involvement Level: {state.involvement_level.value}",
            f"Objective: {state.objective_state.objective}",
            f"Harness Instructions: {state.objective_state.harness_instructions or '(none)'}",
        ]
        if state.current_focus is not None:
            lines.append(
                "Current Focus: "
                f"{state.current_focus.kind.value}:{state.current_focus.target_id} "
                f"[{state.current_focus.mode.value}]"
            )
            if state.current_focus.blocking_reason:
                lines.append(f"Current Focus Reason: {state.current_focus.blocking_reason}")
        if state.objective_state.success_criteria:
            lines.extend(["", "## Success Criteria", ""])
            for criterion in state.objective_state.success_criteria:
                lines.append(f"- {criterion}")
        if state.final_summary:
            lines.extend(["", "## Summary", "", state.final_summary])
        lines.extend(self._render_task_report_section(state))
        lines.extend(self._render_memory_report_section(state))
        lines.extend(self._render_artifact_report_section(state))
        open_attention = [
            item for item in state.attention_requests if item.status is AttentionStatus.OPEN
        ]
        if open_attention:
            lines.extend(["", "## Open Attention", ""])
            for attention in open_attention:
                lines.append(
                    f"- {attention.attention_id} "
                    f"[{attention.attention_type.value}] {attention.title}"
                )
                lines.append(f"  question: {self._shorten(attention.question, limit=220)}")
                if attention.context_brief:
                    lines.append(f"  context: {self._shorten(attention.context_brief, limit=220)}")
                if attention.suggested_options:
                    lines.append(
                        "  options: "
                        + " | ".join(
                            self._shorten(option, limit=120)
                            for option in attention.suggested_options
                        )
                    )
        if state.operator_messages:
            lines.extend(["", "## Operator Messages", ""])
            for message in state.operator_messages[-5:]:
                lines.append(f"- {message.text}")
        if state.iteration_briefs:
            lines.extend(["", "## Timeline", ""])
            for iteration_brief in state.iteration_briefs:
                lines.append(
                    f"- Iteration {iteration_brief.iteration}: "
                    f"{iteration_brief.operator_intent_brief} | "
                    f"{iteration_brief.assignment_brief or 'no assignment'} | "
                    f"{iteration_brief.result_brief or 'no result'} | "
                    f"{iteration_brief.status_brief}"
                )
        if state.agent_turn_briefs:
            lines.extend(["", "## Agent Turns", ""])
            for turn_brief in state.agent_turn_briefs:
                lines.append(
                    f"- {turn_brief.agent_key} "
                    f"({turn_brief.session_display_name or turn_brief.session_id}): "
                    f"{turn_brief.assignment_brief} -> "
                    f"{turn_brief.result_brief or turn_brief.status}"
                )
        return "\n".join(lines) + "\n"

    def build_decision_context_summary(
        self,
        state: OperationState,
        task: TaskState | None,
    ) -> str:
        return self._build_decision_context_summary(state, task)

    def default_outcome_summary(self, state: OperationState) -> str:
        if state.scheduler_state is SchedulerState.PAUSED:
            return "Operation is paused."
        if state.scheduler_state is SchedulerState.PAUSE_REQUESTED:
            return "Pause requested; waiting for the current attached turn to yield."
        if state.scheduler_state is SchedulerState.DRAINING:
            return "Stopping the active attached agent turn."
        if self._runtime_context.is_blocked_on_background_wait(state):
            return "Operation is waiting on a background agent turn."
        if self._runtime_context.is_waiting_on_attached_turn(state):
            return "Operation is waiting on an attached agent turn."
        if state.status is OperationStatus.RUNNING:
            return "Operation is still running."
        return "Operation finished."

    def _render_task_report_section(self, state: OperationState) -> list[str]:
        if not state.tasks:
            return []
        lines = ["", "## Tasks", ""]
        status_order = {
            TaskStatus.RUNNING: 0,
            TaskStatus.READY: 1,
            TaskStatus.BLOCKED: 2,
            TaskStatus.PENDING: 3,
            TaskStatus.COMPLETED: 4,
            TaskStatus.FAILED: 5,
            TaskStatus.CANCELLED: 6,
        }
        root_task_id = state.objective_state.root_task_id
        for task in sorted(
            state.tasks,
            key=lambda item: (
                status_order.get(item.status, 99),
                -item.effective_priority,
                item.created_at,
            ),
        ):
            labels: list[str] = [task.status.value]
            if task.task_id == root_task_id:
                labels.append("root")
            if (
                state.current_focus is not None
                and state.current_focus.kind is FocusKind.TASK
                and task.task_id == state.current_focus.target_id
            ):
                labels.append("focus")
            meta = (
                f"priority={task.effective_priority} "
                f"agent={task.assigned_agent or '-'} "
                f"session={task.linked_session_id or '-'}"
            )
            lines.append(f"- {task.task_id} [{', '.join(labels)}] {task.title}")
            lines.append(f"  {meta}")
            lines.append(f"  goal: {self._shorten(task.goal, limit=220)}")
            lines.append(f"  done: {self._shorten(task.definition_of_done, limit=220)}")
            if task.notes:
                lines.append(f"  notes: {self._shorten(task.notes[-1], limit=220)}")
            if task.memory_refs or task.artifact_refs:
                lines.append(
                    f"  refs: memory={len(task.memory_refs)} artifacts={len(task.artifact_refs)}"
                )
        return lines

    def _render_memory_report_section(self, state: OperationState) -> list[str]:
        if not state.memory_entries:
            return []
        lines = ["", "## Memory", ""]
        current_entries = [
            item for item in state.memory_entries if item.freshness is MemoryFreshness.CURRENT
        ]
        stale_entries = [item for item in state.memory_entries if item not in current_entries]
        for memory in sorted(current_entries, key=lambda item: (item.scope.value, item.created_at)):
            lines.append(f"- {memory.memory_id} [{memory.scope.value}:{memory.scope_id}]")
            lines.append(f"  summary: {self._shorten(memory.summary, limit=220)}")
            if memory.source_refs:
                refs = ", ".join(f"{ref.kind}:{ref.ref_id}" for ref in memory.source_refs[:3])
                lines.append(f"  sources: {refs}")
        if stale_entries:
            lines.append(
                f"- inactive entries: {len(stale_entries)} "
                "(stale or superseded, retained in full inspect JSON)"
            )
        return lines

    def _render_artifact_report_section(self, state: OperationState) -> list[str]:
        if not state.artifacts:
            return []
        lines = ["", "## Artifacts", ""]
        task_titles = {task.task_id: task.title for task in state.tasks}
        for artifact in sorted(state.artifacts, key=lambda item: item.created_at):
            task_label = task_titles.get(artifact.task_id or "", artifact.task_id or "-")
            session_label = artifact.session_id or "-"
            lines.append(
                f"- {artifact.artifact_id} [{artifact.kind}] "
                f"producer={artifact.producer} task={task_label} session={session_label}"
            )
            lines.append(f"  content: {self._shorten(artifact.content, limit=220)}")
            if artifact.raw_ref:
                lines.append(f"  raw_ref: {artifact.raw_ref}")
        return lines

    def _build_decision_context_summary(
        self,
        state: OperationState,
        task: TaskState | None,
    ) -> str:
        if task is not None:
            return (
                f"Focused on task '{task.title}' with status {task.status.value} and "
                f"priority {task.effective_priority}."
            )
        return f"Focused on objective with status {state.status.value}."

    def _build_operator_intent_brief(
        self,
        iteration: IterationState,
        task: TaskState | None,
    ) -> str:
        decision = iteration.decision
        if decision is None:
            return "No operator decision recorded."
        target = task.title if task is not None else "objective"
        return f"Operator chose {decision.action_type.value} for {target}."

    def _build_assignment_brief(
        self,
        iteration: IterationState,
        task: TaskState | None,
        session: AgentSessionHandle | None,
    ) -> str | None:
        decision = iteration.decision
        if decision is None or decision.target_agent is None:
            return None
        instruction = decision.instruction or (
            task.goal if task is not None else "continue objective"
        )
        session_hint = ""
        if session is not None:
            session_hint = f" via session {session.display_name or session.session_id}"
        return (
            f"Asked {decision.target_agent}{session_hint} to "
            f"{self._shorten(instruction, limit=140)}"
        )

    def _build_result_brief(self, result: AgentResult | None) -> str | None:
        if result is None:
            return None
        if result.output_text:
            return self._shorten(result.output_text)
        if result.error is not None:
            return result.error.message
        return result.status.value

    def _build_status_brief(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
    ) -> str:
        if state.status in {
            OperationStatus.COMPLETED,
            OperationStatus.NEEDS_HUMAN,
            OperationStatus.FAILED,
            OperationStatus.CANCELLED,
        }:
            return state.final_summary or state.status.value
        if self._runtime_context.is_blocked_on_background_wait(state):
            return "Waiting on a background agent turn."
        if state.scheduler_state is SchedulerState.DRAINING:
            return "Stopping the active attached agent turn."
        if self._runtime_context.is_waiting_on_attached_turn(state):
            return "Waiting on an attached agent turn."
        if task is not None:
            return f"Task '{task.title}' is now {task.status.value}."
        if iteration.result is not None:
            return f"Latest result status is {iteration.result.status.value}."
        return "Iteration recorded."

    def _build_refs(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        session_id: str | None,
        artifact_id: str | None = None,
    ) -> dict[str, str]:
        refs = {
            "operation_id": state.operation_id,
            "iteration": str(iteration.index),
        }
        if task is not None:
            refs["task_id"] = task.task_id
        if session_id is not None:
            refs["session_id"] = session_id
        if artifact_id is not None:
            refs["artifact_id"] = artifact_id
        return refs

    def _shorten(self, text: str, *, limit: int = 180) -> str:
        normalized = " ".join(text.strip().split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 1].rstrip() + "…"
