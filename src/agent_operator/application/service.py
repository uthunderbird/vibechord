from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta

from agent_operator.application.agent_results import AgentResultService
from agent_operator.application.agent_session_manager import RegistryBackedAgentSessionManager
from agent_operator.application.attached_session_registry import (
    AttachedRuntimeBinding,
)
from agent_operator.application.attached_turns import AttachedTurnService
from agent_operator.application.commands.operation_attention import OperationAttentionCoordinator
from agent_operator.application.commands.operation_cancellation import OperationCancellationService
from agent_operator.application.commands.operation_commands import OperationCommandService
from agent_operator.application.commands.operation_control_state import (
    OperationControlStateCoordinator,
)
from agent_operator.application.decision_execution import DecisionExecutionService
from agent_operator.application.drive.operation_drive import OperationDriveService
from agent_operator.application.drive.operation_drive_control import OperationDriveControlService
from agent_operator.application.drive.operation_drive_decision import (
    OperationDriveDecisionExecutorService,
)
from agent_operator.application.drive.operation_drive_runtime import OperationDriveRuntimeService
from agent_operator.application.drive.operation_drive_trace import OperationDriveTraceService
from agent_operator.application.event_sourcing.event_sourced_birth import (
    EventSourcedOperationBirthService,
)
from agent_operator.application.event_sourcing.event_sourced_commands import (
    EventSourcedCommandApplicationService,
)
from agent_operator.application.loaded_operation import LoadedOperation
from agent_operator.application.operation_entrypoints import OperationEntrypointService
from agent_operator.application.operation_lifecycle import OperationLifecycleCoordinator
from agent_operator.application.operation_turn_execution import OperationTurnExecutionService
from agent_operator.application.queries.operation_traceability import OperationTraceabilityService
from agent_operator.application.runtime.operation_event_relay import OperationEventRelay
from agent_operator.application.runtime.operation_policy_context import (
    OperationPolicyContextCoordinator,
)
from agent_operator.application.runtime.operation_process_dispatch import (
    OperationProcessSignalDispatcher,
)
from agent_operator.application.runtime.operation_runtime import SupervisorBackedOperationRuntime
from agent_operator.application.runtime.operation_runtime_context import OperationRuntimeContext
from agent_operator.application.runtime.operation_runtime_reconciliation import (
    OperationRuntimeReconciliationService,
)
from agent_operator.domain import (
    AgentSessionHandle,
    ExecutionBudget,
    OperationGoal,
    OperationOutcome,
    OperationPolicy,
    OperationState,
    RunOptions,
    RuntimeHints,
)
from agent_operator.protocols import (
    AgentRunSupervisor,
    AgentSessionManager,
    EventSink,
    OperationCommandInbox,
    OperationRuntime,
    OperationStore,
    OperatorBrain,
    OperatorPolicy,
    PlanningTriggerBus,
    PolicyStore,
    ProcessManager,
    ProcessManagerBuilder,
    TraceStore,
    WakeupInbox,
)


class OperatorService:
    _STALE_BACKGROUND_RUN_THRESHOLD = timedelta(seconds=90)

    def __init__(
        self,
        operator_policy: OperatorPolicy,
        brain: OperatorBrain,
        store: OperationStore,
        trace_store: TraceStore,
        event_sink: EventSink,
        agent_runtime_bindings: Mapping[str, AttachedRuntimeBinding],
        session_manager: AgentSessionManager | None,
        operation_lifecycle_coordinator: OperationLifecycleCoordinator,
        event_relay: OperationEventRelay,
        operation_attention_coordinator: OperationAttentionCoordinator,
        operation_policy_context_coordinator: OperationPolicyContextCoordinator,
        process_signal_dispatcher: OperationProcessSignalDispatcher,
        operation_traceability_service: OperationTraceabilityService,
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
        operation_entrypoint_service: OperationEntrypointService,
        operation_cancellation_service: OperationCancellationService,
        wakeup_inbox: WakeupInbox | None = None,
        command_inbox: OperationCommandInbox | None = None,
        planning_trigger_bus: PlanningTriggerBus | None = None,
        policy_store: PolicyStore | None = None,
        supervisor: AgentRunSupervisor | None = None,
        process_manager_builder: ProcessManagerBuilder | None = None,
        project_memory_store: object | None = None,
        attached_turn_timeout: timedelta = timedelta(minutes=30),
        event_sourced_command_service: EventSourcedCommandApplicationService | None = None,
        event_sourced_operation_birth_service: EventSourcedOperationBirthService | None = None,
        operation_runtime: OperationRuntime | None = None,
        history_ledger: object | None = None,
    ) -> None:
        self._operator_policy = operator_policy
        self._brain = brain
        self._store = store
        self._trace_store = trace_store
        self._event_sink = event_sink
        self._attached_session_registry: AgentSessionManager = (
            session_manager
            if session_manager is not None
            else RegistryBackedAgentSessionManager.from_bindings(agent_runtime_bindings)
        )
        self._loaded_operation = LoadedOperation(
            attached_session_registry=self._attached_session_registry
        )
        self._operation_runtime_context = OperationRuntimeContext(
            loaded_operation=self._loaded_operation,
            attached_session_registry=self._attached_session_registry,
        )
        self._wakeup_inbox = wakeup_inbox
        self._command_inbox = command_inbox
        self._planning_trigger_bus: PlanningTriggerBus | None
        if planning_trigger_bus is not None:
            self._planning_trigger_bus = planning_trigger_bus
        elif isinstance(command_inbox, PlanningTriggerBus):
            self._planning_trigger_bus = command_inbox
        else:
            self._planning_trigger_bus = None
        self._policy_store = policy_store
        self._supervisor = supervisor
        self._operation_runtime = (
            operation_runtime
            if operation_runtime is not None
            else (
                SupervisorBackedOperationRuntime(supervisor=supervisor)
                if supervisor is not None
                else None
            )
        )
        self._project_memory_store = project_memory_store
        self._attached_turn_timeout = attached_turn_timeout
        self._operation_lifecycle_coordinator = operation_lifecycle_coordinator
        self._event_sourced_command_service = event_sourced_command_service
        self._attached_turn_service = AttachedTurnService(
            attached_turn_timeout=attached_turn_timeout,
        )
        self._event_relay = event_relay
        self._operation_attention_coordinator = operation_attention_coordinator
        self._operation_policy_context_coordinator = operation_policy_context_coordinator
        self._process_managers: list[ProcessManager] = (
            process_manager_builder.build() if process_manager_builder is not None else []
        )
        self._process_signal_dispatcher = process_signal_dispatcher
        self._traceability_service = operation_traceability_service
        self._operation_control_state_coordinator = operation_control_state_coordinator
        self._agent_result_service = agent_result_service
        self._operation_command_service = operation_command_service
        self._operation_turn_execution_service = operation_turn_execution_service
        self._operation_runtime_reconciliation_service = operation_runtime_reconciliation_service
        self._decision_execution_service = decision_execution_service
        self._operation_drive_control_service = operation_drive_control_service
        self._operation_drive_runtime_service = operation_drive_runtime_service
        self._operation_drive_trace_service = operation_drive_trace_service
        self._operation_drive_decision_executor_service = operation_drive_decision_executor_service
        self._operation_drive_service = operation_drive_service
        self._event_sourced_operation_birth_service = event_sourced_operation_birth_service
        self._operation_entrypoint_service = operation_entrypoint_service
        self._operation_cancellation_service = operation_cancellation_service

    async def run(
        self,
        goal: OperationGoal,
        options: RunOptions | None = None,
        *,
        operation_id: str | None = None,
        attached_sessions: list[AgentSessionHandle] | None = None,
        policy: OperationPolicy | None = None,
        budget: ExecutionBudget | None = None,
        runtime_hints: RuntimeHints | None = None,
    ) -> OperationOutcome:
        opts = options or RunOptions()
        state = await self._operation_entrypoint_service.prepare_run(
            goal=goal,
            policy=policy,
            budget=budget,
            runtime_hints=runtime_hints,
            options=opts,
            operation_id=operation_id,
            attached_sessions=attached_sessions,
            merge_runtime_flags=self._merge_runtime_flags,
            attach_initial_sessions=self._loaded_operation.attach_initial_sessions,
        )
        await self._event_relay.emit(
            "operation.started",
            state,
            0,
            {
                "objective": goal.objective_text,
                "harness_instructions": goal.harness_text,
            },
        )
        await self._traceability_service.sync_traceability_artifacts(state)
        await self._store.save_operation(state)
        return await self._drive_state(state, opts)

    async def resume(
        self,
        operation_id: str,
        *,
        options: RunOptions | None = None,
        budget: ExecutionBudget | None = None,
    ) -> OperationOutcome:
        opts = options or RunOptions()
        state = await self._operation_entrypoint_service.load_for_resume(
            operation_id=operation_id,
            options=opts,
            merge_runtime_flags=self._merge_runtime_flags,
            budget_override=budget,
        )
        return await self._drive_state(state, opts)

    async def recover(
        self,
        operation_id: str,
        *,
        options: RunOptions | None = None,
        budget: ExecutionBudget | None = None,
    ) -> OperationOutcome:
        opts = options or RunOptions()
        state = await self._operation_entrypoint_service.load_for_recover(
            operation_id=operation_id,
            options=opts,
            merge_runtime_flags=self._merge_runtime_flags,
            reconcile_orphaned_recoverable_background_runs=(
                self._operation_runtime_reconciliation_service.reconcile_orphaned_recoverable_background_runs
            ),
            budget_override=budget,
        )
        return await self._drive_state(state, opts)

    async def tick(
        self,
        operation_id: str,
        *,
        options: RunOptions | None = None,
    ) -> OperationOutcome:
        opts = self._operation_entrypoint_service.build_tick_options(options)
        return await self.resume(operation_id, options=opts)

    async def cancel(
        self,
        operation_id: str,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        reason: str | None = None,
    ) -> OperationOutcome:
        outcome = await self._operation_cancellation_service.cancel(
            operation_id=operation_id,
            session_id=session_id,
            run_id=run_id,
            reason=reason,
            find_background_run=self._loaded_operation.find_background_run,
            find_session_record=self._loaded_operation.find_session_record,
            find_latest_result=self._loaded_operation.find_latest_result,
            emit=self._event_relay.emit,
        )
        return outcome

    async def answer_question(self, operation_id: str, question: str) -> str:
        state = await self._store.load_operation(operation_id)
        if state is None:
            raise RuntimeError(f"Operation {operation_id!r} was not found.")
        return await self._brain.answer_question(state, question)

    async def _drive_state(
        self,
        state: OperationState,
        options: RunOptions,
    ) -> OperationOutcome:
        return await self._operation_drive_service.drive(state, options)

    def _merge_runtime_flags(
        self,
        budget: ExecutionBudget,
        options: RunOptions,
    ) -> ExecutionBudget:
        metadata = {
            "run_mode": options.run_mode.value,
            "background_runtime_mode": options.background_runtime_mode.value,
        }
        # Keep legacy run-mode glue on the state through runtime_hints only.
        _ = metadata
        return budget
