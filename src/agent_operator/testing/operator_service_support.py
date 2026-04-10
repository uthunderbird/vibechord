from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from dishka import Provider, Scope, make_container, provide

from agent_operator.application import (
    AgentResultService,
    AgentRunRequest,
    AttachedTurnService,
    DecisionExecutionService,
    LoadedOperation,
    OperationAttentionCoordinator,
    OperationCommandService,
    OperationControlStateCoordinator,
    OperationDriveControlService,
    OperationDriveDecisionExecutorService,
    OperationDriveRuntimeService,
    OperationDriveService,
    OperationDriveTraceService,
    OperationEntrypointService,
    OperationLifecycleCoordinator,
    OperationPolicyContextCoordinator,
    OperationRuntimeContext,
    OperationRuntimeReconciliationService,
    OperationTraceabilityService,
    OperationTurnExecutionService,
    OperatorService,
    SupervisorBackedOperationRuntime,
)
from agent_operator.application.attached_session_registry import AttachedSessionRuntimeRegistry
from agent_operator.application.commands.operation_cancellation import OperationCancellationService
from agent_operator.application.event_sourcing.event_sourced_birth import (
    EventSourcedOperationBirthService,
)
from agent_operator.application.event_sourcing.event_sourced_commands import (
    EventSourcedCommandApplicationService,
)
from agent_operator.application.runtime.operation_event_relay import OperationEventRelay
from agent_operator.application.runtime.operation_process_dispatch import (
    OperationProcessSignalDispatcher,
)
from agent_operator.domain import (
    AgentDescriptor,
    AgentError,
    AgentProgress,
    AgentProgressState,
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    AgentTurnBrief,
    AttentionStatus,
    BackgroundRunStatus,
    BrainActionType,
    BrainDecision,
    CommandStatus,
    DecisionMemo,
    Evaluation,
    ExecutionBudget,
    ExecutionState,
    InvolvementLevel,
    IterationBrief,
    OperationCommand,
    OperationPolicy,
    OperationState,
    PlanningTrigger,
    PolicyEntry,
    PolicyStatus,
    ProgressSummary,
    RunEvent,
    RuntimeHints,
    StoredControlIntent,
    TraceBriefBundle,
    TraceRecord,
    standard_coding_agent_capabilities,
)
from agent_operator.protocols import (
    AgentRunSupervisor,
    EventSink,
    OperationCommandInbox,
    OperationRuntime,
    OperationStore,
    OperatorPolicy,
    PlanningTriggerBus,
    PolicyStore,
    ProcessManager,
    ProcessManagerBuilder,
    TraceStore,
    WakeupInbox,
)


class MemoryStore:
    def __init__(self) -> None:
        self.operations = {}
        self.outcomes = {}

    async def save_operation(self, state) -> None:
        self.operations[state.operation_id] = state

    async def save_outcome(self, outcome) -> None:
        self.outcomes[outcome.operation_id] = outcome

    async def load_operation(self, operation_id: str):
        return self.operations.get(operation_id)

    async def load_outcome(self, operation_id: str):
        return self.outcomes.get(operation_id)

    async def list_operation_ids(self) -> list[str]:
        return list(self.operations)

    async def list_operations(self) -> list:
        return []


class MemoryEventSink:
    def __init__(self) -> None:
        self.events = []

    async def emit(self, event) -> None:
        self.events.append(event)


class MemoryTraceStore:
    def __init__(self) -> None:
        self.bundle = TraceBriefBundle()
        self.trace_records: list[TraceRecord] = []
        self.memos: list[DecisionMemo] = []
        self.report: str | None = None

    async def save_operation_brief(self, brief) -> None:
        self.bundle.operation_brief = brief

    async def append_iteration_brief(self, operation_id: str, brief: IterationBrief) -> None:
        self.bundle.iteration_briefs = [
            item for item in self.bundle.iteration_briefs if item.iteration != brief.iteration
        ]
        self.bundle.iteration_briefs.append(brief)
        self.bundle.iteration_briefs.sort(key=lambda item: item.iteration)

    async def append_agent_turn_brief(self, operation_id: str, brief: AgentTurnBrief) -> None:
        self.bundle.agent_turn_briefs = [
            item
            for item in self.bundle.agent_turn_briefs
            if not (item.iteration == brief.iteration and item.session_id == brief.session_id)
        ]
        self.bundle.agent_turn_briefs.append(brief)

    async def append_command_brief(self, operation_id: str, brief) -> None:
        self.bundle.command_briefs = [
            item for item in self.bundle.command_briefs if item.command_id != brief.command_id
        ]
        self.bundle.command_briefs.append(brief)

    async def append_evaluation_brief(self, operation_id: str, brief) -> None:
        self.bundle.evaluation_briefs = [
            item for item in self.bundle.evaluation_briefs if item.iteration != brief.iteration
        ]
        self.bundle.evaluation_briefs.append(brief)

    async def save_decision_memo(self, operation_id: str, memo: DecisionMemo) -> None:
        self.memos = [item for item in self.memos if item.iteration != memo.iteration]
        self.memos.append(memo)

    async def append_trace_record(self, operation_id: str, record: TraceRecord) -> None:
        self.trace_records.append(record)

    async def write_report(self, operation_id: str, report: str) -> None:
        self.report = report

    async def load_brief_bundle(self, operation_id: str) -> TraceBriefBundle | None:
        return self.bundle

    async def load_trace_records(self, operation_id: str) -> list[TraceRecord]:
        return self.trace_records

    async def load_decision_memos(self, operation_id: str) -> list[DecisionMemo]:
        return self.memos

    async def load_report(self, operation_id: str) -> str | None:
        return self.report


class MemoryHistoryLedger:
    def __init__(self) -> None:
        self.entries: list[tuple[OperationState, object]] = []

    async def append(self, state: OperationState, outcome: object) -> None:
        self.entries.append((state, outcome))


class MemoryCommandInbox:
    def __init__(self) -> None:
        self.commands: dict[str, OperationCommand] = {}
        self.planning_triggers: dict[str, PlanningTrigger] = {}
        self._superseded_planning_trigger_ids: set[str] = set()

    async def enqueue(self, command: OperationCommand) -> None:
        self.commands[command.command_id] = command.model_copy(deep=True)

    async def list(self, operation_id: str) -> list[OperationCommand]:
        return sorted(
            [
                command.model_copy(deep=True)
                for command in self.commands.values()
                if command.operation_id == operation_id
            ],
            key=lambda item: (item.submitted_at, item.command_id),
        )

    async def list_pending(self, operation_id: str) -> list[OperationCommand]:
        return [
            command
            for command in await self.list(operation_id)
            if command.status is CommandStatus.PENDING
        ]

    async def update_status(
        self,
        command_id: str,
        status: CommandStatus,
        rejection_reason: str | None = None,
        applied_at: datetime | None = None,
    ) -> OperationCommand | None:
        command = self.commands.get(command_id)
        if command is None:
            return None
        updated = command.model_copy(deep=True)
        updated.status = status
        if status is CommandStatus.REJECTED:
            updated.rejection_reason = rejection_reason
            updated.applied_at = None
        elif status is CommandStatus.APPLIED:
            updated.rejection_reason = None
            updated.applied_at = applied_at or datetime.now(UTC)
        else:
            updated.rejection_reason = None
            updated.applied_at = None
        self.commands[command_id] = updated
        return updated.model_copy(deep=True)

    async def enqueue_planning_trigger(self, trigger: PlanningTrigger):
        existing = next(
            (
                item
                for item in self.planning_triggers.values()
                if item.operation_id == trigger.operation_id
                and item.dedupe_key == trigger.dedupe_key
                and item.trigger_id not in self._superseded_planning_trigger_ids
            ),
            None,
        )
        if existing is not None:
            return StoredControlIntent.for_planning_trigger(existing)
        self.planning_triggers[trigger.trigger_id] = trigger.model_copy(deep=True)
        return StoredControlIntent.for_planning_trigger(trigger)

    async def list_planning_triggers(self, operation_id: str) -> list[PlanningTrigger]:
        return sorted(
            [
                trigger.model_copy(deep=True)
                for trigger in self.planning_triggers.values()
                if trigger.operation_id == operation_id
            ],
            key=lambda item: (item.submitted_at, item.trigger_id),
        )

    async def list_pending_planning_triggers(self, operation_id: str) -> list[PlanningTrigger]:
        return [
            trigger
            for trigger in await self.list_planning_triggers(operation_id)
            if trigger.trigger_id not in self._superseded_planning_trigger_ids
        ]

    async def mark_planning_trigger_applied(
        self,
        trigger_id: str,
        *,
        applied_at: datetime | None = None,
    ) -> PlanningTrigger | None:
        trigger = self.planning_triggers.pop(trigger_id, None)
        if trigger is None:
            return None
        return trigger.model_copy(deep=True)

    async def mark_planning_trigger_superseded(
        self,
        trigger_id: str,
        *,
        superseded_by_trigger_id: str | None = None,
    ) -> PlanningTrigger | None:
        trigger = self.planning_triggers.get(trigger_id)
        if trigger is None:
            return None
        self._superseded_planning_trigger_ids.add(trigger_id)
        return trigger.model_copy(deep=True)


class MemoryPolicyStore:
    def __init__(self) -> None:
        self.entries: dict[str, PolicyEntry] = {}

    async def save(self, entry: PolicyEntry) -> None:
        self.entries[entry.policy_id] = entry.model_copy(deep=True)

    async def load(self, policy_id: str) -> PolicyEntry | None:
        entry = self.entries.get(policy_id)
        return None if entry is None else entry.model_copy(deep=True)

    async def list(
        self,
        *,
        project_scope: str | None = None,
        status: PolicyStatus | None = None,
    ) -> list[PolicyEntry]:
        entries = [entry.model_copy(deep=True) for entry in self.entries.values()]
        if project_scope is not None:
            entries = [entry for entry in entries if entry.project_scope == project_scope]
        if status is not None:
            entries = [entry for entry in entries if entry.status is status]
        entries.sort(key=lambda item: (item.created_at, item.policy_id))
        return entries


class FakeSupervisor:
    def __init__(
        self,
        *,
        auto_complete_on_poll: bool = False,
        complete_after_polls: int | None = None,
    ) -> None:
        self.runs: dict[str, ExecutionState] = {}
        self.results: dict[str, AgentResult] = {}
        self.requests: list[AgentRunRequest] = []
        self.existing_sessions: list[AgentSessionHandle | None] = []
        self.finalized: list[tuple[str, BackgroundRunStatus, str | None]] = []
        self.wakeup_deliveries: list[str] = []
        self.auto_complete_on_poll = auto_complete_on_poll
        self.complete_after_polls = complete_after_polls
        self.poll_counts: dict[str, int] = {}

    async def start_background_turn(
        self,
        operation_id: str,
        iteration: int,
        adapter_key: str,
        request: AgentRunRequest,
        *,
        existing_session: AgentSessionHandle | None = None,
        task_id: str | None = None,
        wakeup_delivery: str = "enqueue",
    ) -> ExecutionState:
        self.requests.append(request)
        self.existing_sessions.append(existing_session)
        self.wakeup_deliveries.append(wakeup_delivery)
        run = ExecutionState(
            run_id=f"run-{len(self.runs) + 1}",
            operation_id=operation_id,
            adapter_key=adapter_key,
            session_id=(existing_session.session_id if existing_session else "session-1"),
            task_id=task_id,
            iteration=iteration,
            status=BackgroundRunStatus.RUNNING,
        )
        self.runs[run.run_id] = run
        self.results[run.run_id] = AgentResult(
            session_id=run.session_id or "session-1",
            status=AgentResultStatus.SUCCESS,
            output_text="completed by fake background agent",
            completed_at=datetime.now(UTC),
        )
        return run

    async def poll_background_turn(self, run_id: str) -> ExecutionState | None:
        run = self.runs.get(run_id)
        if run is not None:
            self.poll_counts[run_id] = self.poll_counts.get(run_id, 0) + 1
        if (
            run is not None
            and self.auto_complete_on_poll
            and run.status is BackgroundRunStatus.RUNNING
        ):
            run.status = BackgroundRunStatus.COMPLETED
            run.completed_at = datetime.now(UTC)
            run.last_heartbeat_at = run.completed_at
        if (
            run is not None
            and self.complete_after_polls is not None
            and run.status is BackgroundRunStatus.RUNNING
            and self.poll_counts[run_id] >= self.complete_after_polls
        ):
            run.status = BackgroundRunStatus.COMPLETED
            run.completed_at = datetime.now(UTC)
            run.last_heartbeat_at = run.completed_at
        return run

    async def collect_background_turn(self, run_id: str) -> AgentResult | None:
        run = self.runs[run_id]
        if run.status is BackgroundRunStatus.CANCELLED:
            return AgentResult(
                session_id=run.session_id or "session-1",
                status=AgentResultStatus.CANCELLED,
                output_text="",
                completed_at=datetime.now(UTC),
            )
        if run.status is BackgroundRunStatus.DISCONNECTED:
            return AgentResult(
                session_id=run.session_id or "session-1",
                status=AgentResultStatus.DISCONNECTED,
                output_text="",
                error=AgentError(
                    code="claude_acp_disconnected",
                    message="ACP subprocess closed before completing all pending requests.",
                    retryable=True,
                    raw={"recovery_mode": "same_session"},
                ),
                completed_at=datetime.now(UTC),
            )
        if run.status is BackgroundRunStatus.FAILED:
            existing = self.results.get(run_id)
            if existing is not None and existing.status is AgentResultStatus.FAILED:
                return existing
            return AgentResult(
                session_id=run.session_id or "session-1",
                status=AgentResultStatus.FAILED,
                output_text="",
                error=AgentError(
                    code="background_run_failed",
                    message="Background run failed.",
                    retryable=False,
                ),
                completed_at=datetime.now(UTC),
            )
        run.status = BackgroundRunStatus.COMPLETED
        run.completed_at = datetime.now(UTC)
        return self.results.get(run_id)

    async def cancel_background_turn(self, run_id: str) -> None:
        run = self.runs[run_id]
        run.status = BackgroundRunStatus.CANCELLED
        run.completed_at = datetime.now(UTC)

    async def finalize_background_turn(
        self,
        run_id: str,
        status: BackgroundRunStatus,
        *,
        error: str | None = None,
    ) -> None:
        run = self.runs[run_id]
        if run.status not in {
            BackgroundRunStatus.COMPLETED,
            BackgroundRunStatus.FAILED,
            BackgroundRunStatus.CANCELLED,
            BackgroundRunStatus.DISCONNECTED,
        }:
            run.status = status
            run.completed_at = datetime.now(UTC)
            run.last_heartbeat_at = run.completed_at
        self.finalized.append((run_id, status, error))

    async def list_runs(self, operation_id: str) -> list[ExecutionState]:
        return [run for run in self.runs.values() if run.operation_id == operation_id]


class MemoryWakeupInbox:
    def __init__(self) -> None:
        self.pending: list[RunEvent] = []
        self.acked: list[str] = []

    async def enqueue(self, event: RunEvent) -> None:
        self.pending.append(event)

    async def claim(self, operation_id: str, limit: int = 100) -> list[RunEvent]:
        claimed = [item for item in self.pending if item.operation_id == operation_id][:limit]
        self.pending = [item for item in self.pending if item not in claimed]
        return claimed

    async def ack(self, event_ids: list[str]) -> None:
        self.acked.extend(event_ids)

    async def requeue_stale_claims(self) -> int:
        return 0

    async def list_pending(self, operation_id: str) -> list[RunEvent]:
        return [item for item in self.pending if item.operation_id == operation_id]


class _TestServiceProvider(Provider):
    def __init__(self, overrides: dict[str, object]) -> None:
        super().__init__(scope=Scope.APP)
        self._overrides = overrides

    def _get(self, key: str, default):
        return self._overrides.get(key, default)

    @provide(scope=Scope.APP)
    def operator_policy(self) -> OperatorPolicy:
        policy = self._overrides.get("operator_policy")
        if policy is None:
            raise RuntimeError("make_service requires operator_policy or brain.")
        return policy

    @provide(scope=Scope.APP)
    def store(self) -> OperationStore:
        return self._get("store", MemoryStore())

    @provide(scope=Scope.APP)
    def trace_store(self) -> TraceStore:
        return self._get("trace_store", MemoryTraceStore())

    @provide(scope=Scope.APP)
    def event_sink(self) -> EventSink:
        return self._get("event_sink", MemoryEventSink())

    @provide(scope=Scope.APP)
    def agent_runtime_bindings(self) -> dict[str, object]:
        return self._get("agent_runtime_bindings", {})

    @provide(scope=Scope.APP)
    def wakeup_inbox(self) -> WakeupInbox | None:
        return self._overrides.get("wakeup_inbox")

    @provide(scope=Scope.APP)
    def command_inbox(self) -> OperationCommandInbox | None:
        return self._overrides.get("command_inbox")

    @provide(scope=Scope.APP)
    def planning_trigger_bus(
        self,
        command_inbox: OperationCommandInbox | None,
    ) -> PlanningTriggerBus | None:
        override = self._overrides.get("planning_trigger_bus")
        if override is not None:
            return override
        if isinstance(command_inbox, PlanningTriggerBus):
            return command_inbox
        return None

    @provide(scope=Scope.APP)
    def policy_store(self) -> PolicyStore | None:
        return self._overrides.get("policy_store")

    @provide(scope=Scope.APP)
    def supervisor(self) -> AgentRunSupervisor | None:
        return self._overrides.get("supervisor")

    @provide(scope=Scope.APP)
    def process_manager_builder(self) -> ProcessManagerBuilder | None:
        return self._overrides.get("process_manager_builder")

    @provide(scope=Scope.APP)
    def project_memory_store(self) -> object | None:
        return self._overrides.get("project_memory_store")

    @provide(scope=Scope.APP)
    def attached_turn_timeout(self) -> object | None:
        return self._get("attached_turn_timeout", None)

    @provide(scope=Scope.APP)
    def event_sourced_command_service(self) -> EventSourcedCommandApplicationService | None:
        return self._overrides.get("event_sourced_command_service")

    @provide(scope=Scope.APP)
    def event_sourced_operation_birth_service(self) -> EventSourcedOperationBirthService | None:
        return self._overrides.get("event_sourced_operation_birth_service")

    @provide(scope=Scope.APP)
    def operation_entrypoint_service(self) -> OperationEntrypointService | None:
        return self._overrides.get("operation_entrypoint_service")

    @provide(scope=Scope.APP)
    def operation_cancellation_service(self) -> OperationCancellationService | None:
        return self._overrides.get("operation_cancellation_service")

    @provide(scope=Scope.APP)
    def operation_runtime(self) -> OperationRuntime | None:
        return self._overrides.get("operation_runtime")

    @provide(scope=Scope.APP)
    def history_ledger(self) -> object | None:
        return self._overrides.get("history_ledger")

    @provide(scope=Scope.APP)
    def operator_service(
        self,
        operator_policy: OperatorPolicy,
        store: OperationStore,
        trace_store: TraceStore,
        event_sink: EventSink,
        agent_runtime_bindings: dict[str, object],
        wakeup_inbox: WakeupInbox | None,
        command_inbox: OperationCommandInbox | None,
        planning_trigger_bus: PlanningTriggerBus | None,
        policy_store: PolicyStore | None,
        supervisor: AgentRunSupervisor | None,
        process_manager_builder: ProcessManagerBuilder | None,
        project_memory_store: object | None,
        event_sourced_command_service: EventSourcedCommandApplicationService | None,
        event_sourced_operation_birth_service: EventSourcedOperationBirthService | None,
        operation_entrypoint_service: OperationEntrypointService | None,
        operation_cancellation_service: OperationCancellationService | None,
        operation_runtime: OperationRuntime | None,
        history_ledger: object | None,
    ) -> OperatorService:
        attached_turn_timeout = self._overrides.get("attached_turn_timeout")
        if attached_turn_timeout is None:
            from datetime import timedelta

            attached_turn_timeout = timedelta(minutes=30)
        attached_session_registry = AttachedSessionRuntimeRegistry(agent_runtime_bindings)
        loaded_operation = LoadedOperation(attached_session_registry=attached_session_registry)
        runtime_context = OperationRuntimeContext(
            loaded_operation=loaded_operation,
            attached_session_registry=attached_session_registry,
        )
        effective_operation_runtime = operation_runtime
        if effective_operation_runtime is None and supervisor is not None:
            effective_operation_runtime = SupervisorBackedOperationRuntime(supervisor=supervisor)
        lifecycle_coordinator = self._overrides.get("operation_lifecycle_coordinator")
        if lifecycle_coordinator is None:
            lifecycle_coordinator = OperationLifecycleCoordinator(
                store=store,
                history_ledger=history_ledger,
            )
        if event_sourced_command_service is None:
            from agent_operator.application.event_sourcing.event_sourced_replay import (
                EventSourcedReplayService,  # noqa: F401
            )
            from agent_operator.projectors import DefaultOperationProjector
            from agent_operator.runtime import (
                FileOperationCheckpointStore,
                FileOperationEventStore,
            )

            _tmp = Path(tempfile.mkdtemp())
            _event_store = FileOperationEventStore(_tmp / "events")
            _checkpoint_store = FileOperationCheckpointStore(_tmp / "checkpoints")
            _projector = DefaultOperationProjector()
            event_sourced_command_service = EventSourcedCommandApplicationService(
                event_store=_event_store,
                checkpoint_store=_checkpoint_store,
                projector=_projector,
            )
            if event_sourced_operation_birth_service is None:
                from agent_operator.application.event_sourcing.event_sourced_birth import (
                    EventSourcedOperationBirthService,
                )

                event_sourced_operation_birth_service = EventSourcedOperationBirthService(
                    event_store=_event_store,
                    checkpoint_store=_checkpoint_store,
                    projector=_projector,
                )
        attached_turn_service = self._overrides.get("attached_turn_service")
        if attached_turn_service is None:
            attached_turn_service = AttachedTurnService(
                attached_turn_timeout=attached_turn_timeout,
            )
        event_relay = self._overrides.get("event_relay")
        if event_relay is None:
            event_relay = OperationEventRelay(
                event_sink=event_sink,
                wakeup_inbox=wakeup_inbox,
            )
        attention_coordinator = self._overrides.get("operation_attention_coordinator")
        if attention_coordinator is None:
            attention_coordinator = OperationAttentionCoordinator()
        policy_context_coordinator = self._overrides.get("operation_policy_context_coordinator")
        if policy_context_coordinator is None:
            policy_context_coordinator = OperationPolicyContextCoordinator(
                policy_store=policy_store
            )
        process_managers: list[ProcessManager] = (
            process_manager_builder.build() if process_manager_builder is not None else []
        )
        process_signal_dispatcher = self._overrides.get("process_signal_dispatcher")
        if process_signal_dispatcher is None:
            process_signal_dispatcher = OperationProcessSignalDispatcher(
                planning_trigger_bus=planning_trigger_bus,
                process_managers=process_managers,
                emit=event_relay.emit,
            )
        traceability_service = self._overrides.get("operation_traceability_service")
        if traceability_service is None:
            traceability_service = OperationTraceabilityService(
                loaded_operation=loaded_operation,
                trace_store=trace_store,
                runtime_context=runtime_context,
            )
        control_state = self._overrides.get("operation_control_state_coordinator")
        if control_state is None:
            control_state = OperationControlStateCoordinator(
                store=store,
                traceability_service=traceability_service,
            )
        agent_result_service = self._overrides.get("agent_result_service")
        if agent_result_service is None:
            agent_result_service = AgentResultService(
                loaded_operation=loaded_operation,
                operator_policy=operator_policy,
                event_relay=event_relay,
                process_signal_dispatcher=process_signal_dispatcher,
                lifecycle_coordinator=lifecycle_coordinator,
                attention_coordinator=attention_coordinator,
                record_agent_turn_brief=traceability_service.record_agent_turn_brief,
            )
        operation_command_service = self._overrides.get("operation_command_service")
        if operation_command_service is None:
            operation_command_service = OperationCommandService(
                loaded_operation=loaded_operation,
                command_inbox=command_inbox,
                trace_store=trace_store,
                policy_context_coordinator=policy_context_coordinator,
                attention_coordinator=attention_coordinator,
                attached_session_registry=attached_session_registry,
                operation_runtime=effective_operation_runtime,
                event_sourced_command_service=event_sourced_command_service,
                event_relay=event_relay,
                control_state_coordinator=control_state,
                lifecycle_coordinator=lifecycle_coordinator,
                process_signal_dispatcher=process_signal_dispatcher,
                runtime_context=runtime_context,
            )
        turn_execution_service = self._overrides.get("operation_turn_execution_service")
        if turn_execution_service is None:
            turn_execution_service = OperationTurnExecutionService(
                loaded_operation=loaded_operation,
                attached_session_registry=attached_session_registry,
                attached_turn_service=attached_turn_service,
                operation_runtime=effective_operation_runtime,
                store=store,
                event_relay=event_relay,
                process_signal_dispatcher=process_signal_dispatcher,
                traceability_service=traceability_service,
                command_service=operation_command_service,
            )
        runtime_reconciliation_service = self._overrides.get(
            "operation_runtime_reconciliation_service"
        )
        if runtime_reconciliation_service is None:
            runtime_reconciliation_service = OperationRuntimeReconciliationService(
                loaded_operation=loaded_operation,
                operation_runtime=effective_operation_runtime,
                wakeup_inbox=wakeup_inbox,
                event_relay=event_relay,
                stale_background_run_threshold=OperatorService._STALE_BACKGROUND_RUN_THRESHOLD,
                lifecycle_coordinator=lifecycle_coordinator,
                runtime_context=runtime_context,
                agent_result_service=agent_result_service,
                traceability_service=traceability_service,
            )
        decision_execution_service = self._overrides.get("decision_execution_service")
        if decision_execution_service is None:
            decision_execution_service = DecisionExecutionService(
                loaded_operation=loaded_operation,
                attached_session_registry=attached_session_registry,
                attention_coordinator=attention_coordinator,
                lifecycle_coordinator=lifecycle_coordinator,
                runtime_context=runtime_context,
                turn_execution_service=turn_execution_service,
                agent_result_service=agent_result_service,
            )
        operation_drive_control_service = self._overrides.get("operation_drive_control_service")
        if operation_drive_control_service is None:
            operation_drive_control_service = OperationDriveControlService(
                drain_commands=operation_command_service.drain_commands,
                finalize_pending_attention_resolutions=(
                    operation_command_service.finalize_pending_attention_resolutions
                ),
                planning_trigger_bus=planning_trigger_bus,
                emit=event_relay.emit,
            )
        operation_drive_runtime_service = self._overrides.get("operation_drive_runtime_service")
        if operation_drive_runtime_service is None:
            operation_drive_runtime_service = OperationDriveRuntimeService(
                runtime_context=runtime_context,
                runtime_reconciliation_service=runtime_reconciliation_service,
                refresh_policy_context=policy_context_coordinator.refresh_policy_context,
            )
        operation_drive_trace_service = self._overrides.get("operation_drive_trace_service")
        if operation_drive_trace_service is None:
            operation_drive_trace_service = OperationDriveTraceService(
                event_relay=event_relay,
                traceability_service=traceability_service,
            )
        operation_drive_decision_executor_service = self._overrides.get(
            "operation_drive_decision_executor_service"
        )
        if operation_drive_decision_executor_service is None:
            operation_drive_decision_executor_service = OperationDriveDecisionExecutorService(
                decision_execution_service=decision_execution_service,
                supervisor_available=supervisor is not None,
            )
        operation_drive_service = self._overrides.get("operation_drive_service")
        if operation_drive_service is None:
            operation_drive_service = OperationDriveService(
                operator_policy=operator_policy,
                store=store,
                loaded_operation=loaded_operation,
                runtime=operation_drive_runtime_service,
                control=operation_drive_control_service,
                trace=operation_drive_trace_service,
                decision_executor=operation_drive_decision_executor_service,
                lifecycle_coordinator=lifecycle_coordinator,
            )
        effective_entrypoint_service = operation_entrypoint_service
        if effective_entrypoint_service is None:
            effective_entrypoint_service = OperationEntrypointService(
                store=store,
                event_sourced_operation_birth_service=event_sourced_operation_birth_service,
            )
        effective_cancellation_service = operation_cancellation_service
        if effective_cancellation_service is None:
            effective_cancellation_service = OperationCancellationService(
                store=store,
                event_sink=event_sink,
                supervisor=supervisor,
                history_ledger=history_ledger,
                lifecycle_coordinator=lifecycle_coordinator,
            )

        return OperatorService(
            operator_policy=operator_policy,
            store=store,
            trace_store=trace_store,
            event_sink=event_sink,
            agent_runtime_bindings=agent_runtime_bindings,
            wakeup_inbox=wakeup_inbox,
            command_inbox=command_inbox,
            planning_trigger_bus=planning_trigger_bus,
            policy_store=policy_store,
            supervisor=supervisor,
            process_manager_builder=process_manager_builder,
            project_memory_store=project_memory_store,
            attached_turn_timeout=attached_turn_timeout,
            event_sourced_command_service=event_sourced_command_service,
            event_sourced_operation_birth_service=event_sourced_operation_birth_service,
            operation_lifecycle_coordinator=lifecycle_coordinator,
            event_relay=event_relay,
            operation_attention_coordinator=attention_coordinator,
            operation_policy_context_coordinator=policy_context_coordinator,
            process_signal_dispatcher=process_signal_dispatcher,
            operation_traceability_service=traceability_service,
            operation_control_state_coordinator=control_state,
            agent_result_service=agent_result_service,
            operation_command_service=operation_command_service,
            operation_turn_execution_service=turn_execution_service,
            operation_runtime_reconciliation_service=runtime_reconciliation_service,
            decision_execution_service=decision_execution_service,
            operation_drive_control_service=operation_drive_control_service,
            operation_drive_runtime_service=operation_drive_runtime_service,
            operation_drive_trace_service=operation_drive_trace_service,
            operation_drive_decision_executor_service=operation_drive_decision_executor_service,
            operation_drive_service=operation_drive_service,
            operation_entrypoint_service=effective_entrypoint_service,
            operation_cancellation_service=effective_cancellation_service,
            operation_runtime=effective_operation_runtime,
            history_ledger=history_ledger,
        )


def make_service(**kwargs) -> OperatorService:
    if "brain" in kwargs and "operator_policy" not in kwargs:
        kwargs["operator_policy"] = kwargs.pop("brain")
    container = make_container(_TestServiceProvider(kwargs))
    return container.get(OperatorService)


def state_settings(
    *,
    allowed_agents: list[str] | None = None,
    involvement_level: InvolvementLevel = InvolvementLevel.AUTO,
    max_iterations: int = 100,
    timeout_seconds: int | None = None,
    metadata: dict[str, object] | None = None,
    max_task_retries: int = 2,
    operator_message_window: int = 3,
) -> dict[str, object]:
    return {
        "policy": OperationPolicy(
            allowed_agents=list(allowed_agents or []),
            involvement_level=involvement_level,
        ),
        "execution_budget": ExecutionBudget(
            max_iterations=max_iterations,
            timeout_seconds=timeout_seconds,
            max_task_retries=max_task_retries,
        ),
        "runtime_hints": RuntimeHints(
            operator_message_window=operator_message_window,
            metadata=dict(metadata or {}),
        ),
    }


def run_settings(
    *,
    allowed_agents: list[str] | None = None,
    involvement_level: InvolvementLevel = InvolvementLevel.AUTO,
    max_iterations: int = 100,
    timeout_seconds: int | None = None,
    metadata: dict[str, object] | None = None,
    max_task_retries: int = 2,
    operator_message_window: int = 3,
) -> dict[str, object]:
    return {
        "policy": OperationPolicy(
            allowed_agents=list(allowed_agents or []),
            involvement_level=involvement_level,
        ),
        "budget": ExecutionBudget(
            max_iterations=max_iterations,
            timeout_seconds=timeout_seconds,
            max_task_retries=max_task_retries,
        ),
        "runtime_hints": RuntimeHints(
            operator_message_window=operator_message_window,
            metadata=dict(metadata or {}),
        ),
    }


class FakeAgent:
    def __init__(self, *, key: str = "claude_acp", supports_follow_up: bool = True) -> None:
        self.key = key
        self.supports_follow_up = supports_follow_up
        self.started_requests: list[AgentRunRequest] = []
        self.sent_messages: list[str] = []
        self.poll_calls = 0

    async def describe(self) -> AgentDescriptor:
        return AgentDescriptor(
            key=self.key,
            display_name="Claude Code",
            capabilities=standard_coding_agent_capabilities(),
            supports_follow_up=self.supports_follow_up,
        )

    async def start(self, request: AgentRunRequest) -> AgentSessionHandle:
        self.started_requests.append(request)
        return AgentSessionHandle(
            adapter_key=self.key,
            session_id="session-1",
            one_shot=request.one_shot,
        )

    async def send(self, handle: AgentSessionHandle, message: str) -> None:
        self.sent_messages.append(message)

    async def poll(self, handle: AgentSessionHandle) -> AgentProgress:
        self.poll_calls += 1
        return AgentProgress(
            session_id=handle.session_id,
            state=AgentProgressState.COMPLETED,
            message="done",
            updated_at=datetime.now(UTC),
        )

    async def collect(self, handle: AgentSessionHandle) -> AgentResult:
        return AgentResult(
            session_id=handle.session_id,
            status=AgentResultStatus.SUCCESS,
            output_text="completed by fake agent",
            completed_at=datetime.now(UTC),
        )

    async def cancel(self, handle: AgentSessionHandle) -> None:
        return None

    async def close(self, handle: AgentSessionHandle) -> None:
        return None


class EscalatingAgent(FakeAgent):
    async def collect(self, handle: AgentSessionHandle) -> AgentResult:
        return AgentResult(
            session_id=handle.session_id,
            status=AgentResultStatus.SUCCESS,
            output_text=(
                "Need escalated permissions to update files outside writable roots. "
                "Please request escalation."
            ),
            completed_at=datetime.now(UTC),
        )


class WaitingInputAgent(FakeAgent):
    async def poll(self, handle: AgentSessionHandle) -> AgentProgress:
        self.poll_calls += 1
        return AgentProgress(
            session_id=handle.session_id,
            state=AgentProgressState.WAITING_INPUT,
            message="Agent is waiting for approval.",
            updated_at=datetime.now(UTC),
            partial_output="Need approval before continuing.",
            raw={"kind": "approval_request"},
        )

    async def collect(self, handle: AgentSessionHandle) -> AgentResult:
        raise AssertionError("collect should not be called after WAITING_INPUT")


class HangingAttachedAgent(FakeAgent):
    async def poll(self, handle: AgentSessionHandle) -> AgentProgress:
        self.poll_calls += 1
        return AgentProgress(
            session_id=handle.session_id,
            state=AgentProgressState.RUNNING,
            message="Still working on the current theorem.",
            updated_at=datetime.now(UTC),
            partial_output="Latest partial theorem state from the hanging turn.",
        )

    async def collect(self, handle: AgentSessionHandle) -> AgentResult:
        raise AssertionError("collect should not be called after attached-turn recovery")


class EventfulAttachedAgent(FakeAgent):
    def __init__(self) -> None:
        super().__init__()
        self._step = 0

    async def poll(self, handle: AgentSessionHandle) -> AgentProgress:
        self.poll_calls += 1
        self._step += 1
        if self._step == 1:
            return AgentProgress(
                session_id=handle.session_id,
                state=AgentProgressState.RUNNING,
                message="Still working with fresh ACP events.",
                updated_at=datetime.now(UTC),
                partial_output="Fresh activity is still arriving.",
                raw={"last_event_at": datetime.now(UTC).isoformat()},
            )
        return AgentProgress(
            session_id=handle.session_id,
            state=AgentProgressState.COMPLETED,
            message="done",
            updated_at=datetime.now(UTC),
        )

    async def collect(self, handle: AgentSessionHandle) -> AgentResult:
        return AgentResult(
            session_id=handle.session_id,
            status=AgentResultStatus.SUCCESS,
            output_text="completed after fresh ACP activity",
            completed_at=datetime.now(UTC),
        )


class RecoverableDisconnectAgent(FakeAgent):
    def __init__(
        self,
        *,
        key: str = "claude_acp",
        error_code: str = "claude_acp_disconnected",
    ) -> None:
        super().__init__(key=key)
        self._collects = 0
        self._error_code = error_code

    async def collect(self, handle: AgentSessionHandle) -> AgentResult:
        self._collects += 1
        if self._collects == 1:
            return AgentResult(
                session_id=handle.session_id,
                status=AgentResultStatus.DISCONNECTED,
                output_text="",
                error=AgentError(
                    code=self._error_code,
                    message="ACP subprocess closed before completing all pending requests.",
                    retryable=True,
                    raw={"recovery_mode": "same_session"},
                ),
                completed_at=datetime.now(UTC),
            )
        return AgentResult(
            session_id=handle.session_id,
            status=AgentResultStatus.SUCCESS,
            output_text="recovered same session successfully",
            completed_at=datetime.now(UTC),
        )


class HangingClaudeAcpAgentWithLog(HangingAttachedAgent):
    def __init__(self, log_path: Path, *, key: str = "claude_acp") -> None:
        super().__init__(key=key)
        self._log_path = log_path

    async def start(self, request: AgentRunRequest) -> AgentSessionHandle:
        self.started_requests.append(request)
        return AgentSessionHandle(
            adapter_key=self.key,
            session_id="session-1",
            one_shot=request.one_shot,
            metadata={"log_path": str(self._log_path)},
        )


class RateLimitedAgent(FakeAgent):
    async def collect(self, handle: AgentSessionHandle) -> AgentResult:
        return AgentResult(
            session_id=handle.session_id,
            status=AgentResultStatus.FAILED,
            output_text="",
            error=AgentError(
                code="claude_acp_rate_limited",
                message="Claude rate limit hit. Try again in 60 minutes.",
                retryable=True,
                raw={"retry_after_seconds": 3600, "rate_limit_detected": True},
            ),
            completed_at=datetime.now(UTC),
        )


class StaticProgressBrain:
    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


class StartThenStopBrain:
    def __init__(self) -> None:
        self.calls = 0

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="claude_acp",
                instruction="do the task",
                rationale="Use Claude for the task.",
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="The task is complete.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(
            goal_satisfied=True,
            should_continue=False,
            summary="Goal satisfied.",
        )

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


class StartClaudeAcpThenStopBrain(StartThenStopBrain):
    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="claude_acp",
                instruction="do the task",
                rationale="Use Claude ACP for the task.",
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="The task is complete.",
        )


class DescriptorCapturingBrain(StartThenStopBrain):
    def __init__(self) -> None:
        super().__init__()
        self.descriptors: list[dict[str, object]] | None = None

    async def decide_next_action(self, state) -> BrainDecision:
        raw = state.runtime_hints.metadata.get("available_agent_descriptors")
        assert isinstance(raw, list)
        self.descriptors = raw
        return await super().decide_next_action(state)


class MemoryDistillingStartThenStopBrain(StartThenStopBrain):
    async def distill_memory(
        self,
        state,
        *,
        scope: str,
        scope_id: str,
        source_refs: list[dict[str, str]],
        instruction: str,
    ):
        from agent_operator.domain import MemoryEntryDraft

        return MemoryEntryDraft(
            scope=scope,
            scope_id=scope_id,
            summary="Durable task memory captured from the final artifact.",
        )


class StartThenBlockBrain(StartThenStopBrain):
    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(
            goal_satisfied=False,
            should_continue=False,
            summary="Blocked on agent input.",
        )


class StartThenFailBrain:
    def __init__(self) -> None:
        self.calls = 0

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="claude_acp",
                instruction="do the task",
                rationale="Start the task.",
            )
        return BrainDecision(
            action_type=BrainActionType.FAIL,
            rationale="The agent surfaced an external blocker that makes this goal fail.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(
            goal_satisfied=False,
            should_continue=True,
            summary="Need another decision.",
        )

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


class StartTwiceThenStopBrain:
    def __init__(self, *, target_agent: str = "claude_acp") -> None:
        self.calls = 0
        self.target_agent = target_agent

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls <= 2:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent=self.target_agent,
                instruction="keep going",
                rationale="Continue the same agent work.",
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="done",
        )

    async def evaluate_result(self, state) -> Evaluation:
        latest = state.iterations[-1].result if state.iterations else None
        if latest is not None and latest.status is AgentResultStatus.SUCCESS:
            return Evaluation(goal_satisfied=True, should_continue=False, summary="done")
        return Evaluation(goal_satisfied=False, should_continue=True, summary="continue")

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


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
        return Evaluation(goal_satisfied=False, should_continue=True, summary="continue")

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


class ClarificationBrain:
    async def decide_next_action(self, state) -> BrainDecision:
        return BrainDecision(
            action_type=BrainActionType.REQUEST_CLARIFICATION,
            rationale="Which deployment target should the operator use?",
        )

    async def evaluate_result(self, state) -> Evaluation:
        raise AssertionError("evaluate_result should not be called for clarification")

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


class AnswerThenStopBrain:
    async def decide_next_action(self, state) -> BrainDecision:
        answered = next(
            (
                item
                for item in state.attention_requests
                if item.status is AttentionStatus.ANSWERED and item.answer_text
            ),
            None,
        )
        if answered is not None:
            return BrainDecision(
                action_type=BrainActionType.STOP,
                rationale=f"Continuing with human answer: {answered.answer_text}",
            )
        return BrainDecision(
            action_type=BrainActionType.REQUEST_CLARIFICATION,
            rationale="Which deployment target should the operator use?",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(goal_satisfied=True, should_continue=False, summary="done")

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result
