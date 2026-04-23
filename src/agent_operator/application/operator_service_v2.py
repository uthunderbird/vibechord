"""OperatorServiceV2 — v2 operator facade (ADR 0194 Layer 4).

Owns run/resume/cancel. No OperationState, no snapshot writes.
All state changes flow through the event log via DriveService.
"""
from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from agent_operator.application.drive.agent_run_supervisor import AgentRunSupervisorV2
from agent_operator.application.drive.drive_service import DriveService
from agent_operator.application.drive.process_manager_context import ProcessManagerContext
from agent_operator.domain.enums import OperationStatus
from agent_operator.domain.event_sourcing import (
    OperationDomainEventDraft,
    StoredOperationDomainEvent,
)
from agent_operator.domain.events import RunEvent
from agent_operator.domain.operation import (
    ExecutionBudget,
    OperationGoal,
    OperationOutcome,
    OperationPolicy,
    RunOptions,
    RuntimeHints,
)
from agent_operator.protocols import EventSink, OperationEventStore


class OperatorServiceV2:
    """v2 operator facade — event-sourced, no snapshot writes.

    Replaces OperatorService. Wired in Layer 4 when DriveService is production-ready.
    """

    def __init__(
        self,
        *,
        drive_service: DriveService,
        event_store: OperationEventStore,
        event_sink: EventSink | None = None,
        supervisor: AgentRunSupervisorV2 | None = None,
    ) -> None:
        self._drive_service = drive_service
        self._event_store = event_store
        self._event_sink = event_sink
        self._supervisor = supervisor
        self._drive_tasks: list[asyncio.Task[OperationOutcome]] = []
        self._active_contexts: dict[str, ProcessManagerContext] = {}
        self._accepting = True

    async def run(
        self,
        goal: OperationGoal,
        options: RunOptions | None = None,
        *,
        operation_id: str | None = None,
        policy: OperationPolicy | None = None,
        budget: ExecutionBudget | None = None,
        runtime_hints: RuntimeHints | None = None,
    ) -> OperationOutcome:
        """Create a new operation and drive it to completion."""
        if not self._accepting:
            raise RuntimeError("OperatorServiceV2 is draining and not accepting new runs.")
        opts = options or RunOptions()
        if budget is not None and opts.max_cycles is None:
            opts = RunOptions(
                **{**opts.model_dump(), "max_cycles": budget.max_iterations}
            )
        oid = operation_id or str(uuid4())
        now = datetime.now(UTC)

        birth_payload: dict[str, object] = {
            "objective": goal.objective_text or "",
            "harness_instructions": goal.harness_instructions,
            "success_criteria": list(goal.success_criteria) if goal.success_criteria else [],
            "metadata": dict(goal.metadata) if goal.metadata else {},
            "allowed_agents": list(policy.allowed_agents) if policy else [],
            "involvement_level": policy.involvement_level.value if policy else "full",
            "policy": (
                policy.model_dump(mode="json")
                if policy is not None
                else OperationPolicy().model_dump(mode="json")
            ),
            "execution_budget": (
                budget.model_dump(mode="json")
                if budget is not None
                else ExecutionBudget().model_dump(mode="json")
            ),
            "runtime_hints": (
                runtime_hints.model_dump(mode="json")
                if runtime_hints is not None
                else RuntimeHints().model_dump(mode="json")
            ),
            "created_at": now.isoformat(),
        }
        birth_events = [
            OperationDomainEventDraft(
                event_type="operation.created",
                payload=birth_payload,
                timestamp=now,
            )
        ]
        if goal.external_ticket is not None:
            birth_events.append(
                OperationDomainEventDraft(
                    event_type="operation.ticket_linked",
                    payload=goal.external_ticket.model_dump(mode="json"),
                    timestamp=now,
                )
            )

        stored_birth_events = await self._event_store.append(oid, 0, birth_events)
        await self._emit_run_events(stored_birth_events)
        return await self._drive_operation(oid, opts)

    async def resume(
        self,
        operation_id: str,
        *,
        options: RunOptions | None = None,
        budget: ExecutionBudget | None = None,
    ) -> OperationOutcome:
        """Resume an existing operation from its event log."""
        if not self._accepting:
            raise RuntimeError("OperatorServiceV2 is draining and not accepting resumes.")
        opts = options or RunOptions()
        if budget is not None and opts.max_cycles is None:
            opts = RunOptions(
                **{**opts.model_dump(), "max_cycles": budget.max_iterations}
            )
        return await self._drive_operation(operation_id, opts)

    async def cancel(
        self,
        operation_id: str,
        *,
        reason: str | None = None,
    ) -> OperationOutcome:
        """Cancel a running operation by writing a terminal cancel event."""
        last_sequence = await self._event_store.load_last_sequence(operation_id)
        summary = (
            f"Operation cancelled: {reason.strip()}."
            if isinstance(reason, str) and reason.strip()
            else "Operation cancelled."
        )
        cancel_events = [
            OperationDomainEventDraft(
                event_type="operation.status.changed",
                payload={
                    "status": OperationStatus.CANCELLED.value,
                    "final_summary": summary,
                },
            )
        ]
        stored = await self._event_store.append(operation_id, last_sequence, cancel_events)
        await self._emit_run_events(stored)
        now = datetime.now(UTC)
        return OperationOutcome(
            operation_id=operation_id,
            status=OperationStatus.CANCELLED,
            summary=summary,
            ended_at=now,
        )

    async def _emit_run_events(
        self,
        stored_events: Sequence[StoredOperationDomainEvent],
    ) -> None:
        if self._event_sink is None:
            return
        for stored in stored_events:
            payload = stored.payload
            session_id = payload.get("session_id") if isinstance(payload, dict) else None
            task_id = payload.get("task_id") if isinstance(payload, dict) else None
            iteration = payload.get("iteration") if isinstance(payload, dict) else None
            await self._event_sink.emit(
                RunEvent(
                    event_type=stored.event_type,
                    category="domain",
                    operation_id=stored.operation_id,
                    iteration=iteration if isinstance(iteration, int) else 0,
                    task_id=task_id if isinstance(task_id, str) else None,
                    session_id=session_id if isinstance(session_id, str) else None,
                    timestamp=stored.timestamp,
                    payload=payload if isinstance(payload, dict) else {},
                )
            )

    async def _drive_operation(
        self,
        operation_id: str,
        options: RunOptions,
    ) -> OperationOutcome:
        """Run one drive task while tracking its context for shutdown."""

        def _register_context(ctx: ProcessManagerContext) -> None:
            self._active_contexts[operation_id] = ctx

        task = asyncio.create_task(
            self._drive_service.drive(
                operation_id,
                options,
                context_ready=_register_context,
            )
        )
        self._drive_tasks.append(task)
        try:
            return await task
        finally:
            self._active_contexts.pop(operation_id, None)
            self._drive_tasks = [item for item in self._drive_tasks if item is not task]

    async def _on_sigterm(self) -> None:
        """Drain active drive loops, then cancel background tasks in order."""
        self._accepting = False
        for ctx in self._active_contexts.values():
            ctx.request_drain()
        if self._supervisor is not None:
            self._supervisor.mark_draining()
        if self._drive_tasks:
            await asyncio.gather(*self._drive_tasks, return_exceptions=True)
        if self._supervisor is None:
            return
        self._supervisor.cancel_all()
        active_tasks = self._supervisor.get_active_tasks()
        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)
