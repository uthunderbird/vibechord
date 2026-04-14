from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from agent_operator.domain import (
    AgentError,
    AgentProgress,
    AgentProgressState,
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    BackgroundProgressSnapshot,
    BackgroundRunStatus,
    ExecutionState,
    RunEvent,
    RunEventKind,
    SessionStatus,
)
from agent_operator.dtos.requests import AgentRunRequest
from agent_operator.protocols import AgentSessionManager, WakeupInbox
from agent_operator.runtime.files import atomic_write_text, model_validate_json_file_with_retry


class _BackgroundJobSpec(BaseModel):
    run_id: str
    operation_id: str
    iteration: int
    adapter_key: str
    task_id: str | None = None
    request: dict[str, Any]
    existing_session: dict[str, Any] | None = None
    wakeup_delivery: str = "enqueue"
    data_dir: str


class _BackgroundRunFile(BaseModel):
    run_id: str
    operation_id: str
    adapter_key: str
    iteration: int
    task_id: str | None = None
    session_handle: dict[str, Any] | None = None
    status: BackgroundRunStatus = BackgroundRunStatus.PENDING
    pid: int | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_heartbeat_at: datetime | None = None
    completed_at: datetime | None = None
    raw_ref: str | None = None
    progress: BackgroundProgressSnapshot | None = None
    error: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_shape(cls, data: Any) -> Any:
        if isinstance(data, dict) and "run_id" not in data and "execution_id" in data:
            upgraded = dict(data)
            upgraded["run_id"] = upgraded["execution_id"]
            return upgraded
        return data


class _BackgroundResultFile(BaseModel):
    run_id: str
    operation_id: str
    adapter_key: str
    iteration: int
    task_id: str | None = None
    session_handle: dict[str, Any] | None = None
    status: str
    result: dict[str, Any]

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_shape(cls, data: Any) -> Any:
        if (
            isinstance(data, dict)
            and "result" not in data
            and "session_id" in data
            and "status" in data
        ):
            return {
                "run_id": data.get("run_id") or data.get("execution_id") or "",
                "operation_id": data.get("operation_id") or "",
                "adapter_key": data.get("adapter_key") or "",
                "iteration": data.get("iteration") or 0,
                "task_id": data.get("task_id"),
                "session_handle": None,
                "status": data["status"],
                "result": data,
            }
        return data


def _progress_snapshot(progress: AgentProgress) -> BackgroundProgressSnapshot:
    """Translate adapter progress into persisted background progress.

    Args:
        progress: Latest adapter progress snapshot.

    Returns:
        Persistable background progress view used by runtime state inspection.
    """

    raw_last_event_at = None
    if isinstance(progress.raw, dict):
        candidate = progress.raw.get("last_event_at")
        if isinstance(candidate, str):
            with suppress(ValueError):
                raw_last_event_at = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    state = {
        AgentProgressState.PENDING: SessionStatus.RUNNING,
        AgentProgressState.RUNNING: SessionStatus.RUNNING,
        AgentProgressState.WAITING_INPUT: SessionStatus.WAITING,
        AgentProgressState.COMPLETED: SessionStatus.COMPLETED,
        AgentProgressState.FAILED: SessionStatus.FAILED,
        AgentProgressState.CANCELLED: SessionStatus.CANCELLED,
        AgentProgressState.UNKNOWN: SessionStatus.RUNNING,
    }[progress.state]
    return BackgroundProgressSnapshot(
        state=state,
        message=progress.message,
        updated_at=progress.updated_at,
        partial_output=progress.partial_output,
        last_event_at=raw_last_event_at,
    )


def _heartbeat_from_progress(progress: AgentProgress, *, now: datetime) -> datetime:
    """Use real session activity when the adapter exposes it, else fall back to poll time."""

    snapshot = _progress_snapshot(progress)
    if isinstance(progress.raw, dict) and "last_event_at" in progress.raw:
        return snapshot.last_event_at or snapshot.updated_at
    return now


class InProcessAgentRunSupervisor:
    """Run background turns as asyncio tasks inside the current process.

    This supervisor keeps the same persisted `runs/` and `results/` artifacts used by
    CLI inspection, but it stops using a forked worker process as the canonical host.

    Args:
        root: Background artifact root.
        data_dir: Operator data directory used for log references.
        session_manager: Live agent-session manager used by in-process hosting.
        wakeup_inbox: Optional durable wakeup inbox for terminal completion delivery.

    Examples:
        >>> supervisor = InProcessAgentRunSupervisor(Path("/tmp/background"), Path("/tmp"))
        >>> supervisor._runs_dir.name
        'runs'
    """

    def __init__(
        self,
        root: Path,
        data_dir: Path,
        *,
        session_manager: AgentSessionManager,
        wakeup_inbox: WakeupInbox | None = None,
    ) -> None:
        self._root = root
        self._data_dir = data_dir
        self._session_registry = session_manager
        self._wakeup_inbox = wakeup_inbox
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._results_dir.mkdir(parents=True, exist_ok=True)
        self._logs_dir.mkdir(parents=True, exist_ok=True)

    async def start_background_turn(
        self,
        operation_id: str,
        iteration: int,
        adapter_key: str,
        request: AgentRunRequest,
        *,
        existing_session: AgentSessionHandle | None = None,
        task_id: str | None = None,
        wakeup_delivery: str = "enqueue",
    ) -> ExecutionState:
        """Start one in-process background turn."""

        run_id = str(uuid4())
        spec = _BackgroundJobSpec(
            run_id=run_id,
            operation_id=operation_id,
            iteration=iteration,
            adapter_key=adapter_key,
            task_id=task_id,
            request=request.model_dump(mode="json"),
            existing_session=existing_session.model_dump(mode="json")
            if existing_session is not None
            else None,
            wakeup_delivery=wakeup_delivery,
            data_dir=str(self._data_dir),
        )
        atomic_write_text(self._job_path(run_id), spec.model_dump_json(indent=2))
        run_file = _BackgroundRunFile(
            run_id=run_id,
            operation_id=operation_id,
            adapter_key=adapter_key,
            iteration=iteration,
            task_id=task_id,
            raw_ref=str(self._log_path(run_id)),
        )
        self._save_run_file(run_file)
        handshake = asyncio.Event()
        task = asyncio.create_task(self._run_turn(spec, handshake))
        self._tasks[run_id] = task
        await self._wait_for_handshake(run_id, handshake=handshake)
        return await self.poll_background_turn(run_id) or ExecutionState(
            run_id=run_id,
            operation_id=operation_id,
            adapter_key=adapter_key,
            task_id=task_id,
            iteration=iteration,
            status=BackgroundRunStatus.RUNNING,
            raw_ref=str(self._log_path(run_id)),
        )

    async def poll_background_turn(self, run_id: str) -> ExecutionState | None:
        """Load the latest persisted execution state for one background run."""

        path = self._run_path(run_id)
        if not path.exists():
            return None
        record = model_validate_json_file_with_retry(_BackgroundRunFile, path)
        session_id = None
        if record.session_handle is not None:
            session_id = record.session_handle.get("session_id")
        return ExecutionState(
            run_id=record.run_id,
            operation_id=record.operation_id,
            adapter_key=record.adapter_key,
            session_id=session_id if isinstance(session_id, str) else None,
            task_id=record.task_id,
            iteration=record.iteration,
            status=record.status,
            pid=record.pid,
            started_at=record.started_at,
            last_heartbeat_at=record.last_heartbeat_at,
            completed_at=record.completed_at,
            raw_ref=record.raw_ref,
            progress=record.progress,
        )

    async def collect_background_turn(self, run_id: str) -> AgentResult | None:
        """Load the terminal result if the run already finished."""

        path = self._result_path(run_id)
        if not path.exists():
            return None
        record = model_validate_json_file_with_retry(_BackgroundResultFile, path)
        return AgentResult.model_validate(record.result)

    async def cancel_background_turn(self, run_id: str) -> None:
        """Cancel an in-flight background run."""

        path = self._run_path(run_id)
        if not path.exists():
            return
        record = model_validate_json_file_with_retry(_BackgroundRunFile, path)
        task = self._tasks.get(run_id)
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        record.status = BackgroundRunStatus.CANCELLED
        record.completed_at = datetime.now(UTC)
        record.last_heartbeat_at = record.completed_at
        self._save_run_file(record)

    async def finalize_background_turn(
        self,
        run_id: str,
        status: BackgroundRunStatus,
        *,
        error: str | None = None,
    ) -> None:
        """Persist a terminal supervisor-side status override."""

        path = self._run_path(run_id)
        if not path.exists():
            return
        record = model_validate_json_file_with_retry(_BackgroundRunFile, path)
        if record.status in {
            BackgroundRunStatus.COMPLETED,
            BackgroundRunStatus.FAILED,
            BackgroundRunStatus.CANCELLED,
        }:
            return
        record.status = status
        record.error = error
        record.completed_at = datetime.now(UTC)
        record.last_heartbeat_at = record.completed_at
        self._save_run_file(record)

    async def list_runs(self, operation_id: str) -> list[ExecutionState]:
        """List persisted background runs for one operation."""

        runs: list[ExecutionState] = []
        for path in sorted(self._runs_dir.glob("*.json")):
            record = model_validate_json_file_with_retry(_BackgroundRunFile, path)
            if record.operation_id != operation_id:
                continue
            handle = await self.poll_background_turn(record.run_id)
            if handle is not None:
                runs.append(handle)
        return runs

    async def _run_turn(self, spec: _BackgroundJobSpec, handshake: asyncio.Event) -> None:
        """Execute one background turn as an asyncio task."""

        record = model_validate_json_file_with_retry(
            _BackgroundRunFile,
            self._run_path(spec.run_id),
        )
        request = AgentRunRequest.model_validate(spec.request)
        session_handle: AgentSessionHandle | None = None
        try:
            if spec.existing_session is not None:
                session_handle = AgentSessionHandle.model_validate(spec.existing_session)
                await self._session_registry.send(session_handle, request.instruction)
            else:
                session_handle = await self._session_registry.start(spec.adapter_key, request)
            session_handle.metadata = dict(session_handle.metadata or {})
            session_handle.metadata["background_run_id"] = spec.run_id
            session_handle.metadata["background_log_path"] = str(self._log_path(spec.run_id))
            record.session_handle = session_handle.model_dump(mode="json")
            record.status = BackgroundRunStatus.RUNNING
            record.last_heartbeat_at = datetime.now(UTC)
            self._save_run_file(record)
            handshake.set()
            result = await self._wait_for_terminal_result(session_handle, record)
            await self._persist_result(spec, record, result, session_handle)
        except asyncio.CancelledError:
            if session_handle is not None:
                with suppress(Exception):
                    await self._session_registry.cancel(session_handle)
            await self._persist_cancelled_result(spec, record, session_handle)
            handshake.set()
            raise
        except Exception as exc:
            await self._persist_failure_result(spec, record, session_handle, exc)
            handshake.set()
        finally:
            self._tasks.pop(spec.run_id, None)

    async def _wait_for_terminal_result(
        self,
        session_handle: AgentSessionHandle,
        record: _BackgroundRunFile,
    ) -> AgentResult:
        """Poll the adapter until a terminal result is available."""

        while True:
            progress = await self._session_registry.poll(session_handle)
            now = datetime.now(UTC)
            record.progress = _progress_snapshot(progress)
            record.last_heartbeat_at = _heartbeat_from_progress(progress, now=now)
            self._save_run_file(record)
            if progress.state in {AgentProgressState.PENDING, AgentProgressState.RUNNING}:
                await asyncio.sleep(1.0)
                continue
            if progress.state is AgentProgressState.WAITING_INPUT:
                return AgentResult(
                    session_id=session_handle.session_id,
                    status=AgentResultStatus.INCOMPLETE,
                    output_text=progress.partial_output or "",
                    error=AgentError(
                        code="agent_waiting_input",
                        message=progress.message,
                        retryable=False,
                        raw=progress.raw,
                    ),
                    completed_at=progress.updated_at,
                    raw={"progress": progress.model_dump(mode="json")},
                )
            return await self._session_registry.collect(session_handle)

    async def _persist_result(
        self,
        spec: _BackgroundJobSpec,
        record: _BackgroundRunFile,
        result: AgentResult,
        session_handle: AgentSessionHandle | None,
    ) -> None:
        """Persist a terminal result and optional wakeup."""

        result_record = _BackgroundResultFile(
            run_id=spec.run_id,
            operation_id=spec.operation_id,
            adapter_key=spec.adapter_key,
            iteration=spec.iteration,
            task_id=spec.task_id,
            session_handle=(
                session_handle.model_dump(mode="json")
                if session_handle is not None
                else None
            ),
            status=result.status.value,
            result=result.model_dump(mode="json"),
        )
        atomic_write_text(self._result_path(spec.run_id), result_record.model_dump_json(indent=2))
        record.status = {
            AgentResultStatus.SUCCESS: BackgroundRunStatus.COMPLETED,
            AgentResultStatus.INCOMPLETE: BackgroundRunStatus.COMPLETED,
            AgentResultStatus.FAILED: BackgroundRunStatus.FAILED,
            AgentResultStatus.CANCELLED: BackgroundRunStatus.CANCELLED,
            AgentResultStatus.DISCONNECTED: BackgroundRunStatus.DISCONNECTED,
        }[result.status]
        record.completed_at = datetime.now(UTC)
        record.last_heartbeat_at = record.completed_at
        if record.progress is None and result.output_text:
            record.progress = BackgroundProgressSnapshot(
                state=SessionStatus.COMPLETED,
                message="Completed.",
                updated_at=record.completed_at,
                partial_output=result.output_text[-2000:],
                last_event_at=None,
            )
        self._save_run_file(record)
        if self._wakeup_inbox is not None and spec.wakeup_delivery == "enqueue":
            await self._wakeup_inbox.enqueue(
                RunEvent(
                    event_type=f"background_run.{record.status.value}",
                    kind=RunEventKind.WAKEUP,
                    operation_id=spec.operation_id,
                    iteration=spec.iteration,
                    task_id=spec.task_id,
                    session_id=session_handle.session_id if session_handle is not None else None,
                    dedupe_key=f"{spec.run_id}:{record.status.value}",
                    payload={
                        "run_id": spec.run_id,
                        "adapter_key": spec.adapter_key,
                        "status": record.status.value,
                    },
                )
            )

    async def _persist_cancelled_result(
        self,
        spec: _BackgroundJobSpec,
        record: _BackgroundRunFile,
        session_handle: AgentSessionHandle | None,
    ) -> None:
        """Persist the terminal state for an explicitly cancelled run."""

        result = AgentResult(
            session_id=session_handle.session_id if session_handle is not None else spec.run_id,
            status=AgentResultStatus.CANCELLED,
            completed_at=datetime.now(UTC),
            error=AgentError(
                code="background_run_cancelled",
                message="Background run cancelled.",
                retryable=False,
            ),
        )
        await self._persist_result(spec, record, result, session_handle)

    async def _persist_failure_result(
        self,
        spec: _BackgroundJobSpec,
        record: _BackgroundRunFile,
        session_handle: AgentSessionHandle | None,
        exc: Exception,
    ) -> None:
        """Persist an unexpected supervisor failure as a terminal result."""

        result = AgentResult(
            session_id=session_handle.session_id if session_handle is not None else spec.run_id,
            status=AgentResultStatus.FAILED,
            completed_at=datetime.now(UTC),
            error=AgentError(
                code="background_supervisor_failed",
                message=str(exc),
                retryable=False,
            ),
        )
        record.error = "background_supervisor_failed"
        await self._persist_result(spec, record, result, session_handle)

    async def _wait_for_handshake(
        self,
        run_id: str,
        *,
        handshake: asyncio.Event,
        timeout_seconds: float = 10.0,
    ) -> None:
        """Wait until the run exposes a session handle or reaches a terminal state."""

        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            if handshake.is_set():
                return
            path = self._run_path(run_id)
            if path.exists():
                record = model_validate_json_file_with_retry(_BackgroundRunFile, path)
                if record.session_handle is not None or record.status in {
                    BackgroundRunStatus.FAILED,
                    BackgroundRunStatus.CANCELLED,
                }:
                    return
            await asyncio.sleep(0.05)

    def _save_run_file(self, record: _BackgroundRunFile) -> None:
        """Persist one run-state snapshot."""

        atomic_write_text(self._run_path(record.run_id), record.model_dump_json(indent=2))

    @property
    def _jobs_dir(self) -> Path:
        return self._root / "jobs"

    @property
    def _runs_dir(self) -> Path:
        return self._root / "runs"

    @property
    def _results_dir(self) -> Path:
        return self._root / "results"

    @property
    def _logs_dir(self) -> Path:
        return self._root / "logs"

    def _job_path(self, run_id: str) -> Path:
        return self._jobs_dir / f"{run_id}.json"

    def _run_path(self, run_id: str) -> Path:
        return self._runs_dir / f"{run_id}.json"

    def _result_path(self, run_id: str) -> Path:
        return self._results_dir / f"{run_id}.json"

    def _log_path(self, run_id: str) -> Path:
        return self._logs_dir / f"{run_id}.log"
