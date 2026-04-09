from __future__ import annotations

from datetime import datetime

from agent_operator.domain import OperationState, RunEvent, RunEventKind
from agent_operator.protocols import EventSink, WakeupInbox


class OperationEventRelay:
    """Own process-wide run-event and wakeup emission."""

    def __init__(
        self,
        *,
        event_sink: EventSink,
        wakeup_inbox: WakeupInbox | None,
    ) -> None:
        self._event_sink = event_sink
        self._wakeup_inbox = wakeup_inbox

    async def emit(
        self,
        event_type: str,
        state: OperationState,
        iteration: int,
        payload: dict[str, object],
        *,
        task_id: str | None = None,
        session_id: str | None = None,
        kind: RunEventKind = RunEventKind.TRACE,
        category: str | None = "domain",
    ) -> None:
        event = RunEvent(
            event_type=event_type,
            kind=kind,
            category=category,
            operation_id=state.operation_id,
            iteration=iteration,
            task_id=task_id,
            session_id=session_id,
            payload=payload,
        )
        await self._event_sink.emit(event)
        if kind is RunEventKind.WAKEUP and self._wakeup_inbox is not None:
            await self._wakeup_inbox.enqueue(event)

    async def emit_wakeup(
        self,
        event_type: str,
        state: OperationState,
        iteration: int,
        payload: dict[str, object],
        *,
        task_id: str | None = None,
        session_id: str | None = None,
        not_before: datetime | None = None,
        dedupe_key: str | None = None,
        category: str | None = "domain",
    ) -> None:
        event = RunEvent(
            event_type=event_type,
            kind=RunEventKind.WAKEUP,
            category=category,
            operation_id=state.operation_id,
            iteration=iteration,
            task_id=task_id,
            session_id=session_id,
            payload=payload,
            not_before=not_before,
            dedupe_key=dedupe_key,
        )
        await self._event_sink.emit(event)
        if self._wakeup_inbox is not None:
            await self._wakeup_inbox.enqueue(event)
