"""AdapterGateway and deterministic fake adapters."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field

from vibechord.domain import (
    AgentRequest,
    AgentResult,
    BrainAction,
    BrainDecision,
    OperationSnapshot,
    OperationStatus,
)
from vibechord.jsonutil import to_jsonable
from vibechord.protocols import AgentAdapter, OperatorBrain


@dataclass
class ScriptedBrain:
    """Deterministic operator brain for tests and local harnesses.

    Example:
        >>> brain = ScriptedBrain([BrainDecision(BrainAction.COMPLETE, message="done")])
        >>> brain.decide(_snapshot()).action
        <BrainAction.COMPLETE: 'complete'>
    """

    decisions: list[BrainDecision]
    default_decision: BrainDecision = BrainDecision(
        BrainAction.COMPLETE, message="done"
    )

    def decide(self, snapshot: OperationSnapshot) -> BrainDecision:
        """Return the next scripted decision."""

        if self.decisions:
            return self.decisions.pop(0)
        return self.default_decision


@dataclass
class ScriptedAgentAdapter:
    """Deterministic external agent adapter."""

    results: list[AgentResult] = field(default_factory=list)
    default_result: AgentResult = AgentResult(output="agent completed")

    def invoke(self, agent_name: str, agent_input: str) -> AgentResult:
        """Return the next scripted agent result."""

        if self.results:
            return self.results.pop(0)
        if "fail" in agent_input.lower():
            return AgentResult(
                output="", success=False, error="scripted adapter failure"
            )
        return self.default_result


@dataclass(frozen=True)
class ProcessAgentAdapter:
    """External agent adapter backed by a local process command.

    Example:
        >>> adapter = ProcessAgentAdapter(("python", "-c", "print('ok')"))
        >>> adapter.invoke("local", "").success
        True
    """

    command: tuple[str, ...]
    timeout_seconds: float = 30.0

    def invoke(self, agent_name: str, agent_input: str) -> AgentResult:
        """Invoke a local process and map stdout/stderr into AgentResult."""

        if not self.command:
            return AgentResult(output="", success=False, error="empty process command")
        try:
            completed = subprocess.run(
                self.command,
                input=agent_input,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return AgentResult(output="", success=False, error="process timed out")
        except OSError as exc:
            return AgentResult(output="", success=False, error=str(exc))
        if completed.returncode == 0:
            return AgentResult(output=completed.stdout.strip(), success=True)
        error = completed.stderr.strip() or completed.stdout.strip()
        return AgentResult(
            output=completed.stdout.strip(),
            success=False,
            error=error or f"process exited {completed.returncode}",
        )


@dataclass(frozen=True)
class ProcessBrain:
    """Operator brain backed by a local process that returns JSON decisions."""

    command: tuple[str, ...]
    timeout_seconds: float = 30.0

    def decide(self, snapshot: OperationSnapshot) -> BrainDecision:
        """Send a snapshot to the process and map JSON stdout into BrainDecision."""

        if not self.command:
            return BrainDecision(BrainAction.FAIL, message="empty brain command")
        try:
            completed = subprocess.run(
                self.command,
                input=json.dumps(to_jsonable(snapshot), sort_keys=True),
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return BrainDecision(BrainAction.FAIL, message="brain process timed out")
        except OSError as exc:
            return BrainDecision(BrainAction.FAIL, message=str(exc))
        if completed.returncode != 0:
            error = completed.stderr.strip() or completed.stdout.strip()
            return BrainDecision(
                BrainAction.FAIL,
                message=error or f"brain process exited {completed.returncode}",
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            return BrainDecision(
                BrainAction.FAIL,
                message=f"invalid brain JSON: {exc.msg}",
            )
        if not isinstance(payload, dict):
            return BrainDecision(BrainAction.FAIL, message="brain JSON must be object")
        return _brain_decision_from_payload(payload)


class LocalRuleBrain:
    """Small local brain that can drive fake or process agents without a network."""

    def decide(self, snapshot: OperationSnapshot) -> BrainDecision:
        """Choose a deterministic next action from replay-derived state."""

        if snapshot.open_attention_id is not None:
            return BrainDecision(BrainAction.WAIT)
        if snapshot.last_agent_output is not None:
            return BrainDecision(
                BrainAction.COMPLETE,
                message=f"agent output: {snapshot.last_agent_output}",
            )
        if "attention" in snapshot.goal.lower():
            return BrainDecision(
                BrainAction.REQUEST_ATTENTION,
                prompt="Approve continuing this operation?",
            )
        if "agent" in snapshot.goal.lower():
            return BrainDecision(
                BrainAction.INVOKE_AGENT,
                agent_name="local-agent",
                agent_input=snapshot.goal,
            )
        return BrainDecision(BrainAction.COMPLETE, message="completed")


class AdapterGateway:
    """Single gateway for operator brain and external agent protocols."""

    def __init__(self, brain: OperatorBrain, agent_adapter: AgentAdapter) -> None:
        """Create an adapter gateway."""

        self.brain = brain
        self.agent_adapter = agent_adapter

    def decide(self, snapshot: OperationSnapshot) -> BrainDecision:
        """Ask the operator brain for a decision."""

        return self.brain.decide(snapshot)

    def invoke_agent(self, agent_name: str, agent_input: str) -> AgentResult:
        """Invoke an external agent adapter."""

        return self.agent_adapter.invoke(agent_name, agent_input)


def _brain_decision_from_payload(payload: dict[object, object]) -> BrainDecision:
    action_value = payload.get("action")
    if not isinstance(action_value, str):
        return BrainDecision(BrainAction.FAIL, message="brain action must be string")
    try:
        action = BrainAction(action_value)
    except ValueError:
        return BrainDecision(
            BrainAction.FAIL, message=f"unknown brain action: {action_value}"
        )
    return BrainDecision(
        action=action,
        message=_optional_str(payload, "message"),
        prompt=_optional_str(payload, "prompt"),
        agent_name=_optional_str(payload, "agent_name") or "fake-agent",
        agent_input=_optional_str(payload, "agent_input"),
        agent_requests=_agent_requests_from_payload(payload),
    )


def _agent_requests_from_payload(
    payload: dict[object, object],
) -> tuple[AgentRequest, ...]:
    raw_agents = payload.get("agents")
    if not isinstance(raw_agents, list):
        return ()
    requests: list[AgentRequest] = []
    for raw_agent in raw_agents:
        if not isinstance(raw_agent, dict):
            continue
        name = raw_agent.get("agent_name")
        agent_input = raw_agent.get("agent_input")
        if isinstance(name, str) and isinstance(agent_input, str):
            requests.append(AgentRequest(agent_name=name, agent_input=agent_input))
    return tuple(requests)


def _optional_str(payload: dict[object, object], name: str) -> str:
    value = payload.get(name)
    if isinstance(value, str):
        return value
    return ""


def _snapshot() -> OperationSnapshot:
    return OperationSnapshot(
        operation_id="op",
        goal="goal",
        status=OperationStatus.RUNNING,
        source_sequence=1,
    )
