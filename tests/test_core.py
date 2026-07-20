from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

from vibechord.adapters import (
    AdapterGateway,
    LocalRuleBrain,
    ProcessAgentAdapter,
    ProcessBrain,
    ScriptedAgentAdapter,
    ScriptedBrain,
    SingleAgentBrain,
)
from vibechord.codex_exec import CodexExecAdapter, CodexExecConfig
from vibechord.command import CommandApplication
from vibechord.domain import (
    AgentRequest,
    AgentResult,
    AgentTurnDTO,
    BrainAction,
    BrainDecision,
    CommandName,
    ExecutionBudget,
    OperationCommand,
    OperationSnapshot,
    OperationStatus,
)
from vibechord.driver import OperationDriver
from vibechord.projection import ProjectionService
from vibechord.store import EventStoreError, JsonlEventStore
from vibechord.time import FakeClock


def _store(tmp_path: Path) -> JsonlEventStore:
    return JsonlEventStore(tmp_path / "events.jsonl", FakeClock())


def _app(
    tmp_path: Path,
) -> tuple[JsonlEventStore, CommandApplication, ProjectionService]:
    store = _store(tmp_path)
    return store, CommandApplication(store), ProjectionService(store)


def test_execution_budget_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="max_iterations"):
        ExecutionBudget(max_iterations=0)
    with pytest.raises(ValueError, match="max_agent_calls"):
        ExecutionBudget(max_agent_calls=-1)


def test_single_agent_brain_invokes_once_then_completes() -> None:
    brain = SingleAgentBrain("codex-exec")
    initial = OperationSnapshot(
        operation_id="op-1",
        goal="bounded task",
        status=OperationStatus.RUNNING,
        source_sequence=1,
    )
    invoked = brain.decide(initial)
    assert invoked.action is BrainAction.INVOKE_AGENT
    assert invoked.agent_name == "codex-exec"
    assert invoked.agent_input == "bounded task"

    completed = brain.decide(
        OperationSnapshot(
            operation_id="op-1",
            goal="bounded task",
            status=OperationStatus.RUNNING,
            source_sequence=2,
            agent_calls=1,
            last_agent_output="done",
        )
    )
    assert completed.action is BrainAction.COMPLETE
    assert completed.message == "agent execution completed"


def test_codex_exec_adapter_requires_jsonl_and_final_message(tmp_path: Path) -> None:
    executable = tmp_path / "fake-codex"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import pathlib
import sys

prompt = sys.stdin.read()
target = pathlib.Path(sys.argv[sys.argv.index('--output-last-message') + 1])
target.write_text('FINAL:' + prompt, encoding='utf-8')
print(json.dumps({'type': 'thread.started', 'thread_id': 'thread-1'}))
print(json.dumps({'type': 'turn.started'}))
print(json.dumps({'type': 'turn.completed'}))
""",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    config = CodexExecConfig(
        executable=executable,
        working_directory=tmp_path,
        codex_home=codex_home,
        model="gpt-5.6-sol",
        network_access=False,
        environment={"PATH": str(Path(sys.executable).parent)},
        raw_stream_path=tmp_path / "run.jsonl",
        final_message_path=tmp_path / "final.txt",
    )

    adapter = CodexExecAdapter(config)
    result = adapter.invoke("codex-exec", "bounded task")

    assert result.success
    assert result.output == "FINAL:bounded task"
    assert adapter.receipt is not None
    assert adapter.receipt.status == "completed"
    assert adapter.receipt.returncode == 0
    assert adapter.receipt.stream_sha256 is not None
    assert adapter.receipt.final_message_sha256 is not None
    events = [
        json.loads(line) for line in config.raw_stream_path.read_text().splitlines()
    ]
    assert [event["type"] for event in events] == [
        "thread.started",
        "turn.started",
        "turn.completed",
    ]
    assert adapter.receipt.execution_contract_sha256
    assert adapter.receipt.terminal_event == "turn.completed"


def test_codex_exec_adapter_rejects_malformed_jsonl(tmp_path: Path) -> None:
    executable = tmp_path / "fake-codex"
    executable.write_text(
        """#!/usr/bin/env python3
import pathlib
import sys

target = pathlib.Path(sys.argv[sys.argv.index('--output-last-message') + 1])
target.write_text('not enough', encoding='utf-8')
print('not-json')
""",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    config = CodexExecConfig(
        executable=executable,
        working_directory=tmp_path,
        codex_home=codex_home,
        model="gpt-5.6-sol",
        network_access=False,
        environment={"PATH": str(Path(sys.executable).parent)},
        raw_stream_path=tmp_path / "run.jsonl",
        final_message_path=tmp_path / "final.txt",
    )

    adapter = CodexExecAdapter(config)
    result = adapter.invoke("codex-exec", "bounded task")

    assert not result.success
    assert result.error == "Codex emitted malformed JSONL"
    assert adapter.receipt is not None
    assert adapter.receipt.status == "protocol_error"
    assert adapter.receipt.returncode == 0


@pytest.mark.parametrize(
    "event_types",
    [
        ["thread.started", "turn.completed"],
        ["thread.started", "turn.started", "turn.failed"],
        ["thread.started", "turn.started", "turn.aborted", "turn.completed"],
        ["thread.started", "turn.started", "turn.completed", "turn.completed"],
        [
            "thread.started",
            "turn.started",
            "turn.started",
            "turn.completed",
        ],
    ],
)
def test_codex_exec_adapter_requires_one_successful_terminal_turn(
    tmp_path: Path, event_types: list[str]
) -> None:
    executable = tmp_path / "fake-codex"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json,pathlib,sys\n"
        "target=pathlib.Path(sys.argv[sys.argv.index('--output-last-message')+1])\n"
        "target.write_text('invalid terminal stream')\n"
        f"events={event_types!r}\n"
        "for event_type in events: print(json.dumps({'type':event_type}))\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    adapter = CodexExecAdapter(
        CodexExecConfig(
            executable=executable,
            working_directory=tmp_path,
            codex_home=codex_home,
            model="gpt-5.6-sol",
            network_access=False,
            environment={"PATH": str(Path(sys.executable).parent)},
            raw_stream_path=tmp_path / "run.jsonl",
            final_message_path=tmp_path / "final.txt",
        )
    )

    result = adapter.invoke("codex-exec", "bounded task")

    assert not result.success
    assert adapter.receipt is not None
    assert adapter.receipt.status == "protocol_error"
    assert adapter.receipt.terminal_event is None


def test_single_agent_brain_runs_codex_adapter_once(tmp_path: Path) -> None:
    executable = tmp_path / "fake-codex"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import pathlib
import sys

prompt = sys.stdin.read()
target = pathlib.Path(sys.argv[sys.argv.index('--output-last-message') + 1])
target.write_text('RESULT:' + prompt, encoding='utf-8')
print(json.dumps({'type': 'thread.started', 'thread_id': 'thread-1'}))
print(json.dumps({'type': 'turn.started'}))
print(json.dumps({'type': 'turn.completed'}))
""",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    store, command_app, projection = _app(tmp_path)
    command_app.apply(
        OperationCommand(
            name=CommandName.START,
            command_id="start",
            operation_id="op-1",
            payload={"goal": "one bounded tranche"},
        )
    )
    adapter = CodexExecAdapter(
        CodexExecConfig(
            executable=executable,
            working_directory=tmp_path,
            codex_home=codex_home,
            model="gpt-5.6-sol",
            network_access=False,
            environment={"PATH": str(Path(sys.executable).parent)},
            raw_stream_path=tmp_path / "run.jsonl",
            final_message_path=tmp_path / "final.txt",
        )
    )
    driver = OperationDriver(
        store,
        projection,
        AdapterGateway(SingleAgentBrain("codex-exec"), adapter),
    )

    result = driver.run_until_blocked_or_terminal(
        "op-1", ExecutionBudget(max_iterations=2, max_agent_calls=1)
    )

    assert result.status == "completed"
    assert result.iterations == 2
    assert projection.status("op-1").last_agent_output == "RESULT:one bounded tranche"
    event_kinds = [event.kind for event in store.replay("op-1")]
    assert event_kinds.count("agent.invocation.started") == 1
    assert event_kinds.count("agent.invocation.finished") == 1
    assert adapter.receipt is not None
    assert adapter.receipt.status == "completed"


def test_start_command_appends_metadata_and_replay_builds_status(
    tmp_path: Path,
) -> None:
    store, command_app, projection = _app(tmp_path)
    result = command_app.apply(
        OperationCommand(
            name=CommandName.START,
            command_id="cmd-1",
            operation_id="op-1",
            payload={"goal": "ship it"},
        )
    )
    assert result.accepted
    assert result.operation_id == "op-1"
    events = store.replay("op-1")
    assert [event.sequence for event in events] == [1, 2]
    assert events[0].event_id
    status = projection.status("op-1")
    assert status.status == "running"
    assert status.goal == "ship it"


def test_duplicate_command_id_is_idempotent(tmp_path: Path) -> None:
    store, command_app, _projection = _app(tmp_path)
    command = OperationCommand(
        name=CommandName.START,
        command_id="cmd-1",
        operation_id="op-1",
        payload={"goal": "same"},
    )
    first = command_app.apply(command)
    second = command_app.apply(command)
    assert first.resulting_event_ids == second.resulting_event_ids
    assert len(store.replay("op-1")) == 2


def test_event_store_detects_corrupt_events(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("{not-json}\n", encoding="utf-8")
    store = JsonlEventStore(path, FakeClock())
    with pytest.raises(EventStoreError, match="corrupt event"):
        store.all_events()


def test_operation_driver_completion_and_iteration_limit(tmp_path: Path) -> None:
    store, command_app, projection = _app(tmp_path)
    command_app.apply(
        OperationCommand(
            name=CommandName.START,
            command_id="start",
            operation_id="op-1",
            payload={"goal": "complete"},
        )
    )
    driver = OperationDriver(
        store,
        projection,
        AdapterGateway(
            ScriptedBrain([BrainDecision(BrainAction.COMPLETE, message="done")]),
            ScriptedAgentAdapter(),
        ),
    )
    result = driver.run_until_blocked_or_terminal("op-1")
    assert result.status == "completed"
    assert projection.status("op-1").stop_reason == "done"

    command_app.apply(
        OperationCommand(
            name=CommandName.START,
            command_id="start-2",
            operation_id="op-2",
            payload={"goal": "limit"},
        )
    )
    wait_driver = OperationDriver(
        store,
        projection,
        AdapterGateway(
            ScriptedBrain([BrainDecision(BrainAction.INVOKE_AGENT)] * 5),
            ScriptedAgentAdapter(),
        ),
    )
    limited = wait_driver.run_until_blocked_or_terminal(
        "op-2", ExecutionBudget(max_iterations=1)
    )
    assert limited.status == "failed"
    assert projection.status("op-2").stop_reason == "iteration_limit"


def test_attention_answer_and_live_message_flow(tmp_path: Path) -> None:
    store, command_app, projection = _app(tmp_path)
    command_app.apply(
        OperationCommand(
            name=CommandName.START,
            command_id="start",
            operation_id="op-1",
            payload={"goal": "attention"},
        )
    )
    driver = OperationDriver(
        store,
        projection,
        AdapterGateway(
            ScriptedBrain(
                [
                    BrainDecision(BrainAction.REQUEST_ATTENTION, prompt="approve?"),
                    BrainDecision(BrainAction.COMPLETE, message="done"),
                ]
            ),
            ScriptedAgentAdapter(),
        ),
    )
    blocked = driver.run_until_blocked_or_terminal("op-1")
    assert blocked.status == "blocked"
    attention_id = projection.status("op-1").attention_id
    assert attention_id is not None
    command_app.apply(
        OperationCommand(
            name=CommandName.POST_MESSAGE,
            command_id="msg",
            operation_id="op-1",
            payload={"text": "continue"},
        )
    )
    command_app.apply(
        OperationCommand(
            name=CommandName.ANSWER_ATTENTION,
            command_id="answer",
            operation_id="op-1",
            payload={"attention_id": attention_id, "text": "yes"},
        )
    )
    done = driver.run_until_blocked_or_terminal("op-1")
    assert done.status == "completed"
    assert "continue" in projection.status("op-1").recent_messages


def test_fleet_and_live_feed_projection(tmp_path: Path) -> None:
    store, command_app, projection = _app(tmp_path)
    command_app.apply(
        OperationCommand(
            name=CommandName.START,
            command_id="start",
            operation_id="op-1",
            payload={"goal": "fleet"},
        )
    )
    rows = projection.fleet()
    assert rows[0].operation_id == "op-1"
    envelopes = projection.live_feed("op-1")
    assert envelopes[0].kind == "canonical_event"
    assert envelopes[0].sequence == 1


def test_resume_after_persisted_events(tmp_path: Path) -> None:
    store, command_app, projection = _app(tmp_path)
    command_app.apply(
        OperationCommand(
            name=CommandName.START,
            command_id="start",
            operation_id="op-1",
            payload={"goal": "resume"},
        )
    )
    resumed_store = JsonlEventStore(tmp_path / "events.jsonl", FakeClock())
    resumed_projection = ProjectionService(resumed_store)
    assert resumed_projection.status("op-1").goal == "resume"


def test_adapter_failure_becomes_failed_state_and_event(tmp_path: Path) -> None:
    store, command_app, projection = _app(tmp_path)
    command_app.apply(
        OperationCommand(
            name=CommandName.START,
            command_id="start",
            operation_id="op-1",
            payload={"goal": "adapter failure"},
        )
    )
    driver = OperationDriver(
        store,
        projection,
        AdapterGateway(
            ScriptedBrain(
                [
                    BrainDecision(
                        BrainAction.INVOKE_AGENT,
                        agent_name="fake-agent",
                        agent_input="fail please",
                    )
                ]
            ),
            ScriptedAgentAdapter(),
        ),
    )
    result = driver.run_until_blocked_or_terminal("op-1")
    assert result.status == "failed"
    assert projection.status("op-1").stop_reason == "scripted adapter failure"
    assert any(
        event.kind == "agent.invocation.failed" for event in store.replay("op-1")
    )


def test_operation_driver_invokes_multiple_named_agents_in_one_iteration(
    tmp_path: Path,
) -> None:
    class NamedAgentAdapter:
        def invoke(self, agent_name: str, agent_input: str) -> AgentResult:
            outputs = {
                "planner": "planned",
                "critic": "critiqued",
                "verifier": "verified",
            }
            return AgentResult(output=outputs[agent_name])

    store, command_app, projection = _app(tmp_path)
    command_app.apply(
        OperationCommand(
            name=CommandName.START,
            command_id="start",
            operation_id="op-1",
            payload={"goal": "multi-agent task"},
        )
    )
    driver = OperationDriver(
        store,
        projection,
        AdapterGateway(
            ScriptedBrain(
                [
                    BrainDecision(
                        BrainAction.INVOKE_AGENTS,
                        agent_requests=(
                            AgentRequest("planner", "plan"),
                            AgentRequest("critic", "critique"),
                            AgentRequest("verifier", "verify"),
                        ),
                    ),
                    BrainDecision(BrainAction.COMPLETE, message="workers done"),
                ]
            ),
            NamedAgentAdapter(),
        ),
    )

    result = driver.run_until_blocked_or_terminal("op-1")

    assert result.status == "completed"
    status = projection.status("op-1")
    assert status.agent_outputs == (
        AgentTurnDTO(agent_name="planner", status="completed", output="planned"),
        AgentTurnDTO(agent_name="critic", status="completed", output="critiqued"),
        AgentTurnDTO(agent_name="verifier", status="completed", output="verified"),
    )
    events = store.replay("op-1")
    assert [
        event.payload["agent_name"]
        for event in events
        if event.kind == "agent.invocation.started"
    ] == ["planner", "critic", "verifier"]
    event_kinds = [event.kind for event in events]
    first_finished = event_kinds.index("agent.invocation.finished")
    assert event_kinds[:first_finished].count("agent.invocation.started") == 3


def test_multi_agent_invocations_run_concurrently(tmp_path: Path) -> None:
    class BarrierAgentAdapter:
        def __init__(self, expected: int) -> None:
            self.expected = expected
            self.active = 0
            self.max_active = 0
            self.lock = threading.Lock()
            self.all_active = threading.Event()

        def invoke(self, agent_name: str, agent_input: str) -> AgentResult:
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                if self.active == self.expected:
                    self.all_active.set()
            if not self.all_active.wait(timeout=1.0):
                return AgentResult(
                    output="", success=False, error="workers did not overlap"
                )
            with self.lock:
                self.active -= 1
            return AgentResult(output=f"{agent_name}:{agent_input}")

    store, command_app, projection = _app(tmp_path)
    command_app.apply(
        OperationCommand(
            name=CommandName.START,
            command_id="start",
            operation_id="op-1",
            payload={"goal": "parallel multi-agent task"},
        )
    )
    adapter = BarrierAgentAdapter(expected=3)
    driver = OperationDriver(
        store,
        projection,
        AdapterGateway(
            ScriptedBrain(
                [
                    BrainDecision(
                        BrainAction.INVOKE_AGENTS,
                        agent_requests=(
                            AgentRequest("one", "A"),
                            AgentRequest("two", "B"),
                            AgentRequest("three", "C"),
                        ),
                    ),
                    BrainDecision(BrainAction.COMPLETE, message="parallel done"),
                ]
            ),
            adapter,
        ),
    )

    result = driver.run_until_blocked_or_terminal("op-1")

    assert result.status == "completed"
    assert adapter.max_active == 3
    assert [item.agent_name for item in projection.status("op-1").agent_outputs] == [
        "one",
        "two",
        "three",
    ]


def test_multi_agent_invocation_respects_agent_call_budget(tmp_path: Path) -> None:
    store, command_app, projection = _app(tmp_path)
    command_app.apply(
        OperationCommand(
            name=CommandName.START,
            command_id="start",
            operation_id="op-1",
            payload={"goal": "multi-agent budget"},
        )
    )
    driver = OperationDriver(
        store,
        projection,
        AdapterGateway(
            ScriptedBrain(
                [
                    BrainDecision(
                        BrainAction.INVOKE_AGENTS,
                        agent_requests=(
                            AgentRequest("one", "one"),
                            AgentRequest("two", "two"),
                        ),
                    )
                ]
            ),
            ScriptedAgentAdapter(),
        ),
    )

    result = driver.run_until_blocked_or_terminal(
        "op-1", ExecutionBudget(max_agent_calls=1)
    )

    assert result.status == "failed"
    assert projection.status("op-1").stop_reason == "agent_call_limit"
    assert not any(
        event.kind == "agent.invocation.started" for event in store.replay("op-1")
    )


def test_process_agent_adapter_and_local_rule_brain(tmp_path: Path) -> None:
    store, command_app, projection = _app(tmp_path)
    command_app.apply(
        OperationCommand(
            name=CommandName.START,
            command_id="start",
            operation_id="op-1",
            payload={"goal": "agent process task"},
        )
    )
    adapter = ProcessAgentAdapter(
        (
            sys.executable,
            "-c",
            "import sys; print('processed:' + sys.stdin.read().strip())",
        )
    )
    driver = OperationDriver(
        store,
        projection,
        AdapterGateway(LocalRuleBrain(), adapter),
    )
    result = driver.run_until_blocked_or_terminal("op-1")
    assert result.status == "completed"
    assert "processed:agent process task" in str(projection.status("op-1").stop_reason)


def test_process_brain_adapter_maps_json_decisions(tmp_path: Path) -> None:
    store, command_app, projection = _app(tmp_path)
    command_app.apply(
        OperationCommand(
            name=CommandName.START,
            command_id="start",
            operation_id="op-1",
            payload={"goal": "brain process task"},
        )
    )
    brain = ProcessBrain(
        (
            sys.executable,
            "-c",
            "import json; "
            "print(json.dumps({'action':'complete','message':'external'}))",
        )
    )
    driver = OperationDriver(
        store,
        projection,
        AdapterGateway(brain, ScriptedAgentAdapter()),
    )

    result = driver.run_until_blocked_or_terminal("op-1")

    assert result.status == "completed"
    assert projection.status("op-1").stop_reason == "external"


def test_process_brain_adapter_maps_multi_agent_decisions(tmp_path: Path) -> None:
    store, command_app, projection = _app(tmp_path)
    command_app.apply(
        OperationCommand(
            name=CommandName.START,
            command_id="start",
            operation_id="op-1",
            payload={"goal": "brain process multi-agent task"},
        )
    )
    brain = ProcessBrain(
        (
            sys.executable,
            "-c",
            "import json; print(json.dumps({"
            "'action':'invoke_agents',"
            "'message':'',"
            "'prompt':'',"
            "'agent_name':'',"
            "'agent_input':'',"
            "'agents':["
            "{'agent_name':'alpha','agent_input':'A'},"
            "{'agent_name':'beta','agent_input':'B'}"
            "]}))",
        )
    )
    driver = OperationDriver(
        store,
        projection,
        AdapterGateway(
            ScriptedBrain(
                [
                    brain.decide(projection.snapshot("op-1")),
                    BrainDecision(BrainAction.COMPLETE, message="done"),
                ]
            ),
            ScriptedAgentAdapter(
                results=[
                    AgentResult(output="alpha out"),
                    AgentResult(output="beta out"),
                ]
            ),
        ),
    )

    result = driver.run_until_blocked_or_terminal("op-1")

    assert result.status == "completed"
    assert [item.agent_name for item in projection.status("op-1").agent_outputs] == [
        "alpha",
        "beta",
    ]


def test_process_brain_adapter_failure_is_explicit() -> None:
    brain = ProcessBrain(
        (
            sys.executable,
            "-c",
            "print('not-json')",
        )
    )

    decision = brain.decide(
        OperationSnapshot(
            operation_id="op-1",
            goal="bad brain",
            status=OperationStatus.RUNNING,
            source_sequence=1,
        )
    )

    assert decision.action == BrainAction.FAIL
    assert "invalid brain JSON" in decision.message
