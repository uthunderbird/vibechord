from __future__ import annotations

from collections.abc import Awaitable, Callable

from .tui_models import (
    FleetWorkbenchState,
    dashboard_tasks,
    normalize_key,
    oldest_blocking_attention,
    oldest_task_blocking_attention,
    payload_items,
    raw_transcript_lines,
    session_timeline_events,
    tasks_with_blocking_attention,
)
from .tui_rendering import render_workbench


class FleetWorkbenchController:
    def __init__(
        self,
        *,
        load_payload: Callable[[], Awaitable[dict[str, object]]],
        load_operation_payload: Callable[[str], Awaitable[dict[str, object] | None]],
        pause_operation: Callable[[str], Awaitable[str]],
        unpause_operation: Callable[[str], Awaitable[str]],
        interrupt_operation: Callable[[str, str | None], Awaitable[str]],
        cancel_operation: Callable[[str], Awaitable[str]],
        answer_attention: Callable[[str, str, str], Awaitable[str]],
    ) -> None:
        self._load_payload = load_payload
        self._load_operation_payload = load_operation_payload
        self._pause_operation = pause_operation
        self._unpause_operation = unpause_operation
        self._interrupt_operation = interrupt_operation
        self._cancel_operation = cancel_operation
        self._answer_attention = answer_attention
        self.state = FleetWorkbenchState()

    async def refresh(self) -> None:
        try:
            payload = await self._load_payload()
        except Exception as exc:
            self.state.last_message = f"Failed to refresh operation list: {exc}"
            return
        selected_operation_id = (
            self.state.selected_item.operation_id if self.state.selected_item is not None else None
        )
        selected_task_id = (
            self.state.selected_task.task_id
            if self.state.view_level in {"operation", "session"}
            and self.state.selected_task is not None
            else None
        )
        selected_event_summary = (
            self.state.selected_timeline_event.summary
            if self.state.view_level == "session" and self.state.selected_timeline_event is not None
            else None
        )
        items = payload_items(payload)
        self.state.items = items
        self.state.project = (
            payload.get("project")
            if isinstance(payload.get("project"), str) and payload.get("project")
            else None
        )
        self.state.total_operations = (
            payload.get("total_operations")
            if isinstance(payload.get("total_operations"), int)
            else 0
        )
        if not items:
            self.state.selected_index = 0
            self.state.selected_operation_payload = None
            self.state.selected_fleet_brief = None
            self.state.pending_confirmation = None
            self.state.view_level = "fleet"
            return
        if selected_operation_id is not None:
            for index, item in enumerate(items):
                if item.operation_id == selected_operation_id:
                    self.state.selected_index = index
                    break
            else:
                self.state.selected_index = min(self.state.selected_index, len(items) - 1)
        else:
            self.state.selected_index = min(self.state.selected_index, len(items) - 1)
        await self._refresh_selected_operation_payload()
        self.state.selected_fleet_brief = (
            self.state.selected_item.brief if self.state.selected_item is not None else None
        )
        self._restore_selected_task(selected_task_id)
        self._restore_selected_timeline_event(selected_event_summary)

    async def handle_key(self, key: str) -> bool:
        normalized = normalize_key(key)
        if self.state.pending_answer_operation_id is not None:
            return await self._handle_answer_key(key, normalized)
        if self.state.pending_confirmation is not None:
            return await self._handle_confirmation_key(normalized)
        if self.state.view_level == "forensic":
            return await self._handle_forensic_key(normalized)
        if self.state.view_level == "session":
            return await self._handle_session_key(normalized)
        if self.state.view_level == "operation":
            return await self._handle_operation_key(normalized)
        if normalized in {"q", "ctrl+c"}:
            return False
        if normalized in {"up", "k"}:
            self._move_selection(-1)
            return True
        if normalized in {"down", "j"}:
            self._move_selection(1)
            return True
        if normalized == "tab":
            self._jump_to_next_blocking_attention()
            return True
        if normalized == "a":
            await self._select_oldest_blocking_attention_for_scope()
            return True
        if normalized == "r":
            await self.refresh()
            self.state.last_message = "Refreshed fleet view."
            return True
        selected = self.state.selected_item
        if selected is None:
            return True
        if normalized == "enter" and isinstance(self.state.selected_operation_payload, dict):
            self.state.view_level = "operation"
            self.state.operation_panel_mode = "detail"
            self._restore_selected_task(None)
            return True
        if normalized == "p":
            self.state.last_message = await self._pause_operation(selected.operation_id)
            await self.refresh()
            return True
        if normalized == "u":
            self.state.last_message = await self._unpause_operation(selected.operation_id)
            await self.refresh()
            return True
        if normalized == "s":
            self.state.last_message = await self._interrupt_operation(selected.operation_id, None)
            await self.refresh()
            return True
        if normalized == "c":
            self.state.pending_confirmation = selected.operation_id
            self.state.last_message = None
            return True
        return True

    def render(self):
        return render_workbench(self.state)

    async def _handle_operation_key(self, key: str) -> bool:
        if key in {"q", "ctrl+c"}:
            return False
        if key == "esc":
            self.state.view_level = "fleet"
            self.state.last_message = None
            return True
        if key in {"up", "k"}:
            self._move_task_selection(-1)
            return True
        if key in {"down", "j"}:
            self._move_task_selection(1)
            return True
        if key == "tab":
            self._jump_to_next_blocking_task_attention()
            return True
        if key == "a":
            await self._select_oldest_blocking_attention_for_current_task()
            return True
        if key == "enter":
            task = self.state.selected_task
            if task is None or task.linked_session_id is None:
                self.state.last_message = "The selected task has no linked session to inspect."
                return True
            self.state.view_level = "session"
            self.state.session_panel_mode = "timeline"
            self._restore_selected_timeline_event(None)
            return True
        if key in {"i", "d", "t", "m"}:
            self.state.operation_panel_mode = {
                "i": "detail",
                "d": "decisions",
                "t": "events",
                "m": "memory",
            }[key]
            return True
        selected = self.state.selected_item
        if selected is None:
            return True
        if key == "r":
            await self.refresh()
            self.state.last_message = "Refreshed operation view."
            return True
        if key == "p":
            self.state.last_message = await self._pause_operation(selected.operation_id)
            await self.refresh()
            return True
        if key == "u":
            self.state.last_message = await self._unpause_operation(selected.operation_id)
            await self.refresh()
            return True
        if key == "s":
            task = self.state.selected_task
            task_id = (
                task.task_id if task is not None and task.linked_session_id is not None else None
            )
            self.state.last_message = await self._interrupt_operation(
                selected.operation_id, task_id
            )
            await self.refresh()
            return True
        if key == "c":
            self.state.pending_confirmation = selected.operation_id
            self.state.last_message = None
            return True
        return True

    async def _handle_session_key(self, key: str) -> bool:
        if key in {"q", "ctrl+c"}:
            return False
        if key == "esc":
            self.state.view_level = "operation"
            self.state.last_message = None
            return True
        if key in {"up", "k"}:
            self._move_timeline_selection(-1)
            return True
        if key in {"down", "j"}:
            self._move_timeline_selection(1)
            return True
        if key == "a":
            await self._select_oldest_blocking_attention_for_current_task()
            return True
        if key == "enter":
            if self.state.selected_timeline_event is None:
                self.state.last_message = "No timeline item is selected."
                return True
            if not raw_transcript_lines(self.state.selected_operation_payload):
                self.state.last_message = (
                    "No raw transcript for selected session; staying on session timeline."
                )
                return True
            self.state.view_level = "forensic"
            self.state.last_message = None
            return True
        selected = self.state.selected_item
        task = self.state.selected_task
        if selected is None:
            return True
        if key == "r":
            self.state.session_panel_mode = (
                "raw_transcript"
                if self.state.session_panel_mode != "raw_transcript"
                else "timeline"
            )
            return True
        if key == "s":
            task_id = (
                task.task_id if task is not None and task.linked_session_id is not None else None
            )
            self.state.last_message = await self._interrupt_operation(
                selected.operation_id, task_id
            )
            await self.refresh()
            return True
        if key == "p":
            self.state.last_message = await self._pause_operation(selected.operation_id)
            await self.refresh()
            return True
        if key == "u":
            self.state.last_message = await self._unpause_operation(selected.operation_id)
            await self.refresh()
            return True
        if key == "c":
            self.state.pending_confirmation = selected.operation_id
            self.state.last_message = None
            return True
        return True

    async def _handle_forensic_key(self, key: str) -> bool:
        if key in {"q", "ctrl+c"}:
            return False
        if key == "esc":
            self.state.view_level = "session"
            self.state.last_message = None
            return True
        return True

    async def _handle_answer_key(self, key: str, normalized: str) -> bool:
        if key in {"\x1b", "\x03", "esc", "ctrl+c"}:
            self._clear_pending_answer("Answer input aborted.")
            return True
        if normalized == "enter":
            response = self.state.pending_answer_text.strip()
            if not response:
                self.state.last_message = "Answer text cannot be empty."
                return True
            operation_id = self.state.pending_answer_operation_id
            attention_id = self.state.pending_answer_attention_id
            if operation_id is None or attention_id is None:
                self._clear_pending_answer("Answer was aborted due to missing context.")
                return True
            self._clear_pending_answer("Submitting answer...")
            self.state.last_message = await self._answer_attention(
                operation_id, attention_id, response
            )
            await self.refresh()
            return True
        if key in {"\x7f", "\b"}:
            if self.state.pending_answer_text:
                self.state.pending_answer_text = self.state.pending_answer_text[:-1]
            return True
        if normalized in {"up", "down", "left", "right", "tab", "esc"}:
            return True
        if len(key) == 1 and key.isprintable():
            self.state.pending_answer_text += key
        return True

    async def _handle_confirmation_key(self, key: str) -> bool:
        operation_id = self.state.pending_confirmation
        if operation_id is None:
            return True
        self.state.pending_confirmation = None
        if key == "y":
            self.state.last_message = await self._cancel_operation(operation_id)
            await self.refresh()
            return True
        self.state.last_message = f"Cancel aborted for {operation_id}."
        return True

    async def _refresh_selected_operation_payload(self) -> None:
        selected = self.state.selected_item
        if selected is None:
            self.state.selected_operation_payload = None
            self.state.selected_fleet_brief = None
            return
        try:
            payload = await self._load_operation_payload(selected.operation_id)
        except Exception as exc:
            self.state.last_message = f"Failed to refresh operation payload: {exc}"
            return
        self.state.selected_operation_payload = payload

    def _restore_selected_task(self, selected_task_id: str | None) -> None:
        tasks = dashboard_tasks(self.state.selected_operation_payload)
        if not tasks:
            self.state.selected_task_index = 0
            return
        if selected_task_id is not None:
            for index, task in enumerate(tasks):
                if task.task_id == selected_task_id:
                    self.state.selected_task_index = index
                    return
        self.state.selected_task_index = min(self.state.selected_task_index, len(tasks) - 1)

    def _restore_selected_timeline_event(self, selected_summary: str | None) -> None:
        events = session_timeline_events(
            self.state.selected_operation_payload, self.state.selected_task
        )
        if not events:
            self.state.selected_timeline_index = 0
            return
        if selected_summary is not None:
            for index, item in enumerate(events):
                if item.summary == selected_summary:
                    self.state.selected_timeline_index = index
                    return
        self.state.selected_timeline_index = min(
            self.state.selected_timeline_index, len(events) - 1
        )

    def _move_selection(self, delta: int) -> None:
        if self.state.items:
            self.state.selected_index = (self.state.selected_index + delta) % len(self.state.items)

    def _move_task_selection(self, delta: int) -> None:
        tasks = dashboard_tasks(self.state.selected_operation_payload)
        if tasks:
            self.state.selected_task_index = (self.state.selected_task_index + delta) % len(tasks)
            self._restore_selected_timeline_event(None)

    def _move_timeline_selection(self, delta: int) -> None:
        events = session_timeline_events(
            self.state.selected_operation_payload, self.state.selected_task
        )
        if events:
            self.state.selected_timeline_index = (self.state.selected_timeline_index + delta) % len(
                events
            )

    def _jump_to_next_attention(self) -> None:
        if not self.state.items:
            return
        start = self.state.selected_index
        total = len(self.state.items)
        for offset in range(1, total + 1):
            index = (start + offset) % total
            if self.state.items[index].has_attention:
                self.state.selected_index = index
                return

    def _jump_to_next_blocking_attention(self) -> None:
        if not self.state.items:
            return
        start = self.state.selected_index
        total = len(self.state.items)
        for offset in range(1, total + 1):
            index = (start + offset) % total
            if self.state.items[index].has_blocking_attention:
                self.state.selected_index = index
                return

    async def _select_oldest_blocking_attention_for_scope(self) -> None:
        selected = self.state.selected_item
        if selected is None or self.state.selected_operation_payload is None:
            self.state.last_message = "No selected operation for attention navigation."
            return
        payload = self.state.selected_operation_payload
        target = oldest_blocking_attention(payload)
        if target is None:
            self.state.last_message = f"No blocking attention on {selected.operation_id}."
            return
        self._start_answer_flow(selected.operation_id, target.attention_id)

    async def _select_oldest_blocking_attention_for_current_task(self) -> None:
        task = self.state.selected_task
        if task is None or self.state.selected_operation_payload is None:
            self.state.last_message = "No selected task to answer."
            return
        target = oldest_task_blocking_attention(self.state.selected_operation_payload, task.task_id)
        if target is None:
            self.state.last_message = f"No blocking attention on task {task.task_id}."
            return
        self._start_answer_flow(
            self.state.selected_item.operation_id
            if self.state.selected_item is not None
            else task.task_id,
            target.attention_id,
        )

    def _jump_to_next_blocking_task_attention(self) -> None:
        tasks = dashboard_tasks(self.state.selected_operation_payload)
        if not tasks:
            return
        start = self.state.selected_task_index
        total = len(tasks)
        task_blockers = tasks_with_blocking_attention(self.state.selected_operation_payload, tasks)
        for offset in range(1, total + 1):
            index = (start + offset) % total
            if tasks[index].task_id in task_blockers:
                self.state.selected_task_index = index
                self._restore_selected_timeline_event(None)
                return

    def _start_answer_flow(self, operation_id: str, attention_id: str) -> None:
        self.state.pending_answer_operation_id = operation_id
        self.state.pending_answer_attention_id = attention_id
        self.state.pending_answer_text = ""
        self.state.last_message = "Answer selected. Type text, Enter to send, Esc to cancel."
        self.state.pending_confirmation = None

    def _clear_pending_answer(self, message: str) -> None:
        self.state.pending_answer_operation_id = None
        self.state.pending_answer_attention_id = None
        self.state.pending_answer_text = ""
        self.state.last_message = message
        self.state.pending_confirmation = None


def build_fleet_workbench_controller(
    *,
    load_payload: Callable[[], Awaitable[dict[str, object]]],
    load_operation_payload: Callable[[str], Awaitable[dict[str, object] | None]],
    pause_operation: Callable[[str], Awaitable[str]],
    unpause_operation: Callable[[str], Awaitable[str]],
    interrupt_operation: Callable[[str, str | None], Awaitable[str]],
    cancel_operation: Callable[[str], Awaitable[str]],
    answer_attention: Callable[[str, str, str], Awaitable[str]],
) -> FleetWorkbenchController:
    return FleetWorkbenchController(
        load_payload=load_payload,
        load_operation_payload=load_operation_payload,
        pause_operation=pause_operation,
        unpause_operation=unpause_operation,
        interrupt_operation=interrupt_operation,
        cancel_operation=cancel_operation,
        answer_attention=answer_attention,
    )
