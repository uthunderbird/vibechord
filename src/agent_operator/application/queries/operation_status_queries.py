from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from agent_operator.application.queries.operation_projections import OperationProjectionService
from agent_operator.application.queries.operation_state_views import OperationStateViewService
from agent_operator.domain import AttentionStatus, OperationOutcome, OperationState, SchedulerState
from agent_operator.protocols import OperationStore


class TraceStoreLike(Protocol):
    async def load_brief_bundle(self, operation_id: str): ...


class BackgroundInspectionStoreLike(Protocol):
    async def list_runs(self, operation_id: str) -> list: ...


class WakeupInspectionStoreLike(Protocol):
    def read_all(self, operation_id: str | None = None) -> list[dict[str, object]]: ...


class ReplayServiceLike(Protocol):
    async def load(self, operation_id: str): ...


@dataclass(slots=True)
class OperationRuntimeOverlay:
    """Runtime inspection facts attached to a canonical operation read.

    Examples:
        ```python
        overlay = OperationRuntimeOverlay(runtime_alert="pending wakeup")
        assert overlay.authorities["wakeup_inspection"] == "runtime_overlay"
        ```
    """

    wakeups: list[dict[str, object]] = field(default_factory=list)
    background_runs: list[dict[str, object]] = field(default_factory=list)
    trace_brief: object | None = None
    runtime_alert: str | None = None
    authorities: dict[str, str] = field(
        default_factory=lambda: {
            "wakeup_inspection": "runtime_overlay",
            "background_inspection": "runtime_overlay",
            "trace_brief": "trace_overlay",
        }
    )
    staleness: dict[str, str] = field(
        default_factory=lambda: {
            "wakeup_inspection": "read_time",
            "background_inspection": "read_time",
            "trace_brief": "persisted_trace_snapshot",
        }
    )


@dataclass(slots=True)
class OperationReadPayload:
    """Typed read payload shared by status-like surfaces.

    Examples:
        ```python
        payload = OperationReadPayload(
            operation_id="op-1",
            operation=None,
            outcome=None,
            source="event_sourced",
        )
        assert payload.operation_id == "op-1"
        ```
    """

    operation_id: str
    operation: OperationState | None
    outcome: OperationOutcome | None
    source: str
    overlay: OperationRuntimeOverlay = field(default_factory=OperationRuntimeOverlay)
    action_hint: str | None = None
    live_snapshot: dict[str, object] = field(default_factory=dict)
    durable_truth: dict[str, object] | None = None


@dataclass(slots=True)
class OperationStatusQueryService:
    store: OperationStore
    projection_service: OperationProjectionService
    trace_store: TraceStoreLike
    background_inspection_store: BackgroundInspectionStoreLike
    wakeup_inspection_store: WakeupInspectionStoreLike | None
    build_runtime_alert: Callable[..., str | None]
    render_status_brief: Callable[[OperationState], str]
    render_inspect_summary: Callable[..., str]
    render_status_summary: Callable[..., str]
    replay_service: ReplayServiceLike | None = None
    state_view_service: OperationStateViewService = field(
        default_factory=OperationStateViewService
    )

    def _background_run_payload(self, run) -> dict[str, object]:
        return {
            "execution_id": run.execution_id,
            "run_id": run.run_id,
            "operation_id": run.operation_id,
            "adapter_key": run.adapter_key,
            "session_id": run.session_id,
            "task_id": run.task_id,
            "iteration": run.iteration,
            "mode": run.mode.value,
            "launch_kind": run.launch_kind.value,
            "observed_state": run.observed_state.value,
            "status": run.status.value,
            "waiting_reason": run.waiting_reason,
            "handle_ref": (
                {
                    "kind": run.handle_ref.kind,
                    "value": run.handle_ref.value,
                    "metadata": dict(run.handle_ref.metadata),
                }
                if run.handle_ref is not None
                else None
            ),
            "progress": (
                {
                    "state": run.progress.state.value,
                    "message": run.progress.message,
                    "updated_at": run.progress.updated_at.isoformat(),
                    "partial_output": run.progress.partial_output,
                    "last_event_at": (
                        run.progress.last_event_at.isoformat()
                        if run.progress.last_event_at is not None
                        else None
                    ),
                }
                if run.progress is not None
                else None
            ),
            "result_ref": run.result_ref,
            "error_ref": run.error_ref,
            "pid": run.pid,
            "started_at": run.started_at.isoformat(),
            "last_heartbeat_at": (
                run.last_heartbeat_at.isoformat() if run.last_heartbeat_at is not None else None
            ),
            "completed_at": (
                run.completed_at.isoformat() if run.completed_at is not None else None
            ),
            "raw_ref": run.raw_ref,
        }

    async def build_read_payload(self, operation_id: str) -> OperationReadPayload:
        """Build the shared canonical read payload for one operation.

        Args:
            operation_id: Canonical operation identifier.

        Returns:
            Typed read payload with canonical state plus runtime overlays.

        Raises:
            RuntimeError: If neither canonical state nor terminal outcome exists.
        """

        operation = await self._load_event_sourced_operation(operation_id)
        source = "event_sourced" if operation is not None else "legacy_snapshot"
        if operation is None:
            operation = await self._load_snapshot_fallback(operation_id)
        outcome = await self.store.load_outcome(operation_id)
        if operation is None and outcome is None:
            raise RuntimeError(f"Operation {operation_id!r} was not found.")
        if operation is None:
            return OperationReadPayload(
                operation_id=operation_id,
                operation=None,
                outcome=outcome,
                source="outcome_only",
                live_snapshot=self.build_live_snapshot(operation_id, None, outcome),
            )
        wakeups = (
            self.wakeup_inspection_store.read_all(operation_id)
            if self.wakeup_inspection_store is not None
            else []
        )
        runs = await self.background_inspection_store.list_runs(operation_id)
        background_runs = [self._background_run_payload(item) for item in runs]
        brief_bundle = await self.trace_store.load_brief_bundle(operation_id)
        runtime_alert = self.build_runtime_alert(
            status=operation.status,
            wakeups=wakeups,
            background_runs=background_runs,
        )
        action_hint = self.build_status_action_hint(operation)
        return OperationReadPayload(
            operation_id=operation_id,
            operation=operation,
            outcome=outcome,
            source=source,
            overlay=OperationRuntimeOverlay(
                wakeups=wakeups,
                background_runs=background_runs,
                trace_brief=brief_bundle,
                runtime_alert=runtime_alert,
            ),
            action_hint=action_hint,
            live_snapshot=self.build_live_snapshot(
                operation_id,
                operation,
                outcome,
                runtime_alert=runtime_alert,
            ),
            durable_truth=self.projection_service.build_durable_truth_payload(
                operation,
                include_inactive_memory=True,
            ),
        )

    async def build_status_payload(
        self,
        operation_id: str,
    ) -> tuple[OperationState | None, OperationOutcome | None, object | None, str | None]:
        payload = await self.build_read_payload(operation_id)
        return (
            payload.operation,
            payload.outcome,
            payload.overlay.trace_brief,
            payload.overlay.runtime_alert,
        )

    async def _load_event_sourced_operation(self, operation_id: str) -> OperationState | None:
        """Load v2 operations from event-sourced truth when no legacy run snapshot exists."""
        if self.replay_service is None:
            return None
        replay_state = await self.replay_service.load(operation_id)
        if (
            getattr(replay_state, "stored_checkpoint", None) is None
            and getattr(replay_state, "last_applied_sequence", 0) == 0
            and not getattr(replay_state, "suffix_events", [])
        ):
            return None
        checkpoint = getattr(replay_state, "checkpoint", None)
        if checkpoint is None:
            return None
        return self.state_view_service.from_checkpoint(checkpoint)

    async def _load_snapshot_fallback(self, operation_id: str) -> OperationState | None:
        """Load snapshot-era state only as an explicit status-query fallback."""

        return await self.store.load_operation(operation_id)

    async def render_status_output(
        self,
        operation_id: str,
        *,
        json_mode: bool,
        brief: bool,
    ) -> str:
        payload = await self.build_read_payload(operation_id)
        operation = payload.operation
        outcome = payload.outcome
        if operation is None:
            assert outcome is not None
            if json_mode:
                return json.dumps(
                    {
                        "operation_id": operation_id,
                        "status": outcome.status.value,
                        "summary": outcome.summary,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            return f"{operation_id} {outcome.status.value.upper()} {outcome.summary}"

        if json_mode:
            output = {
                "operation_id": operation_id,
                "status": operation.status.value,
                "source": payload.source,
                "summary": payload.live_snapshot,
                "action_hint": payload.action_hint,
                "durable_truth": payload.durable_truth,
                "runtime_overlay": {
                    "authorities": payload.overlay.authorities,
                    "staleness": payload.overlay.staleness,
                    "runtime_alert": payload.overlay.runtime_alert,
                },
            }
            return json.dumps(output, indent=2, ensure_ascii=False)
        if brief:
            return self.render_status_brief(operation)
        return self.render_status_summary(
            operation,
            payload.overlay.trace_brief,
            runtime_alert=payload.overlay.runtime_alert,
            action_hint=payload.action_hint,
        )

    def build_status_action_hint(self, operation: OperationState) -> str | None:
        open_attention = [
            attention
            for attention in operation.attention_requests
            if attention.status is AttentionStatus.OPEN
        ]
        if open_attention:
            return (
                f"operator answer {operation.operation_id} "
                f"{open_attention[0].attention_id} --text '...'"
            )
        if (
            operation.active_session_record is not None
            and operation.scheduler_state is not SchedulerState.DRAINING
        ):
            return f"operator interrupt {operation.operation_id}"
        if operation.scheduler_state in {SchedulerState.PAUSED, SchedulerState.PAUSE_REQUESTED}:
            return f"operator unpause {operation.operation_id}"
        return None

    def build_live_snapshot(
        self,
        operation_id: str,
        operation: OperationState | None,
        outcome: OperationOutcome | None,
        *,
        runtime_alert: str | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {"operation_id": operation_id}
        if operation is None:
            payload["status"] = outcome.status.value if outcome is not None else "unknown"
            payload["summary"] = outcome.summary if outcome is not None else "Operation not found."
            return payload
        payload.update(
            self.projection_service.build_live_snapshot(
                operation,
                None,
                runtime_alert=runtime_alert,
            )
        )
        action_hint = self.build_status_action_hint(operation)
        if action_hint is not None:
            payload["action_hint"] = action_hint
        payload["involvement_level"] = operation.involvement_level.value
        payload["updated_at"] = operation.updated_at.isoformat()
        active_session = operation.active_session_record
        if active_session is None:
            payload.pop("active_session_execution_profile", None)
            payload.pop("session_execution_profile_known", None)
        if active_session is not None:
            payload["session_id"] = active_session.session_id
            payload["adapter_key"] = active_session.adapter_key
            payload["session_status"] = active_session.status.value
            active_session_execution_profile = payload.get("active_session_execution_profile")
            if active_session_execution_profile is not None:
                payload["session_execution_profile_known"] = bool(
                    active_session_execution_profile.get("known")
                )
            if active_session.waiting_reason and payload.get("runtime_alert") is None:
                payload["waiting_reason"] = active_session.waiting_reason
        if operation.attention_requests:
            open_attention = [
                item for item in operation.attention_requests if item.status is AttentionStatus.OPEN
            ]
            if open_attention:
                payload["open_attention_count"] = len(open_attention)
                payload["attention_title"] = open_attention[0].title
                payload["attention_brief"] = (
                    f"[{open_attention[0].attention_type.value}] {open_attention[0].title}"
                )
        summary = outcome.summary if outcome is not None else operation.final_summary
        if summary:
            payload["summary"] = summary
        return payload
