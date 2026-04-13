from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent_operator.adapters.runtime_bindings import AgentRuntimeBinding
from agent_operator.domain import (
    AgentDescriptor,
    AgentProgress,
    AgentProgressState,
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    BackgroundRunStatus,
    BackgroundRuntimeMode,
    BrainActionType,
    BrainDecision,
    CommandStatus,
    CommandTargetScope,
    Evaluation,
    ExecutionState,
    FocusKind,
    FocusMode,
    FocusState,
    IterationState,
    OperationCommand,
    OperationCommandType,
    OperationGoal,
    OperationState,
    OperationStatus,
    OperatorMessage,
    PlanningTrigger,
    ProgressSummary,
    RunMode,
    RunOptions,
    SchedulerState,
    SessionState,
    SessionStatus,
    TaskPatch,
    TaskStatus,
)
from agent_operator.testing.operator_service_support import (
    FakeAgent,
    FakeSupervisor,
    MemoryCommandInbox,
    MemoryEventSink,
    MemoryStore,
    MemoryTraceStore,
    MemoryWakeupInbox,
    StartClaudeAcpThenStopBrain,
    StartThenStopBrain,
    make_service,
    run_settings,
    state_settings,
)
from agent_operator.testing.runtime_bindings import build_test_runtime_bindings


def test_operator_service_accepts_runtime_bindings_without_explicit_adapters() -> None:
    """The public service constructor should accept runtime bindings as canonical input."""
    class _Policy:
        async def decide_next_action(self, state) -> BrainDecision:
            raise AssertionError("not used in constructor test")

        async def evaluate_result(self, state) -> Evaluation:
            raise AssertionError("not used in constructor test")

    service = make_service(
        operator_policy=_Policy(),
        store=MemoryStore(),
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings={
            "fake": AgentRuntimeBinding(
                agent_key="fake",
                descriptor=AgentDescriptor(key="fake", display_name="Fake"),
                build_adapter_runtime=lambda *, working_directory, log_path: None,
                build_session_runtime=lambda *, working_directory, log_path: None,
            )
        },
    )

    assert service._attached_session_registry.has("fake")  # type: ignore[attr-defined]


def test_operator_service_accepts_non_llm_operator_policy() -> None:
    class _Policy:
        async def decide_next_action(self, state) -> BrainDecision:
            raise AssertionError("not used in constructor test")

        async def evaluate_result(self, state) -> Evaluation:
            raise AssertionError("not used in constructor test")

        async def summarize_agent_turn(self, state, *, operator_instruction, result):
            raise AssertionError("not used in constructor test")

        async def normalize_artifact(self, goal, result):
            return result

        async def distill_memory(self, state, *, scope, scope_id, source_refs, instruction):
            raise AssertionError("not used in constructor test")

        async def summarize_progress(self, state):
            raise AssertionError("not used in constructor test")

    service = make_service(
        operator_policy=_Policy(),
        store=MemoryStore(),
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings={},
    )

    assert service is not None


class StopImmediatelyBrain:
    async def answer_question(self, state, question: str) -> str:
        return f"answer: {question}"

    async def decide_next_action(self, state) -> BrainDecision:
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="The operator has enough context to continue after replanning.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(
            goal_satisfied=True,
            should_continue=False,
            summary="Goal satisfied after replanning.",
        )

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


@pytest.mark.anyio
async def test_operator_service_runs_agent_and_completes() -> None:
    trace_store = MemoryTraceStore()
    service = make_service(
        brain=StartClaudeAcpThenStopBrain(),
        store=MemoryStore(),
        trace_store=trace_store,
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )

    outcome = await service.run(
        OperationGoal(objective="fix the issue"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
    )

    assert outcome.status is OperationStatus.COMPLETED
    assert outcome.final_result is not None
    assert outcome.final_result.output_text == "completed by fake agent"
    assert trace_store.bundle.operation_brief is not None
    assert trace_store.bundle.iteration_briefs
    assert trace_store.bundle.agent_turn_briefs
    assert trace_store.memos
    assert trace_store.report is not None


class UnknownAdapterBrain:
    async def answer_question(self, state, question: str) -> str:
        return f"answer: {question}"

    async def decide_next_action(self, state) -> BrainDecision:
        return BrainDecision(
            action_type=BrainActionType.START_AGENT,
            target_agent="missing",
            instruction="do it",
            rationale="Try a missing adapter.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        raise AssertionError("evaluate_result should not be called")

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


@pytest.mark.anyio
async def test_operator_service_fails_on_unavailable_adapter() -> None:
    service = make_service(
        brain=UnknownAdapterBrain(),
        store=MemoryStore(),
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )

    outcome = await service.run(
        OperationGoal(objective="fix the issue"),
        **run_settings(max_iterations=2, allowed_agents=["claude_acp"]),
    )

    assert outcome.status is OperationStatus.FAILED
    assert "not allowed" in outcome.summary


@pytest.mark.anyio
async def test_attached_startup_failure_transitions_operation_to_failed() -> None:
    class StartupTimeoutAgent(FakeAgent):
        async def start(self, request):
            self.started_requests.append(request)
            raise TimeoutError("Claude ACP startup timed out while establishing the session.")

    store = MemoryStore()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings(
            {"claude_acp": StartupTimeoutAgent()}
        ),
    )

    outcome = await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
        operation_id="op-startup-timeout",
    )

    updated = await store.load_operation("op-startup-timeout")
    persisted_outcome = await store.load_outcome("op-startup-timeout")

    assert outcome.status is OperationStatus.FAILED
    assert "startup timed out" in outcome.summary
    assert updated is not None
    assert updated.status is OperationStatus.FAILED
    assert updated.tasks[0].status is TaskStatus.FAILED
    assert len(updated.iterations) == 1
    assert persisted_outcome is not None
    assert persisted_outcome.status is OperationStatus.FAILED


@pytest.mark.anyio
async def test_operator_service_answers_question_from_loaded_operation_state() -> None:
    class AnsweringBrain(StartThenStopBrain):
        async def answer_question(self, state, question: str) -> str:
            return f"{state.goal.objective_text} :: {question}"

    store = MemoryStore()
    operation = OperationState(
        operation_id="op-ask-1",
        goal=OperationGoal(objective="Inspect ADR 0149"),
        **state_settings(),
    )
    await store.save_operation(operation)

    service = make_service(
        brain=AnsweringBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings={},
    )

    answer = await service.answer_question("op-ask-1", "What is the objective?")

    assert answer == "Inspect ADR 0149 :: What is the objective?"


@pytest.mark.anyio
async def test_attached_pause_request_becomes_paused_after_current_turn_yields() -> None:
    operation_id = "op-pause"
    store = MemoryStore()
    command_inbox = MemoryCommandInbox()

    class PauseOnPollAgent(FakeAgent):
        def __init__(self, inbox: MemoryCommandInbox) -> None:
            super().__init__()
            self._inbox = inbox

        async def poll(self, handle: AgentSessionHandle) -> AgentProgress:
            self.poll_calls += 1
            if self.poll_calls == 1:
                await self._inbox.enqueue(
                    OperationCommand(
                        operation_id=operation_id,
                        command_type=OperationCommandType.PAUSE_OPERATOR,
                        target_scope=CommandTargetScope.OPERATION,
                        target_id=operation_id,
                        payload={},
                    )
                )
                return AgentProgress(
                    session_id=handle.session_id,
                    state=AgentProgressState.RUNNING,
                    message="still working",
                    updated_at=datetime.now(UTC),
                )
            return AgentProgress(
                session_id=handle.session_id,
                state=AgentProgressState.COMPLETED,
                message="done",
                updated_at=datetime.now(UTC),
            )

    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings(
            {"claude_acp": PauseOnPollAgent(command_inbox)}
        ),
        command_inbox=command_inbox,
    )

    outcome = await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
        operation_id=operation_id,
    )

    operation = await store.load_operation(outcome.operation_id)
    assert operation is not None
    assert outcome.status is OperationStatus.RUNNING
    assert outcome.summary == "Operation is paused."
    assert operation.scheduler_state is SchedulerState.PAUSED
    commands = await command_inbox.list(outcome.operation_id)
    assert len(commands) == 1
    assert commands[0].status is CommandStatus.APPLIED


@pytest.mark.anyio
async def test_stop_turn_command_cancels_active_attached_turn_and_forces_replan() -> None:
    operation_id = "op-stop-turn"
    store = MemoryStore()
    command_inbox = MemoryCommandInbox()

    class StopOnPollAgent(FakeAgent):
        def __init__(self, inbox: MemoryCommandInbox) -> None:
            super().__init__()
            self._inbox = inbox
            self.cancelled = False

        async def poll(self, handle: AgentSessionHandle) -> AgentProgress:
            self.poll_calls += 1
            if self.poll_calls == 1:
                await self._inbox.enqueue(
                    OperationCommand(
                        operation_id=operation_id,
                        command_type=OperationCommandType.STOP_AGENT_TURN,
                        target_scope=CommandTargetScope.SESSION,
                        target_id=handle.session_id,
                        payload={},
                    )
                )
                return AgentProgress(
                    session_id=handle.session_id,
                    state=AgentProgressState.RUNNING,
                    message="still working",
                    updated_at=datetime.now(UTC),
                )
            return AgentProgress(
                session_id=handle.session_id,
                state=AgentProgressState.COMPLETED,
                message="cancelled",
                updated_at=datetime.now(UTC),
            )

        async def collect(self, handle: AgentSessionHandle) -> AgentResult:
            status = AgentResultStatus.CANCELLED if self.cancelled else AgentResultStatus.SUCCESS
            return AgentResult(
                session_id=handle.session_id,
                status=status,
                output_text="active turn cancelled" if self.cancelled else "completed",
                completed_at=datetime.now(UTC),
            )

        async def cancel(self, handle: AgentSessionHandle) -> None:
            self.cancelled = True

        async def close(self, handle: AgentSessionHandle) -> None:
            pass

    agent = StopOnPollAgent(command_inbox)
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": agent}),
        command_inbox=command_inbox,
    )

    outcome = await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
        operation_id=operation_id,
    )

    operation = await store.load_operation(outcome.operation_id)
    commands = await command_inbox.list(outcome.operation_id)
    assert operation is not None
    assert outcome.status is OperationStatus.COMPLETED
    assert agent.cancelled is True
    assert commands[0].status is CommandStatus.APPLIED
    assert operation.scheduler_state is SchedulerState.ACTIVE
    assert operation.active_session is None
    assert operation.tasks[0].status is TaskStatus.COMPLETED
    assert (
        operation.tasks[0].notes[-1]
        == "Active attached agent turn was stopped by operator command."
    )


@pytest.mark.anyio
async def test_stop_operation_command_cancels_active_attached_run() -> None:
    operation_id = "op-stop-operation"
    store = MemoryStore()
    command_inbox = MemoryCommandInbox()

    class StopOperationOnPollAgent(FakeAgent):
        def __init__(self, inbox: MemoryCommandInbox) -> None:
            super().__init__()
            self._inbox = inbox
            self.cancelled = False

        async def poll(self, handle: AgentSessionHandle) -> AgentProgress:
            self.poll_calls += 1
            if self.poll_calls == 1:
                await self._inbox.enqueue(
                    OperationCommand(
                        operation_id=operation_id,
                        command_type=OperationCommandType.STOP_OPERATION,
                        target_scope=CommandTargetScope.OPERATION,
                        target_id=operation_id,
                        payload={},
                    )
                )
                return AgentProgress(
                    session_id=handle.session_id,
                    state=AgentProgressState.RUNNING,
                    message="still working",
                    updated_at=datetime.now(UTC),
                )
            return AgentProgress(
                session_id=handle.session_id,
                state=AgentProgressState.COMPLETED,
                message="stopped",
                updated_at=datetime.now(UTC),
            )

        async def collect(self, handle: AgentSessionHandle) -> AgentResult:
            if self.cancelled:
                return AgentResult(
                    session_id=handle.session_id,
                    status=AgentResultStatus.CANCELLED,
                    output_text="operation stop command accepted",
                    completed_at=datetime.now(UTC),
                )
            return AgentResult(
                session_id=handle.session_id,
                status=AgentResultStatus.SUCCESS,
                output_text="run complete",
                completed_at=datetime.now(UTC),
            )

        async def cancel(self, handle: AgentSessionHandle) -> None:
            self.cancelled = True

        async def close(self, handle: AgentSessionHandle) -> None:
            pass

    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({
            "claude_acp": StopOperationOnPollAgent(command_inbox),
            "codex_acp": StopOperationOnPollAgent(command_inbox),
        }),
        command_inbox=command_inbox,
    )

    outcome = await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp", "codex_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
        operation_id="op-stop-operation",
    )

    updated = await store.load_operation(outcome.operation_id)
    commands = await command_inbox.list(outcome.operation_id)
    assert updated is not None
    assert updated.status is OperationStatus.CANCELLED
    assert updated.final_summary == "Operation cancelled."
    assert len(commands) == 1
    assert commands[0].command_type is OperationCommandType.STOP_OPERATION
    assert commands[0].status is CommandStatus.APPLIED
    assert outcome.status is OperationStatus.CANCELLED


@pytest.mark.anyio
async def test_operator_service_fails_if_continue_targets_different_adapter() -> None:
    class CrossAdapterContinueBrain:
        def __init__(self) -> None:
            self.calls = 0

        async def decide_next_action(self, state) -> BrainDecision:
            self.calls += 1
            if self.calls == 1:
                return BrainDecision(
                    action_type=BrainActionType.START_AGENT,
                    target_agent="claude_acp",
                    instruction="phase 1",
                    rationale="Start phase 1.",
                )
            return BrainDecision(
                action_type=BrainActionType.CONTINUE_AGENT,
                target_agent="codex_acp",
                instruction="phase 2",
                rationale="Incorrectly continue through another adapter.",
            )

        async def evaluate_result(self, state) -> Evaluation:
            return Evaluation(
                goal_satisfied=False,
                should_continue=True,
                summary="continue",
            )

        async def summarize_progress(self, state) -> ProgressSummary:
            return ProgressSummary(summary="summary")

        async def normalize_artifact(self, goal, result) -> AgentResult:
            return result

    service = make_service(
        brain=CrossAdapterContinueBrain(),
        store=MemoryStore(),
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings(
            {"claude_acp": FakeAgent(), "codex_acp": FakeAgent()}
        ),
    )

    outcome = await service.run(
        OperationGoal(objective="complete two phases"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp", "codex_acp"]),
    )

    assert outcome.status is OperationStatus.FAILED
    assert "different adapter than the active session" in outcome.summary


class StartThenDecisionStopBrain:
    def __init__(self) -> None:
        self.calls = 0

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="claude_acp",
                instruction="produce final artifact",
                rationale="Run the agent first.",
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="Stop after the result already exists.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(
            goal_satisfied=False,
            should_continue=True,
            summary="Need one more brain decision.",
        )

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


@pytest.mark.anyio
async def test_force_recover_collects_completed_background_run_without_wakeup() -> None:
    store = MemoryStore()
    trace_store = MemoryTraceStore()
    event_sink = MemoryEventSink()
    supervisor = FakeSupervisor()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=trace_store,
        event_sink=event_sink,
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        supervisor=supervisor,
    )

    first = await service.run(
        OperationGoal(objective="background task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )

    operation = await store.load_operation(first.operation_id)
    assert operation is not None
    run_id = operation.background_runs[0].run_id
    supervisor.runs[run_id].status = BackgroundRunStatus.COMPLETED
    supervisor.runs[run_id].completed_at = datetime.now(UTC)

    recovered = await service.recover(
        operation.operation_id,
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )

    operation = await store.load_operation(operation.operation_id)
    assert recovered.status is OperationStatus.COMPLETED
    assert recovered.final_result is not None
    assert recovered.final_result.output_text == "completed by fake background agent"
    assert operation is not None
    assert operation.iterations[0].result is not None
    assert operation.iterations[0].result.output_text == "completed by fake background agent"
    assert operation.sessions[0].last_recovered_at is None
    assert any(event.event_type == "session.force_recovered" for event in event_sink.events)


@pytest.mark.anyio
async def test_resume_reconciles_completed_background_run_for_reused_session() -> None:
    store = MemoryStore()
    trace_store = MemoryTraceStore()
    event_sink = MemoryEventSink()
    supervisor = FakeSupervisor()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=trace_store,
        event_sink=event_sink,
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        supervisor=supervisor,
    )

    operation = OperationState(
        goal=OperationGoal(objective="background task"),
        **state_settings(max_iterations=8, allowed_agents=["claude_acp"]),
    )
    session = AgentSessionHandle(
        adapter_key="claude_acp",
        session_id="session-1",
        session_name="main",
    )
    operation.active_session = session
    operation.sessions.append(
        SessionState(
            handle=session,
            status=SessionStatus.RUNNING,
            latest_iteration=6,
            last_result_iteration=4,
            current_execution_id="run-current",
        )
    )
    operation.iterations.extend(
        [
            IterationState(
                index=4,
                session=session,
                result=AgentResult(
                    session_id="session-1",
                    status=AgentResultStatus.SUCCESS,
                    output_text="old result",
                    completed_at=datetime.now(UTC),
                ),
            ),
            IterationState(index=6, session=session),
        ]
    )
    operation.background_runs.append(
        ExecutionState(
            run_id="run-current",
            operation_id=operation.operation_id,
            adapter_key="claude_acp",
            session_id="session-1",
            status=BackgroundRunStatus.RUNNING,
        )
    )
    operation.current_focus = FocusState(
        kind=FocusKind.SESSION,
        target_id="session-1",
        mode=FocusMode.BLOCKING,
    )
    await store.save_operation(operation)

    supervisor.runs["run-current"] = operation.background_runs[0].model_copy(
        update={
            "status": BackgroundRunStatus.COMPLETED,
            "completed_at": datetime.now(UTC),
        }
    )
    supervisor.results["run-current"] = AgentResult(
        session_id="session-1",
        status=AgentResultStatus.SUCCESS,
        output_text="completed by fake background agent",
        completed_at=datetime.now(UTC),
    )

    await service.resume(
        operation.operation_id,
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )

    updated = await store.load_operation(operation.operation_id)
    assert updated is not None
    iteration_six = next(item for item in updated.iterations if item.index == 6)
    assert iteration_six.result is not None
    assert iteration_six.result.output_text == "completed by fake background agent"
    assert updated.sessions[0].status in {
        SessionStatus.IDLE,
        SessionStatus.RUNNING,
    }
    assert updated.sessions[0].last_result_iteration == 6
    assert updated.sessions[0].last_terminal_execution_id == "run-current"
    if updated.sessions[0].status is SessionStatus.IDLE:
        assert updated.sessions[0].current_execution_id is None
        assert updated.sessions[0].current_execution_id is None
    else:
        assert updated.sessions[0].current_execution_id != "run-current"
        assert updated.sessions[0].current_execution_id != "run-current"
    assert updated.current_focus is None or updated.current_focus.target_id != "session-1" or (
        updated.sessions[0].current_execution_id != "run-current"
    )




class StartBackgroundOnlyBrain:
    def __init__(self) -> None:
        self.calls = 0

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        return BrainDecision(
            action_type=BrainActionType.START_AGENT,
            target_agent="claude_acp",
            instruction="run in background",
            rationale="Dispatch the background work.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(
            goal_satisfied=False,
            should_continue=True,
            summary="continue",
        )

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


class CompleteTaskThenStartFreshTaskBrain:
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self.calls = 0

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="claude_acp",
                session_name="next-product-slice-triage",
                instruction="triage the next product slice",
                rationale="Close the previous task and start a fresh product triage.",
                focus_task_id=self.task_id,
                task_updates=[
                    TaskPatch(
                        task_id=self.task_id,
                        status=TaskStatus.COMPLETED,
                        append_notes=["Previous slice is complete; move on to new product triage."],
                    )
                ],
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="done",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(
            goal_satisfied=False,
            should_continue=True,
            summary="continue",
        )

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


@pytest.mark.anyio
async def test_resume_does_not_spawn_duplicate_background_turn_without_wakeup() -> None:
    store = MemoryStore()
    inbox = MemoryWakeupInbox()
    supervisor = FakeSupervisor()
    brain = StartBackgroundOnlyBrain()
    service = make_service(
        brain=brain,
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        wakeup_inbox=inbox,
        supervisor=supervisor,
    )

    first = await service.run(
        OperationGoal(objective="background task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    operation = await store.load_operation(first.operation_id)
    assert operation is not None
    assert first.status is OperationStatus.RUNNING
    assert len(operation.background_runs) == 1
    assert brain.calls == 1


@pytest.mark.anyio
async def test_completed_task_is_not_reused_as_running_focus_on_replan() -> None:
    store = MemoryStore()
    inbox = MemoryWakeupInbox()
    supervisor = FakeSupervisor()
    operation = OperationState(
        goal=OperationGoal(objective="return to product work"),
        **state_settings(max_iterations=5, allowed_agents=["claude_acp"]),
    )
    task = operation.tasks[0]
    task.title = "Activate operator harness end-to-end"
    task.goal = "Complete the minimal tooling slice."
    task.definition_of_done = "Slice is committed and pushed."
    task.status = TaskStatus.READY
    task.effective_priority = 95
    await store.save_operation(operation)

    brain = CompleteTaskThenStartFreshTaskBrain(task.task_id)
    service = make_service(
        brain=brain,
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        wakeup_inbox=inbox,
        supervisor=supervisor,
    )

    resumed = await service.resume(
        operation.operation_id,
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    updated = await store.load_operation(operation.operation_id)

    assert resumed.status is OperationStatus.RUNNING
    assert updated is not None
    updated_task = next(item for item in updated.tasks if item.task_id == task.task_id)
    assert updated_task.status is TaskStatus.COMPLETED
    assert updated_task.linked_session_id is None
    assert updated.current_focus is not None
    assert updated.current_focus.kind is FocusKind.SESSION
    assert updated.current_focus.target_id == "session-1"
    assert updated.iterations[-1].task_id is None


@pytest.mark.anyio
async def test_inject_operator_message_unblocks_blocked_operation_for_replan() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    service = make_service(
        brain=StopImmediatelyBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=inbox,
    )

    operation = OperationState(
        operation_id="op-blocked-replan-message",
        goal=OperationGoal(objective="Continue after a blocked evaluation"),
        **state_settings(allowed_agents=["claude_acp"], max_iterations=4),
        status=OperationStatus.NEEDS_HUMAN,
        final_summary="Blocked pending clarification from the previous cycle.",
    )
    await store.save_operation(operation)

    command = OperationCommand(
        operation_id=operation.operation_id,
        command_type=OperationCommandType.INJECT_OPERATOR_MESSAGE,
        target_scope=CommandTargetScope.OPERATION,
        target_id=operation.operation_id,
        payload={"text": "Do not bypass hooks; fix the blocker honestly and replan."},
    )
    await inbox.enqueue(command)

    outcome = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=2),
    )
    updated = await store.load_operation(operation.operation_id)

    assert outcome.status is OperationStatus.COMPLETED
    assert updated is not None
    assert updated.status is OperationStatus.COMPLETED
    assert updated.operator_messages[-1].text == (
        "Do not bypass hooks; fix the blocker honestly and replan."
    )
    assert inbox.commands[command.command_id].status is CommandStatus.APPLIED
    assert await inbox.list_pending_planning_triggers(operation.operation_id) == []


@pytest.mark.anyio
async def test_resume_processes_persisted_pending_planning_trigger_on_blocked_operation() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    service = make_service(
        brain=StopImmediatelyBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=inbox,
    )

    command = OperationCommand(
        command_id="cmd-persisted-replan",
        operation_id="op-persisted-replan",
        command_type=OperationCommandType.INJECT_OPERATOR_MESSAGE,
        target_scope=CommandTargetScope.OPERATION,
        target_id="op-persisted-replan",
        payload={"text": "Persisted message that still needs a replan cycle."},
        status=CommandStatus.APPLIED,
    )
    await inbox.enqueue(command)
    await inbox.enqueue_planning_trigger(
        PlanningTrigger(
            trigger_id="trigger-persisted-replan",
            operation_id="op-persisted-replan",
            reason="operator_message_recorded",
            source_kind="command",
            source_id=command.command_id,
            dedupe_key="op-persisted-replan:planning_context_changed",
        )
    )

    operation = OperationState(
        operation_id="op-persisted-replan",
        goal=OperationGoal(objective="Continue after persisted replan command"),
        **state_settings(allowed_agents=["claude_acp"], max_iterations=4),
        status=OperationStatus.NEEDS_HUMAN,
        final_summary="Blocked before the replan cycle could run.",
        operator_messages=[
            OperatorMessage(
                text="Persisted message that still needs a replan cycle.",
                source_command_id=command.command_id,
            )
        ],
    )
    await store.save_operation(operation)

    outcome = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=2),
    )
    updated = await store.load_operation(operation.operation_id)

    assert outcome.status is OperationStatus.COMPLETED
    assert updated is not None
    assert updated.status is OperationStatus.COMPLETED
    assert inbox.commands[command.command_id].status is CommandStatus.APPLIED
    assert await inbox.list_pending_planning_triggers(operation.operation_id) == []
