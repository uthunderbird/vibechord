from __future__ import annotations

from collections.abc import Awaitable, Callable

from .models import (
    FleetWorkbenchState,
    filter_fleet_items,
    filtered_dashboard_tasks,
    filtered_session_timeline_events,
    normalize_key,
    oldest_blocking_attention,
    oldest_nonblocking_attention,
    oldest_task_blocking_attention,
    oldest_task_nonblocking_attention,
    operation_scope_attentions,
    payload_items,
    task_scope_attentions,
    tasks_with_blocking_attention,
)
from .rendering import render_workbench


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
        all_items = payload_items(payload)
        self.state.all_items = all_items
        items = filter_fleet_items(all_items, self.state.filter_query)
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
            if self.state.view_level != "fleet":
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
        if self.state.attention_picker_active:
            return self._handle_attention_picker_key(normalized)
        if self.state.pending_forensic_filter_text is not None:
            return self._handle_forensic_filter_key(key, normalized)
        if self.state.pending_session_filter_text is not None:
            return self._handle_session_filter_key(key, normalized)
        if self.state.pending_task_filter_text is not None:
            return self._handle_task_filter_key(key, normalized)
        if self.state.pending_filter_text is not None:
            return await self._handle_filter_key(key, normalized)
        if self.state.pending_answer_operation_id is not None:
            return await self._handle_answer_key(key, normalized)
        if self.state.pending_confirmation is not None:
            return await self._handle_confirmation_key(normalized)
        if self.state.help_overlay_active:
            return self._handle_help_overlay_key(normalized)
        if key == "A":
            self._open_attention_picker_for_scope()
            return True
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
            await self._refresh_selected_fleet_state()
            return True
        if normalized in {"down", "j"}:
            self._move_selection(1)
            await self._refresh_selected_fleet_state()
            return True
        if normalized == "tab":
            self._jump_to_next_blocking_attention()
            await self._refresh_selected_fleet_state()
            return True
        if normalized == "/":
            self._start_filter_input()
            return True
        if normalized == "a":
            await self._select_oldest_blocking_attention_for_scope()
            return True
        if normalized == "n":
            await self._select_oldest_nonblocking_attention_for_scope()
            return True
        if normalized == "?":
            self.state.help_overlay_active = True
            self.state.last_message = None
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
            self._clear_task_filter()
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

    def _handle_attention_picker_key(self, key: str) -> bool:
        if key in {"q", "ctrl+c"}:
            return False
        if key in {"esc", "A"}:
            self._clear_attention_picker()
            self.state.last_message = "Attention picker closed."
            return True
        if key in {"up", "k"}:
            items = self._attention_picker_items()
            if items:
                self.state.attention_picker_index = (
                    self.state.attention_picker_index - 1
                ) % len(items)
            return True
        if key in {"down", "j"}:
            items = self._attention_picker_items()
            if items:
                self.state.attention_picker_index = (
                    self.state.attention_picker_index + 1
                ) % len(items)
            return True
        if key == "enter":
            items = self._attention_picker_items()
            if not items:
                self.state.last_message = "No attention item is available to select."
                self._clear_attention_picker()
                return True
            selected = items[self.state.attention_picker_index]
            operation_id = self.state.attention_picker_operation_id
            if operation_id is None:
                self.state.last_message = "Attention picker lost its operation context."
                self._clear_attention_picker()
                return True
            task_id = self.state.attention_picker_task_id
            self._clear_attention_picker()
            self._set_answer_flow(
                operation_id=operation_id,
                attention_id=selected.attention_id,
                task_id=task_id,
                blocking=selected.blocking,
                prompt="Answer text: ",
            )
            self.state.last_message = "Attention selected. Type text, Enter to send, Esc to cancel."
            return True
        return True

    async def _handle_filter_key(self, key: str, normalized: str) -> bool:
        selected_operation_id = (
            self.state.selected_item.operation_id if self.state.selected_item is not None else None
        )
        if key in {"\x1b", "\x03", "esc", "ctrl+c"}:
            self.state.filter_query = self.state.pending_filter_restore_query
            self.state.pending_filter_text = None
            self._apply_filter(selected_operation_id)
            await self._refresh_selected_fleet_state()
            self.state.last_message = "Filter input aborted."
            return True
        if normalized == "enter":
            committed = (self.state.pending_filter_text or "").strip()
            self.state.filter_query = committed
            self.state.pending_filter_text = None
            self._apply_filter(selected_operation_id)
            await self._refresh_selected_fleet_state()
            self.state.last_message = (
                f"Applied fleet filter: {committed}"
                if committed
                else "Cleared fleet filter."
            )
            return True
        if key in {"\x7f", "\b"}:
            if self.state.pending_filter_text:
                self.state.pending_filter_text = self.state.pending_filter_text[:-1]
            self.state.filter_query = self.state.pending_filter_text or ""
            self._apply_filter(selected_operation_id)
            await self._refresh_selected_fleet_state()
            return True
        if len(key) == 1 and key.isprintable():
            current = self.state.pending_filter_text or ""
            self.state.pending_filter_text = current + key
            self.state.filter_query = self.state.pending_filter_text
            self._apply_filter(selected_operation_id)
            await self._refresh_selected_fleet_state()
        return True

    def render(self):
        return render_workbench(self.state)

    async def _handle_operation_key(self, key: str) -> bool:
        if key in {"q", "ctrl+c"}:
            return False
        if key == "esc":
            self.state.view_level = "fleet"
            self._clear_task_filter()
            self.state.last_message = None
            return True
        if key in {"up", "k"}:
            self._move_task_selection(-1)
            return True
        if key in {"down", "j"}:
            self._move_task_selection(1)
            return True
        if key == "?":
            self.state.help_overlay_active = True
            self.state.last_message = None
            return True
        if key == "tab":
            self._jump_to_next_blocking_task_attention()
            return True
        if key == "a":
            await self._select_oldest_blocking_attention_for_current_task()
            return True
        if key == "n":
            await self._select_oldest_nonblocking_attention_for_current_task()
            return True
        if key == "/":
            self._start_task_filter_input()
            return True
        if key == "enter":
            task = self.state.selected_task
            if task is None or task.linked_session_id is None:
                self.state.last_message = "The selected task has no linked session to inspect."
                return True
            self.state.view_level = "session"
            self.state.session_panel_mode = "timeline"
            self._clear_session_filter()
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
            self._clear_session_filter()
            self._clear_forensic_filter()
            self.state.last_message = None
            return True
        if key in {"up", "k"}:
            self._move_timeline_selection(-1)
            return True
        if key in {"down", "j"}:
            self._move_timeline_selection(1)
            return True
        if key == "?":
            self.state.help_overlay_active = True
            self.state.last_message = None
            return True
        if key == "a":
            await self._select_oldest_blocking_attention_for_current_task()
            return True
        if key == "n":
            await self._select_oldest_nonblocking_attention_for_current_task()
            return True
        if key == "/":
            self._start_session_filter_input()
            return True
        if key == "enter":
            self._open_forensic_view_from_session()
            return True
        selected = self.state.selected_item
        task = self.state.selected_task
        if selected is None:
            return True
        if key == "r":
            self._open_forensic_view_from_session()
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
        if key == "ctrl+c":
            return False
        if key == "?":
            self.state.help_overlay_active = True
            self.state.last_message = None
            return True
        if key in {"esc", "q"}:
            self.state.view_level = "session"
            self._clear_forensic_filter()
            self.state.last_message = None
            return True
        if key == "a":
            await self._select_oldest_blocking_attention_for_current_task()
            return True
        if key == "n":
            await self._select_oldest_nonblocking_attention_for_current_task()
            return True
        if key == "/":
            self._start_forensic_filter_input()
            return True
        return True

    def _handle_help_overlay_key(self, key: str) -> bool:
        if key in {"q", "ctrl+c"}:
            return False
        if key in {"?", "esc"}:
            self.state.help_overlay_active = False
            self.state.last_message = None
        return True

    def _open_forensic_view_from_session(self) -> None:
        if self.state.selected_timeline_event is None:
            self.state.last_message = "No timeline item is selected."
            return
        self.state.view_level = "forensic"
        self._clear_forensic_filter()
        self.state.last_message = None

    def _open_attention_picker_for_scope(self) -> None:
        if self.state.selected_operation_payload is None:
            self.state.last_message = "No selected scope for attention picker."
            return
        operation_id = self.state.selected_item.operation_id if self.state.selected_item else None
        task_id = (
            self.state.selected_task.task_id
            if self.state.view_level in {"operation", "session", "forensic"}
            and self.state.selected_task is not None
            else None
        )
        if operation_id is None:
            self.state.last_message = "No selected scope for attention picker."
            return
        self.state.attention_picker_operation_id = operation_id
        self.state.attention_picker_task_id = task_id
        self.state.attention_picker_index = 0
        self.state.attention_picker_active = bool(self._attention_picker_items())
        self.state.last_message = (
            None
            if self.state.attention_picker_active
            else "No attention items in the current scope."
        )

    def _attention_picker_items(self):
        payload = self.state.selected_operation_payload
        operation_id = self.state.attention_picker_operation_id
        if not isinstance(payload, dict) or operation_id is None:
            return []
        if self.state.attention_picker_task_id is not None:
            return task_scope_attentions(payload, task_id=self.state.attention_picker_task_id)
        return operation_scope_attentions(payload, operation_id=operation_id)

    def _clear_attention_picker(self) -> None:
        self.state.attention_picker_active = False
        self.state.attention_picker_operation_id = None
        self.state.attention_picker_task_id = None
        self.state.attention_picker_index = 0

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
            task_id = self.state.pending_answer_task_id
            blocking = self.state.pending_answer_blocking
            if operation_id is None or attention_id is None:
                self._clear_pending_answer("Answer was aborted due to missing context.")
                return True
            self._clear_pending_answer("Submitting answer...")
            result_message = await self._answer_attention(operation_id, attention_id, response)
            await self.refresh()
            self._continue_answer_flow_after_submission(
                operation_id=operation_id,
                task_id=task_id,
                blocking=blocking,
                result_message=result_message,
            )
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
            current_operation_id = (
                str(self.state.selected_operation_payload.get("operation_id"))
                if isinstance(self.state.selected_operation_payload, dict)
                else None
            )
            if current_operation_id != selected.operation_id:
                self.state.selected_operation_payload = None
                self.state.selected_fleet_brief = None
            self.state.last_message = f"Failed to refresh operation payload: {exc}"
            return
        self.state.selected_operation_payload = payload

    async def _refresh_selected_fleet_state(self) -> None:
        await self._refresh_selected_operation_payload()
        self.state.selected_fleet_brief = (
            self.state.selected_item.brief if self.state.selected_item is not None else None
        )

    def _restore_selected_task(self, selected_task_id: str | None) -> None:
        tasks = filtered_dashboard_tasks(
            self.state.selected_operation_payload,
            self.state.task_filter_query,
        )
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
        events = filtered_session_timeline_events(
            self.state.selected_operation_payload,
            self.state.selected_task,
            self.state.session_filter_query,
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
        tasks = filtered_dashboard_tasks(
            self.state.selected_operation_payload,
            self.state.task_filter_query,
        )
        if tasks:
            self.state.selected_task_index = (self.state.selected_task_index + delta) % len(tasks)
            self._restore_selected_timeline_event(None)

    def _move_timeline_selection(self, delta: int) -> None:
        events = filtered_session_timeline_events(
            self.state.selected_operation_payload,
            self.state.selected_task,
            self.state.session_filter_query,
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
        self._start_answer_flow(
            selected.operation_id,
            target.attention_id,
            blocking=True,
        )

    async def _select_oldest_nonblocking_attention_for_scope(self) -> None:
        selected = self.state.selected_item
        if selected is None or self.state.selected_operation_payload is None:
            self.state.last_message = "No selected operation for attention navigation."
            return
        payload = self.state.selected_operation_payload
        target = oldest_nonblocking_attention(payload)
        if target is None:
            self.state.last_message = f"No non-blocking attention on {selected.operation_id}."
            return
        self._start_answer_flow(
            selected.operation_id,
            target.attention_id,
            blocking=False,
        )

    async def _select_oldest_blocking_attention_for_current_task(self) -> None:
        task = self.state.selected_task
        if task is None or self.state.selected_operation_payload is None:
            self.state.last_message = "No selected task to answer."
            return
        target = oldest_task_blocking_attention(self.state.selected_operation_payload, task.task_id)
        if target is None:
            self.state.last_message = f"No blocking attention on task {task.task_id}."
            return
        self._set_answer_flow(
            operation_id=(
                self.state.selected_item.operation_id
                if self.state.selected_item is not None
                else task.task_id
            ),
            attention_id=target.attention_id,
            task_id=task.task_id,
            blocking=True,
            prompt="Answer text: ",
        )
        self.state.last_message = "Answer selected. Type text, Enter to send, Esc to cancel."
        self.state.pending_confirmation = None

    async def _select_oldest_nonblocking_attention_for_current_task(self) -> None:
        task = self.state.selected_task
        if task is None or self.state.selected_operation_payload is None:
            self.state.last_message = "No selected task to answer."
            return
        target = oldest_task_nonblocking_attention(
            self.state.selected_operation_payload,
            task.task_id,
        )
        if target is None:
            self.state.last_message = f"No non-blocking attention on task {task.task_id}."
            return
        self._set_answer_flow(
            operation_id=(
                self.state.selected_item.operation_id
                if self.state.selected_item is not None
                else task.task_id
            ),
            attention_id=target.attention_id,
            task_id=task.task_id,
            blocking=False,
            prompt="Answer text: ",
        )
        self.state.last_message = "Answer selected. Type text, Enter to send, Esc to cancel."
        self.state.pending_confirmation = None

    def _jump_to_next_blocking_task_attention(self) -> None:
        tasks = filtered_dashboard_tasks(
            self.state.selected_operation_payload,
            self.state.task_filter_query,
        )
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

    def _start_answer_flow(
        self,
        operation_id: str,
        attention_id: str,
        *,
        blocking: bool,
    ) -> None:
        self._set_answer_flow(
            operation_id=operation_id,
            attention_id=attention_id,
            task_id=None,
            blocking=blocking,
            prompt="Answer text: ",
        )
        self.state.last_message = "Answer selected. Type text, Enter to send, Esc to cancel."
        self.state.pending_confirmation = None

    def _set_answer_flow(
        self,
        *,
        operation_id: str,
        attention_id: str,
        task_id: str | None,
        blocking: bool,
        prompt: str,
    ) -> None:
        self.state.pending_answer_operation_id = operation_id
        self.state.pending_answer_attention_id = attention_id
        self.state.pending_answer_task_id = task_id
        self.state.pending_answer_blocking = blocking
        self.state.pending_answer_text = ""
        self.state.pending_answer_prompt = prompt

    def _clear_pending_answer(self, message: str) -> None:
        self.state.pending_answer_operation_id = None
        self.state.pending_answer_attention_id = None
        self.state.pending_answer_task_id = None
        self.state.pending_answer_blocking = True
        self.state.pending_answer_text = ""
        self.state.pending_answer_prompt = "Answer text: "
        self.state.last_message = message
        self.state.pending_confirmation = None

    def _continue_answer_flow_after_submission(
        self,
        *,
        operation_id: str,
        task_id: str | None,
        blocking: bool,
        result_message: str,
    ) -> None:
        payload = self.state.selected_operation_payload
        if not isinstance(payload, dict):
            self.state.last_message = result_message
            return
        next_attention = (
            (
                oldest_task_blocking_attention(payload, task_id)
                if blocking
                else oldest_task_nonblocking_attention(payload, task_id)
            )
            if task_id is not None
            else (
                oldest_blocking_attention(payload)
                if blocking
                else oldest_nonblocking_attention(payload)
            )
        )
        if next_attention is None:
            self.state.last_message = result_message
            return
        remaining = self._remaining_attention_count(
            payload=payload,
            task_id=task_id,
            blocking=blocking,
        )
        scope_label = f"task {task_id}" if task_id is not None else operation_id
        kind_label = "blocking" if blocking else "non-blocking"
        remain_label = "attention remains" if remaining == 1 else "attentions remain"
        self._set_answer_flow(
            operation_id=operation_id,
            attention_id=next_attention.attention_id,
            task_id=task_id,
            blocking=blocking,
            prompt=f"{remaining} {kind_label} {remain_label} in {scope_label}. Answer text: ",
        )
        self.state.last_message = f"{result_message} Next oldest {kind_label} attention selected."
        self.state.pending_confirmation = None

    def _remaining_attention_count(
        self,
        *,
        payload: dict[str, object],
        task_id: str | None,
        blocking: bool,
    ) -> int:
        if task_id is not None:
            return sum(
                1
                for item in payload.get("attention", [])
                if isinstance(item, dict)
                and bool(item.get("blocking")) is blocking
                and item.get("target_id") == task_id
            )
        return sum(
            1
            for item in payload.get("attention", [])
            if isinstance(item, dict) and bool(item.get("blocking")) is blocking
        )

    def _handle_task_filter_key(self, key: str, normalized: str) -> bool:
        selected_task_id = self.state.selected_task.task_id if self.state.selected_task else None
        if key in {"\x1b", "\x03", "esc", "ctrl+c"}:
            self.state.task_filter_query = self.state.pending_task_filter_restore_query
            self.state.pending_task_filter_text = None
            self._apply_task_filter(selected_task_id)
            self.state.last_message = "Task filter input aborted."
            return True
        if normalized == "enter":
            committed = (self.state.pending_task_filter_text or "").strip()
            self.state.task_filter_query = committed
            self.state.pending_task_filter_text = None
            self._apply_task_filter(selected_task_id)
            self.state.last_message = (
                f"Applied task filter: {committed}" if committed else "Cleared task filter."
            )
            return True
        if key in {"\x7f", "\b"}:
            if self.state.pending_task_filter_text:
                self.state.pending_task_filter_text = self.state.pending_task_filter_text[:-1]
            self.state.task_filter_query = self.state.pending_task_filter_text or ""
            self._apply_task_filter(selected_task_id)
            return True
        if len(key) == 1 and key.isprintable():
            current = self.state.pending_task_filter_text or ""
            self.state.pending_task_filter_text = current + key
            self.state.task_filter_query = self.state.pending_task_filter_text
            self._apply_task_filter(selected_task_id)
        return True

    def _start_task_filter_input(self) -> None:
        self.state.pending_task_filter_restore_query = self.state.task_filter_query
        self.state.pending_task_filter_text = self.state.task_filter_query
        self.state.last_message = None
        self.state.pending_confirmation = None

    def _apply_task_filter(self, selected_task_id: str | None) -> None:
        tasks = filtered_dashboard_tasks(
            self.state.selected_operation_payload,
            self.state.task_filter_query,
        )
        if not tasks:
            self.state.selected_task_index = 0
            self._restore_selected_timeline_event(None)
            return
        if selected_task_id is not None:
            for index, task in enumerate(tasks):
                if task.task_id == selected_task_id:
                    self.state.selected_task_index = index
                    break
            else:
                self.state.selected_task_index = 0
        else:
            self.state.selected_task_index = min(self.state.selected_task_index, len(tasks) - 1)
        self._restore_selected_timeline_event(None)

    def _clear_task_filter(self) -> None:
        self.state.task_filter_query = ""
        self.state.pending_task_filter_text = None
        self.state.pending_task_filter_restore_query = ""

    def _handle_session_filter_key(self, key: str, normalized: str) -> bool:
        selected_summary = (
            self.state.selected_timeline_event.summary
            if self.state.selected_timeline_event is not None
            else None
        )
        if key in {"\x1b", "\x03", "esc", "ctrl+c"}:
            self.state.session_filter_query = self.state.pending_session_filter_restore_query
            self.state.pending_session_filter_text = None
            self._apply_session_filter(selected_summary)
            self.state.last_message = "Session filter input aborted."
            return True
        if normalized == "enter":
            committed = (self.state.pending_session_filter_text or "").strip()
            self.state.session_filter_query = committed
            self.state.pending_session_filter_text = None
            self._apply_session_filter(selected_summary)
            self.state.last_message = (
                f"Applied session filter: {committed}"
                if committed
                else "Cleared session filter."
            )
            return True
        if key in {"\x7f", "\b"}:
            if self.state.pending_session_filter_text:
                self.state.pending_session_filter_text = self.state.pending_session_filter_text[:-1]
            self.state.session_filter_query = self.state.pending_session_filter_text or ""
            self._apply_session_filter(selected_summary)
            return True
        if len(key) == 1 and key.isprintable():
            current = self.state.pending_session_filter_text or ""
            self.state.pending_session_filter_text = current + key
            self.state.session_filter_query = self.state.pending_session_filter_text
            self._apply_session_filter(selected_summary)
        return True

    def _start_session_filter_input(self) -> None:
        self.state.pending_session_filter_restore_query = self.state.session_filter_query
        self.state.pending_session_filter_text = self.state.session_filter_query
        self.state.last_message = None
        self.state.pending_confirmation = None

    def _apply_session_filter(self, selected_summary: str | None) -> None:
        events = filtered_session_timeline_events(
            self.state.selected_operation_payload,
            self.state.selected_task,
            self.state.session_filter_query,
        )
        if not events:
            self.state.selected_timeline_index = 0
            return
        if selected_summary is not None:
            for index, event in enumerate(events):
                if event.summary == selected_summary:
                    self.state.selected_timeline_index = index
                    break
            else:
                self.state.selected_timeline_index = 0
            return
        self.state.selected_timeline_index = min(
            self.state.selected_timeline_index, len(events) - 1
        )

    def _clear_session_filter(self) -> None:
        self.state.session_filter_query = ""
        self.state.pending_session_filter_text = None
        self.state.pending_session_filter_restore_query = ""

    def _handle_forensic_filter_key(self, key: str, normalized: str) -> bool:
        if key in {"\x1b", "\x03", "esc", "ctrl+c"}:
            self.state.forensic_filter_query = self.state.pending_forensic_filter_restore_query
            self.state.pending_forensic_filter_text = None
            self.state.last_message = "Forensic filter input aborted."
            return True
        if normalized == "enter":
            committed = (self.state.pending_forensic_filter_text or "").strip()
            self.state.forensic_filter_query = committed
            self.state.pending_forensic_filter_text = None
            self.state.last_message = (
                f"Applied forensic filter: {committed}"
                if committed
                else "Cleared forensic filter."
            )
            return True
        if key in {"\x7f", "\b"}:
            if self.state.pending_forensic_filter_text:
                self.state.pending_forensic_filter_text = (
                    self.state.pending_forensic_filter_text[:-1]
                )
            self.state.forensic_filter_query = self.state.pending_forensic_filter_text or ""
            return True
        if len(key) == 1 and key.isprintable():
            current = self.state.pending_forensic_filter_text or ""
            self.state.pending_forensic_filter_text = current + key
            self.state.forensic_filter_query = self.state.pending_forensic_filter_text
        return True

    def _start_forensic_filter_input(self) -> None:
        self.state.pending_forensic_filter_restore_query = self.state.forensic_filter_query
        self.state.pending_forensic_filter_text = self.state.forensic_filter_query
        self.state.last_message = None
        self.state.pending_confirmation = None

    def _clear_forensic_filter(self) -> None:
        self.state.forensic_filter_query = ""
        self.state.pending_forensic_filter_text = None
        self.state.pending_forensic_filter_restore_query = ""

    def _start_filter_input(self) -> None:
        self.state.pending_filter_restore_query = self.state.filter_query
        self.state.pending_filter_text = self.state.filter_query
        self.state.last_message = None
        self.state.pending_confirmation = None

    def _apply_filter(self, selected_operation_id: str | None) -> None:
        self.state.items = filter_fleet_items(self.state.all_items, self.state.filter_query)
        if not self.state.items:
            self.state.selected_index = 0
            self.state.selected_operation_payload = None
            self.state.selected_fleet_brief = None
            return
        if selected_operation_id is not None:
            for index, item in enumerate(self.state.items):
                if item.operation_id == selected_operation_id:
                    self.state.selected_index = index
                    break
            else:
                self.state.selected_index = 0
            return
        self.state.selected_index = min(self.state.selected_index, len(self.state.items) - 1)


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
