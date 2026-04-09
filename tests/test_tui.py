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
        interrupt_operation=_unexpected_action,
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
        interrupt_operation=_unexpected_action,
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
    calls: list[tuple[str, str]] = []

    async def _pause(operation_id: str) -> str:
        calls.append(("pause", operation_id))
        return f"paused {operation_id}"

    async def _interrupt(operation_id: str) -> str:
        calls.append(("interrupt", operation_id))
        return f"interrupted {operation_id}"

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

    assert calls == [("pause", "op-attn"), ("interrupt", "op-attn")]
    assert controller.state.last_message == "interrupted op-attn"


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
    }


async def _unexpected_action(operation_id: str) -> str:
    raise AssertionError(f"Unexpected action for {operation_id}")
