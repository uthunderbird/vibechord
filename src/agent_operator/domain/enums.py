from enum import StrEnum


class AgentProgressState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class AgentResultStatus(StrEnum):
    SUCCESS = "success"
    INCOMPLETE = "incomplete"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DISCONNECTED = "disconnected"


class BrainActionType(StrEnum):
    START_AGENT = "start_agent"
    CONTINUE_AGENT = "continue_agent"
    WAIT_FOR_AGENT = "wait_for_agent"
    REQUEST_CLARIFICATION = "request_clarification"
    APPLY_POLICY = "apply_policy"
    FAIL = "fail"
    STOP = "stop"


class OperationStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    NEEDS_HUMAN = "needs_human"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CanonicalPersistenceMode(StrEnum):
    EVENT_SOURCED = "event_sourced"


class FeatureStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    ACCEPTED = "accepted"


class TaskStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SessionPolicy(StrEnum):
    ONE_SHOT = "one_shot"
    PREFER_REUSE = "prefer_reuse"
    REQUIRE_REUSE = "require_reuse"


class SessionStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackgroundRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DISCONNECTED = "disconnected"


class SessionObservedState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    TERMINAL = "terminal"


class SessionTerminalState(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionMode(StrEnum):
    ATTACHED = "attached"
    BACKGROUND = "background"


class ExecutionLaunchKind(StrEnum):
    NEW = "new"
    CONTINUE = "continue"
    RECOVER = "recover"


class ExecutionObservedState(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOST = "lost"


class MemoryScope(StrEnum):
    OBJECTIVE = "objective"
    TASK = "task"
    SESSION = "session"
    PROJECT = "project"


class MemoryFreshness(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    SUPERSEDED = "superseded"


class FocusKind(StrEnum):
    TASK = "task"
    SESSION = "session"
    DEPENDENCY_BARRIER = "dependency_barrier"
    ATTENTION_REQUEST = "attention_request"


class FocusMode(StrEnum):
    ADVISORY = "advisory"
    BLOCKING = "blocking"


class InterruptPolicy(StrEnum):
    MATERIAL_WAKEUP = "material_wakeup"
    TERMINAL_ONLY = "terminal_only"


class ResumePolicy(StrEnum):
    REPLAN = "replan"
    RETURN_IF_STILL_RELEVANT = "return_if_still_relevant"


class RunMode(StrEnum):
    ATTACHED = "attached"
    RESUMABLE = "resumable"


class SessionReusePolicy(StrEnum):
    ALWAYS_NEW = "always_new"
    REUSE_IF_IDLE = "reuse_if_idle"


class BackgroundRuntimeMode(StrEnum):
    INLINE = "inline"
    ATTACHED_LIVE = "attached_live"
    RESUMABLE_WAKEUP = "resumable_wakeup"


class RunEventKind(StrEnum):
    TRACE = "trace"
    WAKEUP = "wakeup"


class FactFamily(StrEnum):
    ADAPTER = "adapter"
    TECHNICAL = "technical"


class SchedulerState(StrEnum):
    ACTIVE = "active"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    DRAINING = "draining"


class InvolvementLevel(StrEnum):
    UNATTENDED = "unattended"
    AUTO = "auto"
    COLLABORATIVE = "collaborative"
    APPROVAL_HEAVY = "approval_heavy"


class OperationCommandType(StrEnum):
    PAUSE_OPERATOR = "pause_operator"
    RESUME_OPERATOR = "resume_operator"
    STOP_OPERATION = "stop_operation"
    STOP_AGENT_TURN = "stop_agent_turn"
    SET_INVOLVEMENT_LEVEL = "set_involvement_level"
    SET_ALLOWED_AGENTS = "set_allowed_agents"
    SET_EXECUTION_PROFILE = "set_execution_profile"
    PATCH_OBJECTIVE = "patch_objective"
    PATCH_HARNESS = "patch_harness"
    PATCH_SUCCESS_CRITERIA = "patch_success_criteria"
    INJECT_OPERATOR_MESSAGE = "inject_operator_message"
    ANSWER_ATTENTION_REQUEST = "answer_attention_request"
    RECORD_POLICY_DECISION = "record_policy_decision"
    REVOKE_POLICY_DECISION = "revoke_policy_decision"


class AttentionType(StrEnum):
    QUESTION = "question"
    APPROVAL_REQUEST = "approval_request"
    POLICY_GAP = "policy_gap"
    BLOCKED_EXTERNAL_DEPENDENCY = "blocked_external_dependency"
    NOVEL_STRATEGIC_FORK = "novel_strategic_fork"
    DOCUMENT_UPDATE_PROPOSAL = "document_update_proposal"


class AttentionStatus(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class PolicyCategory(StrEnum):
    GENERAL = "general"
    TESTING = "testing"
    WORKFLOW = "workflow"
    RELEASE = "release"
    AUTONOMY = "autonomy"


class PolicyStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


class PolicyCoverageStatus(StrEnum):
    NO_SCOPE = "no_scope"
    NO_POLICY = "no_policy"
    COVERED = "covered"
    UNCOVERED = "uncovered"


class CommandTargetScope(StrEnum):
    OPERATION = "operation"
    TASK = "task"
    BRANCH = "branch"
    SESSION = "session"
    AGENT_TURN = "agent_turn"
    ATTENTION_REQUEST = "attention_request"


class CommandStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"


class ControlIntentKind(StrEnum):
    USER_COMMAND = "user_command"
    PLANNING_TRIGGER = "planning_trigger"


class ControlIntentStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
