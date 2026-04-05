from __future__ import annotations

import asyncio
import json
import os
import shlex
from collections import deque
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

JsonObject = dict[str, Any]


class AcpProtocolError(RuntimeError):
    pass


class AcpJsonRpcError(AcpProtocolError):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data


class AcpConnection(Protocol):
    async def start(self) -> None: ...

    async def request(self, method: str, params: JsonObject | None = None) -> JsonObject: ...

    async def respond(
        self,
        request_id: int,
        *,
        result: JsonObject | None = None,
        error: JsonObject | None = None,
    ) -> None: ...

    async def notify(self, method: str, params: JsonObject | None = None) -> None: ...

    def drain_notifications(self) -> list[JsonObject]: ...

    def stderr_text(self, limit: int = 4000) -> str: ...

    async def close(self) -> None: ...


class AcpSubprocessConnection:
    # AI_TODO: make it context manager
    def __init__(
        self,
        command: str = "codex-acp",
        *,
        cwd: Path | None = None,
        log_path: Path | None = None,
        env_var_hint: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self._argv = shlex.split(command)
        if not self._argv:
            raise ValueError("ACP command must not be empty.")
        self._cwd = cwd or Path.cwd()
        self._command = command
        self._log_path = log_path
        self._env_var_hint = env_var_hint
        self._env = dict(env or {})
        self._process: asyncio.subprocess.Process | None = None
        # AI_TODO: investigate if it could benefit from group it into TaskGroup
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[JsonObject]] = {}
        self._notifications: deque[JsonObject] = deque()
        self._stderr_chunks: deque[str] = deque(maxlen=200)
        self._next_id = 0
        self._write_lock = asyncio.Lock()
        self._log_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._process is not None:
            return
        await self._append_log_event(
            "subprocess.start",
            {
                "command": self._command,
                "argv": self._argv,
                "cwd": str(self._cwd),
                "env_keys": sorted(self._env),
            },
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *self._argv,
                cwd=str(self._cwd),
                env={**os.environ, **self._env},
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
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
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise AcpProtocolError("ACP subprocess did not expose stdio streams.")
        self._process = process
        await self._append_log_event(
            "subprocess.started",
            {
                "pid": process.pid,
                "command": self._command,
                "cwd": str(self._cwd),
            },
        )
        self._reader_task = asyncio.create_task(self._read_stdout(process.stdout))
        self._stderr_task = asyncio.create_task(self._read_stderr(process.stderr))

    async def request(self, method: str, params: JsonObject | None = None) -> JsonObject:
        await self.start()
        request_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_running_loop()
        future: asyncio.Future[JsonObject] = loop.create_future()
        self._pending[request_id] = future
        await self._send_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or {},
            }
        )
        return await future

    async def notify(self, method: str, params: JsonObject | None = None) -> None:
        await self.start()
        await self._send_message(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {},
            }
        )

    async def respond(
        self,
        request_id: int,
        *,
        result: JsonObject | None = None,
        error: JsonObject | None = None,
    ) -> None:
        await self.start()
        payload: JsonObject = {
            "jsonrpc": "2.0",
            "id": request_id,
        }
        if error is not None:
            payload["error"] = error
        else:
            payload["result"] = result or {}
        await self._send_message(payload)

    def drain_notifications(self) -> list[JsonObject]:
        items = list(self._notifications)
        self._notifications.clear()
        return items

    def stderr_text(self, limit: int = 4000) -> str:
        text = "".join(self._stderr_chunks)
        return text[-limit:]

    async def close(self) -> None:
        process = self._process
        if process is None:
            return
        await self._append_log_event(
            "subprocess.close",
            {
                "pid": process.pid,
                "returncode": process.returncode,
            },
        )
        if process.stdin is not None and not process.stdin.is_closing():
            process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except TimeoutError:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except TimeoutError:
                process.kill()
                await process.wait()
        for task in (self._reader_task, self._stderr_task):
            if task is not None:
                await asyncio.gather(task, return_exceptions=True)
        self._process = None

    async def _send_message(self, payload: JsonObject) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise AcpProtocolError("ACP subprocess is not running.")
        await self._append_log_event("jsonrpc.send", payload)
        data = (json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
        async with self._write_lock:
            process.stdin.write(data)
            await process.stdin.drain()

    async def _read_stdout(self, stdout: asyncio.StreamReader) -> None:
        try:
            async for raw_line in self._iter_lines(stdout):
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                await self._append_log_event("jsonrpc.stdout", {"line": line})
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                if "id" in payload and ("result" in payload or "error" in payload):
                    request_id = payload.get("id")
                    if not isinstance(request_id, int):
                        continue
                    future = self._pending.pop(request_id, None)
                    if future is None or future.done():
                        continue
                    if "error" in payload:
                        error = payload["error"]
                        if isinstance(error, dict):
                            future.set_exception(
                                AcpJsonRpcError(
                                    code=int(error.get("code", -32000)),
                                    message=str(error.get("message", "ACP request failed.")),
                                    data=error.get("data"),
                                )
                            )
                        else:
                            future.set_exception(AcpProtocolError("ACP request failed."))
                    else:
                        result = payload.get("result")
                        if isinstance(result, dict):
                            future.set_result(result)
                        elif result is None:
                            future.set_result({})
                        else:
                            future.set_result({"value": result})
                    continue
                if "method" in payload:
                    self._notifications.append(payload)
        finally:
            error = AcpProtocolError(
                "ACP subprocess closed before completing all pending requests."
            )
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(error)
            self._pending.clear()

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
