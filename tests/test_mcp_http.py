from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from vibechord.mcp import McpSession
from vibechord.mcp_http import make_http_handler
from vibechord.rest import build_auth_config
from vibechord.sdk import VibechordClient


def test_mcp_http_post_routes_jsonrpc_to_shared_session(tmp_path: Path) -> None:
    session = McpSession(VibechordClient(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_http_handler(session))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/mcp",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "vibechord_run",
                        "arguments": {"goal": "http mcp"},
                    },
                }
            ).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["id"] == 1
        assert payload["result"]["structuredContent"]["accepted"] is True
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_mcp_http_authentication(tmp_path: Path) -> None:
    session = McpSession(VibechordClient(tmp_path))
    auth = build_auth_config(token="secret")
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), make_http_handler(session, token=auth)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/mcp",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode(
                "utf-8"
            ),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("request without bearer token should fail")

        authed = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/mcp",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode(
                "utf-8"
            ),
            method="POST",
            headers={
                "Authorization": "Bearer secret",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(authed) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["result"]["tools"][0]["name"] == "vibechord_run"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_mcp_http_notification_returns_accepted(tmp_path: Path) -> None:
    session = McpSession(VibechordClient(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_http_handler(session))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/mcp",
            data=json.dumps(
                {"jsonrpc": "2.0", "method": "notifications/initialized"}
            ).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            assert response.status == 202
            assert response.read() == b""
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_mcp_http_get_streams_recorded_events_with_resume(tmp_path: Path) -> None:
    event_path = tmp_path / "events.jsonl"
    session = McpSession(VibechordClient(tmp_path), event_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_http_handler(session))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        post = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/mcp",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": "run",
                    "method": "tools/call",
                    "params": {
                        "_meta": {"progressToken": "http-progress"},
                        "name": "vibechord_run",
                        "arguments": {"goal": "streaming"},
                    },
                }
            ).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(post) as response:
            assert response.status == 200

        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_port}/mcp"
        ) as response:
            body = response.read().decode("utf-8")
            assert response.headers["Content-Type"] == "text/event-stream"
        assert "id: 1" in body
        assert "notifications/progress" in body
        assert '"id": "run"' in body

        resumed_session = McpSession(VibechordClient(tmp_path), event_path)
        resumed_server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_http_handler(resumed_session)
        )
        resumed_thread = threading.Thread(
            target=resumed_server.serve_forever, daemon=True
        )
        resumed_thread.start()
        resume = urllib.request.Request(
            f"http://127.0.0.1:{resumed_server.server_port}/mcp",
            headers={"Last-Event-ID": "3"},
        )
        try:
            with urllib.request.urlopen(resume) as response:
                resumed = response.read().decode("utf-8")
            assert "id: 4" in resumed
            assert "id: 1" not in resumed
        finally:
            resumed_server.shutdown()
            resumed_thread.join(timeout=5)
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_mcp_http_get_waits_briefly_for_future_events(tmp_path: Path) -> None:
    session = McpSession(VibechordClient(tmp_path), tmp_path / "events.jsonl")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_http_handler(session))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    body_holder: list[str] = []

    def fetch() -> None:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_port}/mcp?wait=2"
        ) as response:
            body_holder.append(response.read().decode("utf-8"))

    fetch_thread = threading.Thread(target=fetch)
    fetch_thread.start()
    try:
        time.sleep(0.1)
        post = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/mcp",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode(
                "utf-8"
            ),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(post) as response:
            assert response.status == 200
        fetch_thread.join(timeout=5)
        assert body_holder
        assert "id: 1" in body_holder[0]
    finally:
        server.shutdown()
        thread.join(timeout=5)
