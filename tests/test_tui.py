from __future__ import annotations

import sys

import anyio
import pytest
from _pytest.monkeypatch import MonkeyPatch
from rich.console import Console
from typer.testing import CliRunner

import agent_operator.cli.main as cli_main
from agent_operator.cli.tui import build_fleet_workbench_controller
from agent_operator.cli.tui import models as tui_models_pkg
from agent_operator.cli.tui import rendering as tui_rendering_pkg
from agent_operator.cli.tui.models import FleetWorkbenchState, dashboard_tasks, task_signal_text
from agent_operator.cli.tui.rendering import (
    human_footer_text,
    human_header_lines,
    render_attention_picker,
    render_forensic_transcript_panel,
    render_help_overlay,
    render_list_table,
    render_session_timeline,
    render_task_board,
)

runner = CliRunner()
pytestmark = pytest.mark.anyio


def test_tui_package_models_exports_state() -> None:
    assert tui_models_pkg.FleetWorkbenchState is FleetWorkbenchState


def test_tui_package_exports_rendering_module() -> None:
    assert tui_rendering_pkg.render_help_overlay is render_help_overlay


def test_human_header_lines_use_human_first_scope_counts() -> None:
    state = FleetWorkbenchState(
        project="alpha",
        total_operations=4,
        all_items=[
            tui_models_pkg.FleetItem.from_payload(
                {
                    "operation_id": "op-run-1",
                    "status": "running",
                    "scheduler_state": "active",
                    "bucket": "active",
                }
            ),
            tui_models_pkg.FleetItem.from_payload(
                {
                    "operation_id": "op-run-2",
                    "status": "running",
                    "scheduler_state": "active",
                    "bucket": "active",
                }
            ),
            tui_models_pkg.FleetItem.from_payload(
                {
                    "operation_id": "op-attn",
                    "status": "needs_human",
                    "scheduler_state": "active",
                    "bucket": "needs_attention",
                }
            ),
            tui_models_pkg.FleetItem.from_payload(
                {
                    "operation_id": "op-pause",
                    "status": "completed",
                    "scheduler_state": "paused",
                    "bucket": "active",
                }
            ),
        ],
    )

    lines = human_header_lines(state)

    assert lines[0] == "Fleet"
    assert lines[1] == "Scope: alpha  Operations: 4  Running: 2  Needs human: 1  Paused: 1"


def test_human_footer_text_uses_compact_fleet_actions() -> None:
    state = FleetWorkbenchState(
        items=[tui_models_pkg.FleetItem.from_payload({"operation_id": "op-1", "bucket": "active"})]
    )

    rendered = str(human_footer_text(state))

    assert "Next blocker Tab" in rendered
    assert "Pause p  Resume u  Interrupt s  Cancel c" in rendered
    assert "Help ?" in rendered


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
                "open_attention_count": 3,
                "open_blocking_attention_count": 2,
                "open_nonblocking_attention_count": 1,
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
            },
            {
                "operation_id": "op-nonblock",
                "status": "running",
                "scheduler_state": "active",
                "objective_brief": "Review non-blocking alerts",
                "open_attention_count": 1,
                "open_blocking_attention_count": 0,
                "open_nonblocking_attention_count": 1,
                "bucket": "active",
            },
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
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    assert controller.state.selected_item is not None
    assert controller.state.selected_item.operation_id == "op-run"

    await controller.handle_key("\t")
    assert controller.state.selected_item is not None
    assert controller.state.selected_item.operation_id == "op-attn"


async def test_help_overlay_opens_and_closes_from_fleet_view() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("?")

    assert controller.state.help_overlay_active is True
    console = Console(record=True, width=140, markup=False)
    console.print(render_help_overlay(controller.state))
    rendered = console.export_text(styles=False)
    assert "open selected operation" in rendered
    assert "filter fleet operations" in rendered

    await controller.handle_key("?")
    assert controller.state.help_overlay_active is False


async def test_help_overlay_opens_from_session_view() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("\r")
    await controller.handle_key("?")

    assert controller.state.help_overlay_active is True
    console = Console(record=True, width=140, markup=False)
    console.print(render_help_overlay(controller.state))
    rendered = console.export_text(styles=False)
    assert "filter session timeline" in rendered
    assert "open selected event in forensic view" in rendered


async def test_fleet_workbench_tab_skips_nonblocking_attention() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("j")
    assert controller.state.selected_item is not None
    assert controller.state.selected_item.operation_id == "op-nonblock"

    await controller.handle_key("\t")
    assert controller.state.selected_item is not None
    assert controller.state.selected_item.operation_id == "op-attn"


async def test_fleet_filter_matches_operation_status_and_objective_fields() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("/")
    for key in "running review":
        await controller.handle_key(key)

    assert controller.state.pending_filter_text == "running review"
    assert [item.operation_id for item in controller.state.items] == ["op-nonblock"]

    await controller.handle_key("\r")
    assert controller.state.pending_filter_text is None
    assert controller.state.filter_query == "running review"
    assert controller.state.last_message == "Applied fleet filter: running review"


async def test_fleet_filter_escape_restores_previous_query() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("/")
    for key in "docs":
        await controller.handle_key(key)
    await controller.handle_key("\r")

    assert [item.operation_id for item in controller.state.items] == ["op-done"]

    await controller.handle_key("/")
    await controller.handle_key("\x7f")
    await controller.handle_key("r")

    assert controller.state.pending_filter_text == "docr"
    assert controller.state.items == []

    await controller.handle_key("\x1b")
    assert controller.state.pending_filter_text is None
    assert controller.state.filter_query == "docs"
    assert [item.operation_id for item in controller.state.items] == ["op-done"]
    assert controller.state.last_message == "Filter input aborted."


async def test_fleet_selection_refreshes_selected_operation_payload() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    assert controller.state.selected_operation_payload is not None
    assert controller.state.selected_operation_payload["operation_id"] == "op-attn"

    await controller.handle_key("j")

    assert controller.state.selected_item is not None
    assert controller.state.selected_item.operation_id == "op-run"
    assert controller.state.selected_operation_payload is not None
    assert controller.state.selected_operation_payload["operation_id"] == "op-run"


async def test_live_fleet_filter_refreshes_selected_operation_payload() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("/")
    for key in "docs":
        await controller.handle_key(key)

    assert controller.state.selected_item is not None
    assert controller.state.selected_item.operation_id == "op-done"
    assert controller.state.selected_operation_payload is not None
    assert controller.state.selected_operation_payload["operation_id"] == "op-done"


def test_filtered_empty_fleet_shows_filter_specific_message() -> None:
    state = FleetWorkbenchState(filter_query="codex")
    table = render_list_table(state)
    console = Console(record=True, width=120, markup=False)
    console.print(table)
    assert "No operations match the current filter." in console.export_text(styles=False)


def test_fleet_list_renders_normalized_multiline_rows() -> None:
    state = FleetWorkbenchState()
    state.items = [
        tui_models_pkg.FleetItem(
            operation_id="op-alert",
            attention_badge="[!!2]",
            display_name="Resolve alert",
            state_label="NEEDS_HUMAN",
            agent_cue="codex_acp",
            recency_brief="21s ago",
            row_hint="waiting: answer needed",
            status="needs_human",
            scheduler_state="active",
            objective_brief="Resolve alert",
            focus_brief=None,
            latest_outcome_brief=None,
            blocker_brief=None,
            runtime_alert=None,
            open_attention_count=2,
            open_blocking_attention_count=2,
            open_nonblocking_attention_count=0,
            attention_briefs=(),
            project_profile_name=None,
            brief=None,
            bucket="needs_attention",
        )
    ]
    table = render_list_table(state)
    console = Console(record=True, width=120, markup=False)
    console.print(table)
    rendered = console.export_text(styles=False)

    assert "Resolve alert" in rendered
    assert "NEEDS_HUMAN · codex_acp · 21s ago" in rendered
    assert "waiting: answer needed" in rendered


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
        answer_attention=_unexpected_answer,
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
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("p")
    await controller.handle_key("s")

    assert calls == [("pause", "op-attn", None), ("interrupt", "op-attn", None)]
    assert controller.state.last_message == "interrupted op-attn:-"


async def test_fleet_workbench_full_state_change_action_contract() -> None:
    calls: list[tuple[str, str, str | None]] = []

    async def _pause(operation_id: str) -> str:
        calls.append(("pause", operation_id, None))
        return f"enqueued: pause_operator [{operation_id}]"

    async def _unpause(operation_id: str) -> str:
        calls.append(("unpause", operation_id, None))
        return f"enqueued: resume_operator [{operation_id}]"

    async def _interrupt(operation_id: str, task_id: str | None) -> str:
        calls.append(("interrupt", operation_id, task_id))
        return f"enqueued: stop_agent_turn [{operation_id}:{task_id or 'none'}]"

    async def _cancel(operation_id: str) -> str:
        calls.append(("cancel", operation_id, None))
        return f"cancelled: {operation_id}"

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_pause,
        unpause_operation=_unpause,
        interrupt_operation=_interrupt,
        cancel_operation=_cancel,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()

    await controller.handle_key("p")
    await controller.handle_key("u")
    await controller.handle_key("s")

    assert calls == [
        ("pause", "op-attn", None),
        ("unpause", "op-attn", None),
        ("interrupt", "op-attn", None),
    ]
    assert controller.state.last_message == "enqueued: stop_agent_turn [op-attn:none]"

    await controller.handle_key("c")
    await controller.handle_key("y")

    assert calls[-1] == ("cancel", "op-attn", None)
    assert controller.state.last_message == "cancelled: op-attn"


async def test_enter_opens_operation_view_and_escape_returns_to_fleet() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
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
        answer_attention=_unexpected_answer,
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

    await controller.handle_key("o")
    assert controller.state.operation_panel_mode == "report"
    report_panel = controller.render()
    assert report_panel is not None

    await controller.handle_key("i")
    assert controller.state.operation_panel_mode == "detail"


async def test_operation_view_l_opens_selected_task_transcript_path() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("l")

    assert controller.state.view_level == "forensic"

    console = Console(record=True, width=160, markup=False)
    console.print(controller.render())
    rendered = console.export_text(styles=False)

    assert "Forensic Transcript" in rendered
    assert "Focused event: [iter 1] agent completed: success" in rendered


async def test_operation_view_l_reports_missing_session_context() -> None:
    async def _load_operation_payload_without_linked_session(
        operation_id: str,
    ) -> dict[str, object]:
        payload = await _load_operation_payload(operation_id)
        tasks = payload.get("tasks")
        if isinstance(tasks, list) and tasks:
            first_task = tasks[0]
            if isinstance(first_task, dict):
                first_task["linked_session_id"] = None
        return payload

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload_without_linked_session,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("l")

    assert controller.state.view_level == "operation"
    assert controller.state.last_message == "The selected task has no linked session to inspect."


async def test_operation_view_report_mode_shows_retrospective_report() -> None:
    async def _load_operation_payload_with_report(operation_id: str) -> dict[str, object]:
        payload = await _load_operation_payload(operation_id)
        payload["report_text"] = "# Report\n\nRetrospective summary."
        return payload

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload_with_report,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("o")

    console = Console(record=True, width=140, markup=False)
    console.print(controller.render())
    rendered = console.export_text(styles=False)

    assert "Retrospective summary." in rendered


async def test_help_overlay_lists_operation_report_mode() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("?")

    console = Console(record=True, width=140, markup=False)
    console.print(render_help_overlay(controller.state))
    rendered = console.export_text(styles=False)

    assert "i / d / t / m / o" in rendered
    assert "open selected task transcript/log path" in rendered


async def test_help_overlay_lists_session_report_toggle() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("\r")
    await controller.handle_key("?")

    console = Console(record=True, width=140, markup=False)
    console.print(render_help_overlay(controller.state))
    rendered = console.export_text(styles=False)

    assert "i / o" in rendered
    assert "open forensic view" in rendered


async def test_operation_view_shows_operation_brief_sections() -> None:
    async def _load_operation_payload_with_brief(operation_id: str) -> dict[str, object]:
        payload = await _load_operation_payload(operation_id)
        payload["operation_brief"] = {
            "goal": "Run compact operation view",
            "now": "Working on task board layout",
            "wait": "manual confirmation required",
            "agent_activity": "codex_acp active session",
            "operator_state": "draining",
            "progress": {
                "done": "",
                "doing": "awaiting operator response",
                "next": "resume execution",
            },
            "attention": "policy gap in mode switch",
            "review": "follow up on the non-blocking queue",
            "recent": "task board layout in progress",
        }
        return payload

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload_with_brief,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")

    console = Console(record=True, width=180, markup=False)
    console.print(controller.render())
    rendered = console.export_text(styles=False)
    for section in (
        "Goal",
        "Now",
        "Wait",
        "Agent",
        "Operator",
        "Progress",
        "Attention",
        "Review",
        "Recent",
        "doing=awaiting operator response",
    ):
        assert section in rendered


async def test_operation_view_tab_jumps_to_task_with_blocking_attention() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")

    assert controller.state.selected_task is not None
    assert controller.state.selected_task.task_id == "task-1"
    await controller.handle_key("\t")

    assert controller.state.selected_task is not None
    assert controller.state.selected_task.task_id == "task-2"


async def test_operation_filter_matches_task_status_and_title_fields() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("/")
    for key in "pending modes":
        await controller.handle_key(key)

    assert controller.state.pending_task_filter_text == "pending modes"
    assert controller.state.selected_task is not None
    assert controller.state.selected_task.task_id == "task-2"

    await controller.handle_key("\r")
    assert controller.state.pending_task_filter_text is None
    assert controller.state.task_filter_query == "pending modes"
    assert controller.state.last_message == "Applied task filter: pending modes"


async def test_operation_filter_escape_restores_previous_query() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("/")
    for key in "task board":
        await controller.handle_key(key)
    await controller.handle_key("\r")

    assert controller.state.selected_task is not None
    assert controller.state.selected_task.task_id == "task-1"

    await controller.handle_key("/")
    await controller.handle_key("\x7f")
    await controller.handle_key("z")

    assert controller.state.pending_task_filter_text == "task boarz"
    assert controller.state.selected_task is None

    await controller.handle_key("\x1b")
    assert controller.state.pending_task_filter_text is None
    assert controller.state.task_filter_query == "task board"
    assert controller.state.selected_task is not None
    assert controller.state.selected_task.task_id == "task-1"
    assert controller.state.last_message == "Task filter input aborted."


def test_filtered_empty_task_board_shows_filter_specific_message() -> None:
    state = FleetWorkbenchState(
        view_level="operation",
        task_filter_query="nomatch",
        selected_operation_payload={"tasks": [{"task_id": "task-1", "task_short_id": "task-1"}]},
    )
    table = render_task_board(state)
    console = Console(record=True, width=120, markup=False)
    console.print(table)
    assert "No tasks match the current filter." in console.export_text(styles=False)


def test_operation_task_board_groups_tasks_into_status_lanes() -> None:
    state = FleetWorkbenchState(
        view_level="operation",
        selected_task_index=1,
        selected_operation_payload={
            "tasks": [
                {
                    "task_id": "task-ready",
                    "task_short_id": "task-ready",
                    "title": "Ready task",
                    "status": "pending",
                    "dependencies": [],
                },
                {
                    "task_id": "task-running",
                    "task_short_id": "task-running",
                    "title": "Running task",
                    "status": "running",
                    "dependencies": [],
                },
                {
                    "task_id": "task-blocked",
                    "task_short_id": "task-blocked",
                    "title": "Blocked task",
                    "status": "pending",
                    "dependencies": ["task-running"],
                },
                {
                    "task_id": "task-done",
                    "task_short_id": "task-done",
                    "title": "Completed task",
                    "status": "completed",
                    "dependencies": [],
                },
            ],
            "attention": [],
        },
    )

    table = render_task_board(state)
    console = Console(record=True, width=140, markup=False)
    console.print(table)
    rendered = console.export_text(styles=False)

    assert rendered.index("[RUNNING]") < rendered.index("[READY]") < rendered.index("[BLOCKED]")
    assert rendered.index("[BLOCKED]") < rendered.index("[COMPLETED]")
    assert ">       ○ task-ready" in rendered
    assert "▶ task-running" in rendered
    assert "◐ task-blocked" in rendered
    assert "✓ task-done" in rendered
    assert "deps" in rendered


def test_operation_task_board_shows_compact_session_cue_lines() -> None:
    state = FleetWorkbenchState(
        view_level="operation",
        selected_operation_payload={
            "tasks": [
                {
                    "task_id": "task-1",
                    "task_short_id": "task-1",
                    "title": "Build the board",
                    "status": "running",
                    "linked_session_id": "session-1",
                    "dependencies": [],
                }
            ],
            "sessions": [
                {
                    "session_id": "session-1",
                    "adapter_key": "codex_acp",
                    "status": "running",
                    "waiting_reason": "Waiting on operator reply.",
                }
            ],
            "attention": [],
        },
    )

    table = render_task_board(state)
    console = Console(record=True, width=140, markup=False)
    console.print(table)
    rendered = console.export_text(styles=False)

    assert "session" in rendered
    assert "codex_acp · session-1 · Status: running · Waiting on operator reply." in rendered


async def test_operation_view_navigation_follows_lane_order() -> None:
    async def _load_operation_payload_lane_order(operation_id: str) -> dict[str, object]:
        payload = await _load_operation_payload(operation_id)
        payload["tasks"] = [
            {
                "task_id": "task-ready",
                "task_short_id": "task-ready",
                "title": "Ready task",
                "goal": "Handle ready work.",
                "definition_of_done": "Ready work visible.",
                "status": "pending",
                "priority": 60,
                "dependencies": [],
                "assigned_agent": "codex_acp",
                "linked_session_id": None,
                "memory_refs": [],
                "artifact_refs": [],
                "notes": [],
            },
            {
                "task_id": "task-done",
                "task_short_id": "task-done",
                "title": "Completed task",
                "goal": "Already finished.",
                "definition_of_done": "Done.",
                "status": "completed",
                "priority": 10,
                "dependencies": [],
                "assigned_agent": "codex_acp",
                "linked_session_id": None,
                "memory_refs": [],
                "artifact_refs": [],
                "notes": [],
            },
            {
                "task_id": "task-blocked",
                "task_short_id": "task-blocked",
                "title": "Blocked task",
                "goal": "Wait on dependency.",
                "definition_of_done": "Dependency resolved.",
                "status": "pending",
                "priority": 40,
                "dependencies": ["task-running"],
                "assigned_agent": "codex_acp",
                "linked_session_id": None,
                "memory_refs": [],
                "artifact_refs": [],
                "notes": [],
            },
            {
                "task_id": "task-running",
                "task_short_id": "task-running",
                "title": "Running task",
                "goal": "Current work.",
                "definition_of_done": "Still active.",
                "status": "running",
                "priority": 90,
                "dependencies": [],
                "assigned_agent": "codex_acp",
                "linked_session_id": "session-1",
                "memory_refs": [],
                "artifact_refs": [],
                "notes": [],
            },
        ]
        return payload

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload_lane_order,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")

    assert controller.state.selected_task is not None
    assert controller.state.selected_task.task_id == "task-running"

    await controller.handle_key("j")
    assert controller.state.selected_task is not None
    assert controller.state.selected_task.task_id == "task-ready"

    await controller.handle_key("j")
    assert controller.state.selected_task is not None
    assert controller.state.selected_task.task_id == "task-blocked"

    await controller.handle_key("j")
    assert controller.state.selected_task is not None
    assert controller.state.selected_task.task_id == "task-done"


async def test_operation_view_a_reports_oldest_blocking_attention_for_task() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("a")

    assert controller.state.pending_answer_operation_id == "op-run"
    assert controller.state.pending_answer_attention_id == "att-1"
    assert controller.state.pending_answer_task_id == "task-1"
    assert controller.state.pending_answer_text == ""
    assert (
        controller.state.last_message == "Answer selected. Type text, Enter to send, Esc to cancel."
    )


async def test_fleet_view_a_enters_answer_mode_and_dispatches_oldest_attention() -> None:
    answers: list[tuple[str, str, str]] = []
    active_attention_ids = ["att-3"]

    async def _load_operation_payload_single_blocker(operation_id: str) -> dict[str, object]:
        payload = await _load_operation_payload(operation_id)
        payload["attention"] = [
            item
            for item in payload["attention"]
            if isinstance(item, dict) and item.get("attention_id") in active_attention_ids
        ]
        return payload

    async def _answer(operation_id: str, attention_id: str, text: str) -> str:
        answers.append((operation_id, attention_id, text))
        active_attention_ids[:] = [item for item in active_attention_ids if item != attention_id]
        return (
            "enqueued: answer_attention_request "
            f"[operation={operation_id}:attention={attention_id}:text={text}]"
        )

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload_single_blocker,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("a")
    await controller.handle_key("r")
    await controller.handle_key("e")
    await controller.handle_key("s")
    await controller.handle_key("p")
    await controller.handle_key("o")
    await controller.handle_key("n")
    await controller.handle_key("s")
    await controller.handle_key("e")
    await controller.handle_key("\r")

    assert answers == [("op-run", "att-3", "response")]
    assert controller.state.pending_answer_operation_id is None
    assert controller.state.pending_answer_attention_id is None
    assert controller.state.pending_answer_task_id is None
    assert (
        controller.state.last_message
        == "enqueued: answer_attention_request [operation=op-run:attention=att-3:text=response]"
    )


async def test_fleet_view_n_dispatches_oldest_nonblocking_attention() -> None:
    answers: list[tuple[str, str, str]] = []
    active_attention_ids = ["att-2"]

    async def _load_operation_payload_single_nonblocking(operation_id: str) -> dict[str, object]:
        payload = await _load_operation_payload(operation_id)
        payload["attention"] = [
            item
            for item in payload["attention"]
            if isinstance(item, dict) and item.get("attention_id") in active_attention_ids
        ]
        return payload

    async def _answer(operation_id: str, attention_id: str, text: str) -> str:
        answers.append((operation_id, attention_id, text))
        active_attention_ids[:] = [item for item in active_attention_ids if item != attention_id]
        return f"answered {operation_id}:{attention_id}:{text}"

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload_single_nonblocking,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("n")
    await controller.handle_key("o")
    await controller.handle_key("k")
    await controller.handle_key("\r")

    assert answers == [("op-run", "att-2", "ok")]
    assert controller.state.pending_answer_operation_id is None
    assert controller.state.pending_answer_attention_id is None
    assert controller.state.last_message == "answered op-run:att-2:ok"


async def test_fleet_attention_picker_selects_specific_attention_item() -> None:
    answers: list[tuple[str, str, str]] = []
    active_attention_ids = ["att-3", "att-1", "att-2"]

    async def _load_operation_payload_with_picker_items(operation_id: str) -> dict[str, object]:
        payload = await _load_operation_payload(operation_id)
        payload["attention"] = [
            item
            for item in payload["attention"]
            if isinstance(item, dict) and item.get("attention_id") in active_attention_ids
        ]
        return payload

    async def _answer(operation_id: str, attention_id: str, text: str) -> str:
        answers.append((operation_id, attention_id, text))
        active_attention_ids[:] = [item for item in active_attention_ids if item != attention_id]
        return f"answered {operation_id}:{attention_id}:{text}"

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload_with_picker_items,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("A")

    assert controller.state.attention_picker_active is True
    console = Console(record=True, width=160, markup=False)
    console.print(render_attention_picker(controller.state))
    rendered = console.export_text(styles=False)
    assert "att-3" in rendered
    assert "att-2" in rendered
    assert "non-blocking" in rendered

    await controller.handle_key("j")
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("o")
    await controller.handle_key("k")
    await controller.handle_key("\r")

    assert answers == [("op-run", "att-2", "ok")]
    assert controller.state.attention_picker_active is False
    assert controller.state.pending_answer_operation_id is None
    assert controller.state.last_message == "answered op-run:att-2:ok"


async def test_task_n_nonblocking_answer_chains_within_same_task_scope() -> None:
    active_attention = [
        {
            "attention_id": "att-2",
            "target_id": "task-1",
            "target_scope": "task",
            "attention_type": "policy_gap",
            "title": "Task one note",
            "question": "First note?",
            "blocking": False,
            "created_at": "2025-12-30T00:00:00Z",
        },
        {
            "attention_id": "att-4",
            "target_id": "task-1",
            "target_scope": "task",
            "attention_type": "policy_gap",
            "title": "Task one follow-up",
            "question": "Second note?",
            "blocking": False,
            "created_at": "2025-12-31T00:00:00Z",
        },
        {
            "attention_id": "att-5",
            "target_id": "task-2",
            "target_scope": "task",
            "attention_type": "policy_gap",
            "title": "Other task note",
            "question": "Task two note?",
            "blocking": False,
            "created_at": "2025-12-29T00:00:00Z",
        },
    ]
    answers: list[tuple[str, str, str]] = []

    async def _load_operation_payload_with_nonblocking_queue(
        operation_id: str,
    ) -> dict[str, object]:
        payload = await _load_operation_payload(operation_id)
        payload["attention"] = [item.copy() for item in active_attention]
        return payload

    async def _answer(operation_id: str, attention_id: str, text: str) -> str:
        answers.append((operation_id, attention_id, text))
        active_attention[:] = [
            item for item in active_attention if item["attention_id"] != attention_id
        ]
        return f"answered {attention_id}"

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload_with_nonblocking_queue,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("n")
    await controller.handle_key("o")
    await controller.handle_key("k")
    await controller.handle_key("\r")

    assert answers == [("op-run", "att-2", "ok")]
    assert controller.state.pending_answer_operation_id == "op-run"
    assert controller.state.pending_answer_attention_id == "att-4"
    assert controller.state.pending_answer_task_id == "task-1"
    assert controller.state.pending_answer_prompt == (
        "1 non-blocking attention remains in task task-1. Answer text: "
    )


async def test_fleet_view_answer_chains_to_next_oldest_blocking_attention() -> None:
    active_attention = [
        {
            "attention_id": "att-early",
            "target_id": "task-1",
            "target_scope": "task",
            "attention_type": "policy_gap",
            "title": "First answer",
            "question": "What first?",
            "blocking": True,
            "created_at": "2025-12-30T00:00:00Z",
        },
        {
            "attention_id": "att-late",
            "target_id": "task-2",
            "target_scope": "task",
            "attention_type": "policy_gap",
            "title": "Second answer",
            "question": "What next?",
            "blocking": True,
            "created_at": "2025-12-31T00:00:00Z",
        },
    ]
    answers: list[tuple[str, str, str]] = []

    async def _load_operation_payload_with_remaining(operation_id: str) -> dict[str, object]:
        payload = await _load_operation_payload(operation_id)
        payload["attention"] = [item.copy() for item in active_attention]
        return payload

    async def _answer(operation_id: str, attention_id: str, text: str) -> str:
        answers.append((operation_id, attention_id, text))
        active_attention[:] = [
            item for item in active_attention if item["attention_id"] != attention_id
        ]
        return f"answered {attention_id}"

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload_with_remaining,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("a")
    for key in "yes":
        await controller.handle_key(key)
    await controller.handle_key("\r")

    assert answers == [("op-run", "att-early", "yes")]
    assert controller.state.pending_answer_operation_id == "op-run"
    assert controller.state.pending_answer_attention_id == "att-late"
    assert controller.state.pending_answer_task_id is None
    assert controller.state.pending_answer_prompt == (
        "1 blocking attention remains in op-run. Answer text: "
    )


async def test_task_answer_chains_within_same_task_scope() -> None:
    active_attention = [
        {
            "attention_id": "att-1",
            "target_id": "task-1",
            "target_scope": "task",
            "attention_type": "policy_gap",
            "title": "Task one first",
            "question": "Task one?",
            "blocking": True,
            "created_at": "2025-12-30T00:00:00Z",
        },
        {
            "attention_id": "att-2",
            "target_id": "task-1",
            "target_scope": "task",
            "attention_type": "policy_gap",
            "title": "Task one second",
            "question": "Task one again?",
            "blocking": True,
            "created_at": "2025-12-31T00:00:00Z",
        },
        {
            "attention_id": "att-3",
            "target_id": "task-2",
            "target_scope": "task",
            "attention_type": "policy_gap",
            "title": "Other task",
            "question": "Task two?",
            "blocking": True,
            "created_at": "2025-12-29T00:00:00Z",
        },
    ]
    answers: list[tuple[str, str, str]] = []

    async def _load_operation_payload_with_task_queue(operation_id: str) -> dict[str, object]:
        payload = await _load_operation_payload(operation_id)
        payload["attention"] = [item.copy() for item in active_attention]
        return payload

    async def _answer(operation_id: str, attention_id: str, text: str) -> str:
        answers.append((operation_id, attention_id, text))
        active_attention[:] = [
            item for item in active_attention if item["attention_id"] != attention_id
        ]
        return f"answered {attention_id}"

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload_with_task_queue,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("a")
    for key in "ok":
        await controller.handle_key(key)
    await controller.handle_key("\r")

    assert answers == [("op-run", "att-1", "ok")]
    assert controller.state.pending_answer_operation_id == "op-run"
    assert controller.state.pending_answer_attention_id == "att-2"
    assert controller.state.pending_answer_task_id == "task-1"
    assert controller.state.pending_answer_prompt == (
        "1 blocking attention remains in task task-1. Answer text: "
    )


async def test_fleet_view_a_rejects_empty_answer_text() -> None:
    answers: list[tuple[str, str, str]] = []

    async def _answer(operation_id: str, attention_id: str, text: str) -> str:
        answers.append((operation_id, attention_id, text))
        return "should-not-be-called"

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("a")
    await controller.handle_key("\r")
    assert controller.state.last_message == "Answer text cannot be empty."
    await controller.handle_key("\x1b")

    assert answers == []
    assert controller.state.pending_answer_operation_id is None
    assert controller.state.pending_answer_attention_id is None
    assert controller.state.last_message == "Answer input aborted."


async def test_fleet_view_a_reports_no_attention_when_none_present() -> None:
    payload = _fleet_payload()
    payload["needs_attention"][0]["open_attention_count"] = 0
    payload["needs_attention"][0]["open_blocking_attention_count"] = 0
    payload["needs_attention"][0]["open_nonblocking_attention_count"] = 0

    async def _empty_attention_payload() -> dict[str, object]:
        return payload

    async def _load_operation_payload_without_blocking(operation_id: str) -> dict[str, object]:
        payload = await _load_operation_payload(operation_id)
        payload["attention"] = []
        return payload

    controller = build_fleet_workbench_controller(
        load_payload=_empty_attention_payload,
        load_operation_payload=_load_operation_payload_without_blocking,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("a")

    assert controller.state.last_message == "No blocking attention on op-attn."


def test_task_signal_text() -> None:
    payload = {
        "attention": [
            {
                "attention_id": "att-1",
                "attention_type": "policy_gap",
                "target_scope": "task",
                "target_id": "task-1",
                "title": "Blocked by policy",
                "question": "What to do?",
                "blocking": True,
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "attention_id": "att-2",
                "attention_type": "resource_block",
                "target_scope": "task",
                "target_id": "task-2",
                "title": "Info update",
                "question": "Any details?",
                "blocking": False,
                "created_at": "2026-01-02T00:00:00Z",
            },
        ]
    }
    operation_payload = {
        "operation_id": "op-1",
        "tasks": [
            {
                "task_id": "task-1",
                "task_short_id": "task-1",
                "title": "task one",
                "goal": "-",
                "definition_of_done": "-",
                "status": "running",
                "priority": 1,
                "dependencies": [],
                "notes": [],
            },
            {
                "task_id": "task-2",
                "task_short_id": "task-2",
                "title": "task two",
                "goal": "-",
                "definition_of_done": "-",
                "status": "pending",
                "priority": 1,
                "dependencies": [],
                "notes": [],
            },
        ],
    }
    operation_payload.update(payload)
    tasks = dashboard_tasks(operation_payload)
    assert task_signal_text(operation_payload, tasks[0]) == "[!!1]"
    assert task_signal_text(operation_payload, tasks[1]) == "[!1]"


async def test_operation_view_enter_opens_session_view_and_escape_returns() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
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


async def test_session_view_r_opens_forensic_and_session_interrupt_stays_task_scoped() -> None:
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
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("\r")
    await controller.handle_key("r")

    assert controller.state.view_level == "forensic"

    await controller.handle_key("\x1b")
    assert controller.state.view_level == "session"

    await controller.handle_key("s")
    assert calls == [("op-run", "task-1")]
    assert controller.state.last_message == "interrupt op-run:task-1"


async def test_session_view_o_shows_retrospective_report() -> None:
    async def _load_operation_payload_with_report(operation_id: str) -> dict[str, object]:
        payload = await _load_operation_payload(operation_id)
        payload["report_text"] = "# Report\n\nRetrospective summary."
        return payload

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload_with_report,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("\r")
    await controller.handle_key("o")

    assert controller.state.session_panel_mode == "report"

    console = Console(record=True, width=140, markup=False)
    console.print(controller.render())
    rendered = console.export_text(styles=False)

    assert "Report" in rendered
    assert "Retrospective summary." in rendered

    await controller.handle_key("i")
    assert controller.state.session_panel_mode == "timeline"


async def test_operation_view_renders_transcript_and_report_escalation_cues() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")

    console = Console(record=True, width=180, markup=False)
    console.print(controller.render())
    rendered = console.export_text(styles=False)

    assert "Next step" in rendered
    assert (
        "Open session Enter  ·  Transcript/log l  ·  Report o  ·  Back Esc  ·  Help ?"
        in rendered
    )


async def test_session_filter_matches_event_type_and_summary_fields() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("\r")
    await controller.handle_key("/")
    for key in "completed success":
        await controller.handle_key(key)

    assert controller.state.pending_session_filter_text == "completed success"
    assert controller.state.selected_timeline_event is not None
    assert controller.state.selected_timeline_event.event_type == "agent.invocation.completed"

    await controller.handle_key("\r")
    assert controller.state.pending_session_filter_text is None
    assert controller.state.session_filter_query == "completed success"
    assert controller.state.last_message == "Applied session filter: completed success"


async def test_session_filter_escape_restores_previous_query() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("\r")
    await controller.handle_key("/")
    for key in "started":
        await controller.handle_key(key)
    await controller.handle_key("\r")

    assert controller.state.selected_timeline_event is not None
    assert controller.state.selected_timeline_event.event_type == "agent.invocation.started"

    await controller.handle_key("/")
    await controller.handle_key("\x7f")
    await controller.handle_key("z")

    assert controller.state.pending_session_filter_text == "startez"
    assert controller.state.selected_timeline_event is None

    await controller.handle_key("\x1b")
    assert controller.state.pending_session_filter_text is None
    assert controller.state.session_filter_query == "started"
    assert controller.state.selected_timeline_event is not None
    assert controller.state.selected_timeline_event.event_type == "agent.invocation.started"
    assert controller.state.last_message == "Session filter input aborted."


async def test_session_view_renders_session_brief_and_selected_event_sections() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("\r")

    console = Console(record=True, width=180, markup=False)
    console.print(controller.render())
    rendered = console.export_text(styles=False)

    for section in (
        "codex_acp",
        "Now",
        "Wait",
        "Agent",
        "Operator",
        "Attention",
        "Review",
        "Latest output",
        "Timeline",
        "Selected 1 of 2 events (newest first)",
        "codex_acp · session-1",
        "Selected Event",
        "agent started",
        "Need a layout decision",
    ):
        assert section in rendered

    assert "Fleet / op-run / session / task-1" in rendered
    assert "Next step" in rendered
    assert "Open forensic Enter/r" in rendered
    assert (
        "Move j/k  Filter /  Open forensic Enter/r  Live detail i  Report o"
        "  Back Esc  Answer a/n  Pick A  Interrupt s  Pause p  Resume u  Cancel c  Help ?  Quit q"
    ) in rendered


async def test_session_timeline_uses_human_event_labels() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("\r")

    console = Console(record=True, width=180, markup=False)
    console.print(controller.render())
    rendered = console.export_text(styles=False)

    assert "agent started" in rendered
    assert "agent completed" in rendered


def test_session_timeline_renders_newest_event_first() -> None:
    state = FleetWorkbenchState(
        view_level="session",
        selected_operation_payload={
            "tasks": [
                {
                    "task_id": "task-1",
                    "task_short_id": "task-1",
                    "title": "Build the board",
                    "status": "running",
                    "linked_session_id": "session-1",
                }
            ],
            "timeline_events": [
                {
                    "event_type": "agent.invocation.started",
                    "iteration": 1,
                    "task_id": "task-1",
                    "session_id": "session-1",
                    "summary": "started first",
                },
                {
                    "event_type": "agent.invocation.completed",
                    "iteration": 2,
                    "task_id": "task-1",
                    "session_id": "session-1",
                    "summary": "completed later",
                },
            ],
        },
        selected_task_index=0,
    )

    table = render_session_timeline(state)
    console = Console(record=True, width=140, markup=False)
    console.print(table)
    rendered = console.export_text(styles=False)

    assert rendered.index("completed later") < rendered.index("started first")


async def test_session_timeline_enter_opens_forensic_view_and_escape_returns() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("\r")
    await controller.handle_key("\r")

    assert controller.state.view_level == "forensic"
    assert controller.state.selected_timeline_event is not None
    assert controller.state.selected_timeline_event.event_type == "agent.invocation.completed"

    await controller.handle_key("\x1b")
    assert controller.state.view_level == "session"


async def test_forensic_q_returns_to_session_view() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("\r")
    await controller.handle_key("r")

    assert controller.state.view_level == "forensic"

    await controller.handle_key("q")
    assert controller.state.view_level == "session"


async def test_session_enter_opens_forensic_if_transcript_is_unavailable() -> None:
    calls: list[tuple[str, str | None]] = []

    async def _interrupt(operation_id: str, task_id: str | None) -> str:
        calls.append((operation_id, task_id))
        return f"interrupt {operation_id}:{task_id or '-'}"

    async def _load_operation_payload_without_transcript(operation_id: str) -> dict[str, object]:
        payload = await _load_operation_payload(operation_id)
        payload["upstream_transcript"] = {"title": "No transcript", "events": []}
        payload["timeline_events"] = [
            {
                "event_type": "agent.invocation.started",
                "iteration": 1,
                "task_id": "task-1",
                "session_id": "session-1",
                "summary": "[iter 1] agent started: codex_acp",
            },
        ]
        return payload

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload_without_transcript,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("\r")
    await controller.handle_key("\r")

    assert controller.state.view_level == "forensic"
    assert controller.state.last_message is None


async def test_forensic_filter_matches_transcript_lines_live() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("\r")
    await controller.handle_key("\r")
    await controller.handle_key("/")
    for key in "right pane":
        await controller.handle_key(key)

    assert controller.state.pending_forensic_filter_text == "right pane"
    assert controller.state.forensic_filter_query == "right pane"
    panel = render_forensic_transcript_panel(controller.state)
    assert "wiring the right pane modes" in panel.plain
    assert "starting task board" not in panel.plain

    await controller.handle_key("\r")
    assert controller.state.pending_forensic_filter_text is None
    assert controller.state.forensic_filter_query == "right pane"
    assert controller.state.last_message == "Applied forensic filter: right pane"


async def test_forensic_filter_escape_restores_previous_query() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("\r")
    await controller.handle_key("\r")
    await controller.handle_key("/")
    for key in "starting":
        await controller.handle_key(key)
    await controller.handle_key("\r")

    assert controller.state.forensic_filter_query == "starting"

    await controller.handle_key("/")
    await controller.handle_key("\x7f")
    await controller.handle_key("z")

    assert controller.state.pending_forensic_filter_text == "startinz"
    assert (
        "No raw transcript lines match the current filter."
        in render_forensic_transcript_panel(controller.state).plain
    )

    await controller.handle_key("\x1b")
    assert controller.state.pending_forensic_filter_text is None
    assert controller.state.forensic_filter_query == "starting"
    assert controller.state.last_message == "Forensic filter input aborted."


async def test_fleet_refresh_failure_is_reported_and_non_fatal() -> None:
    call_count = 0

    async def _flaky_load_payload() -> dict[str, object]:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("transient load failure")
        return _fleet_payload()

    controller = build_fleet_workbench_controller(
        load_payload=_flaky_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    assert controller.state.selected_item is not None
    assert controller.state.selected_item.operation_id == "op-run"

    await controller.refresh()
    assert controller.state.selected_item is not None
    assert controller.state.selected_item.operation_id == "op-run"
    assert (
        controller.state.last_message == "Failed to refresh operation list: transient load failure"
    )


async def test_fleet_operation_payload_refresh_failure_is_non_fatal() -> None:
    call_count = 0

    async def _flaky_load_operation_payload(operation_id: str) -> dict[str, object] | None:
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            raise RuntimeError("operation payload load failure")
        return await _load_operation_payload(operation_id)

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_flaky_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    assert controller.state.selected_task is not None
    assert controller.state.view_level == "operation"
    assert controller.state.selected_task.task_id == "task-1"
    assert controller.state.last_message is None

    await controller.refresh()
    assert controller.state.selected_task is not None
    assert controller.state.selected_task.task_id == "task-1"
    assert (
        controller.state.last_message
        == "Failed to refresh operation payload: operation payload load failure"
    )


def test_empty_fleet_shows_guidance_message() -> None:
    state = FleetWorkbenchState()
    table = render_list_table(state)
    console = Console(record=True, width=120, markup=False)
    console.print(table)
    assert "No active operations. Run 'operator run [goal]' to start." in console.export_text(
        styles=False
    )


def test_filtered_empty_session_timeline_shows_filter_specific_message() -> None:
    state = FleetWorkbenchState(
        view_level="session",
        session_filter_query="nomatch",
        selected_operation_payload={
            "timeline_events": [
                {
                    "event_type": "agent.invocation.started",
                    "iteration": 1,
                    "task_id": "task-1",
                    "session_id": "session-1",
                    "summary": "agent started",
                }
            ]
        },
    )
    table = render_session_timeline(state)
    console = Console(record=True, width=120, markup=False)
    console.print(table)
    assert "No session timeline events match the current filter." in console.export_text(
        styles=False
    )


def test_session_timeline_summary_shows_filter_specific_empty_state() -> None:
    state = FleetWorkbenchState(
        view_level="session",
        session_filter_query="nomatch",
        selected_operation_payload={
            "timeline_events": [
                {
                    "event_type": "agent.invocation.started",
                    "iteration": 1,
                    "task_id": "task-1",
                    "session_id": "session-1",
                    "summary": "agent started",
                }
            ]
        },
    )

    assert (
        tui_rendering_pkg._session_timeline_summary(state)
        == "No timeline events match filter; 1 total before filter"
    )


def test_session_timeline_summary_keeps_plain_empty_state_without_filter() -> None:
    state = FleetWorkbenchState(view_level="session", selected_operation_payload={})

    assert tui_rendering_pkg._session_timeline_summary(state) == "No timeline events."


def test_filtered_empty_forensic_transcript_shows_filter_specific_message() -> None:
    state = FleetWorkbenchState(
        view_level="forensic",
        forensic_filter_query="nomatch",
        selected_operation_payload={
            "upstream_transcript": {"events": ["assistant: starting task board"]}
        },
    )
    panel = render_forensic_transcript_panel(state)
    assert "No raw transcript lines match the current filter." in panel.plain


def test_fleet_header_uses_human_summary_language() -> None:
    state = FleetWorkbenchState(
        all_items=[
            tui_models_pkg.FleetItem.from_payload(
                {
                    "operation_id": "op-needs-human",
                    "display_name": "Answer review",
                    "state_label": "needs_human",
                    "attention_badge": "B1",
                    "status": "needs_human",
                    "scheduler_state": "active",
                }
            ),
            tui_models_pkg.FleetItem.from_payload(
                {
                    "operation_id": "op-paused",
                    "display_name": "Paused job",
                    "state_label": "running/pause_requested",
                    "attention_badge": "-",
                    "status": "running",
                    "scheduler_state": "pause_requested",
                }
            ),
        ],
        items=[
            tui_models_pkg.FleetItem.from_payload(
                {
                    "operation_id": "op-run",
                    "display_name": "Ship dashboard",
                    "state_label": "running",
                    "agent_cue": "profile:alpha",
                    "recency_brief": "layout in progress",
                    "focus_brief": "Working on the task board",
                    "latest_outcome_brief": "awaiting review",
                    "attention_badge": "-",
                    "status": "running",
                    "scheduler_state": "active",
                }
            )
        ],
        selected_index=0,
        total_operations=3,
    )

    assert human_header_lines(state) == [
        "Fleet",
        "Scope: all projects  Operations: 3  Running: 1  Needs human: 1  Paused: 1",
        "Selected: Ship dashboard  Now: Working on the task board  Wait: awaiting review",
    ]


def test_fleet_header_keeps_filter_visible_with_human_counts() -> None:
    fleet_item = tui_models_pkg.FleetItem.from_payload(
        {
            "operation_id": "op-run",
            "display_name": "Ship dashboard",
            "state_label": "running",
            "attention_badge": "-",
            "status": "running",
            "scheduler_state": "active",
        }
    )
    state = FleetWorkbenchState(
        all_items=[fleet_item],
        items=[fleet_item],
        selected_index=0,
        total_operations=4,
        filter_query="dashboard",
    )

    scope_line = human_header_lines(state)[1]
    assert scope_line == (
        "Scope: all projects  Operations: 4  Running: 1  Needs human: 0  Paused: 0  "
        "Fleet filter: dashboard"
    )


async def test_operation_header_surfaces_now_wait_and_attention_summary() -> None:
    async def _load_operation_payload_with_brief(operation_id: str) -> dict[str, object]:
        payload = await _load_operation_payload(operation_id)
        payload["operation_brief"] = {
            "now": "Working on the dashboard layout.",
            "wait": "Waiting for a layout decision.",
            "attention": "[policy_gap] Need a layout decision.",
        }
        return payload

    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload_with_brief,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")

    lines = human_header_lines(controller.state)
    assert lines[0] == "Fleet / op-run / operation"
    summary_line = next(line for line in lines if "Tasks: 2" in line)
    assert "Running: 1" in summary_line
    assert "Blocked: 1" in summary_line
    assert "Now: Working on the dashboard layout." in summary_line
    assert "Wait: Waiting for a layout decision." in summary_line
    assert "Attention: [policy_gap] Need a layout decision." in summary_line


async def test_session_header_and_footer_use_human_action_language() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("\r")

    lines = human_header_lines(controller.state)
    assert lines[0] == "Fleet / op-run / session / task-1"
    assert (
        lines[1] == "Session: codex_acp · session-1 · running · Working through the board layout."
    )
    assert "Now: Working through the board layout." in lines[2]
    assert "Wait: Working through the board layout." in lines[2]
    assert "Attention: Need a layout decision" in lines[2]
    assert (
        human_footer_text(controller.state).plain
        == "Move j/k  Filter /  Open forensic Enter/r  Live detail i  Report o"
        "  Back Esc  Answer a/n  Pick A  Interrupt s  Pause p  Resume u  Cancel c  Help ?  Quit q"
    )


async def test_session_footer_uses_short_human_first_actions() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")
    await controller.handle_key("\r")

    assert (
        human_footer_text(controller.state).plain
        == "Move j/k  Filter /  Open forensic Enter/r  Live detail i  Report o"
        "  Back Esc  Answer a/n  Pick A  Interrupt s  Pause p  Resume u  Cancel c  Help ?  Quit q"
    )


async def test_operation_footer_uses_short_human_first_actions() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    await controller.handle_key("j")
    await controller.handle_key("\r")

    assert (
        human_footer_text(controller.state).plain
        == "Move j/k  Open session Enter  Filter /  Answer a/n  Pick A  Detail i  "
        "Decisions d  Events t  Memory m  Transcript l  Report o  Back Esc  Pause p  "
        "Resume u  Interrupt s  Cancel c  Refresh r  Help ?  Quit q"
    )


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
                "target_scope": "task",
                "attention_type": "policy_gap",
                "title": "Need a layout decision",
                "question": "How should we handle layout priorities?",
                "blocking": True,
                "created_at": "2026-01-02T00:00:00Z",
            },
            {
                "attention_id": "att-2",
                "target_id": "task-1",
                "target_scope": "task",
                "attention_type": "policy_gap",
                "title": "Another layout question",
                "question": "Need a deterministic tie-break?",
                "blocking": False,
                "created_at": "2026-01-03T00:00:00Z",
            },
            {
                "attention_id": "att-3",
                "target_id": "task-2",
                "target_scope": "task",
                "attention_type": "policy_gap",
                "title": "Need modes order",
                "question": "What mode order is safest?",
                "blocking": True,
                "created_at": "2025-12-31T23:00:00Z",
            },
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
        "session_views": [
            {
                "task_id": "task-1",
                "task_short_id": "task-1",
                "task_title": "Build the task board",
                "session": {
                    "session_id": "session-1",
                    "adapter_key": "codex_acp",
                    "status": "running",
                    "waiting_reason": "Working through the board layout.",
                    "bound_task_ids": ["task-1", "task-2"],
                },
                "session_brief": {
                    "now": "Working through the board layout.",
                    "wait": "Working through the board layout.",
                    "agent_activity": "codex_acp session",
                    "operator_state": "observing",
                    "attention": "Need a layout decision",
                    "review": "Another layout question",
                    "latest_output": "[iter 1] agent completed: success",
                },
                "timeline": [
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
                "selected_event": {
                    "event_type": "agent.invocation.completed",
                    "iteration": 1,
                    "task_id": "task-1",
                    "session_id": "session-1",
                    "summary": "[iter 1] agent completed: success",
                },
                "transcript_hint": {
                    "command": "operator log op-run --agent codex",
                },
            }
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
        "report_text": None,
    }


async def test_fleet_view_uses_selected_fleet_brief_sections() -> None:
    payload = {
        "project": None,
        "total_operations": 1,
        "header": {},
        "rows": [
            {
                "operation_id": "op-brief",
                "attention_badge": "!!",
                "display_name": "Resolve alert",
                "state_label": "running",
                "agent_cue": "profile:alpha",
                "recency_brief": "runtime alert",
                "row_hint": "running",
                "sort_bucket": "needs_attention",
                "status": "running",
                "scheduler_state": "active",
                "project_profile_name": "alpha",
                "runtime_alert": "blocked by runtime",
                "focus_brief": "Need manual intervention",
                "latest_outcome_brief": "intervention requested",
                "blocker_brief": "blocked by policy",
                "open_attention_count": 0,
                "open_blocking_attention_count": 0,
                "open_nonblocking_attention_count": 0,
                "attention_briefs": ["[policy_gap] policy review"],
                "attention_titles": ["policy review"],
                "brief": {
                    "goal": "Resolve alert",
                    "now": "Need manual intervention",
                    "wait": "blocked by runtime",
                    "agent_activity": "1 reusable session",
                    "operator_state": "pause requested",
                    "progress": {
                        "done": "initial triage",
                        "doing": "awaiting operator response",
                        "next": "resume after review",
                    },
                    "attention": "[policy_gap] policy review",
                    "review": "review the non-blocking follow-up",
                    "recent": "intervention requested",
                },
            }
        ],
        "control_hints": [],
        "mix": {
            "bucket_counts": {"needs_attention": 1, "active": 0, "recent": 0},
            "status_counts": {"running": 1},
            "scheduler_counts": {"active": 1},
            "involvement_counts": {"auto": 1},
        },
    }

    async def _load_fleet_payload_with_brief() -> dict[str, object]:
        return payload

    controller = build_fleet_workbench_controller(
        load_payload=_load_fleet_payload_with_brief,
        load_operation_payload=_load_operation_payload,
        pause_operation=_unexpected_action,
        unpause_operation=_unexpected_action,
        interrupt_operation=_unexpected_interrupt,
        cancel_operation=_unexpected_action,
        answer_attention=_unexpected_answer,
    )

    await controller.refresh()
    assert controller.state.selected_fleet_brief is not None
    assert controller.state.selected_fleet_brief["goal"] == "Resolve alert"
    console = Console(record=True, width=140, markup=False)
    console.print(controller.render())
    rendered = console.export_text(styles=False)
    for section in (
        "Goal",
        "Now",
        "Wait",
        "Agent",
        "Operator",
        "Progress",
        "Attention",
        "Review",
        "Recent",
        "doing=awaiting operator response",
    ):
        assert section in rendered


async def _unexpected_action(operation_id: str) -> str:
    raise AssertionError(f"Unexpected action for {operation_id}")


async def _unexpected_interrupt(operation_id: str, task_id: str | None) -> str:
    raise AssertionError(f"Unexpected interrupt for {operation_id}:{task_id}")


async def _unexpected_answer(operation_id: str, attention_id: str, text: str) -> str:
    raise AssertionError(f"Unexpected answer for {operation_id}:{attention_id}:{text}")
