"""HTTP JSON-RPC transport for the MCP surface."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlparse

from vibechord.mcp import JsonObject, McpEvent, McpSession
from vibechord.rest import RestAuthConfig, build_auth_config, validate_binding
from vibechord.sdk import VibechordClient


def serve_http(
    root: Path,
    host: str = "127.0.0.1",
    port: int = 8766,
    unsafe: bool = False,
    token: str | None = None,
) -> None:
    """Serve MCP JSON-RPC over HTTP POST."""

    auth = build_auth_config(token)
    validate_binding(host, unsafe, auth)
    client = VibechordClient(root)
    session = McpSession(
        client, client.context.root / ".vibechord" / "mcp-events.jsonl"
    )
    server = ThreadingHTTPServer((host, port), make_http_handler(session, auth))
    server.serve_forever()


def make_http_handler(
    session: McpSession, token: str | RestAuthConfig | None = None
) -> type[BaseHTTPRequestHandler]:
    """Create an HTTP handler for a shared MCP session."""

    auth = token if isinstance(token, RestAuthConfig) else build_auth_config(token)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/mcp":
                _send_error(
                    self, HTTPStatus.NOT_FOUND, "not_found", "endpoint not found"
                )
                return
            if not _authorized(self, auth):
                _send_error(self, HTTPStatus.UNAUTHORIZED, "unauthorized", "bad token")
                return
            request = _read_json(self)
            if request is None:
                _send_error(
                    self, HTTPStatus.BAD_REQUEST, "invalid_json", "invalid JSON"
                )
                return
            response = session.handle_request(request)
            if response is None:
                self.send_response(HTTPStatus.ACCEPTED)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            session.record_response(response)
            _send(self, HTTPStatus.OK, response)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/mcp":
                _send_error(
                    self, HTTPStatus.NOT_FOUND, "not_found", "endpoint not found"
                )
                return
            if not _authorized(self, auth):
                _send_error(self, HTTPStatus.UNAUTHORIZED, "unauthorized", "bad token")
                return
            query = parse_qs(parsed.query)
            last_event_id = _last_event_id(self.headers.get("Last-Event-ID"))
            wait_seconds = _wait_seconds(query.get("wait", ["0"])[0])
            events = (
                session.wait_events_after(last_event_id, wait_seconds)
                if wait_seconds > 0
                else session.events_after(last_event_id)
            )
            _send_sse(self, events)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def _last_event_id(value: str | None) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except ValueError:
        return 0


def _wait_seconds(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError:
        return 0.0
    return max(0.0, min(parsed, 30.0))


def _authorized(handler: BaseHTTPRequestHandler, auth: RestAuthConfig) -> bool:
    if not auth.enabled:
        return True
    header = handler.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return False
    from vibechord.rest import _scopes_for_token

    return _scopes_for_token(auth, header.removeprefix("Bearer ")) is not None


def _read_json(handler: BaseHTTPRequestHandler) -> JsonObject | None:
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return None
    try:
        loaded = json.loads(handler.rfile.read(length).decode("utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, dict):
        return None
    return cast(JsonObject, loaded)


def _send(handler: BaseHTTPRequestHandler, status: HTTPStatus, payload: object) -> None:
    data = json.dumps(payload, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _send_sse(handler: BaseHTTPRequestHandler, events: tuple[McpEvent, ...]) -> None:
    data = "".join(_sse_event(event) for event in events).encode("utf-8")
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _sse_event(event: McpEvent) -> str:
    payload = json.dumps(event.message, sort_keys=True)
    return f"id: {event.event_id}\nevent: message\ndata: {payload}\n\n"


def _send_error(
    handler: BaseHTTPRequestHandler, status: HTTPStatus, code: str, message: str
) -> None:
    _send(
        handler,
        status,
        {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": code, "message": message},
        },
    )
