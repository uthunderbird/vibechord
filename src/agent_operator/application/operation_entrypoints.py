from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from agent_operator.application.event_sourcing.event_sourced_birth import (
    EventSourcedOperationBirthService,
)
from agent_operator.application.event_sourcing.event_sourced_replay import EventSourcedReplayService
from agent_operator.application.operation_lifecycle_entrypoints import (
    OperationLifecycleEntrypointGuard,
)
from agent_operator.application.queries.operation_state_views import OperationStateViewService
from agent_operator.domain import (
    AgentSessionHandle,
    AttentionStatus,
    ExecutionBudget,
    OperationGoal,
    OperationPolicy,
    OperationState,
    OperationStatus,
    RunOptions,
    RuntimeHints,
)
from agent_operator.protocols import OperationStore


class StateAttacher(Protocol):
    """Callback used to attach initial sessions to a newly created operation state."""

    def __call__(
        self, state: OperationState, attached_sessions: list[AgentSessionHandle]
    ) -> None: ...


class BudgetMerger(Protocol):
    """Callback used to merge runtime flags into execution budget."""

    def __call__(self, budget: ExecutionBudget, options: RunOptions) -> ExecutionBudget: ...


class RecoverReconciler(Protocol):
    """Callback used to reconcile recoverable orphaned background runs."""

    async def __call__(self, state: OperationState) -> None: ...


class OperationEntrypointService:
    """Prepare and load operation state for public OperatorService entrypoints.

    This service owns entrypoint-side state preparation for `run`, `resume`, `recover`, and `tick`
    so that `OperatorService` can remain a thin facade over orchestration and delegation.

    Examples:
        >>> service = OperationEntrypointService(store=None)  # doctest: +SKIP
    """

    def __init__(
        self,
        *,
        store: OperationStore,
        event_sourced_operation_birth_service: EventSourcedOperationBirthService | None = None,
        event_sourced_replay_service: EventSourcedReplayService | None = None,
        operation_state_view_service: OperationStateViewService | None = None,
        lifecycle_guard: OperationLifecycleEntrypointGuard | None = None,
    ) -> None:
        self._store = store
        self._event_sourced_operation_birth_service = event_sourced_operation_birth_service
        self._event_sourced_replay_service = event_sourced_replay_service
        self._operation_state_view_service = (
            operation_state_view_service or OperationStateViewService()
        )
        self._lifecycle_guard = lifecycle_guard or OperationLifecycleEntrypointGuard(
            store=store,
            replay_service=event_sourced_replay_service,
        )

    async def prepare_run(
        self,
        *,
        goal: OperationGoal,
        policy: OperationPolicy | None,
        budget: ExecutionBudget | None,
        runtime_hints: RuntimeHints | None,
        options: RunOptions,
        operation_id: str | None,
        attached_sessions: list[AgentSessionHandle] | None,
        merge_runtime_flags: BudgetMerger,
        attach_initial_sessions: StateAttacher,
    ) -> OperationState:
        """Build the initial operation state for `run()`.

        Args:
            goal: Operation goal payload.
            policy: Optional durable operation policy.
            budget: Optional execution budget.
            runtime_hints: Optional runtime hints.
            options: Active runtime options.
            operation_id: Optional caller-provided operation identifier.
            attached_sessions: Optional attached sessions.
            merge_runtime_flags: Constraint merge callback owned by the facade.
            attach_initial_sessions: Session attach callback owned by the facade.

        Returns:
            Prepared operation state ready for shell-side emission and drive.
        """
        if operation_id is not None:
            await self._lifecycle_guard.ensure_new_operation_id(operation_id)
        state = OperationState(
            operation_id=operation_id or str(uuid4()),
            goal=goal,
            policy=policy or OperationPolicy(),
            execution_budget=merge_runtime_flags(budget or ExecutionBudget(), options),
            runtime_hints=runtime_hints or RuntimeHints(),
        )
        if state.run_started_at is None:
            state.run_started_at = datetime.now(UTC)
        self._persist_runtime_mode_metadata(state, options)
        if attached_sessions:
            attach_initial_sessions(state, attached_sessions)
        if self._event_sourced_operation_birth_service is not None:
            await self._event_sourced_operation_birth_service.birth(state)
        if self._event_sourced_replay_service is not None:
            return await self._load_event_sourced(state.operation_id, fallback_state=state)
        return state

    async def load_for_resume(
        self,
        *,
        operation_id: str,
        options: RunOptions,
        merge_runtime_flags: BudgetMerger,
        budget_override: ExecutionBudget | None = None,
    ) -> OperationState:
        """Load and prepare state for `resume()`.

        Args:
            operation_id: Target operation identifier.
            options: Active runtime options.
            merge_runtime_flags: Constraint merge callback owned by the facade.

        Returns:
            Loaded operation state with merged runtime flags.
        """
        state = await self._load_resume_ready_state(operation_id)
        state.execution_budget = merge_runtime_flags(
            budget_override or state.execution_budget,
            options,
        )
        self._persist_runtime_mode_metadata(state, options)
        return state

    async def load_for_recover(
        self,
        *,
        operation_id: str,
        options: RunOptions,
        merge_runtime_flags: BudgetMerger,
        reconcile_orphaned_recoverable_background_runs: RecoverReconciler,
        budget_override: ExecutionBudget | None = None,
    ) -> OperationState:
        """Load and prepare state for `recover()`.

        Args:
            operation_id: Target operation identifier.
            options: Active runtime options.
            merge_runtime_flags: Constraint merge callback owned by the facade.
            reconcile_orphaned_recoverable_background_runs: Recovery reconciliation callback.

        Returns:
            Loaded operation state after recovery reconciliation preparation.
        """
        state = await self._load_resume_ready_state(operation_id)
        state.execution_budget = merge_runtime_flags(
            budget_override or state.execution_budget,
            options,
        )
        self._persist_runtime_mode_metadata(state, options)
        await reconcile_orphaned_recoverable_background_runs(state)
        return state

    def build_tick_options(self, options: RunOptions | None = None) -> RunOptions:
        """Build single-cycle options for `tick()`.

        Args:
            options: Optional caller-provided run options.

        Returns:
            Options constrained to one cycle.
        """
        opts = options or RunOptions()
        return opts.model_copy(update={"max_cycles": 1})

    async def load_canonical_state(self, operation_id: str) -> OperationState:
        """Load canonical state for non-mutating or terminalization entrypoints.

        Args:
            operation_id: Target canonical operation identifier.

        Returns:
            Canonical operation state, using event replay first when available.
        """
        await self._lifecycle_guard.ensure_existing_operation_id(operation_id)
        replay = await self._load_event_sourced_replay(operation_id)
        if replay is not None:
            return self._operation_state_view_service.from_checkpoint(replay.checkpoint)
        fallback_state = await self._load_snapshot_fallback(operation_id)
        if fallback_state is None:
            raise RuntimeError(f"Operation {operation_id!r} was not found.")
        return fallback_state

    async def _load_resume_ready_state(self, operation_id: str) -> OperationState:
        """Load canonical state for continue-only entrypoints with snapshot fallback.

        For event-sourced-only operations, canonical replay is the only authoritative source.
        For mixed-mode operations that still persist extra ephemeral fields in snapshot state,
        replay remains the authority while the snapshot supplies fallback-only runtime details.
        """

        await self._lifecycle_guard.ensure_existing_operation_id(operation_id)
        replay = await self._load_event_sourced_replay(operation_id)
        fallback_state = await self._load_snapshot_fallback(operation_id)
        if replay is None:
            if fallback_state is None:
                raise RuntimeError(f"Operation {operation_id!r} was not found.")
            return fallback_state
        replay_state = self._operation_state_view_service.from_checkpoint(replay.checkpoint)
        if fallback_state is None:
            return replay_state
        return self._merge_replay_with_snapshot(
            replay_state,
            fallback_state,
            checkpoint_has_tasks=bool(replay.checkpoint.tasks),
        )

    async def _load_event_sourced(
        self,
        operation_id: str,
        *,
        fallback_state: OperationState,
    ) -> OperationState:
        if self._event_sourced_replay_service is None:
            return fallback_state
        replay = await self._load_event_sourced_replay(operation_id)
        if replay is None:
            return fallback_state
        replay_state = self._operation_state_view_service.from_checkpoint(replay.checkpoint)
        return self._merge_replay_with_snapshot(
            replay_state,
            fallback_state,
            checkpoint_has_tasks=bool(replay.checkpoint.tasks),
        )

    async def _load_event_sourced_replay(self, operation_id: str):
        if self._event_sourced_replay_service is None:
            return None
        replay_state = await self._event_sourced_replay_service.load(operation_id)
        if (
            getattr(replay_state, "stored_checkpoint", None) is None
            and getattr(replay_state, "last_applied_sequence", 0) == 0
            and not getattr(replay_state, "suffix_events", [])
        ):
            return None
        return replay_state

    async def _load_snapshot_fallback(self, operation_id: str) -> OperationState | None:
        """Load snapshot-era fallback state for mixed-mode continuity only."""

        return await self._store.load_operation(operation_id)

    def _merge_replay_with_snapshot(
        self,
        state: OperationState,
        fallback_state: OperationState,
        *,
        checkpoint_has_tasks: bool,
    ) -> OperationState:
        state.policy = fallback_state.policy.model_copy(deep=True)
        state.execution_budget = fallback_state.execution_budget.model_copy(deep=True)
        state.runtime_hints = fallback_state.runtime_hints.model_copy(deep=True)
        state.goal = fallback_state.goal.model_copy(deep=True)
        state.run_started_at = fallback_state.run_started_at
        state.iterations = [item.model_copy(deep=True) for item in fallback_state.iterations]
        state.features = [item.model_copy(deep=True) for item in fallback_state.features]
        state.memory_entries = [
            item.model_copy(deep=True) for item in fallback_state.memory_entries
        ]
        state.artifacts = [item.model_copy(deep=True) for item in fallback_state.artifacts]
        state.operation_brief = (
            fallback_state.operation_brief.model_copy(deep=True)
            if fallback_state.operation_brief is not None
            else None
        )
        state.iteration_briefs = [
            item.model_copy(deep=True) for item in fallback_state.iteration_briefs
        ]
        state.agent_turn_briefs = [
            item.model_copy(deep=True) for item in fallback_state.agent_turn_briefs
        ]
        state.pending_wakeups = [
            item.model_copy(deep=True) for item in fallback_state.pending_wakeups
        ]
        existing_attention_ids = {
            attention.attention_id for attention in state.attention_requests
        }
        for attention in fallback_state.attention_requests:
            if attention.attention_id in existing_attention_ids:
                continue
            state.attention_requests.append(attention.model_copy(deep=True))
        state.pending_replan_command_ids = list(fallback_state.pending_replan_command_ids)
        state.pending_attention_resolution_ids = [
            attention.attention_id
            for attention in state.attention_requests
            if attention.status is AttentionStatus.ANSWERED
        ]
        if (
            state.current_focus is None
            and fallback_state.current_focus is not None
            and state.status
            not in {
                OperationStatus.COMPLETED,
                OperationStatus.FAILED,
                OperationStatus.CANCELLED,
            }
        ):
            state.current_focus = fallback_state.current_focus.model_copy(deep=True)
        if not checkpoint_has_tasks and fallback_state.tasks:
            state.tasks = [item.model_copy(deep=True) for item in fallback_state.tasks]
            if state.objective is not None and fallback_state.objective is not None:
                state.objective.root_task_id = fallback_state.objective.root_task_id
        if not state.sessions and fallback_state.sessions:
            state.sessions = [item.model_copy(deep=True) for item in fallback_state.sessions]
        return state

    def _persist_runtime_mode_metadata(
        self,
        state: OperationState,
        options: RunOptions,
    ) -> None:
        metadata = state.runtime_hints.metadata
        continuity_run_mode = self._resolve_persisted_mode(
            metadata.get("continuity_run_mode"),
            fallback=metadata.get("run_mode"),
            default=options.run_mode.value,
        )
        continuity_background_runtime_mode = self._resolve_persisted_mode(
            metadata.get("continuity_background_runtime_mode"),
            fallback=metadata.get("background_runtime_mode"),
            default=options.background_runtime_mode.value,
        )
        metadata["run_mode"] = continuity_run_mode
        metadata["background_runtime_mode"] = continuity_background_runtime_mode
        metadata["continuity_run_mode"] = continuity_run_mode
        metadata["continuity_background_runtime_mode"] = continuity_background_runtime_mode
        metadata["invocation_run_mode"] = options.run_mode.value
        metadata["invocation_background_runtime_mode"] = options.background_runtime_mode.value

    def _resolve_persisted_mode(
        self,
        value: object,
        *,
        fallback: object,
        default: str,
    ) -> str:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(fallback, str) and fallback.strip():
            return fallback.strip()
        return default
