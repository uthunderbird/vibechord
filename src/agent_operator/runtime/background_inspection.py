from __future__ import annotations

from pathlib import Path

from agent_operator.domain import AgentResult, ExecutionState
from agent_operator.runtime.files import model_validate_json_file_with_retry
from agent_operator.runtime.supervisor import _BackgroundResultFile, _BackgroundRunFile


class BackgroundRunInspectionStore:
    """Read-only access to persisted background run artifacts.

    This surface exists for CLI inspection and reporting only. It must not be used as a
    background execution host.

    Args:
        root: Background artifact root.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    async def poll_background_turn(self, run_id: str) -> ExecutionState | None:
        """Load the latest persisted execution state for one run."""
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
        """Load the persisted terminal result if it exists."""
        path = self._result_path(run_id)
        if not path.exists():
            return None
        record = model_validate_json_file_with_retry(_BackgroundResultFile, path)
        return AgentResult.model_validate(record.result)

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

    @property
    def _runs_dir(self) -> Path:
        return self._root / "runs"

    @property
    def _results_dir(self) -> Path:
        return self._root / "results"

    def _run_path(self, run_id: str) -> Path:
        return self._runs_dir / f"{run_id}.json"

    def _result_path(self, run_id: str) -> Path:
        return self._results_dir / f"{run_id}.json"
