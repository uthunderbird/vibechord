from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from agent_operator.domain.agent import AgentResult, AgentSessionHandle
from agent_operator.domain.attention import AttentionRequest
from agent_operator.domain.control import OperatorMessage
from agent_operator.domain.enums import (
    BackgroundRunStatus,
    BackgroundRuntimeMode,
    CanonicalPersistenceMode,
    ExecutionLaunchKind,
    ExecutionMode,
    ExecutionObservedState,
    FeatureStatus,
    FocusKind,
    FocusMode,
    InterruptPolicy,
    InvolvementLevel,
    MemoryFreshness,
    MemoryScope,
    OperationStatus,
    PolicyCoverageStatus,
    ResumePolicy,
    RunMode,
    SchedulerState,
    SessionObservedState,
    SessionPolicy,
    SessionStatus,
    SessionTerminalState,
    TaskStatus,
)
from agent_operator.domain.policy import PolicyCoverage, PolicyEntry
from agent_operator.domain.read_model import DecisionRecord
from agent_operator.domain.traceability import (
    AgentTurnBrief,
    AgentTurnSummary,
    IterationBrief,
    OperationBrief,
)

if TYPE_CHECKING:
    from agent_operator.domain.brain import BrainDecision


class ExternalTicketLink(BaseModel):
    provider: str
    project_key: str
    ticket_id: str
    url: str | None = None
    title: str | None = None
    reported: bool = False


class OperationGoal(BaseModel):
    objective: str
    harness_instructions: str | None = None
    success_criteria: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    external_ticket: ExternalTicketLink | None = None

    @property
    def objective_text(self) -> str:
        return self.objective.strip()

    @property
    def harness_text(self) -> str | None:
        text = (self.harness_instructions or "").strip()
        return text or None


class OperationPolicy(BaseModel):
    """Durable operation-owned governance state."""

    allowed_agents: list[str] = Field(default_factory=list)
    involvement_level: InvolvementLevel = InvolvementLevel.AUTO


class ExecutionBudget(BaseModel):
    """Non-canonical execution budget for one live operation run."""

    max_iterations: int = 100
    timeout_seconds: int | None = None
    max_task_retries: int = 2


class RuntimeHints(BaseModel):
    """Non-canonical runtime/read-model helper values."""

    operator_message_window: int = 3
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionProfileOverride(BaseModel):
    adapter_key: str
    model: str
    effort: str | None = None
    reasoning_effort: str | None = None
    approval_policy: str | None = None
    sandbox_mode: str | None = None

    @property
    def effort_field_name(self) -> str | None:
        if self.reasoning_effort is not None:
            return "reasoning_effort"
        if self.effort is not None:
            return "effort"
        return None

    @property
    def effort_value(self) -> str | None:
        if self.reasoning_effort is not None:
            return self.reasoning_effort
        if self.effort is not None:
            return self.effort
        return None


class ExecutionProfileStamp(BaseModel):
    adapter_key: str
    model: str
    effort_field_name: str | None = None
    effort_value: str | None = None
    approval_policy: str | None = None
    sandbox_mode: str | None = None


class RunOptions(BaseModel):
    emit_reasoning: bool = True
    emit_events: bool = True
    dry_run: bool = False
    run_mode: RunMode = RunMode.ATTACHED
    background_runtime_mode: BackgroundRuntimeMode = BackgroundRuntimeMode.ATTACHED_LIVE
    max_cycles: int | None = None

class ObjectiveState(BaseModel):
    objective_id: str = Field(default_factory=lambda: str(uuid4()))
    objective: str
    harness_instructions: str | None = None
    success_criteria: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    root_task_id: str | None = None

class FeatureDraft(BaseModel):
    title: str
    acceptance_criteria: str
    notes: list[str] = Field(default_factory=list)


class FeaturePatch(BaseModel):
    feature_id: str
    title: str | None = None
    acceptance_criteria: str | None = None
    status: FeatureStatus | None = None
    append_notes: list[str] = Field(default_factory=list)


class TaskDraft(BaseModel):
    title: str
    goal: str
    definition_of_done: str
    brain_priority: int = 50
    feature_id: str | None = None
    assigned_agent: str | None = None
    session_policy: SessionPolicy = SessionPolicy.PREFER_REUSE
    dependencies: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TaskPatch(BaseModel):
    task_id: str
    title: str | None = None
    goal: str | None = None
    definition_of_done: str | None = None
    status: TaskStatus | None = None
    brain_priority: int | None = None
    assigned_agent: str | None = None
    linked_session_id: str | None = None
    session_policy: SessionPolicy | None = None
    append_notes: list[str] = Field(default_factory=list)
    add_memory_refs: list[str] = Field(default_factory=list)
    add_artifact_refs: list[str] = Field(default_factory=list)
    add_dependencies: list[str] = Field(default_factory=list)
    remove_dependencies: list[str] = Field(default_factory=list)
    dependency_removal_reason: str | None = None


class FeatureState(BaseModel):
    feature_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    acceptance_criteria: str
    status: FeatureStatus = FeatureStatus.IN_PROGRESS
    notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TaskState(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    task_short_id: str = Field(default_factory=lambda: secrets.token_hex(4))
    title: str
    goal: str
    definition_of_done: str
    status: TaskStatus = TaskStatus.PENDING
    brain_priority: int = 50
    effective_priority: int = 50
    feature_id: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    assigned_agent: str | None = None
    linked_session_id: str | None = None
    session_policy: SessionPolicy = SessionPolicy.PREFER_REUSE
    memory_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    attempt_count: int = 0
    notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SessionState(BaseModel):
    handle: AgentSessionHandle
    status: SessionStatus = SessionStatus.IDLE
    current_execution_id: str | None = None
    last_terminal_execution_id: str | None = None
    bound_task_ids: list[str] = Field(default_factory=list)
    last_result_iteration: int | None = None
    latest_iteration: int | None = None
    attached_turn_started_at: datetime | None = None
    last_progress_at: datetime | None = None
    last_event_at: datetime | None = None
    waiting_reason: str | None = None
    cooldown_until: datetime | None = None
    cooldown_reason: str | None = None
    last_rate_limited_at: datetime | None = None
    recovery_summary: str | None = None
    recovery_count: int = 0
    recovery_attempted_at: datetime | None = None
    last_recovered_at: datetime | None = None
    execution_profile_stamp: ExecutionProfileStamp | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_session_record(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        upgraded = dict(data)
        legacy_status = upgraded.get("status")
        if legacy_status is not None:
            upgraded["status"] = (
                legacy_status
                if isinstance(legacy_status, SessionStatus)
                else SessionStatus(legacy_status)
            )
            upgraded.pop("observed_state", None)
            upgraded.pop("terminal_state", None)
            return upgraded
        observed_state = upgraded.pop("observed_state", None)
        terminal_state = upgraded.pop("terminal_state", None)
        if observed_state is not None or terminal_state is not None:
            upgraded["status"] = cls._status_from_legacy_fields(
                observed_state=observed_state,
                terminal_state=terminal_state,
            )
        return upgraded

    @classmethod
    def _status_from_legacy_fields(
        cls,
        *,
        observed_state: object | None,
        terminal_state: object | None,
    ) -> SessionStatus:
        del cls
        if observed_state in {None, SessionObservedState.IDLE, SessionObservedState.IDLE.value}:
            return SessionStatus.IDLE
        if observed_state in {
            SessionObservedState.RUNNING,
            SessionObservedState.RUNNING.value,
        }:
            return SessionStatus.RUNNING
        if observed_state in {
            SessionObservedState.WAITING,
            SessionObservedState.WAITING.value,
        }:
            return SessionStatus.WAITING
        normalized_terminal_state = (
            terminal_state.value
            if isinstance(terminal_state, SessionTerminalState)
            else terminal_state
        )
        if normalized_terminal_state == "interrupted":
            normalized_terminal_state = SessionTerminalState.CANCELLED.value
        if normalized_terminal_state in {
            SessionTerminalState.CANCELLED,
            SessionTerminalState.CANCELLED.value,
        }:
            return SessionStatus.CANCELLED
        if normalized_terminal_state in {
            SessionTerminalState.FAILED,
            SessionTerminalState.FAILED.value,
        }:
            return SessionStatus.FAILED
        return SessionStatus.COMPLETED

    @property
    def session_id(self) -> str:
        return self.handle.session_id

    @property
    def adapter_key(self) -> str:
        return self.handle.adapter_key

    @property
    def observed_state(self) -> SessionObservedState:
        if self.status is SessionStatus.IDLE:
            return SessionObservedState.IDLE
        if self.status is SessionStatus.RUNNING:
            return SessionObservedState.RUNNING
        if self.status is SessionStatus.WAITING:
            return SessionObservedState.WAITING
        return SessionObservedState.TERMINAL

    @observed_state.setter
    def observed_state(self, value: SessionObservedState) -> None:
        if value is SessionObservedState.IDLE:
            self.status = SessionStatus.IDLE
        elif value is SessionObservedState.RUNNING:
            self.status = SessionStatus.RUNNING
        elif value is SessionObservedState.WAITING:
            self.status = SessionStatus.WAITING
        elif self.status not in {
            SessionStatus.COMPLETED,
            SessionStatus.FAILED,
            SessionStatus.CANCELLED,
        }:
            self.status = SessionStatus.COMPLETED

    @property
    def terminal_state(self) -> SessionTerminalState | None:
        if self.status is SessionStatus.COMPLETED:
            return SessionTerminalState.COMPLETED
        if self.status is SessionStatus.FAILED:
            return SessionTerminalState.FAILED
        if self.status is SessionStatus.CANCELLED:
            return SessionTerminalState.CANCELLED
        return None

    @terminal_state.setter
    def terminal_state(self, value: SessionTerminalState | None) -> None:
        if value is None:
            return
        self.status = {
            SessionTerminalState.COMPLETED: SessionStatus.COMPLETED,
            SessionTerminalState.FAILED: SessionStatus.FAILED,
            SessionTerminalState.CANCELLED: SessionStatus.CANCELLED,
        }[value]


class ArtifactRecord(BaseModel):
    artifact_id: str = Field(default_factory=lambda: str(uuid4()))
    kind: str
    producer: str
    task_id: str | None = None
    session_id: str | None = None
    content: str
    raw_ref: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MemorySourceRef(BaseModel):
    kind: str
    ref_id: str


class MemoryEntry(BaseModel):
    memory_id: str = Field(default_factory=lambda: str(uuid4()))
    scope: MemoryScope
    scope_id: str
    summary: str
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    freshness: MemoryFreshness = MemoryFreshness.CURRENT
    superseded_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FocusState(BaseModel):
    kind: FocusKind
    target_id: str
    mode: FocusMode = FocusMode.ADVISORY
    blocking_reason: str | None = None
    interrupt_policy: InterruptPolicy = InterruptPolicy.MATERIAL_WAKEUP
    resume_policy: ResumePolicy = ResumePolicy.REPLAN
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WakeupRef(BaseModel):
    event_id: str
    event_type: str
    task_id: str | None = None
    session_id: str | None = None
    dedupe_key: str | None = None
    claimed_at: datetime | None = None
    acked_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExecutionHandleRef(BaseModel):
    kind: str
    value: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class BackgroundProgressSnapshot(BaseModel):
    state: SessionStatus
    message: str
    updated_at: datetime
    partial_output: str | None = None
    last_event_at: datetime | None = None


class ExecutionState(BaseModel):
    execution_id: str = Field(default_factory=lambda: str(uuid4()))
    operation_id: str
    adapter_key: str
    session_id: str | None = None
    task_id: str | None = None
    iteration: int | None = None
    mode: ExecutionMode = ExecutionMode.BACKGROUND
    launch_kind: ExecutionLaunchKind = ExecutionLaunchKind.NEW
    observed_state: ExecutionObservedState = ExecutionObservedState.STARTING
    waiting_reason: str | None = None
    handle_ref: ExecutionHandleRef | None = None
    progress: BackgroundProgressSnapshot | None = None
    result_ref: str | None = None
    error_ref: str | None = None
    pid: int | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_heartbeat_at: datetime | None = None
    completed_at: datetime | None = None
    raw_ref: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_background_run(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        upgraded = dict(data)
        if "execution_id" not in upgraded and "run_id" in upgraded:
            upgraded["execution_id"] = upgraded.pop("run_id")
        legacy_status = upgraded.pop("status", None)
        if legacy_status is not None and "observed_state" not in upgraded:
            status = (
                legacy_status
                if isinstance(legacy_status, BackgroundRunStatus)
                else BackgroundRunStatus(legacy_status)
            )
            upgraded["observed_state"] = {
                BackgroundRunStatus.PENDING: ExecutionObservedState.STARTING,
                BackgroundRunStatus.RUNNING: ExecutionObservedState.RUNNING,
                BackgroundRunStatus.COMPLETED: ExecutionObservedState.COMPLETED,
                BackgroundRunStatus.FAILED: ExecutionObservedState.FAILED,
                BackgroundRunStatus.CANCELLED: ExecutionObservedState.CANCELLED,
                BackgroundRunStatus.DISCONNECTED: ExecutionObservedState.LOST,
            }[status]
        return upgraded

    @property
    def run_id(self) -> str:
        return self.execution_id

    @run_id.setter
    def run_id(self, value: str) -> None:
        self.execution_id = value

    @property
    def status(self) -> BackgroundRunStatus:
        if self.observed_state is ExecutionObservedState.STARTING:
            return BackgroundRunStatus.PENDING
        if self.observed_state in {
            ExecutionObservedState.RUNNING,
            ExecutionObservedState.WAITING,
        }:
            return BackgroundRunStatus.RUNNING
        if self.observed_state is ExecutionObservedState.COMPLETED:
            return BackgroundRunStatus.COMPLETED
        if self.observed_state is ExecutionObservedState.FAILED:
            return BackgroundRunStatus.FAILED
        if self.observed_state is ExecutionObservedState.LOST:
            return BackgroundRunStatus.DISCONNECTED
        return BackgroundRunStatus.CANCELLED

    @status.setter
    def status(self, value: BackgroundRunStatus) -> None:
        self.observed_state = {
            BackgroundRunStatus.PENDING: ExecutionObservedState.STARTING,
            BackgroundRunStatus.RUNNING: ExecutionObservedState.RUNNING,
            BackgroundRunStatus.COMPLETED: ExecutionObservedState.COMPLETED,
            BackgroundRunStatus.FAILED: ExecutionObservedState.FAILED,
            BackgroundRunStatus.CANCELLED: ExecutionObservedState.CANCELLED,
            BackgroundRunStatus.DISCONNECTED: ExecutionObservedState.LOST,
        }[value]

    def model_copy(
        self,
        *,
        update: dict[str, Any] | None = None,
        deep: bool = False,
    ) -> ExecutionState:
        normalized = dict(update or {})
        if "run_id" in normalized and "execution_id" not in normalized:
            normalized["execution_id"] = normalized.pop("run_id")
        if "status" in normalized and "observed_state" not in normalized:
            status = normalized.pop("status")
            if not isinstance(status, BackgroundRunStatus):
                status = BackgroundRunStatus(status)
            normalized["observed_state"] = {
                BackgroundRunStatus.PENDING: ExecutionObservedState.STARTING,
                BackgroundRunStatus.RUNNING: ExecutionObservedState.RUNNING,
                BackgroundRunStatus.COMPLETED: ExecutionObservedState.COMPLETED,
                BackgroundRunStatus.FAILED: ExecutionObservedState.FAILED,
                BackgroundRunStatus.CANCELLED: ExecutionObservedState.CANCELLED,
                BackgroundRunStatus.DISCONNECTED: ExecutionObservedState.LOST,
            }[status]
        return super().model_copy(update=normalized, deep=deep)


class BlockingFocus(BaseModel):
    kind: FocusKind
    target_id: str
    blocking_reason: str
    interrupt_policy: InterruptPolicy = InterruptPolicy.MATERIAL_WAKEUP
    resume_policy: ResumePolicy = ResumePolicy.REPLAN


class IterationState(BaseModel):
    index: int
    decision: BrainDecision | None = None
    task_id: str | None = None
    session: AgentSessionHandle | None = None
    result: AgentResult | None = None
    turn_summary: AgentTurnSummary | None = None
    notes: list[str] = Field(default_factory=list)


class OperationState(BaseModel):
    """Persisted operation aggregate for the snapshot-era runtime.

    Attributes:
        canonical_persistence_mode: Declares which persistence surface is canonical for the
            operation. New operations are born as `event_sourced`; older persisted payloads still
            upgrade missing canonical mode to `snapshot_legacy`.

    Examples:
        >>> state = OperationState(
        ...     goal=OperationGoal(prompt="Inspect the repository."),
        ...     policy=OperationPolicy(),
        ... )
        >>> state.canonical_persistence_mode.value
        'event_sourced'
    """

    schema_version: int = 2
    operation_id: str = Field(default_factory=lambda: str(uuid4()))
    canonical_persistence_mode: CanonicalPersistenceMode = (
        CanonicalPersistenceMode.EVENT_SOURCED
    )
    goal: OperationGoal
    policy: OperationPolicy = Field(default_factory=OperationPolicy)
    execution_budget: ExecutionBudget = Field(default_factory=ExecutionBudget)
    runtime_hints: RuntimeHints = Field(default_factory=RuntimeHints)
    execution_profile_overrides: dict[str, ExecutionProfileOverride] = Field(default_factory=dict)
    objective: ObjectiveState | None = None
    status: OperationStatus = OperationStatus.RUNNING
    iterations: list[IterationState] = Field(default_factory=list)
    features: list[FeatureState] = Field(default_factory=list)
    tasks: list[TaskState] = Field(default_factory=list)
    sessions: list[SessionState] = Field(default_factory=list)
    executions: list[ExecutionState] = Field(default_factory=list)
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    memory_entries: list[MemoryEntry] = Field(default_factory=list)
    operation_brief: OperationBrief | None = None
    iteration_briefs: list[IterationBrief] = Field(default_factory=list)
    recent_decisions: list[DecisionRecord] = Field(default_factory=list)
    agent_turn_briefs: list[AgentTurnBrief] = Field(default_factory=list)
    permission_events: list[dict[str, object]] = Field(default_factory=list)
    current_focus: FocusState | None = None
    pending_wakeups: list[WakeupRef] = Field(default_factory=list)
    attention_requests: list[AttentionRequest] = Field(default_factory=list)
    active_policies: list[PolicyEntry] = Field(default_factory=list)
    policy_coverage: PolicyCoverage = Field(default_factory=PolicyCoverage)
    involvement_level: InvolvementLevel = InvolvementLevel.AUTO
    scheduler_state: SchedulerState = SchedulerState.ACTIVE
    operator_messages: list[OperatorMessage] = Field(default_factory=list)
    processed_command_ids: list[str] = Field(default_factory=list)
    pending_replan_command_ids: list[str] = Field(default_factory=list)
    pending_attention_resolution_ids: list[str] = Field(default_factory=list)
    final_summary: str | None = None
    run_started_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _hydrate_long_lived_defaults(self) -> OperationState:
        if self.schema_version != 2:
            raise ValueError(
                "Unsupported operation state schema. This operator only supports schema_version=2."
            )
        if self.objective is None:
            self.objective = ObjectiveState(
                objective=self.goal.objective_text,
                harness_instructions=self.goal.harness_text,
                success_criteria=list(self.goal.success_criteria),
                metadata=dict(self.goal.metadata),
                summary=self.final_summary,
            )
        else:
            if self.final_summary and not self.objective.summary:
                self.objective.summary = self.final_summary
        if self.involvement_level is InvolvementLevel.AUTO:
            self.involvement_level = self.policy.involvement_level
        if self.policy_coverage.project_scope is None:
            raw_scope = self.goal.metadata.get("policy_scope")
            if isinstance(raw_scope, str) and raw_scope.strip():
                self.policy_coverage.project_scope = raw_scope.strip()
        if (
            self.policy_coverage.status is PolicyCoverageStatus.NO_SCOPE
            and self.policy_coverage.project_scope is not None
            and self.active_policies
        ):
            self.policy_coverage.status = PolicyCoverageStatus.COVERED
            self.policy_coverage.scoped_policy_count = max(
                self.policy_coverage.scoped_policy_count,
                len(self.active_policies),
            )
            self.policy_coverage.active_policy_count = len(self.active_policies)
            self.policy_coverage.summary = (
                f"{len(self.active_policies)} active policy "
                f"{'entry applies' if len(self.active_policies) == 1 else 'entries apply'} now."
            )
        if not self.tasks:
            root_task = TaskState(
                title="Primary objective",
                goal=self.objective.objective,
                definition_of_done=(
                    self.goal.success_criteria[0]
                    if self.goal.success_criteria
                    else "Satisfy the operation goal."
                ),
                status=self._derive_root_task_status(),
                brain_priority=100,
                effective_priority=100,
                assigned_agent=self.policy.allowed_agents[0]
                if len(self.policy.allowed_agents) == 1
                else None,
                session_policy=SessionPolicy.PREFER_REUSE,
            )
            self.tasks = [root_task]
            self.objective.root_task_id = root_task.task_id
        elif self.objective.root_task_id is None:
            self.objective.root_task_id = self.tasks[0].task_id
        return self

    def _derive_root_task_status(self) -> TaskStatus:
        if self.status is OperationStatus.COMPLETED:
            return TaskStatus.COMPLETED
        if self.status is OperationStatus.FAILED:
            return TaskStatus.FAILED
        if self.status is OperationStatus.CANCELLED:
            return TaskStatus.CANCELLED
        if self.status is OperationStatus.NEEDS_HUMAN:
            return TaskStatus.BLOCKED
        return TaskStatus.READY

    @property
    def active_session_record(self) -> SessionState | None:
        if self.current_focus and self.current_focus.kind is FocusKind.SESSION:
            for record in self.sessions:
                if record.session_id == self.current_focus.target_id:
                    return record
        root_task_id = self.objective.root_task_id if self.objective is not None else None
        if root_task_id is not None:
            for task in self.tasks:
                if task.task_id != root_task_id or task.linked_session_id is None:
                    continue
                for record in self.sessions:
                    if (
                        record.session_id == task.linked_session_id
                        and not record.handle.one_shot
                        and record.status
                        not in {
                            SessionStatus.COMPLETED,
                            SessionStatus.FAILED,
                            SessionStatus.CANCELLED,
                        }
                    ):
                        return record
        running_attached = [
            record
            for record in self.sessions
            if record.status is SessionStatus.RUNNING and record.current_execution_id is None
        ]
        if running_attached:
            running_attached.sort(
                key=lambda record: (
                    record.latest_iteration or 0,
                    record.updated_at,
                    record.created_at,
                )
            )
            return running_attached[-1]
        reusable = [
            record
            for record in self.sessions
            if (
                not record.handle.one_shot
                and record.status
                not in {
                    SessionStatus.COMPLETED,
                    SessionStatus.FAILED,
                    SessionStatus.CANCELLED,
                }
            )
        ]
        if reusable:
            reusable.sort(
                key=lambda record: (
                    record.latest_iteration or -1,
                    record.updated_at,
                    record.created_at,
                )
            )
            return reusable[-1]
        return None

    @property
    def background_runs(self) -> list[ExecutionState]:
        return self.executions

    @background_runs.setter
    def background_runs(self, value: list[ExecutionState]) -> None:
        self.executions = value

    @property
    def objective_state(self) -> ObjectiveState:
        assert self.objective is not None
        return self.objective


class OperationSummary(BaseModel):
    operation_id: str
    status: OperationStatus
    objective_prompt: str
    final_summary: str | None = None
    focus: str | None = None
    runnable_task_count: int = 0
    reusable_session_count: int = 0
    updated_at: datetime


class OperationOutcome(BaseModel):
    operation_id: str
    status: OperationStatus
    summary: str
    ended_at: datetime | None = None
    final_result: AgentResult | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
