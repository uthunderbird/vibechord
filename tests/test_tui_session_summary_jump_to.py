from __future__ import annotations

from rich.console import Console

from agent_operator.cli.tui.models import FleetWorkbenchState
from agent_operator.cli.tui.rendering import render_session_brief_table


def test_session_brief_table_uses_next_step_summary_cue() -> None:
    state = FleetWorkbenchState(
        view_level="session",
        selected_operation_payload={
            "tasks": [
                {
                    "task_id": "task-1",
                    "task_short_id": "task-1",
                    "title": "Build the task board",
                    "status": "running",
                    "linked_session_id": "session-1",
                }
            ],
            "session_views": [
                {
                    "task_id": "task-1",
                    "session": {
                        "adapter_key": "codex_acp",
                        "session_id": "session-1",
                    },
                    "session_brief": {
                        "now": "Working through the board layout.",
                        "wait": "Waiting for a layout decision.",
                        "attention": "Need a layout decision",
                        "latest_output": "[iter 1] agent started: codex_acp",
                    },
                }
            ],
        },
    )

    console = Console(record=True, width=160, markup=False)
    console.print(render_session_brief_table(state))
    rendered = console.export_text(styles=False)

    assert "Timeline" in rendered
    assert "No timeline events." in rendered
    assert "Next step" in rendered
    assert (
        "Open forensic Enter/r  ·  Live detail i  ·  Report o  ·  Back Esc  ·  Help ?"
        in rendered
    )
