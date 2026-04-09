from __future__ import annotations

import sys

import anyio
import pytest
from _pytest.monkeypatch import MonkeyPatch
from typer.testing import CliRunner

import agent_operator.cli.main as cli_main
from agent_operator.cli.tui import build_fleet_workbench_controller

runner = CliRunner()
pytestmark = pytest.mark.anyio


def _fleet_payload() -> dict[str, object]:
    return {
        "project": None,
        "total_operations": 3,
        "needs_attention": [
            {
                "operation_id": "op-attn",
                "status": "needs_human",
                "scheduler_state": "active",
                "objective_brief": "Answer a policy question",
                "open_attention_count": 1,
                "attention_briefs": ["[policy_gap] Need a human answer"],
                "bucket": "needs_attention",
            }
        ],
        "active": [
            {
                "operation_id": "op-run",
                "status": "running",
                "scheduler_state": "active",
                "objective_brief": "Ship the dashboard",
                "open_attention_count": 0,
                "bucket": "active",
            }
        ],
        "recent": [
            {
                "operation_id": "op-done",
                "status": "completed",
                "scheduler_state": "active",
                "objective_brief": "Write docs",
                "open_attention_count": 0,
                "bucket": "recent",
            }
        ],
    }


async def test_fleet_workbench_tab_jumps_to_next_attention() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
    )

    await controller.refresh()
    await controller.handle_key("j")
    assert controller.state.selected_item is not None
    assert controller.state.selected_item.operation_id == "op-run"

    await controller.handle_key("\t")
    assert controller.state.selected_item is not None
    assert controller.state.selected_item.operation_id == "op-attn"


async def test_fleet_workbench_cancel_requires_confirmation() -> None:
    calls: list[str] = []

    async def _cancel(operation_id: str) -> str:
        calls.append(operation_id)
        return f"cancelled {operation_id}"

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_cancel,
    )

    await controller.refresh()
    await controller.handle_key("c")
    assert controller.state.pending_confirmation == "op-attn"

    await controller.handle_key("n")
    assert calls == []
    assert controller.state.pending_confirmation is None
    assert controller.state.last_message == "Cancel aborted for op-attn."

    await controller.handle_key("c")
    await controller.handle_key("y")
    assert calls == ["op-attn"]
    assert controller.state.last_message == "cancelled op-attn"


async def test_fleet_workbench_pause_and_interrupt_dispatch_actions() -> None:
    calls: list[tuple[str, str, str | None]] = []

    async def _pause(operation_id: str) -> str:
        calls.append(("pause", operation_id, None))
        return f"paused {operation_id}"

    async def _interrupt(operation_id: str, task_id: str | None) -> str:
        calls.append(("interrupt", operation_id, task_id))
        return f"interrupted {operation_id}:{task_id or '-'}"

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_pause,
        unpause_operation=_unexpected_action,
        interrupt_operation=_interrupt,
        cancel_operation=_unexpected_action,
    )

    await controller.refresh()
    await controller.handle_key("p")
    await controller.handle_key("s")

    assert calls == [("pause", "op-attn", None), ("interrupt", "op-attn", None)]
    assert controller.state.last_message == "interrupted op-attn:-"


async def test_enter_opens_operation_view_and_escape_returns_to_fleet() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")

    assert controller.state.view_level == "operation"
    assert controller.state.selected_task is not None
    assert controller.state.selected_task.task_id == "task-1"

    await controller.handle_key("\x1b")
    assert controller.state.view_level == "fleet"


async def test_operation_view_switches_modes_and_moves_task_selection() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("j")

    assert controller.state.selected_task is not None
    assert controller.state.selected_task.task_id == "task-2"

    await controller.handle_key("d")
    assert controller.state.operation_panel_mode == "decisions"
    decisions_panel = controller.render()
    assert decisions_panel is not None

    await controller.handle_key("t")
    assert controller.state.operation_panel_mode == "events"

    await controller.handle_key("m")
    assert controller.state.operation_panel_mode == "memory"

    await controller.handle_key("i")
    assert controller.state.operation_panel_mode == "detail"


async def test_operation_view_enter_opens_session_view_and_escape_returns() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("\r")

    assert controller.state.view_level == "session"
    assert controller.state.selected_timeline_event is not None
    assert controller.state.selected_timeline_event.session_id == "session-1"

    await controller.handle_key("\x1b")
    assert controller.state.view_level == "operation"


async def test_session_view_toggles_raw_transcript_and_uses_task_scoped_interrupt() -> None:
    calls: list[tuple[str, str | None]] = []

    async def _interrupt(operation_id: str, task_id: str | None) -> str:
        calls.append((operation_id, task_id))
        return f"interrupt {operation_id}:{task_id or '-'}"

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_interrupt,
        cancel_operation=_unexpected_action,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("\r")
    await controller.handle_key("r")

    assert controller.state.session_panel_mode == "raw_transcript"

    await controller.handle_key("s")
    assert calls == [("op-run", "task-1")]
    assert controller.state.last_message == "interrupt op-run:task-1"


async def test_session_timeline_enter_opens_forensic_view_and_escape_returns() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("\r")
    await controller.handle_key("\r")

    assert controller.state.view_level == "forensic"
    assert controller.state.selected_timeline_event is not None
    assert controller.state.selected_timeline_event.event_type == "agent.invocation.started"

    await controller.handle_key("\x1b")
    assert controller.state.view_level == "session"


def test_fleet_prefers_interactive_workbench_when_both_streams_are_ttys(
    monkeypatch: MonkeyPatch,
) -> None:
    invoked: list[tuple[str | None, bool, float]] = []

    async def _fake_fleet_tui_async(
        project: str | None,
        include_all: bool,
        poll_interval: float,
    ) -> None:
        invoked.append((project, include_all, poll_interval))

    monkeypatch.setattr(cli_main, "_fleet_tui_async", _fake_fleet_tui_async)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    anyio.run(cli_main._fleet_async, None, False, False, False, 0.5)

    assert invoked == [(None, False, 0.5)]


async def _load_payload() -> dict[str, object]:
    return _fleet_payload()


async def _load_operation_payload(operation_id: str) -> dict[str, object]:
    return {
        "operation_id": operation_id,
        "context": {
            "run_mode": "attached",
            "involvement_level": "auto",
            "active_session": {
                "adapter_key": "codex_acp",
                "status": "running",
            },
        },
        "summary": {
            "work_summary": f"working on {operation_id}",
            "next_step": "finish the current slice",
        },
        "tasks": [
            {
                "task_id": "task-1",
                "task_short_id": "task-1",
                "title": "Build the task board",
                "goal": "Render the operation task board.",
                "definition_of_done": "Board visible in TUI.",
                "status": "running",
                "priority": 90,
                "dependencies": [],
                "assigned_agent": "codex_acp",
                "linked_session_id": "session-1",
                "memory_refs": ["mem-1"],
                "artifact_refs": ["artifact-1"],
                "notes": ["Task board is the current focus."],
            },
            {
                "task_id": "task-2",
                "task_short_id": "task-2",
                "title": "Wire right pane modes",
                "goal": "Show decisions, events, and memory.",
                "definition_of_done": "Mode keys switch the right pane.",
                "status": "pending",
                "priority": 80,
                "dependencies": ["task-1"],
                "assigned_agent": "codex_acp",
                "linked_session_id": "session-1",
                "memory_refs": ["mem-2"],
                "artifact_refs": [],
                "notes": [],
            },
        ],
        "sessions": [
            {
                "session_id": "session-1",
                "adapter_key": "codex_acp",
                "status": "running",
                "waiting_reason": "Working through the board layout.",
            }
        ],
        "attention": [
            {
                "attention_id": "att-1",
                "target_id": "task-1",
                "title": "Need a layout decision",
            }
        ],
        "recent_events": [
            "[iter 1] decision: start_agent -> codex_acp",
            "[iter 1] agent started: codex_acp",
        ],
        "timeline_events": [
            {
                "event_type": "agent.invocation.started",
                "iteration": 1,
                "task_id": "task-1",
                "session_id": "session-1",
                "summary": "[iter 1] agent started: codex_acp",
            },
            {
                "event_type": "agent.invocation.completed",
                "iteration": 1,
                "task_id": "task-1",
                "session_id": "session-1",
                "summary": "[iter 1] agent completed: success",
            },
        ],
        "upstream_transcript": {
            "title": "Codex Log",
            "events": [
                "assistant: starting task board",
                "assistant: wiring the right pane modes",
            ],
        },
        "decision_memos": [
            {
                "iteration": 2,
                "task_id": "task-1",
                "decision_context_summary": "Need the first task board slice.",
                "chosen_action": "start_agent",
                "rationale": "The task board is the current priority.",
            }
        ],
        "memory_entries": [
            {
                "memory_id": "mem-1",
                "scope": "task",
                "scope_id": "task-1",
                "summary": "The task board should keep the left pane stable.",
                "freshness": "current",
            },
            {
                "memory_id": "mem-2",
                "scope": "task",
                "scope_id": "task-2",
                "summary": "Use d/t/m/i mode switches.",
                "freshness": "current",
            },
        ],
    }


async def _unexpected_action(operation_id: str) -> str:
    raise AssertionError(f"Unexpected action for {operation_id}")


async def _unexpected_interrupt(operation_id: str, task_id: str | None) -> str:
    raise AssertionError(f"Unexpected interrupt for {operation_id}:{task_id}")
