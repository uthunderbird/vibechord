"""Minimal REST delivery surface built on stdlib http.server."""

from __future__ import annotations

import hmac
import json
import socket
import ssl
from dataclasses import dataclass
from hashlib import sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from vibechord.domain import CommandName, OperationCommand
from vibechord.jsonutil import to_jsonable
from vibechord.projection import ProjectionError
from vibechord.workspace import AppContext, build_context


class RestConfigError(ValueError):
    """Raised when REST exposure config is unsafe."""


READ_SCOPE = "read"
WRITE_SCOPE = "write"
ADMIN_SCOPE = "admin"


@dataclass(frozen=True)
class TokenGrant:
    """Hashed bearer token and its granted scopes."""

    token_hash: str
    scopes: frozenset[str]


@dataclass(frozen=True)
class RestAuthConfig:
    """Bearer-token authorization configuration."""

    grants: tuple[TokenGrant, ...]

    @property
    def enabled(self) -> bool:
        """Return whether REST requests require authorization."""

        return bool(self.grants)


@dataclass(frozen=True)
class AuthDecision:
    """Result of REST authorization."""

    allowed: bool
    status: HTTPStatus
    code: str
    message: str


def serve(
    root: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    unsafe: bool = False,
    token: str | None = None,
    read_token: str | None = None,
    control_token: str | None = None,
    production: bool = False,
    tls_cert: Path | None = None,
    tls_key: Path | None = None,
) -> None:
    """Serve the REST API."""

    auth = build_auth_config(token, read_token, control_token)
    validate_binding(host, unsafe, auth, production, tls_cert)
    context = build_context(root)
    handler = make_handler(context, auth)
    server = ThreadingHTTPServer((host, port), handler)
    if tls_cert is not None:
        server.socket = _wrap_tls(server.socket, tls_cert, tls_key)
    server.serve_forever()


def validate_binding(
    host: str,
    unsafe: bool = False,
    token: str | RestAuthConfig | None = None,
    production: bool = False,
    tls_cert: Path | None = None,
) -> None:
    """Reject non-loopback REST exposure unless explicitly marked unsafe."""

    auth = token if isinstance(token, RestAuthConfig) else build_auth_config(token)
    non_loopback = host not in {"127.0.0.1", "localhost", "::1"}
    if production and unsafe:
        raise RestConfigError("production REST cannot use unsafe exposure")
    if production and non_loopback and not auth.enabled:
        raise RestConfigError("production non-loopback REST requires auth")
    if production and non_loopback and tls_cert is None:
        raise RestConfigError("production non-loopback REST requires TLS cert")
    if non_loopback and not unsafe and not auth.enabled:
        raise RestConfigError(
            "REST binds to loopback by default; configure auth or use unsafe for dev"
        )


def build_auth_config(
    token: str | None = None,
    read_token: str | None = None,
    control_token: str | None = None,
) -> RestAuthConfig:
    """Build scoped bearer-token authorization config."""

    grants: list[TokenGrant] = []
    if token:
        grants.append(TokenGrant(_hash_token(token), frozenset({ADMIN_SCOPE})))
    if read_token:
        grants.append(TokenGrant(_hash_token(read_token), frozenset({READ_SCOPE})))
    if control_token:
        grants.append(
            TokenGrant(_hash_token(control_token), frozenset({READ_SCOPE, WRITE_SCOPE}))
        )
    return RestAuthConfig(tuple(grants))


def make_handler(
    context: AppContext, token: str | RestAuthConfig | None = None
) -> type[BaseHTTPRequestHandler]:
    """Create a request handler bound to an application context."""

    auth = token if isinstance(token, RestAuthConfig) else build_auth_config(token)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            decision = _authorize(self, auth, READ_SCOPE)
            if not decision.allowed:
                _send_error(self, decision.status, decision.code, decision.message)
                return
            _handle_get(self, context)

        def do_POST(self) -> None:  # noqa: N802
            decision = _authorize(self, auth, WRITE_SCOPE)
            if not decision.allowed:
                _send_error(self, decision.status, decision.code, decision.message)
                return
            _handle_post(self, context)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def _authorize(
    handler: BaseHTTPRequestHandler, auth: RestAuthConfig, required_scope: str
) -> AuthDecision:
    if not auth.enabled:
        return AuthDecision(True, HTTPStatus.OK, "", "")
    header = handler.headers.get("Authorization", "")
    prefix = "Bearer "
    if not header.startswith(prefix):
        return AuthDecision(
            False, HTTPStatus.UNAUTHORIZED, "unauthorized", "missing bearer token"
        )
    token = header.removeprefix(prefix)
    scopes = _scopes_for_token(auth, token)
    if scopes is None:
        return AuthDecision(False, HTTPStatus.UNAUTHORIZED, "unauthorized", "bad token")
    if ADMIN_SCOPE in scopes or required_scope in scopes:
        return AuthDecision(True, HTTPStatus.OK, "", "")
    return AuthDecision(
        False,
        HTTPStatus.FORBIDDEN,
        "forbidden",
        f"token lacks {required_scope} scope",
    )


def _scopes_for_token(auth: RestAuthConfig, token: str) -> frozenset[str] | None:
    token_hash = _hash_token(token)
    for grant in auth.grants:
        if hmac.compare_digest(grant.token_hash, token_hash):
            return grant.scopes
    return None


def _hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _handle_get(handler: BaseHTTPRequestHandler, context: AppContext) -> None:
    parsed = urlparse(handler.path)
    path = parsed.path
    query = parse_qs(parsed.query)
    try:
        if path == "/v1/health":
            _send(handler, HTTPStatus.OK, {"status": "ok"})
            return
        if path == "/v1/agents":
            _send(
                handler,
                HTTPStatus.OK,
                {"agents": [{"name": "fake-agent", "kind": "fake"}]},
            )
            return
        if path == "/v1/fleet":
            _send(handler, HTTPStatus.OK, context.projection_service.fleet())
            return
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[:2] == ["v1", "operations"]:
            _send(handler, HTTPStatus.OK, context.projection_service.status(parts[2]))
            return
        if (
            len(parts) == 4
            and parts[:2] == ["v1", "operations"]
            and parts[3] in {"events", "live"}
        ):
            after = _sequence_cursor(query.get("after", ["0"])[0])
            envelopes = tuple(
                envelope
                for envelope in context.projection_service.live_feed(parts[2])
                if envelope.sequence > after
            )
            _send(handler, HTTPStatus.OK, envelopes)
            return
        _send_error(handler, HTTPStatus.NOT_FOUND, "not_found", "endpoint not found")
    except ProjectionError as exc:
        _send_error(handler, HTTPStatus.NOT_FOUND, "operation_not_found", str(exc))


def _handle_post(handler: BaseHTTPRequestHandler, context: AppContext) -> None:
    path = urlparse(handler.path).path
    command_id = handler.headers.get("Idempotency-Key")
    if command_id is None or command_id.strip() == "":
        _send_error(
            handler, HTTPStatus.BAD_REQUEST, "idempotency_key_required", "missing key"
        )
        return
    body = _read_body(handler)
    if path == "/v1/operations":
        goal = str(body.get("goal", ""))
        result = context.command_application.apply(
            OperationCommand(
                name=CommandName.START,
                command_id=command_id,
                payload={"goal": goal},
            )
        )
        _send(
            handler,
            HTTPStatus.ACCEPTED if result.accepted else HTTPStatus.BAD_REQUEST,
            result,
        )
        return
    parts = path.strip("/").split("/")
    if len(parts) >= 4 and parts[:2] == ["v1", "operations"]:
        operation_id = parts[2]
        action = parts[3]
        command = _command_from_rest(action, operation_id, command_id, body)
        if command is None:
            _send_error(
                handler, HTTPStatus.NOT_FOUND, "not_found", "endpoint not found"
            )
            return
        result = context.command_application.apply(command)
        context.command_application.record_audit(operation_id, command_id, action)
        _send(
            handler,
            HTTPStatus.ACCEPTED if result.accepted else HTTPStatus.BAD_REQUEST,
            result,
        )
        return
    _send_error(handler, HTTPStatus.NOT_FOUND, "not_found", "endpoint not found")


def _command_from_rest(
    action: str, operation_id: str, command_id: str, body: dict[str, object]
) -> OperationCommand | None:
    if action == "messages":
        return OperationCommand(
            name=CommandName.POST_MESSAGE,
            command_id=command_id,
            operation_id=operation_id,
            payload={"text": str(body.get("text", ""))},
        )
    if action == "attention":
        return OperationCommand(
            name=CommandName.ANSWER_ATTENTION,
            command_id=command_id,
            operation_id=operation_id,
            payload={
                "attention_id": str(body.get("attention_id", "")),
                "text": str(body.get("text", "")),
            },
        )
    if action == "commands":
        command_name = str(body.get("command", ""))
        mapping = {
            "cancel": CommandName.CANCEL,
            "pause": CommandName.PAUSE,
            "resume": CommandName.RESUME,
            "interrupt": CommandName.INTERRUPT,
        }
        name = mapping.get(command_name)
        if name is None:
            return None
        return OperationCommand(
            name=name, command_id=command_id, operation_id=operation_id
        )
    return None


def _read_body(handler: BaseHTTPRequestHandler) -> dict[str, object]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    data = handler.rfile.read(length)
    loaded = json.loads(data.decode("utf-8"))
    if not isinstance(loaded, dict):
        return {}
    return loaded


def _send(handler: BaseHTTPRequestHandler, status: HTTPStatus, payload: object) -> None:
    data = json.dumps(to_jsonable(payload), sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _send_error(
    handler: BaseHTTPRequestHandler, status: HTTPStatus, code: str, message: str
) -> None:
    _send(
        handler,
        status,
        {
            "code": code,
            "message": message,
            "details": {},
            "operation_id": None,
            "retryable": False,
            "correlation_id": None,
        },
    )


def _sequence_cursor(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def _wrap_tls(
    raw_socket: socket.socket, tls_cert: Path, tls_key: Path | None
) -> ssl.SSLSocket:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(tls_cert), None if tls_key is None else str(tls_key))
    return context.wrap_socket(raw_socket, server_side=True)
