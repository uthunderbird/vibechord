"""TUI view-model, reducer, line-oriented, and curses runtime helpers."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TextIO

from vibechord.domain import CommandName, FleetRowDTO, OperationCommand, StatusDTO
from vibechord.workspace import AppContext


class Screen(Protocol):
    """Small curses-compatible screen protocol."""

    def clear(self) -> None:
        """Clear the screen."""

    def addstr(self, y: int, x: int, text: str) -> None:
        """Add text at one location."""

    def refresh(self) -> None:
        """Refresh the terminal."""

    def getch(self) -> int:
        """Read one key code."""


@dataclass(frozen=True)
class TuiState:
    """TUI state derived from shared query payloads."""

    scope: str
    selected_index: int
    fleet_rows: tuple[FleetRowDTO, ...]
    operation: StatusDTO | None = None
    pending_confirmation: str | None = None


@dataclass(frozen=True)
class ReducerResult:
    """Result of handling one key event."""

    state: TuiState
    command: OperationCommand | None = None


def fleet_view(rows: tuple[FleetRowDTO, ...], selected_index: int = 0) -> TuiState:
    """Build a fleet-level view model."""

    return TuiState(scope="fleet", selected_index=selected_index, fleet_rows=rows)


def operation_view(operation: StatusDTO) -> TuiState:
    """Build an operation-level view model."""

    return TuiState(
        scope="operation", selected_index=0, fleet_rows=(), operation=operation
    )


def render(state: TuiState) -> str:
    """Render a deterministic text snapshot for tests."""

    if state.scope == "fleet":
        lines = ["Fleet"]
        for index, row in enumerate(state.fleet_rows):
            marker = ">" if index == state.selected_index else " "
            stale = " stale" if row.stale else ""
            attention = f" attention={row.attention}" if row.attention else ""
            lines.append(f"{marker} {row.operation_id} {row.status}{stale}{attention}")
        return "\n".join(lines)
    if state.operation is None:
        return "Operation\nempty"
    stale = " stale" if state.operation.stale else ""
    attention = (
        f"\nattention: {state.operation.attention_prompt}"
        if state.operation.attention_prompt
        else ""
    )
    return (
        f"Operation {state.operation.operation_id}\n"
        f"{state.operation.status}{stale}{attention}"
    )


def render_fullscreen(state: TuiState) -> tuple[str, ...]:
    """Render a full-screen snapshot as bounded lines."""

    lines = [
        "vibechord",
        "q quit  r refresh  enter open  esc back",
        "m message  a answer  p pause/resume  i interrupt  c cancel",
        "",
    ]
    lines.extend(render(state).splitlines())
    if state.pending_confirmation == "cancel":
        lines.append("")
        lines.append("press c again to confirm cancel")
    return tuple(lines)


def reduce_key(
    state: TuiState,
    key: str,
    command_id: str,
    text: str = "",
    attention_id: str = "",
) -> ReducerResult:
    """Handle one key event without mutating canonical state."""

    if key in {"j", "down"} and state.fleet_rows:
        next_index = min(state.selected_index + 1, len(state.fleet_rows) - 1)
        return ReducerResult(
            state=TuiState(state.scope, next_index, state.fleet_rows, state.operation)
        )
    if key in {"k", "up"} and state.fleet_rows:
        next_index = max(state.selected_index - 1, 0)
        return ReducerResult(
            state=TuiState(state.scope, next_index, state.fleet_rows, state.operation)
        )
    operation_id = _current_operation_id(state)
    if operation_id is None:
        return ReducerResult(state=state)
    if key == "m" and text:
        return ReducerResult(
            state=state,
            command=OperationCommand(
                name=CommandName.POST_MESSAGE,
                command_id=command_id,
                operation_id=operation_id,
                payload={"text": text},
            ),
        )
    if key == "a" and text and attention_id:
        return ReducerResult(
            state=state,
            command=OperationCommand(
                name=CommandName.ANSWER_ATTENTION,
                command_id=command_id,
                operation_id=operation_id,
                payload={"attention_id": attention_id, "text": text},
            ),
        )
    if key == "c":
        if state.pending_confirmation == "cancel":
            return ReducerResult(
                state=TuiState(
                    state.scope, state.selected_index, state.fleet_rows, state.operation
                ),
                command=OperationCommand(
                    name=CommandName.CANCEL,
                    command_id=command_id,
                    operation_id=operation_id,
                ),
            )
        return ReducerResult(
            state=TuiState(
                state.scope,
                state.selected_index,
                state.fleet_rows,
                state.operation,
                pending_confirmation="cancel",
            )
        )
    return ReducerResult(state=state)


def _current_operation_id(state: TuiState) -> str | None:
    if state.operation is not None:
        return state.operation.operation_id
    if not state.fleet_rows:
        return None
    return state.fleet_rows[state.selected_index].operation_id


def run_curses(
    context: AppContext,
    screen: Screen,
    once: bool = False,
    input_provider: Callable[[str], str] | None = None,
) -> None:
    """Run a curses-compatible full-screen TUI loop."""

    state = fleet_view(context.projection_service.fleet())
    while True:
        _draw_screen(screen, state)
        if once:
            return
        key = screen.getch()
        if key in {ord("q"), ord("Q")}:
            return
        state = _handle_curses_key(context, state, key, input_provider)


def _draw_screen(screen: Screen, state: TuiState) -> None:
    screen.clear()
    for index, line in enumerate(render_fullscreen(state)):
        screen.addstr(index, 0, line)
    screen.refresh()


def _handle_curses_key(
    context: AppContext,
    state: TuiState,
    key: int,
    input_provider: Callable[[str], str] | None,
) -> TuiState:
    if key in {ord("r"), ord("R")}:
        return _refresh_state(context, state)
    if key in {10, 13} and state.scope == "fleet":
        operation_id = _current_operation_id(state)
        if operation_id is None:
            return state
        return operation_view(context.projection_service.status(operation_id))
    if key == 27:
        return fleet_view(context.projection_service.fleet())
    if key in {ord("j"), ord("J")}:
        return reduce_key(state, "j", command_id="tui-navigation").state
    if key in {ord("k"), ord("K")}:
        return reduce_key(state, "k", command_id="tui-navigation").state

    operation_id = _current_operation_id(state)
    if operation_id is None:
        return state
    command = _command_for_curses_key(context, state, operation_id, key, input_provider)
    if command is not None:
        context.command_application.apply(command)
    if key in {ord("c"), ord("C")} and state.pending_confirmation != "cancel":
        return reduce_key(state, "c", command_id="tui-cancel").state
    return _refresh_state(context, state)


def _command_for_curses_key(
    context: AppContext,
    state: TuiState,
    operation_id: str,
    key: int,
    input_provider: Callable[[str], str] | None,
) -> OperationCommand | None:
    command_id = f"tui-{uuid.uuid4()}"
    if key in {ord("m"), ord("M")}:
        text = _input(input_provider, "message")
        return reduce_key(state, "m", command_id=command_id, text=text).command
    if key in {ord("a"), ord("A")}:
        status = context.projection_service.status(operation_id)
        if status.attention_id is None:
            return None
        text = _input(input_provider, "answer")
        return reduce_key(
            operation_view(status),
            "a",
            command_id=command_id,
            text=text,
            attention_id=status.attention_id,
        ).command
    if key in {ord("p"), ord("P")}:
        status = context.projection_service.status(operation_id)
        name = CommandName.RESUME if status.status == "paused" else CommandName.PAUSE
        return OperationCommand(
            name=name, command_id=command_id, operation_id=operation_id
        )
    if key in {ord("i"), ord("I")}:
        return OperationCommand(
            name=CommandName.INTERRUPT,
            command_id=command_id,
            operation_id=operation_id,
        )
    if key in {ord("c"), ord("C")} and state.pending_confirmation == "cancel":
        return OperationCommand(
            name=CommandName.CANCEL,
            command_id=command_id,
            operation_id=operation_id,
        )
    return None


def _input(input_provider: Callable[[str], str] | None, prompt: str) -> str:
    if input_provider is None:
        return ""
    return input_provider(prompt)


def _refresh_state(context: AppContext, state: TuiState) -> TuiState:
    if state.scope == "operation" and state.operation is not None:
        return operation_view(
            context.projection_service.status(state.operation.operation_id)
        )
    rows = context.projection_service.fleet()
    selected = min(state.selected_index, max(len(rows) - 1, 0))
    return fleet_view(rows, selected)


def run_terminal(
    context: AppContext,
    once: bool = False,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> None:
    """Run a small terminal TUI loop over shared projections and commands."""

    if not once and input_stream is None and output_stream is None:
        import curses

        curses.wrapper(lambda screen: run_curses(context, screen))
        return

    import sys

    source = input_stream or sys.stdin
    sink = output_stream or sys.stdout
    state = fleet_view(context.projection_service.fleet())
    sink.write(render(state) + "\n")
    sink.flush()
    if once:
        return
    for line in source:
        command_text = line.strip()
        if command_text in {"q", "quit"}:
            return
        if command_text in {"j", "k", "down", "up"}:
            result = reduce_key(state, command_text, command_id="tui-navigation")
            state = result.state
        elif command_text.startswith("m "):
            result = reduce_key(
                state,
                "m",
                command_id=f"tui-message-{state.selected_index}",
                text=command_text[2:],
            )
            if result.command is not None:
                context.command_application.apply(result.command)
        elif command_text == "c":
            result = reduce_key(state, "c", command_id="tui-cancel")
            state = result.state
            if result.command is not None:
                context.command_application.apply(result.command)
        state = fleet_view(context.projection_service.fleet(), state.selected_index)
        sink.write(render(state) + "\n")
        sink.flush()
