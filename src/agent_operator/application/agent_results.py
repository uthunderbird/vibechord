from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from agent_operator.application.commands.operation_attention import OperationAttentionCoordinator
from agent_operator.application.loaded_operation import LoadedOperation
from agent_operator.application.operation_lifecycle import OperationLifecycleCoordinator
from agent_operator.application.process_signals import ProcessManagerSignal
from agent_operator.application.runtime.operation_event_relay import OperationEventRelay
from agent_operator.application.runtime.operation_process_dispatch import (
    OperationProcessSignalDispatcher,
)
from agent_operator.domain import (
    AgentError,
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    AgentTurnSummary,
    ArtifactRecord,
    BackgroundRunStatus,
    FocusKind,
    FocusMode,
    FocusState,
    InterruptPolicy,
    IterationState,
    MemoryEntry,
    MemoryFreshness,
    MemoryScope,
    MemorySourceRef,
    OperationGoal,
    OperationState,
    OperationStatus,
    ResumePolicy,
    SchedulerState,
    SessionRecord,
    SessionRecordStatus,
    TaskState,
    TaskStatus,
)


class AgentResultService:
    def __init__(
        self,
        *,
        loaded_operation: LoadedOperation,
        operator_policy: object,
        event_relay: OperationEventRelay,
        process_signal_dispatcher: OperationProcessSignalDispatcher,
        lifecycle_coordinator: OperationLifecycleCoordinator,
        attention_coordinator: OperationAttentionCoordinator,
        record_agent_turn_brief: Callable[..., Awaitable[None]],
    ) -> None:
        self._loaded_operation = loaded_operation
        self._operator_policy = operator_policy
        self._event_relay = event_relay
        self._process_signal_dispatcher = process_signal_dispatcher
        self._lifecycle_coordinator = lifecycle_coordinator
        self._attention_coordinator = attention_coordinator
        self._record_agent_turn_brief = record_agent_turn_brief

    async def handle_agent_result(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        session: AgentSessionHandle,
        result: AgentResult,
        *,
        wakeup_event_id: str | None = None,
    ) -> None:
        was_stopping_attached_turn = (
            state.scheduler_state is SchedulerState.DRAINING
            and state.current_focus is not None
            and state.current_focus.kind is FocusKind.SESSION
            and state.current_focus.target_id == session.session_id
        )
        result = await self.normalize_result_if_needed(state.goal, result)
        iteration.result = self.compact_result_for_state(result)
        record = self._loaded_operation.ensure_session_record(state, session)
        preserve_reused_follow_up_frontier = self._should_preserve_cancelled_follow_up_frontier(
            state,
            session,
            result,
            wakeup_event_id=wakeup_event_id,
            was_stopping_attached_turn=was_stopping_attached_turn,
        )
        if preserve_reused_follow_up_frontier:
            record.status = SessionRecordStatus.WAITING
            record.waiting_reason = (
                "Background follow-up turn cancelled before producing a material result."
            )
        else:
            record.status = self.map_result_to_session_status(result)
        record.last_result_iteration = iteration.index
        record.latest_iteration = iteration.index
        if not preserve_reused_follow_up_frontier:
            record.waiting_reason = None
        record.updated_at = datetime.now(UTC)
        execution_id = None
        if record.current_execution_id is not None:
            execution_id = record.current_execution_id
            run = self._loaded_operation.find_background_run(state, execution_id)
            if run is not None:
                run.status = {
                    AgentResultStatus.SUCCESS: BackgroundRunStatus.COMPLETED,
                    AgentResultStatus.INCOMPLETE: BackgroundRunStatus.COMPLETED,
                    AgentResultStatus.FAILED: BackgroundRunStatus.FAILED,
                    AgentResultStatus.CANCELLED: BackgroundRunStatus.CANCELLED,
                    AgentResultStatus.DISCONNECTED: BackgroundRunStatus.DISCONNECTED,
                }[result.status]
                run.completed_at = datetime.now(UTC)
                run.last_heartbeat_at = run.completed_at
            record.last_terminal_execution_id = execution_id
            record.current_execution_id = None
        artifact = None
        if not preserve_reused_follow_up_frontier:
            artifact = self._loaded_operation.store_result_artifact(state, task, session, result)
        if self.is_rate_limit_result(result):
            assert artifact is not None
            await self.enter_rate_limit_wait(state, record, session, iteration, result)
            return
        if result.status is AgentResultStatus.DISCONNECTED:
            disconnect_reason = "Recovering agent connection after ACP disconnect."
            self._lifecycle_coordinator.mark_needs_human(
                state,
                summary=disconnect_reason,
            )
            record.waiting_reason = disconnect_reason
            record.status = SessionRecordStatus.WAITING
            state.current_focus = FocusState(
                kind=FocusKind.SESSION,
                target_id=session.session_id,
                mode=FocusMode.BLOCKING,
                blocking_reason=disconnect_reason,
                interrupt_policy=InterruptPolicy.MATERIAL_WAKEUP,
                resume_policy=ResumePolicy.RETURN_IF_STILL_RELEVANT,
            )
            await self._process_signal_dispatcher.dispatch(
                state,
                iteration.index,
                ProcessManagerSignal(
                    operation_id=state.operation_id,
                    signal_type="execution_lost",
                    execution_id=record.current_execution_id,
                    session_id=session.session_id,
                    metadata={"session_id": session.session_id, "result_status": "disconnected"},
                ),
            )
        if task is not None:
            task.updated_at = datetime.now(UTC)
            if artifact is not None:
                task.artifact_refs.append(artifact.artifact_id)
            if preserve_reused_follow_up_frontier:
                task.status = TaskStatus.BLOCKED
            elif result.status is AgentResultStatus.SUCCESS:
                task.status = TaskStatus.COMPLETED
            elif result.status is AgentResultStatus.INCOMPLETE:
                task.status = TaskStatus.BLOCKED
            elif result.status is AgentResultStatus.CANCELLED and was_stopping_attached_turn:
                task.status = TaskStatus.READY
                task.notes.append("Active attached agent turn was stopped by operator command.")
                task.notes = task.notes[-20:]
            elif result.status is AgentResultStatus.CANCELLED:
                task.status = TaskStatus.CANCELLED
            elif result.status is AgentResultStatus.DISCONNECTED:
                task.status = TaskStatus.BLOCKED
            else:
                task.status = TaskStatus.FAILED
            if artifact is not None:
                await self.refresh_task_memory(state, task, artifact)
        if preserve_reused_follow_up_frontier:
            state.current_focus = FocusState(
                kind=FocusKind.SESSION,
                target_id=session.session_id,
                mode=FocusMode.BLOCKING,
                blocking_reason=record.waiting_reason,
                interrupt_policy=InterruptPolicy.MATERIAL_WAKEUP,
                resume_policy=ResumePolicy.RETURN_IF_STILL_RELEVANT,
            )
            return
        if result.status is AgentResultStatus.INCOMPLETE:
            attention = self._attention_coordinator.attention_from_incomplete_result(
                state,
                session,
                task,
                result,
            )
            if attention is not None:
                await self._event_relay.emit(
                    "attention.request.created",
                    state,
                    iteration.index,
                    self._attention_coordinator.event_payload(attention),
                    task_id=task.task_id if task is not None else None,
                    session_id=session.session_id,
                )
                self._lifecycle_coordinator.mark_needs_human(
                    state,
                    summary=f"Blocked on attention request: {attention.title}.",
                )
                state.current_focus = FocusState(
                    kind=FocusKind.ATTENTION_REQUEST,
                    target_id=attention.attention_id,
                    mode=FocusMode.BLOCKING,
                    blocking_reason=attention.question,
                    interrupt_policy=InterruptPolicy.MATERIAL_WAKEUP,
                    resume_policy=ResumePolicy.REPLAN,
                )
        if was_stopping_attached_turn:
            state.scheduler_state = SchedulerState.ACTIVE
            if (
                state.status is OperationStatus.RUNNING
                and state.current_focus is not None
                and state.current_focus.kind is FocusKind.SESSION
                and state.current_focus.target_id == session.session_id
            ):
                state.current_focus = None
        turn_summary = await self.summarize_agent_turn(iteration, task, state, result)
        iteration.turn_summary = turn_summary
        await self._record_agent_turn_brief(
            state,
            iteration,
            task,
            session,
            result,
            artifact,
            background_run_id=execution_id,
            turn_summary=turn_summary,
            wakeup_event_id=wakeup_event_id,
        )
        await self._event_relay.emit(
            "agent.invocation.completed",
            state,
            iteration.index,
            result.model_dump(mode="json"),
            task_id=iteration.task_id,
            session_id=session.session_id,
        )

    def _should_preserve_cancelled_follow_up_frontier(
        self,
        state: OperationState,
        session: AgentSessionHandle,
        result: AgentResult,
        *,
        wakeup_event_id: str | None,
        was_stopping_attached_turn: bool,
    ) -> bool:
        if wakeup_event_id is None or was_stopping_attached_turn:
            return False
        if result.status is not AgentResultStatus.CANCELLED:
            return False
        if result.output_text.strip():
            return False
        if result.error is not None:
            return False
        focus = state.current_focus
        return (
            focus is not None
            and focus.kind is FocusKind.SESSION
            and focus.target_id == session.session_id
            and focus.mode is FocusMode.BLOCKING
        )

    async def enter_rate_limit_wait(
        self,
        state: OperationState,
        record: SessionRecord,
        session: AgentSessionHandle,
        iteration: IterationState,
        result: AgentResult,
    ) -> None:
        retry_after_seconds = self.retry_after_seconds_from_raw(
            result.error.raw if result.error is not None else None
        )
        cooldown = self.normalize_rate_limit_cooldown(retry_after_seconds, default_seconds=60 * 60)
        error_message = result.error.message if result.error is not None else "unknown"
        reason = f"Rate limit detected: {error_message}."
        record.cooldown_until = cooldown
        record.cooldown_reason = reason
        record.waiting_reason = reason
        if record.current_execution_id is not None:
            record.last_terminal_execution_id = record.current_execution_id
            record.current_execution_id = None
        if record.last_result_iteration is None:
            record.last_result_iteration = iteration.index
        if record.latest_iteration is None:
            record.latest_iteration = iteration.index
        record.status = SessionRecordStatus.WAITING
        self._lifecycle_coordinator.mark_needs_human(state, summary=reason)
        state.current_focus = FocusState(
            kind=FocusKind.SESSION,
            target_id=session.session_id,
            mode=FocusMode.BLOCKING,
            blocking_reason=reason,
            interrupt_policy=InterruptPolicy.MATERIAL_WAKEUP,
            resume_policy=ResumePolicy.REPLAN,
        )
        await self.schedule_session_cooldown_expiry_wakeup(state, session.session_id, cooldown)
        await self._event_relay.emit(
            "session.cooldown.set",
            state,
            iteration.index,
            {
                "session_id": session.session_id,
                "adapter_key": session.adapter_key,
                "cooldown_until": cooldown.isoformat() if cooldown is not None else None,
                "retry_after_seconds": retry_after_seconds,
            },
            task_id=iteration.task_id,
            session_id=session.session_id,
        )

    async def schedule_session_cooldown_expiry_wakeup(
        self,
        state: OperationState,
        session_id: str,
        cooldown_until: datetime,
    ) -> None:
        await self._event_relay.emit_wakeup(
            "session.cooldown_expired",
            state,
            0,
            {"session_id": session_id},
            session_id=session_id,
            not_before=cooldown_until,
        )

    def is_legacy_rate_limit_error(self, error: AgentError) -> bool:
        if self.is_rate_limit_error_like(error.code, error.message, error.raw):
            return True
        raw = error.raw
        if not isinstance(raw, dict):
            return False
        if raw.get("rate_limit_detected") is True:
            return True
        message = error.message.lower()
        return any(
            marker in message
            for marker in (
                "hit your limit",
                "you have hit your limit",
                "usage limit",
                "quota exceeded",
                "resets 1am",
            )
        )

    def is_rate_limit_error_like(
        self,
        code: str,
        message: str,
        raw: dict[str, object] | None,
    ) -> bool:
        if code in {"claude_acp_rate_limited", "codex_acp_provider_overloaded"}:
            return True
        if raw is not None and raw.get("rate_limit_detected") is True:
            return True
        if raw is not None and raw.get("failure_kind") == "provider_capacity":
            return True
        lowered = message.lower()
        markers = (
            "rate limit",
            "rate_limit",
            "too many requests",
            "429",
            "usage limit",
            "quota exceeded",
            "credit balance is too low",
            "try again in",
            "you've hit your limit",
            "you hit your limit",
            "resets 1am",
            "at capacity",
            "server overloaded",
        )
        return any(marker in lowered for marker in markers)

    def normalize_rate_limit_cooldown(
        self,
        retry_after_seconds: int | None,
        *,
        default_seconds: int = 60 * 60,
    ) -> datetime:
        duration_seconds = (
            retry_after_seconds
            if isinstance(retry_after_seconds, int) and retry_after_seconds > 0
            else default_seconds
        )
        return datetime.now(UTC) + timedelta(seconds=duration_seconds)

    def retry_after_seconds_from_raw(self, raw: dict[str, object] | None) -> int | None:
        if not isinstance(raw, dict):
            return None
        raw_retry_after = raw.get("retry_after_seconds")
        if isinstance(raw_retry_after, int) and raw_retry_after > 0:
            return raw_retry_after
        if isinstance(raw_retry_after, float) and raw_retry_after > 0:
            return int(raw_retry_after)
        if isinstance(raw_retry_after, str) and raw_retry_after.strip().isdigit():
            return int(raw_retry_after.strip())
        return None

    def is_rate_limit_result(self, result: AgentResult) -> bool:
        return self.is_rate_limit_error_like(
            result.error.code if result.error is not None else "",
            result.error.message if result.error is not None else "",
            result.error.raw if result.error is not None else None,
        )

    def compact_result_for_state(self, result: AgentResult) -> AgentResult:
        raw = self.compact_result_raw(result.raw)
        error = result.error
        if error is not None and error.raw is not None:
            error = error.model_copy(update={"raw": self.compact_result_raw(error.raw)})
        return result.model_copy(update={"transcript": None, "raw": raw, "error": error})

    async def summarize_agent_turn(
        self,
        iteration: IterationState,
        task: TaskState | None,
        state: OperationState,
        result: AgentResult,
    ) -> AgentTurnSummary | None:
        if iteration.decision is None:
            return None
        summarize_turn = getattr(self._operator_policy, "summarize_agent_turn", None)
        if summarize_turn is None or not callable(summarize_turn):
            return None
        operator_instruction = (
            iteration.decision.instruction
            or iteration.decision.expected_outcome
            or (task.goal if task is not None else state.goal.objective_text)
        )
        return await summarize_turn(state, operator_instruction=operator_instruction, result=result)

    def compact_result_raw(self, raw: dict[str, object] | None) -> dict[str, object] | None:
        if raw is None:
            return None
        compact: dict[str, object] = {}
        for key in (
            "run_id",
            "returncode",
            "stale",
            "escalation_detected",
            "escalation_match",
            "matched_pattern",
            "attached_turn_recovered",
            "used_log_tail_recovery",
            "raw_output",
        ):
            if key in raw:
                compact[key] = raw[key]
        if not compact:
            compact["omitted"] = True
        return compact

    async def normalize_result_if_needed(
        self,
        goal: OperationGoal,
        result: AgentResult,
    ) -> AgentResult:
        result = self.flag_escalation_request_if_needed(result)
        instruction = goal.metadata.get("result_normalization_instruction")
        if not isinstance(instruction, str) or not instruction.strip():
            return result
        return await self._operator_policy.normalize_artifact(goal, result)

    def flag_escalation_request_if_needed(self, result: AgentResult) -> AgentResult:
        haystacks = [
            result.output_text,
            result.transcript or "",
            result.error.message if result.error is not None else "",
        ]
        lowered = "\n".join(part for part in haystacks if part).lower()
        patterns = [
            "needs escalation",
            "requesting escalation",
            "requires escalation",
            "requires approval",
            "need approval",
            "need escalated",
            "outside writable root",
            "outside writable roots",
            "outside the writable root",
            "outside the writable roots",
            "operation not permitted",
            "conversation interrupted - tell the model what to do differently",
        ]
        matched = next((pattern for pattern in patterns if pattern in lowered), None)
        if matched is None:
            return result
        raw = dict(result.raw or {})
        raw["escalation_detected"] = True
        raw["escalation_match"] = matched
        return result.model_copy(
            update={
                "status": AgentResultStatus.INCOMPLETE,
                "error": AgentError(
                    code="agent_requested_escalation",
                    message=(
                        "The agent requested human approval, escalation, or access "
                        "outside the current sandbox."
                    ),
                    retryable=False,
                    raw={"matched_pattern": matched},
                ),
                "raw": raw,
            }
        )

    async def refresh_task_memory(
        self,
        state: OperationState,
        task: TaskState,
        artifact: ArtifactRecord,
    ) -> None:
        if not artifact.content.strip() or not hasattr(self._operator_policy, "distill_memory"):
            return
        draft = await self._operator_policy.distill_memory(
            state,
            scope=MemoryScope.TASK.value,
            scope_id=task.task_id,
            source_refs=[
                {"kind": "artifact", "ref_id": artifact.artifact_id},
                {"kind": "task", "ref_id": task.task_id},
            ],
            instruction=(
                "Capture durable task memory: the completed result, key findings, "
                "unresolved caveats, and what future iterations should assume."
            ),
        )
        previous_current = [
            memory
            for memory in state.memory_entries
            if memory.scope is MemoryScope.TASK
            and memory.scope_id == task.task_id
            and memory.freshness is MemoryFreshness.CURRENT
        ]
        entry = MemoryEntry(
            scope=MemoryScope(draft.scope),
            scope_id=draft.scope_id,
            summary=draft.summary,
            source_refs=draft.source_refs
            or [MemorySourceRef(kind="artifact", ref_id=artifact.artifact_id)],
            freshness=MemoryFreshness.CURRENT,
        )
        for memory in previous_current:
            memory.freshness = MemoryFreshness.SUPERSEDED
            memory.superseded_by = entry.memory_id
            memory.updated_at = datetime.now(UTC)
        state.memory_entries.append(entry)
        if entry.memory_id not in task.memory_refs:
            task.memory_refs.append(entry.memory_id)

    def map_result_to_session_status(self, result: AgentResult) -> SessionRecordStatus:
        if result.status is AgentResultStatus.SUCCESS:
            return SessionRecordStatus.IDLE
        if result.status is AgentResultStatus.CANCELLED:
            return SessionRecordStatus.CANCELLED
        if result.status is AgentResultStatus.FAILED:
            return SessionRecordStatus.FAILED
        return SessionRecordStatus.WAITING
