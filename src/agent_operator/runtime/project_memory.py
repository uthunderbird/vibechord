from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from agent_operator.domain import MemoryEntry, MemoryFreshness, MemoryScope


class FileProjectMemoryStore:
    """Persistent store for project-scope MemoryEntry objects.

    Entries are stored as JSON files under <root>/<project_scope>/<memory_id>.json.
    Only entries with scope=PROJECT and freshness=CURRENT are returned by list_active().
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    async def save(self, entry: MemoryEntry) -> None:
        path = self._entry_path(entry.scope_id, entry.memory_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry.model_dump_json(indent=2), encoding="utf-8")

    async def load(self, memory_id: str) -> MemoryEntry | None:
        for path in self._root.rglob(f"{memory_id}.json"):
            if path.is_file():
                return MemoryEntry.model_validate_json(path.read_text(encoding="utf-8"))
        return None

    async def list_active(self, *, project_scope: str) -> list[MemoryEntry]:
        scope_dir = self._scope_dir(project_scope)
        if not scope_dir.is_dir():
            return []
        entries = [
            MemoryEntry.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted(scope_dir.glob("*.json"))
            if p.is_file()
        ]
        return [
            e for e in entries
            if e.scope is MemoryScope.PROJECT and e.freshness is MemoryFreshness.CURRENT
        ]

    async def expire(self, memory_id: str) -> None:
        entry = await self.load(memory_id)
        if entry is None:
            return
        entry.freshness = MemoryFreshness.SUPERSEDED
        entry.updated_at = datetime.now(UTC)
        await self.save(entry)

    def _scope_dir(self, project_scope: str) -> Path:
        # Sanitise scope string to a safe directory name
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in project_scope)
        return self._root / safe

    def _entry_path(self, scope_id: str, memory_id: str) -> Path:
        return self._scope_dir(scope_id) / f"{memory_id}.json"
