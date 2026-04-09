from __future__ import annotations

import select
import sys
import termios
import tty
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

type _TerminalSettings = (
    list[int | list[bytes | int]]
    | list[int | list[bytes]]
    | list[int | list[int]]
)


@dataclass(frozen=True, slots=True)
class _FleetItem:
    operation_id: str
    status: str
    scheduler_state: str
    objective_brief: str
    focus_brief: str | None
    latest_outcome_brief: str | None
    blocker_brief: str | None
    runtime_alert: str | None
    open_attention_count: int
    attention_briefs: tuple[str, ...]
    project_profile_name: str | None
    bucket: str

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> _FleetItem:
        attention_briefs_raw = payload.get("attention_briefs")
        attention_briefs = tuple(
            str(item) for item in attention_briefs_raw if isinstance(item, str)
        ) if isinstance(attention_briefs_raw, list) else ()
        return cls(
            operation_id=str(payload.get("operation_id") or "-"),
            status=str(payload.get("status") or "-"),
            scheduler_state=str(payload.get("scheduler_state") or "-"),
            objective_brief=str(payload.get("objective_brief") or "-"),
            focus_brief=_optional_text(payload.get("focus_brief")),
            latest_outcome_brief=_optional_text(payload.get("latest_outcome_brief")),
            blocker_brief=_optional_text(payload.get("blocker_brief")),
            runtime_alert=_optional_text(payload.get("runtime_alert")),
            open_attention_count=_optional_int(payload.get("open_attention_count")),
            attention_briefs=attention_briefs,
            project_profile_name=_optional_text(payload.get("project_profile_name")),
            bucket=str(payload.get("bucket") or "recent"),
        )

    @property
    def has_attention(self) -> bool:
        return self.runtime_alert is not None or self.open_attention_count > 0


@dataclass(frozen=True, slots=True)
class _OperationTaskItem:
    task_id: str
    task_short_id: str
    title: str
    goal: str
    definition_of_done: str
    status: str
    priority: int
    dependencies: tuple[str, ...]
    assigned_agent: str | None
    linked_session_id: str | None
    memory_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    notes: tuple[str, ...]

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> _OperationTaskItem:
        return cls(
            task_id=str(payload.get("task_id") or "-"),
            task_short_id=str(payload.get("task_short_id") or "-"),
            title=str(payload.get("title") or "-"),
            goal=str(payload.get("goal") or "-"),
            definition_of_done=str(payload.get("definition_of_done") or "-"),
            status=str(payload.get("status") or "-"),
            priority=_optional_int(payload.get("priority")),
            dependencies=_text_tuple(payload.get("dependencies")),
            assigned_agent=_optional_text(payload.get("assigned_agent")),
            linked_session_id=_optional_text(payload.get("linked_session_id")),
            memory_refs=_text_tuple(payload.get("memory_refs")),
            artifact_refs=_text_tuple(payload.get("artifact_refs")),
            notes=_text_tuple(payload.get("notes")),
        )


@dataclass(frozen=True, slots=True)
class _TimelineEventItem:
    event_type: str
    iteration: int
    task_id: str | None
    session_id: str | None
    summary: str

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> _TimelineEventItem:
        return cls(
            event_type=str(payload.get("event_type") or "-"),
            iteration=_optional_int(payload.get("iteration")),
            task_id=_optional_text(payload.get("task_id")),
            session_id=_optional_text(payload.get("session_id")),
            summary=str(payload.get("summary") or "-"),
        )


@dataclass(slots=True)
class _FleetWorkbenchState:
    items: list[_FleetItem] = field(default_factory=list)
    selected_index: int = 0
    selected_operation_payload: dict[str, object] | None = None
    project: str | None = None
    total_operations: int = 0
    last_message: str | None = None
    pending_confirmation: str | None = None
    view_level: str = "fleet"
    selected_task_index: int = 0
    operation_panel_mode: str = "detail"
    selected_timeline_index: int = 0
    session_panel_mode: str = "timeline"

    @property
    def selected_item(self) -> _FleetItem | None:
        if not self.items:
            return None
        if self.selected_index < 0 or self.selected_index >= len(self.items):
            return None
        return self.items[self.selected_index]

    @property
    def selected_task(self) -> _OperationTaskItem | None:
        tasks = _dashboard_tasks(self.selected_operation_payload)
        if not tasks:
            return None
        if self.selected_task_index < 0 or self.selected_task_index >= len(tasks):
            return None
        return tasks[self.selected_task_index]

    @property
    def selected_timeline_event(self) -> _TimelineEventItem | None:
        events = _session_timeline_events(self.selected_operation_payload, self.selected_task)
        if not events:
            return None
        if self.selected_timeline_index < 0 or self.selected_timeline_index >= len(events):
            return None
        return events[self.selected_timeline_index]


class _FleetWorkbenchController:
    def __init__(
        self,
        *,
        load_payload: Callable[[], Awaitable[dict[str, object]]],
        load_operation_payload: Callable[[str], Awaitable[dict[str, object] | None]],
        pause_operation: Callable[[str], Awaitable[str]],
        unpause_operation: Callable[[str], Awaitable[str]],
        interrupt_operation: Callable[[str, str | None], Awaitable[str]],
        cancel_operation: Callable[[str], Awaitable[str]],
    ) -> None:
        self._load_payload = load_payload
        self._load_operation_payload = load_operation_payload
        self._pause_operation = pause_operation
        self._unpause_operation = unpause_operation
        self._interrupt_operation = interrupt_operation
        self._cancel_operation = cancel_operation
        self.state = _FleetWorkbenchState()

    async def refresh(self) -> None:
        """Reload fleet truth and refresh the selected operation detail."""

        payload = await self._load_payload()
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
            if self.state.view_level == "session"
            and self.state.selected_timeline_event is not None
            else None
        )
        items = _payload_items(payload)
        self.state.items = items
        self.state.project = _optional_text(payload.get("project"))
        self.state.total_operations = _optional_int(payload.get("total_operations"))
        if not items:
            self.state.selected_index = 0
            self.state.selected_operation_payload = None
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
        self._restore_selected_task(selected_task_id)
        self._restore_selected_timeline_event(selected_event_summary)

    async def handle_key(self, key: str) -> bool:
        """Apply one keystroke and return whether the workbench should keep running."""

        normalized = _normalize_key(key)
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
            self._jump_to_next_attention()
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

    def render(self) -> Group:
        """Build the Rich renderable for the current workbench state."""

        header = self._header_lines()
        left = Panel(
            self._render_left_pane(),
            title=(
                "Event Context"
                if self.state.view_level == "forensic"
                else
                "Timeline"
                if self.state.view_level == "session"
                else "Tasks"
                if self.state.view_level == "operation"
                else "Operations"
            ),
            border_style="cyan",
        )
        right = Panel(
            self._render_right_pane(),
            title=self._right_pane_title(),
            border_style="green",
        )
        footer = self._render_footer_text()
        return Group(
            Panel("\n".join(header), border_style="blue"),
            Columns([left, right], equal=True, expand=True),
            Panel(footer, border_style="magenta"),
        )

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
        if key == "enter":
            task = self.state.selected_task
            if task is None or task.linked_session_id is None:
                self.state.last_message = "The selected task has no linked session to inspect."
                return True
            self.state.view_level = "session"
            self.state.session_panel_mode = "timeline"
            self._restore_selected_timeline_event(None)
            return True
        if key == "i":
            self.state.operation_panel_mode = "detail"
            return True
        if key == "d":
            self.state.operation_panel_mode = "decisions"
            return True
        if key == "t":
            self.state.operation_panel_mode = "events"
            return True
        if key == "m":
            self.state.operation_panel_mode = "memory"
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
                task.task_id
                if task is not None and task.linked_session_id is not None
                else None
            )
            self.state.last_message = await self._interrupt_operation(
                selected.operation_id,
                task_id,
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
        if key == "enter":
            if self.state.selected_timeline_event is None:
                self.state.last_message = "No timeline item is selected."
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
                task.task_id
                if task is not None and task.linked_session_id is not None
                else None
            )
            self.state.last_message = await self._interrupt_operation(
                selected.operation_id,
                task_id,
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
            return
        self.state.selected_operation_payload = await self._load_operation_payload(
            selected.operation_id
        )

    def _restore_selected_task(self, selected_task_id: str | None) -> None:
        tasks = _dashboard_tasks(self.state.selected_operation_payload)
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
        events = _session_timeline_events(
            self.state.selected_operation_payload,
            self.state.selected_task,
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
            self.state.selected_timeline_index,
            len(events) - 1,
        )

    def _move_selection(self, delta: int) -> None:
        if not self.state.items:
            return
        self.state.selected_index = (self.state.selected_index + delta) % len(self.state.items)

    def _move_task_selection(self, delta: int) -> None:
        tasks = _dashboard_tasks(self.state.selected_operation_payload)
        if not tasks:
            return
        self.state.selected_task_index = (self.state.selected_task_index + delta) % len(tasks)
        self._restore_selected_timeline_event(None)

    def _move_timeline_selection(self, delta: int) -> None:
        events = _session_timeline_events(
            self.state.selected_operation_payload,
            self.state.selected_task,
        )
        if not events:
            return
        self.state.selected_timeline_index = (
            self.state.selected_timeline_index + delta
        ) % len(events)

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

    def _render_left_pane(self) -> Table:
        if self.state.view_level == "forensic":
            return self._render_forensic_context()
        if self.state.view_level == "session":
            return self._render_session_timeline()
        if self.state.view_level == "operation":
            return self._render_task_board()
        return self._render_list_table()

    def _render_right_pane(self) -> Table | Text:
        if self.state.view_level == "forensic":
            return self._render_forensic_transcript_panel()
        if self.state.view_level == "session":
            return self._render_session_panel()
        if self.state.view_level == "operation":
            return self._render_operation_panel()
        return self._render_detail_table()

    def _header_lines(self) -> list[str]:
        breadcrumb = "fleet"
        if self.state.view_level == "operation" and self.state.selected_item is not None:
            breadcrumb += f" > {self.state.selected_item.operation_id}"
        if self.state.view_level == "session" and self.state.selected_item is not None:
            breadcrumb += f" > {self.state.selected_item.operation_id}"
            if self.state.selected_task is not None:
                breadcrumb += f" > {self.state.selected_task.task_short_id}"
        if self.state.view_level == "forensic" and self.state.selected_item is not None:
            breadcrumb += f" > {self.state.selected_item.operation_id}"
            if self.state.selected_task is not None:
                breadcrumb += f" > {self.state.selected_task.task_short_id}"
            if self.state.selected_timeline_event is not None:
                breadcrumb += (
                    f" > iter-{self.state.selected_timeline_event.iteration}"
                    f":{self.state.selected_timeline_event.event_type}"
                )
        return [
            f"breadcrumb={breadcrumb}",
            (
                f"project={self.state.project}"
                if self.state.project is not None
                else "project=all"
            )
            + f"  operations={self.state.total_operations}",
        ]

    def _right_pane_title(self) -> str:
        if self.state.view_level == "operation":
            mode = self.state.operation_panel_mode.title()
            if self.state.selected_task is not None:
                return f"{mode}: {self.state.selected_task.task_short_id}"
            return mode
        if self.state.view_level == "session":
            if self.state.session_panel_mode == "raw_transcript":
                return "Raw Transcript"
            event = self.state.selected_timeline_event
            if event is not None:
                return f"Timeline: iter {event.iteration}"
            return "Timeline"
        if self.state.view_level == "forensic":
            event = self.state.selected_timeline_event
            if event is not None:
                return f"Forensic Transcript: iter {event.iteration}"
            return "Forensic Transcript"
        if self.state.selected_item is not None:
            return f"Detail: {self.state.selected_item.operation_id}"
        return "Detail"

    def _render_list_table(self) -> Table:
        table = Table(expand=True, box=None, show_header=True)
        table.add_column("", no_wrap=True)
        table.add_column("Op", no_wrap=True)
        table.add_column("State", no_wrap=True)
        table.add_column("Signal", no_wrap=True)
        table.add_column("Objective")
        if not self.state.items:
            table.add_row("", "-", "-", "-", "No active operations.")
            return table
        for index, item in enumerate(self.state.items):
            marker = ">" if index == self.state.selected_index else " "
            signal = _signal_text(item)
            table.add_row(
                marker,
                item.operation_id,
                _status_text(item),
                signal,
                item.objective_brief,
            )
        return table

    def _render_task_board(self) -> Table:
        table = Table(expand=True, box=None, show_header=True)
        table.add_column("", no_wrap=True)
        table.add_column("Lane", no_wrap=True)
        table.add_column("Task", no_wrap=True)
        table.add_column("State", no_wrap=True)
        table.add_column("Title")
        tasks = _dashboard_tasks(self.state.selected_operation_payload)
        if not tasks:
            table.add_row("", "-", "-", "-", "No tasks.")
            return table
        for index, task in enumerate(tasks):
            marker = ">" if index == self.state.selected_task_index else " "
            table.add_row(
                marker,
                _task_lane(task),
                task.task_short_id,
                task.status,
                task.title,
            )
        return table

    def _render_session_timeline(self) -> Table:
        table = Table(expand=True, box=None, show_header=True)
        table.add_column("", no_wrap=True)
        table.add_column("Iter", no_wrap=True)
        table.add_column("Type", no_wrap=True)
        table.add_column("Summary")
        events = _session_timeline_events(
            self.state.selected_operation_payload,
            self.state.selected_task,
        )
        if not events:
            table.add_row("", "-", "-", "No session timeline events.")
            return table
        for index, event in enumerate(events):
            marker = ">" if index == self.state.selected_timeline_index else " "
            table.add_row(
                marker,
                str(event.iteration),
                event.event_type,
                event.summary,
            )
        return table

    def _render_forensic_context(self) -> Table:
        table = Table(expand=True, box=None, show_header=False)
        table.add_column("Field", no_wrap=True, style="bold")
        table.add_column("Value")
        event = self.state.selected_timeline_event
        task = self.state.selected_task
        if event is None:
            table.add_row("Event", "No forensic event selected.")
            return table
        if task is not None:
            table.add_row("Task", f"{task.task_short_id} · {task.title}")
        table.add_row("Type", event.event_type)
        table.add_row("Iteration", str(event.iteration))
        if event.task_id is not None:
            table.add_row("Task id", event.task_id)
        if event.session_id is not None:
            table.add_row("Session", event.session_id)
        table.add_row("Summary", event.summary)
        return table

    def _render_detail_table(self) -> Table:
        table = Table(expand=True, box=None, show_header=False)
        table.add_column("Field", no_wrap=True, style="bold")
        table.add_column("Value")
        selected = self.state.selected_item
        detail = self.state.selected_operation_payload
        if selected is None:
            table.add_row("Status", "No operation selected.")
            return table
        table.add_row("Operation", selected.operation_id)
        table.add_row("Status", _status_text(selected))
        table.add_row("Objective", selected.objective_brief)
        if selected.project_profile_name is not None:
            table.add_row("Project", selected.project_profile_name)
        if selected.focus_brief is not None:
            table.add_row("Focus", selected.focus_brief)
        if selected.latest_outcome_brief is not None:
            table.add_row("Latest", selected.latest_outcome_brief)
        if selected.blocker_brief is not None:
            table.add_row("Blocker", selected.blocker_brief)
        if selected.runtime_alert is not None:
            table.add_row("Alert", selected.runtime_alert)
        if selected.attention_briefs:
            table.add_row("Attention", "\n".join(selected.attention_briefs))
        if not isinstance(detail, dict):
            table.add_row("Detail", "No operation detail available.")
            return table
        summary = detail.get("summary")
        if isinstance(summary, dict):
            work_summary = _optional_text(summary.get("work_summary"))
            next_step = _optional_text(summary.get("next_step"))
            verification = _optional_text(summary.get("verification_summary"))
            if work_summary is not None:
                table.add_row("Work", work_summary)
            if next_step is not None:
                table.add_row("Next", next_step)
            if verification is not None:
                table.add_row("Verify", verification)
        context = detail.get("context")
        if isinstance(context, dict):
            run_mode = _optional_text(context.get("run_mode"))
            involvement = _optional_text(context.get("involvement_level"))
            if run_mode is not None:
                table.add_row("Run mode", run_mode)
            if involvement is not None:
                table.add_row("Involvement", involvement)
            active_session = context.get("active_session")
            if isinstance(active_session, dict):
                session_status = _optional_text(active_session.get("status")) or "-"
                adapter = _optional_text(active_session.get("adapter_key")) or "-"
                table.add_row("Session", f"{adapter} [{session_status}]")
                waiting_reason = _optional_text(active_session.get("waiting_reason"))
                if waiting_reason is not None:
                    table.add_row("Waiting", waiting_reason)
            open_attention = context.get("open_attention")
            if isinstance(open_attention, list) and open_attention:
                titles = [
                    str(item.get("title"))
                    for item in open_attention
                    if isinstance(item, dict) and item.get("title")
                ]
                if titles:
                    table.add_row("Open attention", "\n".join(titles[:3]))
        return table

    def _render_operation_panel(self) -> Table | Text:
        if self.state.operation_panel_mode == "decisions":
            return self._render_decisions_panel()
        if self.state.operation_panel_mode == "events":
            return self._render_events_panel()
        if self.state.operation_panel_mode == "memory":
            return self._render_memory_panel()
        return self._render_task_detail_table()

    def _render_session_panel(self) -> Table | Text:
        if self.state.session_panel_mode == "raw_transcript":
            return self._render_raw_transcript_panel()
        return self._render_timeline_detail_table()

    def _render_task_detail_table(self) -> Table:
        table = Table(expand=True, box=None, show_header=False)
        table.add_column("Field", no_wrap=True, style="bold")
        table.add_column("Value")
        task = self.state.selected_task
        payload = (
            self.state.selected_operation_payload
            if isinstance(self.state.selected_operation_payload, dict)
            else {}
        )
        if task is None:
            table.add_row("Task", "No task selected.")
            return table
        table.add_row("Task", f"{task.task_short_id} · {task.title}")
        table.add_row("Status", task.status)
        table.add_row("Priority", str(task.priority))
        table.add_row("Goal", task.goal)
        table.add_row("Done", task.definition_of_done)
        if task.assigned_agent is not None:
            table.add_row("Agent", task.assigned_agent)
        if task.linked_session_id is not None:
            table.add_row("Session", task.linked_session_id)
        if task.dependencies:
            table.add_row("Dependencies", ", ".join(task.dependencies))
        if task.memory_refs:
            table.add_row("Memory refs", ", ".join(task.memory_refs))
        if task.artifact_refs:
            table.add_row("Artifact refs", ", ".join(task.artifact_refs))
        if task.notes:
            table.add_row("Notes", "\n".join(task.notes))
        session_line = _task_session_summary(payload, task)
        if session_line is not None:
            table.add_row("Session detail", session_line)
        task_attentions = _task_attention_titles(payload, task)
        if task_attentions:
            table.add_row("Attention", "\n".join(task_attentions))
        return table

    def _render_decisions_panel(self) -> Text:
        payload = self.state.selected_operation_payload
        decisions = _filtered_decisions(payload, self.state.selected_task)
        if not decisions:
            return Text("No decision memos for the selected scope.")
        return Text("\n\n".join(decisions))

    def _render_events_panel(self) -> Text:
        payload = self.state.selected_operation_payload
        events = payload.get("recent_events") if isinstance(payload, dict) else None
        if not isinstance(events, list) or not events:
            return Text("No recent events.")
        return Text("\n".join(str(item) for item in events if isinstance(item, str)))

    def _render_memory_panel(self) -> Text:
        entries = _filtered_memory_entries(
            self.state.selected_operation_payload,
            self.state.selected_task,
        )
        if not entries:
            return Text("No memory entries for the selected scope.")
        return Text("\n\n".join(entries))

    def _render_timeline_detail_table(self) -> Table:
        table = Table(expand=True, box=None, show_header=False)
        table.add_column("Field", no_wrap=True, style="bold")
        table.add_column("Value")
        event = self.state.selected_timeline_event
        if event is None:
            table.add_row("Timeline", "No event selected.")
            return table
        table.add_row("Type", event.event_type)
        table.add_row("Iteration", str(event.iteration))
        if event.task_id is not None:
            table.add_row("Task", event.task_id)
        if event.session_id is not None:
            table.add_row("Session", event.session_id)
        table.add_row("Summary", event.summary)
        return table

    def _render_raw_transcript_panel(self) -> Text:
        payload = self.state.selected_operation_payload
        lines = _raw_transcript_lines(payload)
        event = self.state.selected_timeline_event
        prefix: list[str] = []
        if event is not None:
            prefix = [
                f"Focused event: {event.summary}",
                f"event_type={event.event_type} iteration={event.iteration}",
                "",
            ]
        if not lines:
            return Text(
                "\n".join(prefix + ["No raw transcript available for the selected session."])
            )
        return Text("\n".join(prefix + lines))

    def _render_forensic_transcript_panel(self) -> Text:
        return self._render_raw_transcript_panel()

    def _render_footer_text(self) -> Text:
        selected = self.state.selected_item
        if self.state.pending_confirmation is not None and selected is not None:
            return Text(
                f"Cancel {self.state.pending_confirmation}? [y/N]  "
                "Any non-affirmative key aborts."
            )
        if self.state.last_message is not None:
            return Text(self.state.last_message)
        if self.state.view_level == "forensic":
            return Text("Esc back to session timeline  q quit")
        if self.state.view_level == "session":
            return Text(
                "j/k move  r raw transcript toggle  Esc back  s interrupt task/session  "
                "p pause  u unpause  c cancel  q quit"
            )
        if self.state.view_level == "operation":
            return Text(
                "j/k move  Enter session  i detail  d decisions  t events  m memory  "
                "Esc back  p pause  u unpause  s interrupt task/session  c cancel  "
                "r refresh  q quit"
            )
        help_line = Text(
            "j/k or arrows move  Enter open  tab next-attention  p pause  u unpause  "
            "s interrupt  c cancel  r refresh  q quit"
        )
        if selected is None:
            return help_line
        return Text(f"{selected.operation_id} selected. ") + help_line


async def run_fleet_workbench(
    *,
    controller: _FleetWorkbenchController,
    poll_interval: float,
) -> None:
    """Run the interactive fleet workbench event loop."""

    from rich.console import Console
    from rich.live import Live

    console = Console()
    await controller.refresh()
    with _raw_stdin(sys.stdin.fileno()), Live(
        controller.render(),
        console=console,
        refresh_per_second=8,
        screen=True,
    ) as live:
        while True:
            key = _read_key(timeout_seconds=poll_interval)
            if key is None:
                await controller.refresh()
                live.update(controller.render(), refresh=True)
                continue
            keep_running = await controller.handle_key(key)
            live.update(controller.render(), refresh=True)
            if not keep_running:
                return


def build_fleet_workbench_controller(
    *,
    load_payload: Callable[[], Awaitable[dict[str, object]]],
    load_operation_payload: Callable[[str], Awaitable[dict[str, object] | None]],
    pause_operation: Callable[[str], Awaitable[str]],
    unpause_operation: Callable[[str], Awaitable[str]],
    interrupt_operation: Callable[[str, str | None], Awaitable[str]],
    cancel_operation: Callable[[str], Awaitable[str]],
) -> _FleetWorkbenchController:
    """Create the fleet workbench controller."""

    return _FleetWorkbenchController(
        load_payload=load_payload,
        load_operation_payload=load_operation_payload,
        pause_operation=pause_operation,
        unpause_operation=unpause_operation,
        interrupt_operation=interrupt_operation,
        cancel_operation=cancel_operation,
    )


def _payload_items(payload: dict[str, object]) -> list[_FleetItem]:
    items: list[_FleetItem] = []
    for bucket in ("needs_attention", "active", "recent"):
        raw_items = payload.get(bucket)
        if not isinstance(raw_items, list):
            continue
        for entry in raw_items:
            if not isinstance(entry, dict):
                continue
            item = _FleetItem.from_payload(entry)
            items.append(item)
    return items


def _dashboard_tasks(payload: dict[str, object] | None) -> list[_OperationTaskItem]:
    if not isinstance(payload, dict):
        return []
    raw_tasks = payload.get("tasks")
    if not isinstance(raw_tasks, list):
        return []
    return [
        _OperationTaskItem.from_payload(item)
        for item in raw_tasks
        if isinstance(item, dict)
    ]


def _session_timeline_events(
    payload: dict[str, object] | None,
    task: _OperationTaskItem | None,
) -> list[_TimelineEventItem]:
    if not isinstance(payload, dict):
        return []
    raw_events = payload.get("timeline_events")
    if not isinstance(raw_events, list):
        return []
    session_id = task.linked_session_id if task is not None else None
    task_id = task.task_id if task is not None else None
    events = [
        _TimelineEventItem.from_payload(item)
        for item in raw_events
        if isinstance(item, dict)
    ]
    if session_id is None and task_id is None:
        return events
    filtered = [
        item
        for item in events
        if item.session_id == session_id or item.task_id == task_id
    ]
    return filtered or events


def _optional_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _optional_int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _text_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str))


def _status_text(item: _FleetItem) -> str:
    base = item.status
    if item.scheduler_state != "active":
        return f"{base}/{item.scheduler_state}"
    return base


def _signal_text(item: _FleetItem) -> str:
    if item.runtime_alert is not None:
        return "!! alert"
    if item.open_attention_count > 0:
        return f"!! {item.open_attention_count}"
    return "-"


def _task_lane(task: _OperationTaskItem) -> str:
    if task.status == "running":
        return "RUNNING"
    if task.status == "completed":
        return "COMPLETED"
    if task.status == "failed":
        return "FAILED"
    if task.status == "cancelled":
        return "CANCELLED"
    if task.dependencies:
        return "BLOCKED"
    return "READY"


def _task_session_summary(
    payload: dict[str, object],
    task: _OperationTaskItem,
) -> str | None:
    raw_sessions = payload.get("sessions")
    if not isinstance(raw_sessions, list):
        return None
    for session in raw_sessions:
        if not isinstance(session, dict):
            continue
        if _optional_text(session.get("session_id")) != task.linked_session_id:
            continue
        adapter = _optional_text(session.get("adapter_key")) or "-"
        status = _optional_text(session.get("status")) or "-"
        waiting = _optional_text(session.get("waiting_reason"))
        summary = f"{adapter} [{status}]"
        if waiting is not None:
            summary += f" waiting={waiting}"
        return summary
    return None


def _task_attention_titles(
    payload: dict[str, object],
    task: _OperationTaskItem,
) -> list[str]:
    raw_attention = payload.get("attention") if isinstance(payload, dict) else None
    if not isinstance(raw_attention, list):
        return []
    lines: list[str] = []
    for item in raw_attention:
        if not isinstance(item, dict):
            continue
        target_id = _optional_text(item.get("target_id"))
        if target_id not in {None, task.task_id}:
            continue
        title = _optional_text(item.get("title"))
        if title is not None:
            lines.append(title)
    return lines


def _filtered_decisions(
    payload: dict[str, object] | None,
    task: _OperationTaskItem | None,
) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw_decisions = payload.get("decision_memos")
    if not isinstance(raw_decisions, list):
        return []
    entries: list[str] = []
    for item in raw_decisions:
        if not isinstance(item, dict):
            continue
        task_id = _optional_text(item.get("task_id"))
        if task is not None and task_id not in {None, task.task_id}:
            continue
        iteration = _optional_int(item.get("iteration"))
        chosen_action = _optional_text(item.get("chosen_action")) or "-"
        rationale = _optional_text(item.get("rationale")) or "-"
        context = _optional_text(item.get("decision_context_summary"))
        parts = [f"iter {iteration}: {chosen_action}"]
        if context is not None:
            parts.append(f"context: {context}")
        parts.append(f"why: {rationale}")
        entries.append("\n".join(parts))
    return entries


def _filtered_memory_entries(
    payload: dict[str, object] | None,
    task: _OperationTaskItem | None,
) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw_entries = payload.get("memory_entries")
    if not isinstance(raw_entries, list):
        return []
    rendered: list[str] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        scope_id = _optional_text(item.get("scope_id"))
        memory_id = _optional_text(item.get("memory_id")) or "-"
        freshness = _optional_text(item.get("freshness")) or "-"
        scope = _optional_text(item.get("scope")) or "-"
        summary = _optional_text(item.get("summary")) or "-"
        if (
            task is not None
            and scope_id not in {None, task.task_id}
            and memory_id not in task.memory_refs
        ):
            continue
        rendered.append(f"{memory_id} [{scope}/{freshness}]\n{summary}")
    return rendered


def _raw_transcript_lines(payload: dict[str, object] | None) -> list[str]:
    if not isinstance(payload, dict):
        return []
    transcript = payload.get("upstream_transcript")
    if isinstance(transcript, dict):
        events = transcript.get("events")
        if isinstance(events, list):
            return [str(item) for item in events if isinstance(item, str)]
    codex_log = payload.get("codex_log")
    if isinstance(codex_log, list):
        return [str(item) for item in codex_log if isinstance(item, str)]
    return []


def _normalize_key(key: str) -> str:
    if key == "\x1b[A":
        return "up"
    if key == "\x1b[B":
        return "down"
    if key == "\x1b":
        return "esc"
    if key == "\t":
        return "tab"
    if key == "\x03":
        return "ctrl+c"
    if key == "\r":
        return "enter"
    return key.lower()


def _read_key(*, timeout_seconds: float) -> str | None:
    ready, _, _ = select.select([sys.stdin], [], [], timeout_seconds)
    if not ready:
        return None
    first = sys.stdin.read(1)
    if first != "\x1b":
        return first
    ready, _, _ = select.select([sys.stdin], [], [], 0.01)
    if not ready:
        return first
    second = sys.stdin.read(1)
    if second != "[":
        return first + second
    ready, _, _ = select.select([sys.stdin], [], [], 0.01)
    if not ready:
        return first + second
    third = sys.stdin.read(1)
    return first + second + third


class _raw_stdin:
    def __init__(self, file_descriptor: int) -> None:
        self._file_descriptor = file_descriptor
        self._original_settings: _TerminalSettings | None = None

    def __enter__(self) -> _raw_stdin:
        self._original_settings = termios.tcgetattr(self._file_descriptor)
        tty.setcbreak(self._file_descriptor)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._original_settings is not None:
            termios.tcsetattr(
                self._file_descriptor,
                termios.TCSADRAIN,
                self._original_settings,
            )
