from __future__ import annotations

import asyncio
import json
import os
import shlex
from collections import deque
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from acp import connect_to_agent, spawn_stdio_transport, text_block
from acp.interfaces import (
    Agent,
    Client,
    PermissionOption,
    RequestPermissionResponse,
    ToolCallUpdate,
)

from agent_operator.acp.client import AcpProtocolError, JsonObject


class _SdkConnectionProtocol(Protocol):
    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: JsonObject | None = None,
        client_info: JsonObject | None = None,
        **kwargs: Any,
    ) -> Any: ...

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> Any: ...

    async def load_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> Any: ...

    async def list_sessions(
        self,
        cursor: str | None = None,
        cwd: str | None = None,
        **kwargs: Any,
    ) -> Any: ...

    async def set_session_mode(self, mode_id: str, session_id: str, **kwargs: Any) -> Any: ...

    async def set_session_model(self, model_id: str, session_id: str, **kwargs: Any) -> Any: ...

    async def set_config_option(
        self,
        config_id: str,
        session_id: str,
        value: str | bool,
        **kwargs: Any,
    ) -> Any: ...

    async def prompt(
        self,
        prompt: list[Any],
        session_id: str,
        message_id: str | None = None,
        **kwargs: Any,
    ) -> Any: ...

    async def fork_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> Any: ...

    async def resume_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> Any: ...

    async def close_session(self, session_id: str, **kwargs: Any) -> Any: ...

    async def authenticate(self, method_id: str, **kwargs: Any) -> Any: ...

    async def cancel(self, session_id: str, **kwargs: Any) -> None: ...

    async def close(self) -> None: ...


class _SdkTransportContext(
    AbstractAsyncContextManager[
        tuple[
            asyncio.StreamReader,
            asyncio.StreamWriter,
            asyncio.subprocess.Process,
        ]
    ]
):
    def __init__(
        self,
        command: str,
        *args: str,
        env: dict[str, str],
        cwd: Path,
        limit: int | None = None,
    ) -> None:
        self._manager = spawn_stdio_transport(command, *args, env=env, cwd=cwd, limit=limit)

    async def __aenter__(
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter, asyncio.subprocess.Process]:
        return await self._manager.__aenter__()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._manager.__aexit__(exc_type, exc, tb)


class _SdkBridgeClient(Client):
    def __init__(self, owner: AcpSdkConnection) -> None:
        self._owner = owner

    async def request_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: ToolCallUpdate,
        **kwargs: Any,
    ) -> RequestPermissionResponse:
        return await self._owner._request_permission(options, session_id, tool_call, kwargs or None)

    async def session_update(
        self,
        session_id: str,
        update: Any,
        **kwargs: Any,
    ) -> None:
        payload = {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": session_id,
                "update": update.model_dump(by_alias=True, exclude_none=True),
            },
        }
        self._owner._notifications.append(payload)
        await self._owner._append_log_event(
            "jsonrpc.stdout",
            {"line": json.dumps(payload, ensure_ascii=True)},
        )

    async def write_text_file(
        self,
        content: str,
        path: str,
        session_id: str,
        **kwargs: Any,
    ) -> None:
        raise AcpProtocolError("ACP SDK client write_text_file is not supported by operator.")

    async def read_text_file(
        self,
        path: str,
        session_id: str,
        limit: int | None = None,
        line: int | None = None,
        **kwargs: Any,
    ) -> Any:
        raise AcpProtocolError("ACP SDK client read_text_file is not supported by operator.")

    async def create_terminal(self, *args: Any, **kwargs: Any) -> Any:
        raise AcpProtocolError("ACP SDK client terminal operations are not supported by operator.")

    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs: Any) -> Any:
        raise AcpProtocolError("ACP SDK client terminal operations are not supported by operator.")

    async def release_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> None:
        raise AcpProtocolError("ACP SDK client terminal operations are not supported by operator.")

    async def wait_for_terminal_exit(self, session_id: str, terminal_id: str, **kwargs: Any) -> Any:
        raise AcpProtocolError("ACP SDK client terminal operations are not supported by operator.")

    async def kill_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> None:
        raise AcpProtocolError("ACP SDK client terminal operations are not supported by operator.")

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise AcpProtocolError(f"ACP SDK client ext_method is not supported: {method}")

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        raise AcpProtocolError(f"ACP SDK client ext_notification is not supported: {method}")

    def on_connect(self, conn: Agent) -> None:
        return None


class AcpSdkConnection:
    def __init__(
        self,
        command: str = "codex-acp",
        *,
        cwd: Path | None = None,
        log_path: Path | None = None,
        env_var_hint: str | None = None,
        env: dict[str, str] | None = None,
        stdio_limit_bytes: int | None = 1_048_576,
        transport_factory: Callable[
            [str, list[str], dict[str, str], Path, int | None],
            AbstractAsyncContextManager[
                tuple[asyncio.StreamReader, asyncio.StreamWriter, asyncio.subprocess.Process]
            ],
        ]
        | None = None,
        client_factory: Callable[
            [Client, asyncio.StreamWriter, asyncio.StreamReader],
            _SdkConnectionProtocol,
        ]
        | None = None,
    ) -> None:
        self._argv = shlex.split(command)
        if not self._argv:
            raise ValueError("ACP command must not be empty.")
        self._cwd = cwd or Path.cwd()
        self._command = command
        self._log_path = log_path
        self._env_var_hint = env_var_hint
        self._env = dict(env or {})
        self._stdio_limit_bytes = stdio_limit_bytes
        self._transport_factory = transport_factory or self._default_transport_factory
        self._client_factory = client_factory or self._default_client_factory
        self._transport_cm: AbstractAsyncContextManager[
            tuple[asyncio.StreamReader, asyncio.StreamWriter, asyncio.subprocess.Process]
        ] | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._connection: _SdkConnectionProtocol | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_chunks: deque[str] = deque(maxlen=200)
        self._notifications: deque[JsonObject] = deque()
        self._pending_permission_requests: dict[int, asyncio.Future[RequestPermissionResponse]] = {}
        self._next_request_id = 0
        self._log_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._connection is not None:
            return
        await self._append_log_event(
            "subprocess.start",
            {
                "command": self._command,
                "argv": self._argv,
                "cwd": str(self._cwd),
                "env_keys": sorted(self._env),
                "stdio_limit_bytes": self._stdio_limit_bytes,
                "substrate_backend": "sdk",
            },
        )
        try:
            transport_cm = self._transport_factory(
                self._argv[0],
                self._argv[1:],
                self._merged_env(),
                self._cwd,
                self._stdio_limit_bytes,
            )
            reader, writer, process = await transport_cm.__aenter__()
        except FileNotFoundError as exc:
            argv0 = self._argv[0]
            message = (
                f"ACP command {argv0!r} was not found. "
                f"Configured command: {self._command!r}."
            )
            if self._env_var_hint is not None:
                message += (
                    f" Check whether environment variable {self._env_var_hint} is unset "
                    "or points to a missing executable."
                )
            await self._append_log_event(
                "subprocess.error",
                {
                    "error": "file_not_found",
                    "command": self._command,
                    "argv": self._argv,
                    "cwd": str(self._cwd),
                    "env_var_hint": self._env_var_hint,
                    "message": message,
                },
            )
            raise AcpProtocolError(message) from exc
        except Exception as exc:
            await self._append_log_event(
                "subprocess.error",
                {
                    "error": "startup_failed",
                    "command": self._command,
                    "argv": self._argv,
                    "cwd": str(self._cwd),
                    "message": str(exc),
                },
            )
            raise
        self._transport_cm = transport_cm
        self._process = process
        self._connection = self._client_factory(_SdkBridgeClient(self), writer, reader)
        if process.stderr is not None:
            self._stderr_task = asyncio.create_task(self._read_stderr(process.stderr))
        await self._append_log_event(
            "subprocess.started",
            {
                "pid": process.pid,
                "command": self._command,
                "cwd": str(self._cwd),
                "stdio_limit_bytes": self._stdio_limit_bytes,
                "substrate_backend": "sdk",
            },
        )

    async def request(self, method: str, params: JsonObject | None = None) -> JsonObject:
        await self.start()
        payload = params or {}
        conn = self._require_connection()
        await self._append_log_event("jsonrpc.send", {"method": method, "params": payload})
        try:
            if method == "initialize":
                response = await conn.initialize(
                    protocol_version=int(payload.get("protocolVersion", 1)),
                    client_capabilities=payload.get("clientCapabilities"),
                    client_info=payload.get("clientInfo"),
                )
            elif method == "session/new":
                response = await conn.new_session(
                    cwd=str(payload["cwd"]),
                    mcp_servers=list(payload.get("mcpServers", [])),
                )
            elif method == "session/load":
                response = await conn.load_session(
                    cwd=str(payload["cwd"]),
                    session_id=str(payload["sessionId"]),
                    mcp_servers=list(payload.get("mcpServers", [])),
                )
            elif method == "session/list":
                response = await conn.list_sessions(
                    cursor=payload.get("cursor"),
                    cwd=str(payload["cwd"]) if payload.get("cwd") is not None else None,
                )
            elif method == "session/set_mode":
                response = await conn.set_session_mode(
                    mode_id=str(payload["modeId"]),
                    session_id=str(payload["sessionId"]),
                )
            elif method == "session/set_model":
                response = await conn.set_session_model(
                    model_id=str(payload["modelId"]),
                    session_id=str(payload["sessionId"]),
                )
            elif method == "session/set_config_option":
                response = await conn.set_config_option(
                    config_id=str(payload["configId"]),
                    session_id=str(payload["sessionId"]),
                    value=payload["value"],
                )
            elif method == "session/prompt":
                blocks = [
                    text_block(str(item.get("text", "")))
                    for item in payload.get("prompt", [])
                ]
                response = await conn.prompt(
                    prompt=blocks,
                    session_id=str(payload["sessionId"]),
                    message_id=payload.get("messageId"),
                )
            elif method == "session/fork":
                response = await conn.fork_session(
                    cwd=str(payload["cwd"]),
                    session_id=str(payload["sessionId"]),
                    mcp_servers=list(payload.get("mcpServers", [])),
                )
            elif method == "session/resume":
                response = await conn.resume_session(
                    cwd=str(payload["cwd"]),
                    session_id=str(payload["sessionId"]),
                    mcp_servers=list(payload.get("mcpServers", [])),
                )
            elif method == "session/close":
                response = await conn.close_session(
                    session_id=str(payload["sessionId"]),
                )
            elif method == "session/authenticate":
                response = await conn.authenticate(
                    method_id=str(payload["methodId"]),
                )
            else:
                raise AcpProtocolError(f"Unsupported ACP SDK request method: {method}")
        except Exception as exc:
            await self._append_log_event(
                "jsonrpc.error",
                {"method": method, "message": str(exc)},
            )
            raise
        result = (
            response.model_dump(by_alias=True, exclude_none=True)
            if response is not None
            else {}
        )
        await self._append_log_event("jsonrpc.result", {"method": method, "result": result})
        return result

    async def respond(
        self,
        request_id: int,
        *,
        result: JsonObject | None = None,
        error: JsonObject | None = None,
    ) -> None:
        future = self._pending_permission_requests.pop(request_id, None)
        if future is None:
            raise AcpProtocolError(f"Unknown ACP SDK request id: {request_id}")
        await self._append_log_event(
            "jsonrpc.respond",
            {"id": request_id, "result": result or {}, "error": error},
        )
        if error is not None:
            future.set_exception(AcpProtocolError(str(error)))
            return
        response = result or {"outcome": {"outcome": "cancelled"}}
        future.set_result(RequestPermissionResponse.model_validate(response))

    async def notify(self, method: str, params: JsonObject | None = None) -> None:
        await self.start()
        payload = params or {}
        await self._append_log_event("jsonrpc.notify", {"method": method, "params": payload})
        conn = self._require_connection()
        if method == "session/cancel":
            await conn.cancel(session_id=str(payload["sessionId"]))
            return
        raise AcpProtocolError(f"Unsupported ACP SDK notify method: {method}")

    def drain_notifications(self) -> list[JsonObject]:
        items = list(self._notifications)
        self._notifications.clear()
        return items

    def stderr_text(self, limit: int = 4000) -> str:
        text = "".join(self._stderr_chunks)
        return text[-limit:]

    async def close(self) -> None:
        if self._connection is None and self._transport_cm is None:
            return
        process = self._process
        await self._append_log_event(
            "subprocess.close",
            {
                "pid": process.pid if process is not None else None,
                "returncode": process.returncode if process is not None else None,
                "substrate_backend": "sdk",
            },
        )
        if self._connection is not None:
            with suppress(Exception):
                await self._connection.close()
        if self._transport_cm is not None:
            with suppress(Exception):
                await self._transport_cm.__aexit__(None, None, None)
        if self._stderr_task is not None:
            with suppress(Exception):
                await self._stderr_task
        error = AcpProtocolError("ACP subprocess closed before completing all pending requests.")
        for future in self._pending_permission_requests.values():
            if not future.done():
                future.set_exception(error)
        self._pending_permission_requests.clear()
        self._connection = None
        self._process = None
        self._transport_cm = None
        self._stderr_task = None

    async def _request_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: ToolCallUpdate,
        meta: JsonObject | None,
    ) -> RequestPermissionResponse:
        request_id = self._next_request_id
        self._next_request_id += 1
        future: asyncio.Future[RequestPermissionResponse] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending_permission_requests[request_id] = future
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "session/request_permission",
            "params": {
                "sessionId": session_id,
                "toolCall": tool_call.model_dump(by_alias=True, exclude_none=True),
                "options": [
                    option.model_dump(by_alias=True, exclude_none=True)
                    for option in options
                ],
            },
        }
        if meta:
            payload["params"]["_meta"] = meta
        self._notifications.append(payload)
        await self._append_log_event(
            "jsonrpc.stdout",
            {"line": json.dumps(payload, ensure_ascii=True)},
        )
        return await future

    async def _read_stderr(self, stderr: asyncio.StreamReader) -> None:
        async for raw_line in self._iter_lines(stderr):
            text = raw_line.decode("utf-8", errors="ignore")
            self._stderr_chunks.append(text)
            await self._append_log_event("subprocess.stderr", {"line": text.rstrip("\n")})

    async def _iter_lines(self, reader: asyncio.StreamReader) -> AsyncIterator[bytes]:
        buffer = bytearray()
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                if buffer:
                    yield bytes(buffer)
                break
            buffer.extend(chunk)
            while True:
                newline_index = buffer.find(b"\n")
                if newline_index == -1:
                    break
                line = bytes(buffer[: newline_index + 1])
                del buffer[: newline_index + 1]
                yield line

    async def _append_log_event(self, event: str, payload: JsonObject) -> None:
        if self._log_path is None:
            return
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            **payload,
        }
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        async with self._log_lock:
            with self._log_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.write("\n")

    def _default_transport_factory(
        self,
        command: str,
        args: list[str],
        env: dict[str, str],
        cwd: Path,
        limit: int | None,
    ) -> AbstractAsyncContextManager[
        tuple[asyncio.StreamReader, asyncio.StreamWriter, asyncio.subprocess.Process]
    ]:
        return _SdkTransportContext(command, *args, env=env, cwd=cwd, limit=limit)

    def _default_client_factory(
        self,
        client: Client,
        writer: asyncio.StreamWriter,
        reader: asyncio.StreamReader,
    ) -> _SdkConnectionProtocol:
        return connect_to_agent(client, writer, reader)

    def _merged_env(self) -> dict[str, str]:
        return {**os.environ, **self._env}

    def _require_connection(self) -> _SdkConnectionProtocol:
        if self._connection is None:
            raise AcpProtocolError("ACP SDK client is not running.")
        return self._connection
