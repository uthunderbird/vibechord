from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any, cast

from vibechord.mcp import McpSession, handle_request, run_stdio
from vibechord.sdk import VibechordClient


def test_mcp_initialize_and_tool_list(tmp_path: Path) -> None:
    client = VibechordClient(tmp_path)

    initialized = handle_request(
        client,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    listed = handle_request(client, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

    assert initialized is not None
    capabilities = initialized["result"]["capabilities"]
    assert capabilities["tools"]["listChanged"] is False
    assert capabilities["resources"]["subscribe"] is True
    assert capabilities["prompts"]["listChanged"] is False
    assert listed is not None
    tools = listed["result"]["tools"]
    assert {tool["name"] for tool in tools} >= {
        "vibechord_run",
        "vibechord_status",
        "vibechord_fleet",
        "vibechord_live",
        "vibechord_message",
    }


def test_mcp_tool_calls_use_shared_sdk_contracts(tmp_path: Path) -> None:
    client = VibechordClient(tmp_path)

    run_response = handle_request(
        client,
        {
            "jsonrpc": "2.0",
            "id": "run",
            "method": "tools/call",
            "params": {"name": "vibechord_run", "arguments": {"goal": "mcp goal"}},
        },
    )

    assert run_response is not None
    run_result = run_response["result"]
    assert run_result["isError"] is False
    operation_id = run_result["structuredContent"]["operation_id"]
    status_response = handle_request(
        client,
        {
            "jsonrpc": "2.0",
            "id": "status",
            "method": "tools/call",
            "params": {
                "name": "vibechord_status",
                "arguments": {"operation_id": operation_id},
            },
        },
    )
    assert status_response is not None
    assert status_response["result"]["structuredContent"]["status"] == "completed"


def test_mcp_tool_call_emits_progress_when_requested(tmp_path: Path) -> None:
    event_path = tmp_path / "mcp-events.jsonl"
    session = McpSession(VibechordClient(tmp_path), event_path)
    notifications: list[dict[str, Any]] = []
    session.progress_sink = notifications.append

    response = session.handle_request(
        {
            "jsonrpc": "2.0",
            "id": "run",
            "method": "tools/call",
            "params": {
                "_meta": {"progressToken": "progress-1"},
                "name": "vibechord_run",
                "arguments": {"goal": "progress goal"},
            },
        }
    )

    assert response is not None
    assert response["result"]["isError"] is False
    assert [event.event_id for event in session.events_after(0)] == [1, 2, 3]
    assert [item["method"] for item in notifications] == [
        "notifications/progress",
        "notifications/progress",
        "notifications/progress",
    ]
    progress_values = [
        cast(dict[str, Any], item["params"])["progress"] for item in notifications
    ]
    assert progress_values == sorted(progress_values)
    assert (
        cast(dict[str, Any], notifications[0]["params"])["progressToken"]
        == "progress-1"
    )

    resumed = McpSession(VibechordClient(tmp_path), event_path)
    assert [event.event_id for event in resumed.events_after(0)] == [1, 2, 3]


def test_mcp_reports_unknown_tools_as_protocol_errors(tmp_path: Path) -> None:
    response = handle_request(
        VibechordClient(tmp_path),
        {
            "jsonrpc": "2.0",
            "id": "bad",
            "method": "tools/call",
            "params": {"name": "missing", "arguments": {}},
        },
    )

    assert response is not None
    assert response["error"]["code"] == -32602


def test_mcp_resources_read_shared_projection_data(tmp_path: Path) -> None:
    client = VibechordClient(tmp_path)
    run = client.run("resource goal")
    assert run.operation_id is not None

    listed = handle_request(
        client, {"jsonrpc": "2.0", "id": 1, "method": "resources/list"}
    )
    read = handle_request(
        client,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "resources/read",
            "params": {"uri": f"vibechord://operations/{run.operation_id}/status"},
        },
    )

    assert listed is not None
    assert listed["result"]["resources"][0]["uri"] == "vibechord://project"
    assert read is not None
    content = json.loads(read["result"]["contents"][0]["text"])
    assert content["operation_id"] == run.operation_id
    assert content["status"] == "completed"


def test_mcp_resource_subscriptions_are_session_state(tmp_path: Path) -> None:
    session = McpSession(VibechordClient(tmp_path))

    subscribed = session.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "resources/subscribe",
            "params": {"uri": "vibechord://fleet"},
        }
    )
    assert subscribed is not None
    assert subscribed["result"] == {}
    assert "vibechord://fleet" in session.subscribed_resources

    unsubscribed = session.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "resources/unsubscribe",
            "params": {"uri": "vibechord://fleet"},
        }
    )

    assert "vibechord://fleet" not in session.subscribed_resources
    assert unsubscribed is not None
    assert unsubscribed["result"] == {}


def test_mcp_prompts_list_and_get() -> None:
    client = VibechordClient(".")

    listed = handle_request(
        client, {"jsonrpc": "2.0", "id": 1, "method": "prompts/list"}
    )
    fetched = handle_request(
        client,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "prompts/get",
            "params": {
                "name": "vibechord_start_operation",
                "arguments": {"goal": "ship"},
            },
        },
    )

    assert listed is not None
    assert listed["result"]["prompts"][0]["name"] == "vibechord_start_operation"
    assert fetched is not None
    message = fetched["result"]["messages"][0]
    assert message["role"] == "user"
    assert "ship" in message["content"]["text"]


def test_mcp_stdio_reads_and_writes_jsonrpc_lines(tmp_path: Path) -> None:
    incoming = StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
    )
    outgoing = StringIO()

    assert run_stdio(tmp_path, input_stream=incoming, output_stream=outgoing) == 0

    payload = json.loads(outgoing.getvalue())
    assert payload["jsonrpc"] == "2.0"
    assert payload["result"]["tools"][0]["name"] == "vibechord_run"


def test_mcp_stdio_writes_progress_before_tool_response(tmp_path: Path) -> None:
    incoming = StringIO(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "run",
                "method": "tools/call",
                "params": {
                    "_meta": {"progressToken": 7},
                    "name": "vibechord_run",
                    "arguments": {"goal": "stdio progress"},
                },
            }
        )
        + "\n"
    )
    outgoing = StringIO()

    assert run_stdio(tmp_path, input_stream=incoming, output_stream=outgoing) == 0

    messages = [json.loads(line) for line in outgoing.getvalue().splitlines()]
    assert [message.get("method") for message in messages[:3]] == [
        "notifications/progress",
        "notifications/progress",
        "notifications/progress",
    ]
    assert messages[0]["params"]["progressToken"] == 7
    assert messages[-1]["id"] == "run"
    assert messages[-1]["result"]["structuredContent"]["accepted"] is True
