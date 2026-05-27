"""MCP stdio surface over the local SDK contracts."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Condition
from typing import Any, TextIO, cast

from vibechord.jsonutil import to_jsonable
from vibechord.sdk import VibechordClient

JsonObject = dict[str, Any]
RequestId = str | int | None
ProgressSink = Callable[[JsonObject], None]

PROTOCOL_VERSION = "2025-06-18"


@dataclass(frozen=True)
class McpEvent:
    """Recorded MCP transport event for resumable delivery."""

    event_id: int
    message: JsonObject


def handle_request(client: VibechordClient, request: JsonObject) -> JsonObject | None:
    """Handle one JSON-RPC request or notification."""

    return McpSession(client).handle_request(request)


class McpSession:
    """Stateful MCP request handler for one stdio session."""

    def __init__(self, client: VibechordClient, event_path: Path | None = None) -> None:
        """Create a session backed by one local SDK client."""

        self.client = client
        self.subscribed_resources: set[str] = set()
        self.progress_sink: ProgressSink | None = None
        self._event_path = event_path
        self._condition = Condition()
        self._events = _load_events(event_path)
        self._next_event_id = (
            max((event.event_id for event in self._events), default=0) + 1
        )

    def handle_request(self, request: JsonObject) -> JsonObject | None:
        """Handle one JSON-RPC request or notification."""

        request_id = request.get("id")
        method = request.get("method")
        if not isinstance(method, str):
            return _error(request_id, -32600, "invalid JSON-RPC request")
        if "id" not in request:
            return None
        if method == "initialize":
            return _result(request_id, _initialize_result())
        if method == "ping":
            return _result(request_id, {})
        if method == "tools/list":
            return _result(request_id, {"tools": _tools()})
        if method == "tools/call":
            progress = _progress_reporter(request, self._record_progress)
            return _handle_tool_call(
                self.client, request_id, request.get("params"), progress
            )
        if method == "resources/list":
            return _result(request_id, {"resources": _resources()})
        if method == "resources/read":
            return _handle_resource_read(self.client, request_id, request.get("params"))
        if method == "resources/subscribe":
            return self._handle_resource_subscribe(request_id, request.get("params"))
        if method == "resources/unsubscribe":
            return self._handle_resource_unsubscribe(request_id, request.get("params"))
        if method == "prompts/list":
            return _result(request_id, {"prompts": _prompts()})
        if method == "prompts/get":
            return _handle_prompt_get(request_id, request.get("params"))
        return _error(request_id, -32601, f"method not found: {method}")

    def _handle_resource_subscribe(
        self, request_id: object, params: object
    ) -> JsonObject:
        uri = _uri_param(params)
        if uri is None:
            return _error(request_id, -32602, "resource uri must be a string")
        self.subscribed_resources.add(uri)
        return _result(request_id, {})

    def _handle_resource_unsubscribe(
        self, request_id: object, params: object
    ) -> JsonObject:
        uri = _uri_param(params)
        if uri is None:
            return _error(request_id, -32602, "resource uri must be a string")
        self.subscribed_resources.discard(uri)
        return _result(request_id, {})

    def record_response(self, response: JsonObject) -> McpEvent:
        """Record a JSON-RPC response for resumable transports."""

        return self._record_event(response)

    def events_after(self, event_id: int) -> tuple[McpEvent, ...]:
        """Return recorded transport events after a cursor."""

        with self._condition:
            return tuple(event for event in self._events if event.event_id > event_id)

    def wait_events_after(
        self, event_id: int, timeout_seconds: float
    ) -> tuple[McpEvent, ...]:
        """Wait briefly for events after a cursor and return available events."""

        with self._condition:
            self._condition.wait_for(
                lambda: any(event.event_id > event_id for event in self._events),
                timeout=timeout_seconds,
            )
            return tuple(event for event in self._events if event.event_id > event_id)

    def _record_progress(self, notification: JsonObject) -> None:
        event = self._record_event(notification)
        if self.progress_sink is not None:
            self.progress_sink(event.message)

    def _record_event(self, message: JsonObject) -> McpEvent:
        with self._condition:
            event = McpEvent(self._next_event_id, message)
            self._events.append(event)
            self._append_event(event)
            self._next_event_id += 1
            self._condition.notify_all()
            return event

    def _append_event(self, event: McpEvent) -> None:
        if self._event_path is None:
            return
        self._event_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"event_id": event.event_id, "message": event.message}
        with self._event_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")


def run_stdio(
    root: Path, input_stream: TextIO | None = None, output_stream: TextIO | None = None
) -> int:
    """Run a newline-delimited JSON-RPC stdio loop."""

    session = McpSession(VibechordClient(root))
    incoming = input_stream or sys.stdin
    outgoing = output_stream or sys.stdout
    session.progress_sink = lambda notification: _write_json(outgoing, notification)
    for line in incoming:
        line = line.strip()
        if not line:
            continue
        response: JsonObject | None
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = _error(None, -32700, f"parse error: {exc.msg}")
        else:
            if not isinstance(request, dict):
                response = _error(None, -32600, "invalid JSON-RPC request")
            else:
                response = session.handle_request(cast(JsonObject, request))
        if response is not None:
            session.record_response(response)
            _write_json(outgoing, response)
    return 0


def _load_events(event_path: Path | None) -> list[McpEvent]:
    if event_path is None or not event_path.exists():
        return []
    events: list[McpEvent] = []
    for line_number, line in enumerate(
        event_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"corrupt MCP event log at line {line_number}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"corrupt MCP event log at line {line_number}")
        event_id = payload.get("event_id")
        message = payload.get("message")
        if not isinstance(event_id, int) or not isinstance(message, dict):
            raise ValueError(f"corrupt MCP event log at line {line_number}")
        events.append(McpEvent(event_id, cast(JsonObject, message)))
    return events


def _handle_tool_call(
    client: VibechordClient,
    request_id: object,
    params: object,
    progress: ProgressSink | None = None,
) -> JsonObject:
    if not isinstance(params, dict):
        return _error(request_id, -32602, "tools/call params must be an object")
    name = params.get("name")
    arguments = params.get("arguments", {})
    if not isinstance(name, str) or not isinstance(arguments, dict):
        return _error(request_id, -32602, "invalid tools/call params")

    try:
        _report_progress(progress, 1, 3, "validated tool request")
        structured = _call_tool(client, name, arguments)
        _report_progress(progress, 2, 3, "completed tool execution")
    except KeyError:
        return _error(request_id, -32602, f"unknown tool: {name}")
    except (TypeError, ValueError) as exc:
        return _result(request_id, _tool_error(str(exc)))
    _report_progress(progress, 3, 3, "encoded tool result")

    return _result(
        request_id,
        {
            "content": [
                {"type": "text", "text": json.dumps(structured, sort_keys=True)}
            ],
            "structuredContent": structured,
            "isError": False,
        },
    )


def _call_tool(
    client: VibechordClient, name: str, arguments: dict[str, Any]
) -> JsonObject:
    if name == "vibechord_run":
        goal = _required_str(arguments, "goal")
        return cast(JsonObject, to_jsonable(client.run(goal)))
    if name == "vibechord_status":
        operation_id = _required_str(arguments, "operation_id")
        return cast(JsonObject, to_jsonable(client.status(operation_id)))
    if name == "vibechord_fleet":
        return {"fleet": to_jsonable(client.fleet())}
    if name == "vibechord_live":
        operation_id = _required_str(arguments, "operation_id")
        return {"events": to_jsonable(client.live(operation_id))}
    if name == "vibechord_message":
        operation_id = _required_str(arguments, "operation_id")
        text = _required_str(arguments, "text")
        return cast(JsonObject, to_jsonable(client.message(operation_id, text)))
    raise KeyError(name)


def _progress_reporter(
    request: JsonObject, progress_sink: ProgressSink | None
) -> ProgressSink | None:
    if progress_sink is None:
        return None
    progress_token = _progress_token(request.get("params"))
    if progress_token is None:
        return None

    def report(notification: JsonObject) -> None:
        progress_sink(
            _progress_notification(
                progress_token,
                cast(float, notification["progress"]),
                cast(float | None, notification.get("total")),
                cast(str | None, notification.get("message")),
            )
        )

    return report


def _progress_token(params: object) -> str | int | None:
    if not isinstance(params, dict):
        return None
    meta = params.get("_meta")
    if not isinstance(meta, dict):
        return None
    token = meta.get("progressToken")
    if isinstance(token, str | int):
        return token
    return None


def _report_progress(
    progress: ProgressSink | None,
    current: float,
    total: float,
    message: str,
) -> None:
    if progress is None:
        return
    progress({"progress": current, "total": total, "message": message})


def _progress_notification(
    progress_token: str | int,
    progress: float,
    total: float | None = None,
    message: str | None = None,
) -> JsonObject:
    params: JsonObject = {"progressToken": progress_token, "progress": progress}
    if total is not None:
        params["total"] = total
    if message is not None:
        params["message"] = message
    return {"jsonrpc": "2.0", "method": "notifications/progress", "params": params}


def _required_str(arguments: dict[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _initialize_result() -> JsonObject:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"subscribe": True, "listChanged": False},
            "prompts": {"listChanged": False},
        },
        "serverInfo": {
            "name": "vibechord",
            "title": "vibechord",
            "version": "0.1.0",
        },
        "instructions": "Use tools to supervise local vibechord operations.",
    }


def _tools() -> list[JsonObject]:
    return [
        _tool(
            "vibechord_run", "Run Operation", "Start and drive an operation.", ("goal",)
        ),
        _tool(
            "vibechord_status",
            "Operation Status",
            "Read operation status.",
            ("operation_id",),
        ),
        _tool("vibechord_fleet", "Fleet", "List operation fleet rows.", ()),
        _tool(
            "vibechord_live",
            "Live Feed",
            "Read live-feed envelopes for an operation.",
            ("operation_id",),
        ),
        _tool(
            "vibechord_message",
            "Post Message",
            "Post a live operator message to an operation.",
            ("operation_id", "text"),
        ),
    ]


def _resources() -> list[JsonObject]:
    return [
        {
            "uri": "vibechord://project",
            "name": "project",
            "description": "Workspace and state-directory information.",
            "mimeType": "application/json",
        },
        {
            "uri": "vibechord://fleet",
            "name": "fleet",
            "description": "Current operation fleet rows.",
            "mimeType": "application/json",
        },
    ]


def _handle_resource_read(
    client: VibechordClient, request_id: object, params: object
) -> JsonObject:
    uri = _uri_param(params)
    if uri is None:
        return _error(request_id, -32602, "resource uri must be a string")
    try:
        resource = _read_resource(client, uri)
    except KeyError:
        return _error(request_id, -32602, f"unknown resource: {uri}")
    return _result(request_id, {"contents": [resource]})


def _read_resource(client: VibechordClient, uri: str) -> JsonObject:
    if uri == "vibechord://project":
        return _text_resource(
            uri,
            {
                "root": str(client.context.root),
                "state_dir": str(client.context.root / ".vibechord"),
            },
        )
    if uri == "vibechord://fleet":
        return _text_resource(uri, {"fleet": to_jsonable(client.fleet())})
    prefix = "vibechord://operations/"
    suffix = "/status"
    if uri.startswith(prefix) and uri.endswith(suffix):
        operation_id = uri.removeprefix(prefix).removesuffix(suffix)
        return _text_resource(uri, to_jsonable(client.status(operation_id)))
    raise KeyError(uri)


def _text_resource(uri: str, value: object) -> JsonObject:
    return {
        "uri": uri,
        "mimeType": "application/json",
        "text": json.dumps(value, sort_keys=True),
    }


def _uri_param(params: object) -> str | None:
    if not isinstance(params, dict):
        return None
    uri = params.get("uri")
    if not isinstance(uri, str) or not uri:
        return None
    return uri


def _prompts() -> list[JsonObject]:
    return [
        {
            "name": "vibechord_start_operation",
            "title": "Start Operation",
            "description": "Ask a model to turn an objective into a vibechord run.",
            "arguments": [
                {
                    "name": "goal",
                    "description": "The operation goal.",
                    "required": True,
                }
            ],
        },
        {
            "name": "vibechord_inspect_operation",
            "title": "Inspect Operation",
            "description": "Ask a model to inspect one operation from shared status.",
            "arguments": [
                {
                    "name": "operation_id",
                    "description": "The operation id.",
                    "required": True,
                }
            ],
        },
    ]


def _handle_prompt_get(request_id: object, params: object) -> JsonObject:
    if not isinstance(params, dict):
        return _error(request_id, -32602, "prompts/get params must be an object")
    name = params.get("name")
    arguments = params.get("arguments", {})
    if not isinstance(name, str) or not isinstance(arguments, dict):
        return _error(request_id, -32602, "invalid prompts/get params")
    try:
        prompt = _prompt(name, arguments)
    except KeyError:
        return _error(request_id, -32602, f"unknown prompt: {name}")
    except ValueError as exc:
        return _error(request_id, -32602, str(exc))
    return _result(request_id, prompt)


def _prompt(name: str, arguments: dict[object, object]) -> JsonObject:
    if name == "vibechord_start_operation":
        goal = _required_prompt_arg(arguments, "goal")
        return _prompt_result(
            "Start a vibechord operation",
            f"Start a vibechord operation for this goal: {goal}",
        )
    if name == "vibechord_inspect_operation":
        operation_id = _required_prompt_arg(arguments, "operation_id")
        return _prompt_result(
            "Inspect a vibechord operation",
            "Inspect the operation status, live feed, and fleet context for "
            f"operation id {operation_id}.",
        )
    raise KeyError(name)


def _required_prompt_arg(arguments: dict[object, object], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _prompt_result(description: str, text: str) -> JsonObject:
    return {
        "description": description,
        "messages": [
            {
                "role": "user",
                "content": {"type": "text", "text": text},
            }
        ],
    }


def _tool(
    name: str, title: str, description: str, required: tuple[str, ...]
) -> JsonObject:
    properties: JsonObject = {}
    for field_name in required:
        properties[field_name] = {"type": "string"}
    return {
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": list(required),
            "additionalProperties": False,
        },
    }


def _tool_error(message: str) -> JsonObject:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }


def _result(request_id: object, result: JsonObject) -> JsonObject:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: object, code: int, message: str) -> JsonObject:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _write_json(output_stream: TextIO, message: JsonObject) -> None:
    output_stream.write(json.dumps(message, sort_keys=True) + "\n")
    output_stream.flush()
