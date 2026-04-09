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


@dataclass(slots=True)
class _FleetWorkbenchState:
    items: list[_FleetItem] = field(default_factory=list)
    selected_index: int = 0
    selected_operation_payload: dict[str, object] | None = None
    project: str | None = None
    total_operations: int = 0
    last_message: str | None = None
    pending_confirmation: str | None = None

    @property
    def selected_item(self) -> _FleetItem | None:
        if not self.items:
            return None
        if self.selected_index < 0 or self.selected_index >= len(self.items):
            return None
        return self.items[self.selected_index]


class _FleetWorkbenchController:
    def __init__(
        self,
        *,
        load_payload: Callable[[], Awaitable[dict[str, object]]],
        load_operation_payload: Callable[[str], Awaitable[dict[str, object] | None]],
        pause_operation: Callable[[str], Awaitable[str]],
        unpause_operation: Callable[[str], Awaitable[str]],
        interrupt_operation: Callable[[str], Awaitable[str]],
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
        items = _payload_items(payload)
        self.state.items = items
        self.state.project = _optional_text(payload.get("project"))
        self.state.total_operations = _optional_int(payload.get("total_operations"))
        if not items:
            self.state.selected_index = 0
            self.state.selected_operation_payload = None
            self.state.pending_confirmation = None
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

    async def handle_key(self, key: str) -> bool:
        """Apply one keystroke and return whether the workbench should keep running."""

        normalized = _normalize_key(key)
        if self.state.pending_confirmation is not None:
            return await self._handle_confirmation_key(normalized)
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
        if normalized == "p":
            self.state.last_message = await self._pause_operation(selected.operation_id)
            await self.refresh()
            return True
        if normalized == "u":
            self.state.last_message = await self._unpause_operation(selected.operation_id)
            await self.refresh()
            return True
        if normalized == "s":
            self.state.last_message = await self._interrupt_operation(selected.operation_id)
            await self.refresh()
            return True
        if normalized == "c":
            self.state.pending_confirmation = selected.operation_id
            self.state.last_message = None
            return True
        return True

    def render(self) -> Group:
        """Build the Rich renderable for the current workbench state."""

        header = [
            "Fleet Workbench",
            (
                f"project={self.state.project}"
                if self.state.project is not None
                else "project=all"
            ),
            f"operations={self.state.total_operations}",
        ]
        left = Panel(self._render_list_table(), title="Operations", border_style="cyan")
        right = Panel(
            self._render_detail_table(),
            title=(
                f"Detail: {self.state.selected_item.operation_id}"
                if self.state.selected_item is not None
                else "Detail"
            ),
            border_style="green",
        )
        footer = self._render_footer_text()
        return Group(
            Panel("  ".join(header), border_style="blue"),
            Columns([left, right], equal=True, expand=True),
            Panel(footer, border_style="magenta"),
        )

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

    def _move_selection(self, delta: int) -> None:
        if not self.state.items:
            return
        self.state.selected_index = (self.state.selected_index + delta) % len(self.state.items)

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

    def _render_footer_text(self) -> Text:
        selected = self.state.selected_item
        help_line = Text(
            "j/k or arrows move  tab next-attention  p pause  u unpause  s interrupt  "
            "c cancel  r refresh  q quit"
        )
        if self.state.pending_confirmation is not None and selected is not None:
            return Text(
                f"Cancel {self.state.pending_confirmation}? [y/N]  "
                "Any non-affirmative key aborts."
            )
        if self.state.last_message is not None:
            return Text(self.state.last_message)
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
    interrupt_operation: Callable[[str], Awaitable[str]],
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


def _optional_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _optional_int(value: object) -> int:
    return value if isinstance(value, int) else 0


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


def _normalize_key(key: str) -> str:
    if key == "\x1b[A":
        return "up"
    if key == "\x1b[B":
        return "down"
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
