from __future__ import annotations

from agent_operator.application.attached_session_registry import AttachedSessionRuntimeRegistry
from agent_operator.application.loaded_operation import LoadedOperation
from agent_operator.domain import (
    BackgroundRunStatus,
    BackgroundRuntimeMode,
    FocusKind,
    FocusMode,
    OperationState,
    OperationStatus,
    RunOptions,
    SessionRecord,
    SessionRecordStatus,
)


class OperationRuntimeContext:
    """Provide runtime capability projection and scheduler gating for one operation."""

    def __init__(
        self,
        *,
        loaded_operation: LoadedOperation,
        attached_session_registry: AttachedSessionRuntimeRegistry,
    ) -> None:
        self._loaded_operation = loaded_operation
        self._attached_session_registry = attached_session_registry

    async def refresh_available_agent_descriptors(self, state: OperationState) -> None:
        allowed = state.policy.allowed_agents or self._attached_session_registry.keys()
        descriptors: list[dict[str, object]] = []
        for adapter_key in allowed:
            if not self._attached_session_registry.has(adapter_key):
                continue
            descriptor = await self._attached_session_registry.describe(adapter_key)
            descriptors.append(
                {
                    "key": descriptor.key,
                    "display_name": descriptor.display_name,
                    "capabilities": [
                        item.model_dump(mode="json") for item in descriptor.capabilities
                    ],
                    "supports_follow_up": descriptor.supports_follow_up,
                    "supports_cancellation": descriptor.supports_cancellation,
                    "metadata": descriptor.metadata,
                }
            )
        state.runtime_hints.metadata["available_agent_descriptors"] = descriptors

    def is_blocked_on_background_wait(self, state: OperationState) -> bool:
        focus = state.current_focus
        if focus is None or focus.mode is not FocusMode.BLOCKING:
            return False
        if focus.kind is not FocusKind.SESSION:
            return False
        record = self._loaded_operation.find_session_record(state, focus.target_id)
        if record is None or record.current_execution_id is None:
            return False
        run = self._loaded_operation.find_background_run(state, record.current_execution_id)
        if run is None:
            return False
        return run.status in {BackgroundRunStatus.PENDING, BackgroundRunStatus.RUNNING}

    def is_waiting_on_attached_turn(self, state: OperationState) -> bool:
        if state.status is not OperationStatus.RUNNING:
            return False
        if self.is_blocked_on_background_wait(state):
            return False
        if not state.iterations:
            return False
        latest = state.iterations[-1]
        if latest.session is None or latest.result is not None:
            return False
        record = self._loaded_operation.find_session_record(state, latest.session.session_id)
        if record is None or record.status is not SessionRecordStatus.RUNNING:
            return False
        if record.current_execution_id is not None:
            run = self._loaded_operation.find_background_run(state, record.current_execution_id)
            if run is None:
                return False
            return run.status in {BackgroundRunStatus.PENDING, BackgroundRunStatus.RUNNING}
        return True

    def should_use_background_runtime(self, options: RunOptions) -> bool:
        return options.background_runtime_mode is not BackgroundRuntimeMode.INLINE

    def uses_resumable_wakeup_runtime(self, options: RunOptions) -> bool:
        return options.background_runtime_mode is BackgroundRuntimeMode.RESUMABLE_WAKEUP

    def should_retry_from_recoverable_block(self, state: OperationState) -> bool:
        return self.resolve_recoverable_session_for_retry(state) is not None

    def resolve_recoverable_session_for_retry(self, state: OperationState) -> SessionRecord | None:
        recoverables = [
            session
            for session in state.sessions
            if (
                not session.handle.one_shot
                and session.status is SessionRecordStatus.WAITING
                and session.waiting_reason is not None
                and "Recovering agent connection after ACP disconnect." in session.waiting_reason
            )
        ]
        if not recoverables:
            return None
        if state.current_focus is not None and state.current_focus.kind is FocusKind.SESSION:
            focused = next(
                (
                    session
                    for session in recoverables
                    if session.session_id == state.current_focus.target_id
                ),
                None,
            )
            if focused is not None:
                return focused
        if len(recoverables) == 1:
            return recoverables[0]
        latest = [session for session in recoverables if session.latest_iteration is not None]
        if latest:
            latest.sort(key=lambda session: session.latest_iteration or 0, reverse=True)
            return latest[0]
        return recoverables[0]
