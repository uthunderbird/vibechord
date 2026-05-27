from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from io import StringIO
from pathlib import Path

import pytest

from vibechord import rest
from vibechord.cli import main
from vibechord.domain import CommandName, FleetRowDTO, OperationCommand, StatusDTO
from vibechord.tui import (
    fleet_view,
    operation_view,
    reduce_key,
    render,
    render_fullscreen,
    run_curses,
    run_terminal,
)
from vibechord.verify import commands_for
from vibechord.workspace import build_context


def test_cli_json_status_and_fleet_share_dto_shape(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["--root", str(tmp_path), "--json", "init"]) == 0
    capsys.readouterr()
    assert main(["--root", str(tmp_path), "--json", "run", "goal"]) == 0
    run_payload = json.loads(capsys.readouterr().out)
    operation_id = run_payload["operation_id"]
    assert main(["--root", str(tmp_path), "--json", "status", operation_id]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert {
        "operation_id",
        "status",
        "goal",
        "source_sequence",
        "stale",
    } <= status_payload.keys()
    assert main(["--root", str(tmp_path), "--json", "fleet", "--once"]) == 0
    fleet_payload = json.loads(capsys.readouterr().out)
    assert {
        "operation_id",
        "status",
        "label",
        "source_sequence",
        "stale",
    } <= fleet_payload[0].keys()
    assert main(["--root", str(tmp_path), "--json", "project"]) == 0
    project_payload = json.loads(capsys.readouterr().out)
    assert project_payload["root"] == str(tmp_path.resolve())
    assert main(["--root", str(tmp_path), "--json", "agent"]) == 0
    agent_payload = json.loads(capsys.readouterr().out)
    assert agent_payload["agents"][0]["name"] == "fake-agent"
    assert (
        main(["--root", str(tmp_path), "--json", "show", "report", operation_id]) == 0
    )
    report_payload = json.loads(capsys.readouterr().out)
    assert report_payload["status"]["operation_id"] == operation_id


def test_tui_render_and_reducer_dispatch_command() -> None:
    row = FleetRowDTO("op-1", "running", "goal", None, None, 1, False)
    state = fleet_view((row,))
    assert "op-1 running" in render(state)
    result = reduce_key(state, "m", command_id="cmd", text="hello")
    assert result.command is not None
    assert result.command.operation_id == "op-1"
    op_state = operation_view(
        StatusDTO("op-1", "blocked", "goal", 1, True, None, "a1", "approve?", (), None)
    )
    assert "stale" in render(op_state)
    assert "approve?" in render(op_state)
    assert "q quit" in render_fullscreen(state)[1]


def test_terminal_tui_runtime_renders_once(tmp_path: Path) -> None:
    context = build_context(tmp_path)
    context.command_application.apply(
        OperationCommand(
            name=CommandName.START,
            command_id="start",
            operation_id="op-1",
            payload={"goal": "tui"},
        )
    )
    output = StringIO()
    run_terminal(context, once=True, output_stream=output)
    assert "Fleet" in output.getvalue()
    assert "op-1" in output.getvalue()


class FakeScreen:
    def __init__(self, keys: list[int]) -> None:
        self.keys = keys
        self.frames: list[str] = []
        self.current: list[str] = []

    def clear(self) -> None:
        self.current = []

    def addstr(self, y: int, x: int, text: str) -> None:
        self.current.append(text)

    def refresh(self) -> None:
        self.frames.append("\n".join(self.current))

    def getch(self) -> int:
        if not self.keys:
            return ord("q")
        return self.keys.pop(0)


def test_curses_tui_runtime_opens_operation_and_posts_message(tmp_path: Path) -> None:
    context = build_context(tmp_path)
    context.command_application.apply(
        OperationCommand(
            name=CommandName.START,
            command_id="start",
            operation_id="op-1",
            payload={"goal": "fullscreen"},
        )
    )
    screen = FakeScreen([10, ord("m"), ord("q")])

    run_curses(
        context,
        screen,
        input_provider=lambda prompt: "hello" if prompt == "message" else "",
    )

    assert any("Operation op-1" in frame for frame in screen.frames)
    assert context.projection_service.status("op-1").recent_messages == ("hello",)


def test_curses_tui_cancel_requires_confirmation(tmp_path: Path) -> None:
    context = build_context(tmp_path)
    context.command_application.apply(
        OperationCommand(
            name=CommandName.START,
            command_id="start",
            operation_id="op-1",
            payload={"goal": "cancel"},
        )
    )
    screen = FakeScreen([ord("c"), ord("c"), ord("q")])

    run_curses(context, screen)

    assert context.projection_service.status("op-1").status == "cancelled"


def test_rest_local_binding_guard() -> None:
    rest.validate_binding("127.0.0.1")
    rest.validate_binding("0.0.0.0", token="secret")
    rest.validate_binding(
        "0.0.0.0", token=rest.build_auth_config(read_token="read-secret")
    )
    rest.validate_binding(
        "0.0.0.0",
        token=rest.build_auth_config(token="secret"),
        production=True,
        tls_cert=Path("cert.pem"),
    )
    try:
        rest.validate_binding("0.0.0.0")
    except rest.RestConfigError:
        pass
    else:
        raise AssertionError("non-loopback binding must fail without unsafe")
    with pytest.raises(rest.RestConfigError, match="cannot use unsafe"):
        rest.validate_binding(
            "0.0.0.0",
            unsafe=True,
            token=rest.build_auth_config(token="secret"),
            production=True,
            tls_cert=Path("cert.pem"),
        )
    with pytest.raises(rest.RestConfigError, match="requires auth"):
        rest.validate_binding("0.0.0.0", production=True, tls_cert=Path("cert.pem"))
    with pytest.raises(rest.RestConfigError, match="requires TLS cert"):
        rest.validate_binding(
            "0.0.0.0",
            token=rest.build_auth_config(token="secret"),
            production=True,
        )


def test_rest_auth_config_hashes_tokens() -> None:
    auth = rest.build_auth_config(
        token="admin-secret",
        read_token="read-secret",
        control_token="control-secret",
    )

    assert auth.enabled is True
    hashes = {grant.token_hash for grant in auth.grants}
    assert "admin-secret" not in hashes
    assert "read-secret" not in hashes
    assert "control-secret" not in hashes
    assert len(hashes) == 3


def test_rest_endpoints_route_through_shared_application(tmp_path: Path) -> None:
    context = build_context(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), rest.make_handler(context))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        create = urllib.request.Request(
            f"{base}/v1/operations",
            data=json.dumps({"goal": "rest"}).encode("utf-8"),
            method="POST",
            headers={
                "Idempotency-Key": "rest-start",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(create) as response:
            operation = json.loads(response.read().decode("utf-8"))
        operation_id = operation["operation_id"]
        with urllib.request.urlopen(create) as response:
            retried_operation = json.loads(response.read().decode("utf-8"))
        assert retried_operation["operation_id"] == operation_id
        with urllib.request.urlopen(f"{base}/v1/operations/{operation_id}") as response:
            status = json.loads(response.read().decode("utf-8"))
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert response.headers["Cache-Control"] == "no-store"
        assert status["operation_id"] == operation_id
        message = urllib.request.Request(
            f"{base}/v1/operations/{operation_id}/messages",
            data=json.dumps({"text": "hello"}).encode("utf-8"),
            method="POST",
            headers={
                "Idempotency-Key": "rest-message",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(message) as response:
            posted = json.loads(response.read().decode("utf-8"))
        assert posted["accepted"] is True
        with urllib.request.urlopen(
            f"{base}/v1/operations/{operation_id}/events"
        ) as response:
            events = json.loads(response.read().decode("utf-8"))
        assert any(event["payload_kind"] == "rest.audit" for event in events)
        with urllib.request.urlopen(
            f"{base}/v1/operations/{operation_id}/live?after=1"
        ) as response:
            live = json.loads(response.read().decode("utf-8"))
        assert all(event["sequence"] > 1 for event in live)
        with urllib.request.urlopen(f"{base}/v1/agents") as response:
            agents = json.loads(response.read().decode("utf-8"))
        assert agents["agents"][0]["name"] == "fake-agent"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_verify_command_families_are_defined() -> None:
    assert commands_for("fast")[0] == ("uv", "run", "ruff", "check", ".")
    assert commands_for("full")[-1] == ("uv", "run", "pytest")


def test_rest_token_authentication(tmp_path: Path) -> None:
    context = build_context(tmp_path)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), rest.make_handler(context, token="secret")
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/v1/health"
        )
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("request without bearer token should fail")
        authed = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/v1/health",
            headers={"Authorization": "Bearer secret"},
        )
        with urllib.request.urlopen(authed) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["status"] == "ok"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_rest_scoped_token_authorization(tmp_path: Path) -> None:
    context = build_context(tmp_path)
    auth = rest.build_auth_config(read_token="reader", control_token="controller")
    server = ThreadingHTTPServer(("127.0.0.1", 0), rest.make_handler(context, auth))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        reader_get = urllib.request.Request(
            f"{base}/v1/fleet",
            headers={"Authorization": "Bearer reader"},
        )
        with urllib.request.urlopen(reader_get) as response:
            assert response.status == 200

        reader_post = urllib.request.Request(
            f"{base}/v1/operations",
            data=json.dumps({"goal": "blocked"}).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": "Bearer reader",
                "Idempotency-Key": "read-post",
                "Content-Type": "application/json",
            },
        )
        try:
            urllib.request.urlopen(reader_post)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 403
            assert payload["code"] == "forbidden"
        else:
            raise AssertionError("read token must not mutate")

        control_post = urllib.request.Request(
            f"{base}/v1/operations",
            data=json.dumps({"goal": "allowed"}).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": "Bearer controller",
                "Idempotency-Key": "control-post",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(control_post) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["accepted"] is True
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_rest_mutations_require_idempotency_key(tmp_path: Path) -> None:
    context = build_context(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), rest.make_handler(context))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/v1/operations",
            data=json.dumps({"goal": "rest"}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["code"] == "idempotency_key_required"
        else:
            raise AssertionError("missing idempotency key should fail")
    finally:
        server.shutdown()
        thread.join(timeout=5)
