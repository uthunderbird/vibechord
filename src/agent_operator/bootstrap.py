from __future__ import annotations

from datetime import timedelta

from dishka import Provider, Scope, make_container, provide

from agent_operator.adapters import (
    AgentRuntimeBinding,
    build_agent_runtime_bindings,
)
from agent_operator.application import (
    AgentResultService,
    AttachedSessionManager,
    AttachedTurnService,
    DecisionExecutionService,
    EventSourcedCommandApplicationService,
    EventSourcedOperationBirthService,
    LlmFirstOperatorPolicy,
    OperationCommandService,
    OperationControlStateCoordinator,
    OperationDriveControlService,
    OperationDriveDecisionExecutorService,
    OperationDriveRuntimeService,
    OperationDriveService,
    OperationDriveTraceService,
    OperationEntrypointService,
    OperationLifecycleCoordinator,
    OperationRuntimeReconciliationService,
    OperationTraceabilityService,
    OperatorService,
    OperatorServiceV2,
    SupervisorBackedOperationRuntime,
)
from agent_operator.application.commands.operation_attention import OperationAttentionCoordinator
from agent_operator.application.commands.operation_cancellation import OperationCancellationService
from agent_operator.application.drive import (
    AgentRunSupervisorV2,
    DriveService,
    LifecycleGate,
    PolicyExecutor,
    RuntimeReconciler,
)
from agent_operator.application.event_sourcing.event_sourced_replay import EventSourcedReplayService
from agent_operator.application.loaded_operation import LoadedOperation
from agent_operator.application.operation_turn_execution import OperationTurnExecutionService
from agent_operator.application.process_managers import CodeProcessManagerBuilder
from agent_operator.application.runtime.operation_event_relay import OperationEventRelay
from agent_operator.application.runtime.operation_policy_context import (
    OperationPolicyContextCoordinator,
)
from agent_operator.application.runtime.operation_process_dispatch import (
    OperationProcessSignalDispatcher,
)
from agent_operator.application.runtime.operation_runtime_context import OperationRuntimeContext
from agent_operator.application.ticketing import TicketReportingService
from agent_operator.config import OperatorSettings, load_global_config
from agent_operator.projectors import DefaultOperationProjector
from agent_operator.protocols import AgentSessionManager, EventSink, ProcessManager
from agent_operator.providers import (
    CodexStructuredOutputProvider,
    OpenAIResponsesStructuredOutputProvider,
    ProviderBackedBrain,
    ProviderBackedPermissionEvaluator,
)
from agent_operator.runtime import (
    BackgroundRunInspectionStore,
    FileControlIntentBus,
    FileFactStore,
    FileOperationCheckpointStore,
    FileOperationCommandInbox,
    FileOperationEventStore,
    FileOperationHistoryLedger,
    FileOperationStore,
    FilePolicyStore,
    FileProjectMemoryStore,
    FileTraceStore,
    FileWakeupInbox,
    InProcessAgentRunSupervisor,
    JsonlEventSink,
    discover_workspace_root,
)


class _BootstrapProviderBase(Provider):
    def __init__(
        self,
        settings: OperatorSettings,
        *,
        event_sink: EventSink | None,
    ) -> None:
        super().__init__(scope=Scope.APP)
        self._settings = settings
        self._event_sink_override = event_sink


class StorageProvider(_BootstrapProviderBase):
    @provide(scope=Scope.APP)
    def store(self) -> FileOperationStore:
        return FileOperationStore(self._settings.data_dir / "runs")

    @provide(scope=Scope.APP)
    def trace_store(self) -> FileTraceStore:
        return FileTraceStore(self._settings.data_dir / "runs")

    @provide(scope=Scope.APP)
    def event_sink(self) -> EventSink:
        return self._event_sink_override or JsonlEventSink(self._settings.data_dir, "default")

    @provide(scope=Scope.APP)
    def wakeup_inbox(self) -> FileWakeupInbox:
        return FileWakeupInbox(self._settings.data_dir / "wakeups")

    @provide(scope=Scope.APP)
    def control_intent_bus(self) -> FileControlIntentBus:
        return FileControlIntentBus(self._settings.data_dir / "control_intents")

    @provide(scope=Scope.APP)
    def command_inbox(self) -> FileOperationCommandInbox:
        return FileOperationCommandInbox(self._settings.data_dir / "commands")

    @provide(scope=Scope.APP)
    def event_store(self) -> FileOperationEventStore:
        return FileOperationEventStore(self._settings.data_dir / "operation_events")

    @provide(scope=Scope.APP)
    def fact_store(self) -> FileFactStore:
        return FileFactStore(self._settings.data_dir / "facts")

    @provide(scope=Scope.APP)
    def checkpoint_store(self) -> FileOperationCheckpointStore:
        return FileOperationCheckpointStore(self._settings.data_dir / "operation_checkpoints")

    @provide(scope=Scope.APP)
    def policy_store(self) -> FilePolicyStore:
        return FilePolicyStore(self._settings.data_dir / "policies")

    @provide(scope=Scope.APP)
    def project_memory_store(self) -> FileProjectMemoryStore:
        return FileProjectMemoryStore(self._settings.data_dir / "project_memory")


class BrainProvider(_BootstrapProviderBase):
    @provide(scope=Scope.APP)
    def provider(
        self,
    ) -> OpenAIResponsesStructuredOutputProvider | CodexStructuredOutputProvider:
        return _build_provider(self._settings)

    @provide(scope=Scope.APP)
    def brain(
        self,
        provider: OpenAIResponsesStructuredOutputProvider | CodexStructuredOutputProvider,
    ) -> ProviderBackedBrain:
        return ProviderBackedBrain(provider)

    @provide(scope=Scope.APP)
    def operator_policy(self, brain: ProviderBackedBrain) -> LlmFirstOperatorPolicy:
        return LlmFirstOperatorPolicy(brain)

    @provide(scope=Scope.APP)
    def permission_evaluator(
        self,
        provider: OpenAIResponsesStructuredOutputProvider | CodexStructuredOutputProvider,
        store: FileOperationStore,
        policy_store: FilePolicyStore,
        replay_service: EventSourcedReplayService,
    ) -> ProviderBackedPermissionEvaluator:
        return ProviderBackedPermissionEvaluator(
            provider,
            store=store,
            policy_store=policy_store,
            replay_service=replay_service,
        )

    @provide(scope=Scope.APP)
    def runtime_bindings(
        self,
        permission_evaluator: ProviderBackedPermissionEvaluator,
    ) -> dict[str, AgentRuntimeBinding]:
        return build_agent_runtime_bindings(
            self._settings,
            permission_evaluator=permission_evaluator,
        )


class EventSourcingProvider(_BootstrapProviderBase):
    @provide(scope=Scope.APP)
    def projector(self) -> DefaultOperationProjector:
        return DefaultOperationProjector()

    @provide(scope=Scope.APP)
    def birth_service(
        self,
        event_store: FileOperationEventStore,
        checkpoint_store: FileOperationCheckpointStore,
        projector: DefaultOperationProjector,
    ) -> EventSourcedOperationBirthService:
        return EventSourcedOperationBirthService(
            event_store=event_store,
            checkpoint_store=checkpoint_store,
            projector=projector,
        )

    @provide(scope=Scope.APP)
    def event_sourced_command_service(
        self,
        event_store: FileOperationEventStore,
        checkpoint_store: FileOperationCheckpointStore,
        projector: DefaultOperationProjector,
    ) -> EventSourcedCommandApplicationService:
        return EventSourcedCommandApplicationService(
            event_store=event_store,
            checkpoint_store=checkpoint_store,
            projector=projector,
        )

    @provide(scope=Scope.APP)
    def replay_service(
        self,
        event_store: FileOperationEventStore,
        checkpoint_store: FileOperationCheckpointStore,
        projector: DefaultOperationProjector,
    ) -> EventSourcedReplayService:
        return EventSourcedReplayService(
            event_store=event_store,
            checkpoint_store=checkpoint_store,
            projector=projector,
        )


class RuntimeProvider(_BootstrapProviderBase):
    @provide(scope=Scope.APP)
    def attached_session_registry(
        self,
        runtime_bindings: dict[str, AgentRuntimeBinding],
        event_sink: EventSink,
    ) -> AttachedSessionManager:
        return AttachedSessionManager(runtime_bindings, event_sink=event_sink)

    @provide(scope=Scope.APP)
    def agent_session_manager(
        self,
        attached_session_registry: AttachedSessionManager,
    ) -> AgentSessionManager:
        return attached_session_registry

    @provide(scope=Scope.APP)
    def loaded_operation(
        self,
        attached_session_registry: AgentSessionManager,
    ) -> LoadedOperation:
        return LoadedOperation(attached_session_registry=attached_session_registry)

    @provide(scope=Scope.APP)
    def operation_runtime_context(
        self,
        loaded_operation: LoadedOperation,
        attached_session_registry: AgentSessionManager,
    ) -> OperationRuntimeContext:
        return OperationRuntimeContext(
            loaded_operation=loaded_operation,
            attached_session_registry=attached_session_registry,
        )

    @provide(scope=Scope.APP)
    def supervisor(
        self,
        wakeup_inbox: FileWakeupInbox,
        session_manager: AgentSessionManager,
    ) -> InProcessAgentRunSupervisor:
        return InProcessAgentRunSupervisor(
            self._settings.data_dir / "background",
            self._settings.data_dir,
            session_manager=session_manager,
            wakeup_inbox=wakeup_inbox,
        )

    @provide(scope=Scope.APP)
    def operation_runtime(
        self,
        supervisor: InProcessAgentRunSupervisor,
    ) -> SupervisorBackedOperationRuntime:
        return SupervisorBackedOperationRuntime(supervisor=supervisor)

    @provide(scope=Scope.APP)
    def history_ledger(self) -> FileOperationHistoryLedger:
        return FileOperationHistoryLedger(
            discover_workspace_root(cwd=self._settings.data_dir) / "operator-history.jsonl"
        )

    @provide(scope=Scope.APP)
    def operation_entrypoint_service(
        self,
        store: FileOperationStore,
        birth_service: EventSourcedOperationBirthService,
        replay_service: EventSourcedReplayService,
    ) -> OperationEntrypointService:
        return OperationEntrypointService(
            store=store,
            event_sourced_operation_birth_service=birth_service,
            event_sourced_replay_service=replay_service,
        )

    @provide(scope=Scope.APP)
    def process_manager_builder(self) -> CodeProcessManagerBuilder:
        return CodeProcessManagerBuilder()

    @provide(scope=Scope.APP)
    def process_managers(
        self,
        process_manager_builder: CodeProcessManagerBuilder,
    ) -> list[ProcessManager]:
        return process_manager_builder.build()


class OperatorGraphProvider(_BootstrapProviderBase):
    @provide(scope=Scope.APP)
    def operation_lifecycle_coordinator(
        self,
        store: FileOperationStore,
        history_ledger: FileOperationHistoryLedger,
        event_store: FileOperationEventStore,
        replay_service: EventSourcedReplayService,
        operation_attention_coordinator: OperationAttentionCoordinator,
    ) -> OperationLifecycleCoordinator:
        return OperationLifecycleCoordinator(
            store=store,
            history_ledger=history_ledger,
            event_store=event_store,
            replay_service=replay_service,
            ticket_reporter=TicketReportingService(
                store=store,
                global_config=load_global_config(),
                attention_coordinator=operation_attention_coordinator,
            ),
        )

    @provide(scope=Scope.APP)
    def attached_turn_service(self) -> AttachedTurnService:
        return AttachedTurnService(
            attached_turn_timeout=timedelta(minutes=self._settings.attached_turn_timeout_minutes),
        )

    @provide(scope=Scope.APP)
    def event_relay(
        self,
        event_sink: EventSink,
        wakeup_inbox: FileWakeupInbox,
    ) -> OperationEventRelay:
        return OperationEventRelay(event_sink=event_sink, wakeup_inbox=wakeup_inbox)

    @provide(scope=Scope.APP)
    def operation_attention_coordinator(self) -> OperationAttentionCoordinator:
        return OperationAttentionCoordinator()

    @provide(scope=Scope.APP)
    def operation_policy_context_coordinator(
        self,
        policy_store: FilePolicyStore,
    ) -> OperationPolicyContextCoordinator:
        return OperationPolicyContextCoordinator(policy_store=policy_store)

    @provide(scope=Scope.APP)
    def process_signal_dispatcher(
        self,
        control_intent_bus: FileControlIntentBus,
        process_managers: list[ProcessManager],
        event_relay: OperationEventRelay,
    ) -> OperationProcessSignalDispatcher:
        return OperationProcessSignalDispatcher(
            planning_trigger_bus=control_intent_bus,
            process_managers=process_managers,
            emit=event_relay.emit,
        )

    @provide(scope=Scope.APP)
    def traceability_service(
        self,
        loaded_operation: LoadedOperation,
        trace_store: FileTraceStore,
        operation_runtime_context: OperationRuntimeContext,
    ) -> OperationTraceabilityService:
        return OperationTraceabilityService(
            loaded_operation=loaded_operation,
            trace_store=trace_store,
            runtime_context=operation_runtime_context,
        )

    @provide(scope=Scope.APP)
    def operation_control_state_coordinator(
        self,
        store: FileOperationStore,
        traceability_service: OperationTraceabilityService,
        event_sourced_command_service: EventSourcedCommandApplicationService,
    ) -> OperationControlStateCoordinator:
        return OperationControlStateCoordinator(
            store=store,
            traceability_service=traceability_service,
            event_sourced_command_service=event_sourced_command_service,
        )

    @provide(scope=Scope.APP)
    def agent_result_service(
        self,
        loaded_operation: LoadedOperation,
        operator_policy: LlmFirstOperatorPolicy,
        event_relay: OperationEventRelay,
        process_signal_dispatcher: OperationProcessSignalDispatcher,
        operation_lifecycle_coordinator: OperationLifecycleCoordinator,
        operation_attention_coordinator: OperationAttentionCoordinator,
        traceability_service: OperationTraceabilityService,
    ) -> AgentResultService:
        return AgentResultService(
            loaded_operation=loaded_operation,
            operator_policy=operator_policy,
            event_relay=event_relay,
            process_signal_dispatcher=process_signal_dispatcher,
            lifecycle_coordinator=operation_lifecycle_coordinator,
            attention_coordinator=operation_attention_coordinator,
            record_agent_turn_brief=traceability_service.record_agent_turn_brief,
        )

    @provide(scope=Scope.APP)
    def operation_command_service(
        self,
        loaded_operation: LoadedOperation,
        command_inbox: FileOperationCommandInbox,
        trace_store: FileTraceStore,
        operation_policy_context_coordinator: OperationPolicyContextCoordinator,
        operation_attention_coordinator: OperationAttentionCoordinator,
        attached_session_registry: AgentSessionManager,
        operation_runtime: SupervisorBackedOperationRuntime,
        event_sourced_command_service: EventSourcedCommandApplicationService,
        event_relay: OperationEventRelay,
        operation_control_state_coordinator: OperationControlStateCoordinator,
        operation_lifecycle_coordinator: OperationLifecycleCoordinator,
        process_signal_dispatcher: OperationProcessSignalDispatcher,
        operation_runtime_context: OperationRuntimeContext,
    ) -> OperationCommandService:
        return OperationCommandService(
            loaded_operation=loaded_operation,
            command_inbox=command_inbox,
            trace_store=trace_store,
            policy_context_coordinator=operation_policy_context_coordinator,
            attention_coordinator=operation_attention_coordinator,
            attached_session_registry=attached_session_registry,
            operation_runtime=operation_runtime,
            event_sourced_command_service=event_sourced_command_service,
            event_relay=event_relay,
            control_state_coordinator=operation_control_state_coordinator,
            lifecycle_coordinator=operation_lifecycle_coordinator,
            process_signal_dispatcher=process_signal_dispatcher,
            runtime_context=operation_runtime_context,
        )

    @provide(scope=Scope.APP)
    def operation_turn_execution_service(
        self,
        loaded_operation: LoadedOperation,
        attached_session_registry: AgentSessionManager,
        attached_turn_service: AttachedTurnService,
        operation_runtime: SupervisorBackedOperationRuntime,
        store: FileOperationStore,
        event_relay: OperationEventRelay,
        process_signal_dispatcher: OperationProcessSignalDispatcher,
        traceability_service: OperationTraceabilityService,
        operation_command_service: OperationCommandService,
    ) -> OperationTurnExecutionService:
        return OperationTurnExecutionService(
            loaded_operation=loaded_operation,
            attached_session_registry=attached_session_registry,
            attached_turn_service=attached_turn_service,
            operation_runtime=operation_runtime,
            store=store,
            event_relay=event_relay,
            process_signal_dispatcher=process_signal_dispatcher,
            traceability_service=traceability_service,
            command_service=operation_command_service,
        )

    @provide(scope=Scope.APP)
    def operation_runtime_reconciliation_service(
        self,
        loaded_operation: LoadedOperation,
        operation_runtime: SupervisorBackedOperationRuntime,
        wakeup_inbox: FileWakeupInbox,
        event_relay: OperationEventRelay,
        operation_lifecycle_coordinator: OperationLifecycleCoordinator,
        operation_runtime_context: OperationRuntimeContext,
        agent_result_service: AgentResultService,
        traceability_service: OperationTraceabilityService,
    ) -> OperationRuntimeReconciliationService:
        return OperationRuntimeReconciliationService(
            loaded_operation=loaded_operation,
            operation_runtime=operation_runtime,
            wakeup_inbox=wakeup_inbox,
            event_relay=event_relay,
            stale_background_run_threshold=OperatorService._STALE_BACKGROUND_RUN_THRESHOLD,
            lifecycle_coordinator=operation_lifecycle_coordinator,
            runtime_context=operation_runtime_context,
            agent_result_service=agent_result_service,
            traceability_service=traceability_service,
        )

    @provide(scope=Scope.APP)
    def decision_execution_service(
        self,
        loaded_operation: LoadedOperation,
        attached_session_registry: AgentSessionManager,
        operation_attention_coordinator: OperationAttentionCoordinator,
        event_relay: OperationEventRelay,
        operation_lifecycle_coordinator: OperationLifecycleCoordinator,
        operation_runtime_context: OperationRuntimeContext,
        operation_turn_execution_service: OperationTurnExecutionService,
        agent_result_service: AgentResultService,
    ) -> DecisionExecutionService:
        return DecisionExecutionService(
            loaded_operation=loaded_operation,
            attached_session_registry=attached_session_registry,
            attention_coordinator=operation_attention_coordinator,
            event_relay=event_relay,
            lifecycle_coordinator=operation_lifecycle_coordinator,
            runtime_context=operation_runtime_context,
            turn_execution_service=operation_turn_execution_service,
            agent_result_service=agent_result_service,
        )

    @provide(scope=Scope.APP)
    def operation_drive_control_service(
        self,
        operation_command_service: OperationCommandService,
        control_intent_bus: FileControlIntentBus,
        event_relay: OperationEventRelay,
    ) -> OperationDriveControlService:
        return OperationDriveControlService(
            drain_commands=operation_command_service.drain_commands,
            finalize_pending_attention_resolutions=(
                operation_command_service.finalize_pending_attention_resolutions
            ),
            planning_trigger_bus=control_intent_bus,
            emit=event_relay.emit,
        )

    @provide(scope=Scope.APP)
    def operation_drive_runtime_service(
        self,
        operation_runtime_context: OperationRuntimeContext,
        operation_runtime_reconciliation_service: OperationRuntimeReconciliationService,
        operation_policy_context_coordinator: OperationPolicyContextCoordinator,
    ) -> OperationDriveRuntimeService:
        return OperationDriveRuntimeService(
            runtime_context=operation_runtime_context,
            runtime_reconciliation_service=operation_runtime_reconciliation_service,
            refresh_policy_context=operation_policy_context_coordinator.refresh_policy_context,
        )

    @provide(scope=Scope.APP)
    def operation_drive_trace_service(
        self,
        event_relay: OperationEventRelay,
        traceability_service: OperationTraceabilityService,
    ) -> OperationDriveTraceService:
        return OperationDriveTraceService(
            event_relay=event_relay,
            traceability_service=traceability_service,
        )

    @provide(scope=Scope.APP)
    def operation_drive_decision_executor_service(
        self,
        decision_execution_service: DecisionExecutionService,
        supervisor: InProcessAgentRunSupervisor,
    ) -> OperationDriveDecisionExecutorService:
        return OperationDriveDecisionExecutorService(
            decision_execution_service=decision_execution_service,
            supervisor_available=supervisor is not None,
        )

    @provide(scope=Scope.APP)
    def operation_drive_service(
        self,
        operator_policy: LlmFirstOperatorPolicy,
        store: FileOperationStore,
        loaded_operation: LoadedOperation,
        operation_drive_runtime_service: OperationDriveRuntimeService,
        operation_drive_control_service: OperationDriveControlService,
        operation_drive_trace_service: OperationDriveTraceService,
        operation_drive_decision_executor_service: OperationDriveDecisionExecutorService,
        operation_lifecycle_coordinator: OperationLifecycleCoordinator,
    ) -> OperationDriveService:
        return OperationDriveService(
            operator_policy=operator_policy,
            store=store,
            loaded_operation=loaded_operation,
            runtime=operation_drive_runtime_service,
            control=operation_drive_control_service,
            trace=operation_drive_trace_service,
            decision_executor=operation_drive_decision_executor_service,
            lifecycle_coordinator=operation_lifecycle_coordinator,
        )

    @provide(scope=Scope.APP)
    def operation_cancellation_service(
        self,
        store: FileOperationStore,
        event_sink: EventSink,
        supervisor: InProcessAgentRunSupervisor,
        history_ledger: FileOperationHistoryLedger,
        operation_lifecycle_coordinator: OperationLifecycleCoordinator,
    ) -> OperationCancellationService:
        return OperationCancellationService(
            store=store,
            event_sink=event_sink,
            supervisor=supervisor,
            history_ledger=history_ledger,
            lifecycle_coordinator=operation_lifecycle_coordinator,
        )

    @provide(scope=Scope.APP)
    def operator_service(
        self,
        brain: ProviderBackedBrain,
        operator_policy: LlmFirstOperatorPolicy,
        store: FileOperationStore,
        trace_store: FileTraceStore,
        event_sink: EventSink,
        runtime_bindings: dict[str, AgentRuntimeBinding],
        session_manager: AgentSessionManager,
        wakeup_inbox: FileWakeupInbox,
        command_inbox: FileOperationCommandInbox,
        control_intent_bus: FileControlIntentBus,
        policy_store: FilePolicyStore,
        project_memory_store: FileProjectMemoryStore,
        supervisor: InProcessAgentRunSupervisor,
        event_sourced_command_service: EventSourcedCommandApplicationService,
        birth_service: EventSourcedOperationBirthService,
        history_ledger: FileOperationHistoryLedger,
        operation_entrypoint_service: OperationEntrypointService,
        process_manager_builder: CodeProcessManagerBuilder,
        operation_lifecycle_coordinator: OperationLifecycleCoordinator,
        event_relay: OperationEventRelay,
        operation_attention_coordinator: OperationAttentionCoordinator,
        operation_policy_context_coordinator: OperationPolicyContextCoordinator,
        process_signal_dispatcher: OperationProcessSignalDispatcher,
        traceability_service: OperationTraceabilityService,
        operation_control_state_coordinator: OperationControlStateCoordinator,
        agent_result_service: AgentResultService,
        operation_command_service: OperationCommandService,
        operation_turn_execution_service: OperationTurnExecutionService,
        operation_runtime_reconciliation_service: OperationRuntimeReconciliationService,
        decision_execution_service: DecisionExecutionService,
        operation_drive_control_service: OperationDriveControlService,
        operation_drive_runtime_service: OperationDriveRuntimeService,
        operation_drive_trace_service: OperationDriveTraceService,
        operation_drive_decision_executor_service: OperationDriveDecisionExecutorService,
        operation_drive_service: OperationDriveService,
        operation_cancellation_service: OperationCancellationService,
        operation_runtime: SupervisorBackedOperationRuntime,
    ) -> OperatorService:
        return OperatorService(
            operator_policy=operator_policy,
            brain=brain,
            store=store,
            trace_store=trace_store,
            event_sink=event_sink,
            agent_runtime_bindings=runtime_bindings,
            session_manager=session_manager,
            wakeup_inbox=wakeup_inbox,
            command_inbox=command_inbox,
            planning_trigger_bus=control_intent_bus,
            policy_store=policy_store,
            project_memory_store=project_memory_store,
            supervisor=supervisor,
            process_manager_builder=process_manager_builder,
            attached_turn_timeout=timedelta(minutes=self._settings.attached_turn_timeout_minutes),
            operation_lifecycle_coordinator=operation_lifecycle_coordinator,
            event_sourced_command_service=event_sourced_command_service,
            event_sourced_operation_birth_service=birth_service,
            event_relay=event_relay,
            operation_attention_coordinator=operation_attention_coordinator,
            operation_policy_context_coordinator=operation_policy_context_coordinator,
            process_signal_dispatcher=process_signal_dispatcher,
            operation_traceability_service=traceability_service,
            operation_control_state_coordinator=operation_control_state_coordinator,
            agent_result_service=agent_result_service,
            operation_command_service=operation_command_service,
            operation_turn_execution_service=operation_turn_execution_service,
            operation_runtime_reconciliation_service=operation_runtime_reconciliation_service,
            decision_execution_service=decision_execution_service,
            operation_drive_control_service=operation_drive_control_service,
            operation_drive_runtime_service=operation_drive_runtime_service,
            operation_drive_trace_service=operation_drive_trace_service,
            operation_drive_decision_executor_service=operation_drive_decision_executor_service,
            operation_drive_service=operation_drive_service,
            history_ledger=history_ledger,
            operation_entrypoint_service=operation_entrypoint_service,
            operation_cancellation_service=operation_cancellation_service,
            operation_runtime=operation_runtime,
        )


class V2Provider(_BootstrapProviderBase):
    """Providers for the v2 drive stack (ADR 0194/0195/0200)."""

    @provide(scope=Scope.APP)
    def agent_run_supervisor_v2(self) -> AgentRunSupervisorV2:
        return AgentRunSupervisorV2()

    @provide(scope=Scope.APP)
    def lifecycle_gate(self) -> LifecycleGate:
        return LifecycleGate()

    @provide(scope=Scope.APP)
    def runtime_reconciler(
        self,
        wakeup_inbox: FileWakeupInbox,
        command_inbox: FileOperationCommandInbox,
        event_sourced_command_service: EventSourcedCommandApplicationService,
        supervisor_v2: AgentRunSupervisorV2,
    ) -> RuntimeReconciler:
        return RuntimeReconciler(
            wakeup_inbox=wakeup_inbox,
            command_inbox=command_inbox,
            event_sourced_command_service=event_sourced_command_service,
            supervisor=supervisor_v2,
        )

    @provide(scope=Scope.APP)
    def policy_executor(
        self,
        brain: ProviderBackedBrain,
        supervisor_v2: AgentRunSupervisorV2,
        session_manager: AgentSessionManager,
        event_store: FileOperationEventStore,
        command_inbox: FileOperationCommandInbox,
        control_intent_bus: FileControlIntentBus,
        operation_attention_coordinator: OperationAttentionCoordinator,
    ) -> PolicyExecutor:
        return PolicyExecutor(
            brain=brain,
            supervisor=supervisor_v2,
            session_manager=session_manager,
            event_store=event_store,
            command_inbox=command_inbox,
            planning_trigger_bus=control_intent_bus,
            attention_coordinator=operation_attention_coordinator,
        )

    @provide(scope=Scope.APP)
    def drive_service(
        self,
        lifecycle_gate: LifecycleGate,
        reconciler: RuntimeReconciler,
        executor: PolicyExecutor,
        event_store: FileOperationEventStore,
        checkpoint_store: FileOperationCheckpointStore,
        replay_service: EventSourcedReplayService,
        history_ledger: FileOperationHistoryLedger,
        policy_store: FilePolicyStore,
        session_manager: AgentSessionManager,
        event_sink: EventSink,
    ) -> DriveService:
        return DriveService(
            lifecycle_gate=lifecycle_gate,
            reconciler=reconciler,
            executor=executor,
            event_store=event_store,
            checkpoint_store=checkpoint_store,
            replay_service=replay_service,
            policy_store=policy_store,
            adapter_registry=session_manager,
            event_sink=event_sink,
            history_ledger=history_ledger,
        )

    @provide(scope=Scope.APP)
    def operator_service_v2(
        self,
        drive_service: DriveService,
        event_store: FileOperationEventStore,
        event_sink: EventSink,
        supervisor_v2: AgentRunSupervisorV2,
        event_sourced_command_service: EventSourcedCommandApplicationService,
    ) -> OperatorServiceV2:
        return OperatorServiceV2(
            drive_service=drive_service,
            event_store=event_store,
            event_sink=event_sink,
            supervisor=supervisor_v2,
            event_sourced_command_service=event_sourced_command_service,
        )


def build_v2_service(
    settings: OperatorSettings,
    *,
    event_sink: EventSink | None = None,
) -> OperatorServiceV2:
    container = make_container(
        StorageProvider(settings, event_sink=event_sink),
        BrainProvider(settings, event_sink=event_sink),
        EventSourcingProvider(settings, event_sink=event_sink),
        RuntimeProvider(settings, event_sink=event_sink),
        OperatorGraphProvider(settings, event_sink=event_sink),
        V2Provider(settings, event_sink=event_sink),
    )
    return container.get(OperatorServiceV2)


def build_service(
    settings: OperatorSettings,
    *,
    event_sink: EventSink | None = None,
) -> OperatorService:
    container = make_container(
        StorageProvider(settings, event_sink=event_sink),
        BrainProvider(settings, event_sink=event_sink),
        EventSourcingProvider(settings, event_sink=event_sink),
        RuntimeProvider(settings, event_sink=event_sink),
        OperatorGraphProvider(settings, event_sink=event_sink),
    )
    return container.get(OperatorService)


def build_brain(settings: OperatorSettings) -> ProviderBackedBrain:
    return ProviderBackedBrain(_build_provider(settings))


def build_store(settings: OperatorSettings) -> FileOperationStore:
    return FileOperationStore(settings.data_dir / "runs")


def build_event_store(settings: OperatorSettings) -> FileOperationEventStore:
    return FileOperationEventStore(settings.data_dir / "operation_events")


def build_fact_store(settings: OperatorSettings) -> FileFactStore:
    return FileFactStore(settings.data_dir / "facts")


def build_event_sink(settings: OperatorSettings, operation_id: str) -> JsonlEventSink:
    return JsonlEventSink(settings.data_dir, operation_id)


def build_trace_store(settings: OperatorSettings) -> FileTraceStore:
    return FileTraceStore(settings.data_dir / "runs")


def build_wakeup_inbox(settings: OperatorSettings) -> FileWakeupInbox:
    return FileWakeupInbox(settings.data_dir / "wakeups")


def build_command_inbox(settings: OperatorSettings) -> FileOperationCommandInbox:
    return FileOperationCommandInbox(
        settings.data_dir / "commands",
        bus=FileControlIntentBus(settings.data_dir / "commands"),
    )


def build_policy_store(settings: OperatorSettings) -> FilePolicyStore:
    return FilePolicyStore(settings.data_dir / "policies")


def build_replay_service(settings: OperatorSettings) -> EventSourcedReplayService:
    return EventSourcedReplayService(
        event_store=FileOperationEventStore(settings.data_dir / "operation_events"),
        checkpoint_store=FileOperationCheckpointStore(settings.data_dir / "operation_checkpoints"),
        projector=DefaultOperationProjector(),
    )


def build_background_run_inspection_store(
    settings: OperatorSettings,
) -> BackgroundRunInspectionStore:
    """Build the read-only background run inspection surface used by CLI commands."""
    return BackgroundRunInspectionStore(settings.data_dir / "background")


def build_history_ledger(settings: OperatorSettings) -> FileOperationHistoryLedger:
    return FileOperationHistoryLedger(
        discover_workspace_root(cwd=settings.data_dir) / "operator-history.jsonl"
    )


def _build_provider(
    settings: OperatorSettings,
) -> OpenAIResponsesStructuredOutputProvider | CodexStructuredOutputProvider:
    if settings.brain_provider in {"codex", "openai_codex"}:
        return CodexStructuredOutputProvider(
            model=settings.codex_brain.model,
            base_url=settings.codex_brain.base_url,
            originator=settings.codex_brain.originator,
            reasoning_effort=settings.codex_brain.reasoning_effort,
            timeout_seconds=settings.codex_brain.timeout_seconds,
        )
    if settings.brain_provider == "openai":
        if not settings.openai.api_key:
            raise RuntimeError("OPERATOR_OPENAI__API_KEY is required when brain_provider=openai.")
        return OpenAIResponsesStructuredOutputProvider(
            model=settings.openai.model,
            base_url=settings.openai.base_url,
            api_key=settings.openai.api_key,
            timeout_seconds=settings.openai.timeout_seconds,
        )
    raise RuntimeError(f"Unsupported brain provider: {settings.brain_provider!r}")
