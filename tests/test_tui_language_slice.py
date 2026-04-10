from __future__ import annotations

from agent_operator.cli.tui.models import FleetItem, FleetWorkbenchState
from agent_operator.cli.tui.rendering import human_footer_text, rendered_header_lines


def _fleet_item(**overrides: object) -> FleetItem:
    payload = {
        "operation_id": "op-run",
        "display_name": "Ship dashboard",
        "state_label": "running",
        "attention_badge": "-",
        "status": "running",
        "scheduler_state": "active",
        "focus_brief": "Working on the task board",
        "latest_outcome_brief": "awaiting review",
    }
    payload.update(overrides)
    return FleetItem.from_payload(payload)


def test_rendered_header_lines_use_human_operation_summary_language() -> None:
    state = FleetWorkbenchState(
        items=[_fleet_item()],
        selected_index=0,
        total_operations=3,
        view_level="operation",
        selected_operation_payload={
            "operation_brief": {
                "now": "Working on the dashboard layout.",
                "wait": "Waiting for a layout decision.",
                "attention": "[policy_gap] Need a layout decision.",
            },
            "tasks": [
                {
                    "task_id": "task-1",
                    "task_short_id": "task-1",
                    "title": "Build the task board",
                    "goal": "Render the operation task board.",
                    "definition_of_done": "Board visible in TUI.",
                    "status": "running",
                },
                {
                    "task_id": "task-2",
                    "task_short_id": "task-2",
                    "title": "Wire right pane modes",
                    "goal": "Show decisions, events, and memory.",
                    "definition_of_done": "Mode keys switch the right pane.",
                    "status": "pending",
                    "dependencies": ["task-1"],
                },
            ],
        },
    )

    lines = rendered_header_lines(state)

    assert lines[0] == "Fleet / op-run / operation"
    assert lines[1] == "Scope: all projects  Operations: 3  Running: 1  Needs human: 0  Paused: 0"
    assert "Tasks: 2  Running: 1  Blocked: 1" in lines[2]
    assert "Now: Working on the dashboard layout." in lines[2]
    assert "Wait: Waiting for a layout decision." in lines[2]
    assert "Attention: [policy_gap] Need a layout decision." in lines[2]


def test_human_footer_text_uses_current_human_first_session_actions() -> None:
    state = FleetWorkbenchState(
        items=[_fleet_item()],
        selected_index=0,
        view_level="session",
    )

    assert (
        human_footer_text(state).plain
        == "Move j/k  Filter /  Open forensic Enter/r  Live detail i  Report o"
        "  Back Esc  Answer a/n  Pick A  Interrupt s  Pause p  Resume u"
        "  Cancel c  Help ?  Quit q"
    )
