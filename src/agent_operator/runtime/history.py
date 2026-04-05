from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from agent_operator.domain import OperationOutcome, OperationState, OperationStatus
from agent_operator.runtime.profiles import load_project_profile_from_path


class HistoryLedgerEntry(BaseModel):
    op_id: str
    goal: str
    profile: str | None = None
    started: datetime | None = None
    ended: datetime
    status: str
    stop_reason: str


class FileOperationHistoryLedger:
    """Committed append-only operation history ledger."""

    def __init__(self, path: Path) -> None:
        self._path = path

    async def append(self, state: OperationState, outcome: OperationOutcome) -> None:
        if not self._is_enabled(state):
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        entry = HistoryLedgerEntry(
            op_id=outcome.operation_id,
            goal=self._goal_summary(state),
            profile=self._profile_name(state),
            started=state.run_started_at,
            ended=datetime.now(UTC),
            status=outcome.status.value,
            stop_reason=self._stop_reason(state, outcome),
        )
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(entry.model_dump_json())
            handle.write("\n")

    def list_entries(self) -> list[HistoryLedgerEntry]:
        if not self._path.exists():
            return []
        entries: list[HistoryLedgerEntry] = []
        with self._path.open(encoding="utf-8") as handle:
            for line in handle:
                payload = line.strip()
                if not payload:
                    continue
                entries.append(HistoryLedgerEntry.model_validate_json(payload))
        return entries

    @property
    def path(self) -> Path:
        return self._path

    def _is_enabled(self, state: OperationState) -> bool:
        profile_path = state.goal.metadata.get("project_profile_path")
        if not isinstance(profile_path, str) or not profile_path.strip():
            return True
        candidate = Path(profile_path)
        if not candidate.exists():
            return True
        profile = load_project_profile_from_path(candidate)
        return profile.history_ledger

    def _goal_summary(self, state: OperationState) -> str:
        text = state.objective_state.objective.strip() or state.goal.objective_text.strip()
        if len(text) <= 200:
            return text
        return text[:197].rstrip() + "..."

    def _profile_name(self, state: OperationState) -> str | None:
        raw = state.goal.metadata.get("project_profile_name")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return None

    def _stop_reason(self, state: OperationState, outcome: OperationOutcome) -> str:
        if outcome.status is OperationStatus.CANCELLED:
            return "user_cancelled"
        summary = (outcome.summary or state.final_summary or "").strip()
        if outcome.status is OperationStatus.COMPLETED:
            return "explicit_success"
        if summary == "Maximum iterations reached.":
            return "iteration_limit_exhausted"
        if summary.startswith("Time limit of ") and summary.endswith(" seconds exceeded."):
            return "timeout_seconds"
        return outcome.status.value
