from __future__ import annotations

import pytest
from rich.console import Console

from agent_operator.cli.tui import build_fleet_workbench_controller

pytestmark = pytest.mark.anyio


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
        "Session: codex_acp",
        "Now",
        "Wait",
        "Attention",
        "Latest output",
        "Selected Event",
        "agent started",
        "Need a layout decision",
    ):
        assert section in rendered


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


async def test_session_view_a_enters_answer_mode_for_task_attention() -> None:
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
    await controller.handle_key("a")

    assert controller.state.pending_answer_operation_id == "op-run"
    assert controller.state.pending_answer_attention_id == "att-1"
    assert controller.state.pending_answer_text == ""
    assert (
        controller.state.last_message == "Answer selected. Type text, Enter to send, Esc to cancel."
    )


async def test_session_view_a_dispatches_answer_for_current_task() -> None:
    answers: list[tuple[str, str, str]] = []

    async def _answer(operation_id: str, attention_id: str, text: str) -> str:
        answers.append((operation_id, attention_id, text))
        return f"answered {operation_id}:{attention_id}:{text}"

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
    await controller.handle_key("\r")
    await controller.handle_key("\r")
    await controller.handle_key("a")
    await controller.handle_key("o")
    await controller.handle_key("k")
    await controller.handle_key("\r")

    assert answers == [("op-run", "att-1", "ok")]
    assert controller.state.pending_answer_operation_id is None
    assert controller.state.pending_answer_attention_id is None
    assert controller.state.last_message == "answered op-run:att-1:ok"


async def test_session_enter_opens_forensic_even_without_raw_transcript() -> None:
    controller = build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload_without_transcript,
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
    assert controller.state.last_message is None

    console = Console(record=True, width=180, markup=False)
    console.print(controller.render())
    rendered = console.export_text(styles=False)
    assert "Forensic Transcript" in rendered
    assert "No raw transcript available for the selected session." in rendered


async def test_forensic_view_a_enters_answer_mode_for_current_task() -> None:
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
    await controller.handle_key("a")

    assert controller.state.view_level == "forensic"
    assert controller.state.pending_answer_operation_id == "op-run"
    assert controller.state.pending_answer_attention_id == "att-1"


async def test_forensic_view_a_dispatches_answer_for_current_task() -> None:
    answers: list[tuple[str, str, str]] = []

    async def _answer(operation_id: str, attention_id: str, text: str) -> str:
        answers.append((operation_id, attention_id, text))
        return f"answered {operation_id}:{attention_id}:{text}"

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
    await controller.handle_key("\r")
    await controller.handle_key("\r")
    await controller.handle_key("\r")
    await controller.handle_key("a")
    await controller.handle_key("y")
    await controller.handle_key("e")
    await controller.handle_key("s")
    await controller.handle_key("\r")

    assert answers == [("op-run", "att-1", "yes")]
    assert controller.state.pending_answer_operation_id is None
    assert controller.state.pending_answer_attention_id is None
    assert controller.state.last_message == "answered op-run:att-1:yes"


async def _load_payload() -> dict[str, object]:
    return {
        "project": None,
        "total_operations": 2,
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
            }
        ],
        "recent": [],
    }


async def _load_operation_payload(operation_id: str) -> dict[str, object]:
    return {
        "operation_id": operation_id,
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
            }
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
            }
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
    }


async def _load_operation_payload_without_transcript(operation_id: str) -> dict[str, object]:
    payload = await _load_operation_payload(operation_id)
    payload["upstream_transcript"] = {"title": "No transcript", "events": []}
    return payload


async def _unexpected_action(operation_id: str) -> str:
    raise AssertionError(f"Unexpected action for {operation_id}")


async def _unexpected_interrupt(operation_id: str, task_id: str | None) -> str:
    raise AssertionError(f"Unexpected interrupt for {operation_id}:{task_id}")


async def _unexpected_answer(operation_id: str, attention_id: str, text: str) -> str:
    raise AssertionError(f"Unexpected answer for {operation_id}:{attention_id}:{text}")
