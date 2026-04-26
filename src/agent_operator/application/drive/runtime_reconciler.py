"""RuntimeReconciler — reconciles runtime-side inputs with canonical state (ADR 0195).

Contract: async, reads from inboxes and supervisor, never mutates aggregate directly.
Runtime observations are returned as OperationDomainEventDraft instances. Control
commands are applied through the event-sourced command application boundary.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agent_operator.application.drive.agent_run_supervisor import AgentRunSupervisorV2
from agent_operator.application.drive.process_manager_context import ProcessManagerContext
from agent_operator.application.event_sourcing.event_sourced_commands import (
    EventSourcedCommandApplicationService,
)
from agent_operator.domain.aggregate import OperationAggregate
from agent_operator.domain.enums import BackgroundRunStatus, CommandStatus
from agent_operator.domain.event_sourcing import OperationDomainEventDraft
from agent_operator.protocols import AgentRunSupervisor, OperationCommandInbox, WakeupInbox

type RuntimeSupervisor = AgentRunSupervisor | AgentRunSupervisorV2


class RuntimeReconciler:
    """Drain inboxes and poll background runs, returning domain events.

    Replaces OperationDriveRuntimeService + OperationRuntimeReconciliationService
    with a clean event-returning interface (ADR 0195). The drive loop applies the
    returned events to the aggregate before calling PolicyExecutor.
    """

    def __init__(
        self,
        *,
        wakeup_inbox: WakeupInbox,
        command_inbox: OperationCommandInbox,
        event_sourced_command_service: EventSourcedCommandApplicationService | None = None,
        supervisor: RuntimeSupervisor | None = None,
        stale_run_threshold: timedelta = timedelta(minutes=5),
    ) -> None:
        self._wakeup_inbox = wakeup_inbox
        self._command_inbox = command_inbox
        self._event_sourced_command_service = event_sourced_command_service
        self._supervisor = supervisor
        self._stale_run_threshold = stale_run_threshold

    async def drain_wakeups(
        self,
        agg: OperationAggregate,
        ctx: ProcessManagerContext,
    ) -> list[OperationDomainEventDraft]:
        """Claim pending wakeup events and translate them into domain events."""
        await self._wakeup_inbox.requeue_stale_claims()
        claimed = await self._wakeup_inbox.claim(agg.operation_id)
        if not claimed:
            return []

        events: list[OperationDomainEventDraft] = []
        ack_ids: list[str] = []
        release_ids: list[str] = []
        now = datetime.now(UTC)

        for event in claimed:
            run_id = event.payload.get("run_id") if isinstance(event.payload, dict) else None
            if (
                not isinstance(run_id, str)
                or self._supervisor is None
                or isinstance(self._supervisor, AgentRunSupervisorV2)
            ):
                release_ids.append(event.event_id)
                continue

            run = await self._supervisor.poll_background_turn(run_id)
            if run is None:
                release_ids.append(event.event_id)
                continue

            # Translate wakeup into execution observed state event
            new_observed_state: str | None = None
            if event.event_type.endswith("completed"):
                new_observed_state = "completed"
            elif event.event_type.endswith("failed"):
                new_observed_state = "failed"
            elif event.event_type.endswith("cancelled"):
                new_observed_state = "cancelled"

            if new_observed_state is not None:
                events.append(
                    OperationDomainEventDraft(
                        event_type="execution.observed_state.changed",
                        payload={
                            "execution_id": run_id,
                            "observed_state": new_observed_state,
                            "completed_at": now.isoformat(),
                            "updated_at": now.isoformat(),
                        },
                    )
                )
                if event.session_id:
                    events.append(
                        OperationDomainEventDraft(
                            event_type="execution.session_linked",
                            payload={
                                "execution_id": run_id,
                                "session_id": event.session_id,
                            },
                        )
                    )
                ack_ids.append(event.event_id)
            else:
                release_ids.append(event.event_id)

        if ack_ids:
            await self._wakeup_inbox.ack(ack_ids)
        if release_ids:
            await self._wakeup_inbox.release(release_ids)

        return events

    async def drain_commands(
        self,
        agg: OperationAggregate,
        ctx: ProcessManagerContext,
    ) -> list[OperationDomainEventDraft]:
        """Apply pending commands through the canonical event-sourced boundary."""
        pending = await self._command_inbox.list_pending(agg.operation_id)
        if not pending:
            return []

        now = datetime.now(UTC)
        if self._event_sourced_command_service is None:
            raise RuntimeError(
                "RuntimeReconciler command draining requires "
                "EventSourcedCommandApplicationService."
            )

        for command in pending:
            command_id = getattr(command, "command_id", None) or str(id(command))

            if command_id in agg.processed_command_ids:
                await self._command_inbox.update_status(
                    command_id,
                    CommandStatus.APPLIED,
                    applied_at=now,
                )
                continue

            result = await self._event_sourced_command_service.apply(command)
            if result.applied:
                await self._command_inbox.update_status(
                    command_id,
                    CommandStatus.APPLIED,
                    applied_at=now,
                )
            else:
                await self._command_inbox.update_status(
                    command_id,
                    CommandStatus.REJECTED,
                    rejection_reason=result.rejection_reason,
                    applied_at=now,
                )
            if result.stored_events:
                ctx.canonical_replay_advanced = True

        return []

    async def poll_background_runs(
        self,
        agg: OperationAggregate,
        ctx: ProcessManagerContext,
    ) -> list[OperationDomainEventDraft]:
        """Poll supervisor for background run status changes and detect stale runs."""
        if self._supervisor is None or isinstance(self._supervisor, AgentRunSupervisorV2):
            return []

        events: list[OperationDomainEventDraft] = []
        now = datetime.now(UTC)

        for execution in agg.executions:
            if execution.observed_state.value in {"completed", "failed", "cancelled", "lost"}:
                continue

            run = await self._supervisor.poll_background_turn(execution.execution_id)
            if run is None:
                continue

            new_status = run.status
            if new_status in {
                BackgroundRunStatus.COMPLETED,
                BackgroundRunStatus.FAILED,
                BackgroundRunStatus.CANCELLED,
                BackgroundRunStatus.DISCONNECTED,
            }:
                observed = "completed" if new_status is BackgroundRunStatus.COMPLETED else (
                    "failed" if new_status is BackgroundRunStatus.FAILED else "cancelled"
                )
                events.append(
                    OperationDomainEventDraft(
                        event_type="execution.observed_state.changed",
                        payload={
                            "execution_id": execution.execution_id,
                            "observed_state": observed,
                            "completed_at": now.isoformat(),
                            "updated_at": now.isoformat(),
                        },
                    )
                )
                continue

            # Stale detection
            heartbeat = run.last_heartbeat_at
            if (
                new_status in {BackgroundRunStatus.PENDING, BackgroundRunStatus.RUNNING}
                and heartbeat is not None
                and (now - heartbeat) > self._stale_run_threshold
            ):
                events.append(
                    OperationDomainEventDraft(
                        event_type="execution.observed_state.changed",
                        payload={
                            "execution_id": execution.execution_id,
                            "observed_state": "failed",
                            "error": "background_run_stale",
                            "completed_at": now.isoformat(),
                            "updated_at": now.isoformat(),
                        },
                    )
                )

        return events

    async def detect_orphaned_sessions(
        self,
        agg: OperationAggregate,
        ctx: ProcessManagerContext,
    ) -> list[OperationDomainEventDraft]:
        """Detect sessions in RUNNING/PENDING with no supervisor record (ADR 0201).

        Uses AgentRunSupervisorV2.get_all_tracked_session_ids() when available for
        precise orphan detection: a session is orphaned only if it was never registered
        in this process lifetime (not merely completed). Falls back to poll_background_turn()
        for v1 AgentRunSupervisor.
        """
        if ctx.orphan_check_completed:
            return []

        ctx.orphan_check_completed = True

        if self._supervisor is None:
            return []

        events: list[OperationDomainEventDraft] = []
        now = datetime.now(UTC)

        # Prefer v2 supervisor registry — distinguishes "never seen" from "completed"
        if isinstance(self._supervisor, AgentRunSupervisorV2):
            known_ids = self._supervisor.get_all_tracked_session_ids(agg.operation_id)
            for session in agg.sessions:
                if session.status.value not in {"running", "pending"}:
                    continue
                if session.session_id in known_ids:
                    continue
                # Never registered in this process — orphaned after restart
                events.append(
                    OperationDomainEventDraft(
                        event_type="session.crashed",
                        payload={
                            "session_id": session.session_id,
                            "reason": "ORPHANED_AFTER_RESTART",
                            "crashed_at": now.isoformat(),
                        },
                    )
                )
            return events

        # v1 fallback: poll supervisor for each active execution
        active_execution_ids = {
            s.current_execution_id
            for s in agg.sessions
            if s.current_execution_id is not None
        }
        for execution in agg.executions:
            if execution.observed_state.value not in {"running", "pending"}:
                continue
            if execution.execution_id not in active_execution_ids:
                continue
            run = await self._supervisor.poll_background_turn(execution.execution_id)
            if run is None:
                events.append(
                    OperationDomainEventDraft(
                        event_type="execution.observed_state.changed",
                        payload={
                            "execution_id": execution.execution_id,
                            "observed_state": "failed",
                            "error": "ORPHANED_AFTER_RESTART",
                            "completed_at": now.isoformat(),
                            "updated_at": now.isoformat(),
                        },
                    )
                )
        return events

    async def reconcile(
        self,
        agg: OperationAggregate,
        ctx: ProcessManagerContext,
    ) -> list[OperationDomainEventDraft]:
        """Run all reconciliation steps and return the combined event list."""
        all_events: list[OperationDomainEventDraft] = []
        all_events.extend(await self.drain_wakeups(agg, ctx))
        all_events.extend(await self.drain_commands(agg, ctx))
        all_events.extend(await self.poll_background_runs(agg, ctx))
        all_events.extend(await self.detect_orphaned_sessions(agg, ctx))
        return all_events
