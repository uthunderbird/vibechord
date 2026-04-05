from __future__ import annotations

import json
import time
from pathlib import Path

from agent_operator.domain import (
    OperationOutcome,
    OperationState,
    OperationSummary,
    SessionStatus,
    TaskStatus,
)
from agent_operator.runtime.files import atomic_write_text


class FileOperationStore:
    """Minimal JSON-backed store for operation state and outcomes."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    async def save_operation(self, state: OperationState) -> None:
        path = self._root / f"{state.operation_id}.operation.json"
        atomic_write_text(path, state.model_dump_json(indent=2))

    async def save_outcome(self, outcome: OperationOutcome) -> None:
        path = self._root / f"{outcome.operation_id}.outcome.json"
        atomic_write_text(path, outcome.model_dump_json(indent=2))

    async def load_operation(self, operation_id: str) -> OperationState | None:
        path = self._root / f"{operation_id}.operation.json"
        if not path.exists():
            return None
        payload = self._read_text_with_retry(path)
        raw = json.loads(payload)
        if raw.get("schema_version") != 2:
            raise ValueError(
                "Unsupported operation state schema. This operator only supports schema_version=2."
            )
        return OperationState.model_validate(raw)

    async def load_outcome(self, operation_id: str) -> OperationOutcome | None:
        path = self._root / f"{operation_id}.outcome.json"
        if not path.exists():
            return None
        return OperationOutcome.model_validate_json(self._read_text_with_retry(path))

    async def list_operation_ids(self) -> list[str]:
        operation_ids: list[str] = []
        for path in sorted(self._root.glob("*.operation.json")):
            with path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            operation_id = payload.get("operation_id")
            if isinstance(operation_id, str):
                operation_ids.append(operation_id)
        return operation_ids

    async def list_operations(self) -> list[OperationSummary]:
        summaries: list[OperationSummary] = []
        for path in sorted(self._root.glob("*.operation.json")):
            state = OperationState.model_validate_json(self._read_text_with_retry(path))
            runnable_task_count = sum(
                1 for task in state.tasks if task.status in {TaskStatus.READY, TaskStatus.RUNNING}
            )
            reusable_session_count = sum(
                1
                for session in state.sessions
                if not session.handle.one_shot
                and session.status
                in {
                    SessionStatus.IDLE,
                    SessionStatus.RUNNING,
                    SessionStatus.WAITING,
                }
            )
            focus = None
            if state.current_focus is not None:
                focus = f"{state.current_focus.kind.value}:{state.current_focus.target_id}"
            summaries.append(
                OperationSummary(
                    operation_id=state.operation_id,
                    status=state.status,
                    objective_prompt=state.objective_state.objective,
                    final_summary=state.final_summary,
                    focus=focus,
                    runnable_task_count=runnable_task_count,
                    reusable_session_count=reusable_session_count,
                    updated_at=state.updated_at,
                )
            )
        return summaries

    def _read_text_with_retry(
        self,
        path: Path,
        *,
        attempts: int = 3,
        delay_seconds: float = 0.02,
    ) -> str:
        last_payload = ""
        for index in range(attempts):
            payload = path.read_text(encoding="utf-8")
            if payload.strip():
                return payload
            last_payload = payload
            if index < attempts - 1:
                time.sleep(delay_seconds)
        return last_payload
