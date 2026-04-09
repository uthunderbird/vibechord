from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from agent_operator.domain import BackgroundRunStatus, OperationStatus

DELETABLE_DATA_DIR_NAMES = (
    "runs",
    "events",
    "commands",
    "control_intents",
    "wakeups",
    "operation_events",
    "operation_checkpoints",
    "background",
    "project_memory",
    "policies",
    "acp",
    "claude",
    "monitor",
    "projects",
    "last",
)

PRESERVED_WORKSPACE_NAMES = (
    "operator-profile.yaml",
    "operator-profiles",
)

PRESERVED_DATA_DIR_NAMES = (
    "profiles",
    "uv-cache",
)

TERMINAL_OPERATION_STATUSES = {
    OperationStatus.COMPLETED.value,
    OperationStatus.FAILED.value,
    OperationStatus.CANCELLED.value,
}

LIVE_BACKGROUND_RUN_STATUSES = {
    BackgroundRunStatus.PENDING.value,
    BackgroundRunStatus.RUNNING.value,
}


@dataclass(frozen=True)
class ProjectClearResult:
    deleted: tuple[Path, ...]
    preserved: tuple[Path, ...]


def find_project_clear_blockers(data_dir: Path) -> list[str]:
    blockers: list[str] = []

    runs_dir = data_dir / "runs"
    if runs_dir.is_dir():
        for path in sorted(runs_dir.glob("*.operation.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            status = payload.get("status")
            operation_id = payload.get("operation_id")
            if isinstance(status, str) and status not in TERMINAL_OPERATION_STATUSES:
                label = (
                    operation_id
                    if isinstance(operation_id, str) and operation_id
                    else path.stem
                )
                blockers.append(label)

    background_runs_dir = data_dir / "background" / "runs"
    if background_runs_dir.is_dir():
        for path in sorted(background_runs_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            status = payload.get("status")
            if status not in LIVE_BACKGROUND_RUN_STATUSES:
                continue
            operation_id = payload.get("operation_id")
            run_id = payload.get("run_id")
            if isinstance(operation_id, str) and operation_id:
                if operation_id not in blockers:
                    blockers.append(operation_id)
                continue
            if isinstance(run_id, str) and run_id:
                blockers.append(f"background:{run_id}")

    return blockers


def clear_project_operator_state(*, workspace_root: Path, data_dir: Path) -> ProjectClearResult:
    blockers = find_project_clear_blockers(data_dir)
    if blockers:
        joined = ", ".join(blockers)
        raise RuntimeError(
            "Refusing to clear operator state while active or recoverable operations still exist: "
            f"{joined}"
        )

    deleted: list[Path] = []
    preserved: list[Path] = []

    for name in PRESERVED_WORKSPACE_NAMES:
        candidate = workspace_root / name
        if candidate.exists():
            preserved.append(candidate)

    for name in PRESERVED_DATA_DIR_NAMES:
        candidate = data_dir / name
        if candidate.exists():
            preserved.append(candidate)

    for name in DELETABLE_DATA_DIR_NAMES:
        candidate = data_dir / name
        if _delete_path(candidate):
            deleted.append(candidate)

    history_path = workspace_root / "operator-history.jsonl"
    if _delete_path(history_path):
        deleted.append(history_path)

    return ProjectClearResult(
        deleted=tuple(sorted(deleted)),
        preserved=tuple(sorted(preserved)),
    )


def _delete_path(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return False
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()
    return True
