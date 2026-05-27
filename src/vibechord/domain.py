"""Domain model for the vibechord operation loop.

The domain module owns vocabulary and invariants only. Persistence, rendering,
and provider-specific payloads live elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal


class OperationStatus(StrEnum):
    """Lifecycle states for an operation."""

    RUNNING = "running"
    BLOCKED = "blocked"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class CommandName(StrEnum):
    """Typed command names accepted by CommandApplication."""

    START = "start"
    CANCEL = "cancel"
    PAUSE = "pause"
    RESUME = "resume"
    ANSWER_ATTENTION = "answer_attention"
    POST_MESSAGE = "post_message"
    INTERRUPT = "interrupt"


class BrainAction(StrEnum):
    """Actions returned by an operator brain."""

    COMPLETE = "complete"
    FAIL = "fail"
    REQUEST_ATTENTION = "request_attention"
    INVOKE_AGENT = "invoke_agent"
    INVOKE_AGENTS = "invoke_agents"
    WAIT = "wait"


EnvelopeKind = Literal[
    "canonical_event", "derived_projection", "runtime_overlay", "warning"
]


@dataclass(frozen=True)
class ExecutionBudget:
    """Deterministic stop policy limits.

    Example:
        >>> ExecutionBudget(max_iterations=1).max_iterations
        1
    """

    max_iterations: int = 10
    max_agent_calls: int = 10

    def __post_init__(self) -> None:
        """Validate budget values."""

        if self.max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        if self.max_agent_calls < 0:
            raise ValueError("max_agent_calls must be >= 0")


@dataclass(frozen=True)
class OperationCommand:
    """A typed input to CommandApplication."""

    name: CommandName
    command_id: str
    operation_id: str | None = None
    payload: dict[str, str | int | bool] = field(default_factory=dict)


@dataclass(frozen=True)
class RunEvent:
    """Canonical event persisted by EventStore."""

    operation_id: str
    sequence: int
    event_id: str
    kind: str
    timestamp: str
    payload: dict[str, str | int | bool]
    command_id: str | None = None


@dataclass(frozen=True)
class CommandResult:
    """Stable command response shared by delivery surfaces."""

    command_id: str
    accepted: bool
    code: str
    message: str
    operation_id: str | None = None
    resulting_event_ids: tuple[str, ...] = ()
    retryable: bool = False


@dataclass(frozen=True)
class AgentRequest:
    """One external agent invocation requested by the operator brain.

    Example:
        >>> AgentRequest(agent_name="reviewer", agent_input="check").agent_name
        'reviewer'
    """

    agent_name: str
    agent_input: str


@dataclass(frozen=True)
class BrainDecision:
    """Operator brain decision in domain-level terms."""

    action: BrainAction
    message: str = ""
    prompt: str = ""
    agent_name: str = "fake-agent"
    agent_input: str = ""
    agent_requests: tuple[AgentRequest, ...] = ()


@dataclass(frozen=True)
class AgentResult:
    """Domain-level result from an external agent adapter."""

    output: str
    success: bool = True
    error: str = ""


@dataclass(frozen=True)
class AgentTurnDTO:
    """Projected agent turn state for status, TUI, REST, and SDK surfaces."""

    agent_name: str
    status: str
    output: str = ""
    error: str = ""


@dataclass(frozen=True)
class OperationSnapshot:
    """Replay-derived canonical operation state."""

    operation_id: str
    goal: str
    status: OperationStatus
    source_sequence: int
    iterations: int = 0
    agent_calls: int = 0
    stop_reason: str | None = None
    open_attention_id: str | None = None
    open_attention_prompt: str | None = None
    recent_messages: tuple[str, ...] = ()
    last_agent_output: str | None = None
    agent_outputs: tuple[AgentTurnDTO, ...] = ()


@dataclass(frozen=True)
class StatusDTO:
    """Shared operation status DTO for CLI, TUI, and REST."""

    operation_id: str
    status: str
    goal: str
    source_sequence: int
    stale: bool
    stop_reason: str | None
    attention_id: str | None
    attention_prompt: str | None
    recent_messages: tuple[str, ...]
    last_agent_output: str | None
    agent_outputs: tuple[AgentTurnDTO, ...] = ()


@dataclass(frozen=True)
class FleetRowDTO:
    """Shared fleet row DTO."""

    operation_id: str
    status: str
    label: str
    attention: str | None
    live_chat: str | None
    source_sequence: int
    stale: bool


@dataclass(frozen=True)
class LiveFeedEnvelope:
    """Shared live-feed envelope for all delivery transports."""

    operation_id: str
    sequence: int
    kind: EnvelopeKind
    payload_kind: str
    payload: dict[str, str | int | bool | None]
    stale: bool = False


@dataclass(frozen=True)
class HarnessSummary:
    """Machine-readable fake-harness summary."""

    schema_version: str
    run_id: str
    workflow: str
    status: str
    operation_ids: tuple[str, ...]
    event_artifact_paths: tuple[str, ...]
    last_event_sequence_by_operation: dict[str, int]
    rails_exercised: tuple[str, ...]
    failed_rail: str | None
    failure_message: str | None
    started_at: str
    finished_at: str
