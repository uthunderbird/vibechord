"""Direct Codex execution adapter."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import threading
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from vibechord.domain import AgentResult

_DISABLED_FEATURES = (
    "apps",
    "goals",
    "memories",
    "personality",
    "plugin_sharing",
    "plugins",
    "remote_plugin",
)


@dataclass(frozen=True)
class CodexExecConfig:
    """Immutable direct-Codex execution settings.

    Example:
        >>> config = CodexExecConfig(
        ...     executable=Path("/opt/codex"),
        ...     working_directory=Path("/work"),
        ...     codex_home=Path("/state/codex"),
        ...     model="gpt-5.6-sol",
        ...     network_access=False,
        ...     environment={"PATH": "/usr/bin"},
        ...     raw_stream_path=Path("/state/run.jsonl"),
        ...     final_message_path=Path("/state/final.txt"),
        ... )
        >>> config.model
        'gpt-5.6-sol'
    """

    executable: Path
    working_directory: Path
    codex_home: Path
    model: str
    network_access: bool
    environment: Mapping[str, str]
    raw_stream_path: Path
    final_message_path: Path
    stream_limit_bytes: int = 8 * 1024 * 1024
    stderr_tail_bytes: int = 64 * 1024
    final_message_limit_bytes: int = 1024 * 1024

    def __post_init__(self) -> None:
        """Reject incomplete or unsafe execution settings."""

        if not self.model.strip():
            raise ValueError("model must not be empty")
        object.__setattr__(
            self,
            "environment",
            MappingProxyType(dict(self.environment)),
        )
        for value, label in (
            (self.stream_limit_bytes, "stream_limit_bytes"),
            (self.stderr_tail_bytes, "stderr_tail_bytes"),
            (self.final_message_limit_bytes, "final_message_limit_bytes"),
        ):
            if value < 1:
                raise ValueError(f"{label} must be positive")


@dataclass(frozen=True)
class CodexExecReceipt:
    """Terminal execution facts for one direct Codex invocation."""

    status: str
    returncode: int | None
    error: str
    stderr_tail: str
    stream_sha256: str | None
    stream_bytes: int
    final_message_sha256: str | None
    final_message_bytes: int


class CodexExecAdapter:
    """Run one ephemeral Codex execution and normalize its terminal result."""

    def __init__(self, config: CodexExecConfig) -> None:
        """Create an adapter from launcher-validated settings."""

        self.config = config
        self.receipt: CodexExecReceipt | None = None

    def invoke(self, agent_name: str, agent_input: str) -> AgentResult:
        """Run Codex once using stdin, JSONL output, and a final-message file."""

        del agent_name
        self.receipt = None
        error = self._validate_paths()
        if error is not None:
            return self._failure("configuration_error", None, error, "")

        config = self.config
        environment = dict(config.environment)
        environment["CODEX_HOME"] = str(config.codex_home)
        stderr_tail: deque[bytes] = deque()
        stderr_size = 0
        stream_size = 0
        stream_events = 0
        stream_error: str | None = None

        try:
            process = subprocess.Popen(
                self._command(),
                cwd=config.working_directory,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            return self._failure("spawn_error", None, str(exc), "")

        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        process_stdin = process.stdin
        process_stdout = process.stdout
        process_stderr = process.stderr

        def drain_stdout() -> None:
            nonlocal stream_error, stream_events, stream_size
            try:
                with config.raw_stream_path.open("xb") as stream:
                    for line in iter(process_stdout.readline, b""):
                        stream_size += len(line)
                        if stream_size > config.stream_limit_bytes:
                            stream_error = (
                                "Codex JSONL exceeded the configured byte limit"
                            )
                            continue
                        stream.write(line)
                        if not line.strip():
                            continue
                        try:
                            payload = json.loads(line)
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            stream_error = "Codex emitted malformed JSONL"
                            continue
                        if not isinstance(payload, dict):
                            stream_error = "Codex JSONL events must be objects"
                            continue
                        stream_events += 1
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError as exc:
                stream_error = f"Codex JSONL artifact failed: {exc}"

        def drain_stderr() -> None:
            nonlocal stderr_size
            for chunk in iter(lambda: process_stderr.read(8192), b""):
                stderr_tail.append(chunk)
                stderr_size += len(chunk)
                while stderr_tail and stderr_size > config.stderr_tail_bytes:
                    stderr_size -= len(stderr_tail.popleft())

        stdout_thread = threading.Thread(target=drain_stdout, daemon=True)
        stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        try:
            process_stdin.write(agent_input.encode("utf-8"))
            process_stdin.close()
        except OSError:
            pass
        returncode = process.wait()
        stdout_thread.join()
        stderr_thread.join()

        stderr_text = b"".join(stderr_tail).decode("utf-8", errors="replace").strip()
        if returncode != 0:
            detail = stderr_text or f"Codex exited {returncode}"
            return self._failure("process_error", returncode, detail, stderr_text)
        if stream_error is not None:
            return self._failure(
                "protocol_error", returncode, stream_error, stderr_text
            )
        if stream_events == 0:
            return self._failure(
                "protocol_error",
                returncode,
                "Codex emitted no JSONL events",
                stderr_text,
            )
        try:
            metadata = config.final_message_path.lstat()
            final_message = config.final_message_path.read_bytes()
        except OSError as exc:
            return self._failure(
                "protocol_error",
                returncode,
                f"Codex final message is unavailable: {exc}",
                stderr_text,
            )
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            return self._failure(
                "protocol_error",
                returncode,
                "Codex final message is not a regular file",
                stderr_text,
            )
        if len(final_message) > config.final_message_limit_bytes:
            return self._failure(
                "protocol_error",
                returncode,
                "Codex final message exceeded the byte limit",
                stderr_text,
            )
        try:
            output = final_message.decode("utf-8").strip()
        except UnicodeDecodeError:
            return self._failure(
                "protocol_error",
                returncode,
                "Codex final message is not UTF-8",
                stderr_text,
            )
        if not output:
            return self._failure(
                "protocol_error",
                returncode,
                "Codex final message is empty",
                stderr_text,
            )
        stream_sha256, actual_stream_bytes = _file_evidence(config.raw_stream_path)
        final_sha256 = hashlib.sha256(final_message).hexdigest()
        self.receipt = CodexExecReceipt(
            status="completed",
            returncode=returncode,
            error="",
            stderr_tail=stderr_text,
            stream_sha256=stream_sha256,
            stream_bytes=actual_stream_bytes,
            final_message_sha256=final_sha256,
            final_message_bytes=len(final_message),
        )
        return AgentResult(output=output, success=True)

    def _failure(
        self,
        status: str,
        returncode: int | None,
        error: str,
        stderr_tail: str,
    ) -> AgentResult:
        stream_sha256, stream_bytes = _file_evidence(self.config.raw_stream_path)
        final_sha256, final_bytes = _file_evidence(self.config.final_message_path)
        self.receipt = CodexExecReceipt(
            status=status,
            returncode=returncode,
            error=error,
            stderr_tail=stderr_tail,
            stream_sha256=stream_sha256,
            stream_bytes=stream_bytes,
            final_message_sha256=final_sha256,
            final_message_bytes=final_bytes,
        )
        return AgentResult(output="", success=False, error=error)

    def _validate_paths(self) -> str | None:
        config = self.config
        try:
            executable = config.executable.lstat()
            working_directory = config.working_directory.lstat()
            codex_home = config.codex_home.lstat()
        except OSError as exc:
            return f"Codex execution path is unavailable: {exc}"
        if (
            not stat.S_ISREG(executable.st_mode)
            or executable.st_nlink != 1
            or not os.access(config.executable, os.X_OK)
        ):
            return "Codex executable is not one executable regular file"
        if not stat.S_ISDIR(working_directory.st_mode):
            return "Codex working directory is invalid"
        if not stat.S_ISDIR(codex_home.st_mode):
            return "Codex home is invalid"
        for artifact in (config.raw_stream_path, config.final_message_path):
            if artifact.exists() or artifact.is_symlink():
                return f"Codex artifact path already exists: {artifact}"
            try:
                parent = artifact.parent.lstat()
            except OSError as exc:
                return f"Codex artifact parent is unavailable: {exc}"
            if not stat.S_ISDIR(parent.st_mode):
                return f"Codex artifact parent is invalid: {artifact.parent}"
        return None

    def _command(self) -> tuple[str, ...]:
        config = self.config
        command = [
            str(config.executable),
            "exec",
            "--json",
            "--output-last-message",
            str(config.final_message_path),
            "--strict-config",
            "--ignore-user-config",
            "--ephemeral",
            "--color",
            "never",
            "-C",
            str(config.working_directory),
            "-m",
            config.model,
            "-s",
            "workspace-write",
            "-c",
            'approval_policy="never"',
            "-c",
            "sandbox_workspace_write.network_access="
            + ("true" if config.network_access else "false"),
        ]
        for feature in _DISABLED_FEATURES:
            command.extend(("-c", f"features.{feature}=false"))
        command.append("-")
        return tuple(command)


def _file_evidence(path: Path) -> tuple[str | None, int]:
    try:
        metadata = path.lstat()
        data = path.read_bytes()
    except OSError:
        return None, 0
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        return None, 0
    return hashlib.sha256(data).hexdigest(), len(data)
