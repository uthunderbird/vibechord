from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from agent_operator.domain import RunEvent
from agent_operator.runtime.files import atomic_write_text, model_validate_json_file_with_retry

logger = logging.getLogger(__name__)


class _WakeupEnvelope(BaseModel):
    event: RunEvent
    status: str = "pending"
    claimed_at: datetime | None = None
    acked_at: datetime | None = None


class FileWakeupInbox:
    def __init__(self, root: Path, *, stale_after_seconds: int = 300) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._stale_after = timedelta(seconds=stale_after_seconds)

    async def enqueue(self, event: RunEvent) -> None:
        existing = self._find_by_dedupe(event.operation_id, event.dedupe_key)
        if existing is not None:
            return
        path = self._path(event.event_id)
        envelope = _WakeupEnvelope(event=event)
        path.write_text(envelope.model_dump_json(indent=2), encoding="utf-8")

    async def claim(self, operation_id: str, limit: int = 100) -> list[RunEvent]:
        claimed: list[RunEvent] = []
        now = datetime.now(UTC)
        for path in sorted(self._root.glob("*.json")):
            envelope = self._load(path)
            if envelope.event.operation_id != operation_id or envelope.status != "pending":
                continue
            if envelope.event.not_before is not None and envelope.event.not_before > now:
                continue
            envelope.status = "claimed"
            envelope.claimed_at = now
            self._save(path, envelope)
            claimed.append(envelope.event)
            if len(claimed) >= limit:
                break
        return claimed

    async def ack(self, event_ids: list[str]) -> None:
        now = datetime.now(UTC)
        for event_id in event_ids:
            path = self._path(event_id)
            if not path.exists():
                continue
            envelope = self._load(path)
            envelope.status = "acked"
            envelope.acked_at = now
            self._save(path, envelope)

    async def release(self, event_ids: list[str]) -> None:
        for event_id in event_ids:
            path = self._path(event_id)
            if not path.exists():
                continue
            envelope = self._load(path)
            if envelope.status != "claimed":
                continue
            envelope.status = "pending"
            envelope.claimed_at = None
            self._save(path, envelope)

    async def requeue_stale_claims(self) -> int:
        now = datetime.now(UTC)
        count = 0
        for path in sorted(self._root.glob("*.json")):
            envelope = self._load(path)
            if envelope.status != "claimed" or envelope.claimed_at is None:
                continue
            if now - envelope.claimed_at <= self._stale_after:
                continue
            envelope.status = "pending"
            envelope.claimed_at = None
            self._save(path, envelope)
            count += 1
        return count

    async def list_pending(self, operation_id: str) -> list[RunEvent]:
        events: list[RunEvent] = []
        for path in sorted(self._root.glob("*.json")):
            envelope = self._load(path)
            if envelope.event.operation_id != operation_id or envelope.status != "pending":
                continue
            events.append(envelope.event)
        return events

    def ready_operation_ids(self) -> list[str]:
        now = datetime.now(UTC)
        operation_ids: set[str] = set()
        for path in sorted(self._root.glob("*.json")):
            envelope = self._load(path)
            if envelope.status != "pending":
                continue
            if envelope.event.not_before is not None and envelope.event.not_before > now:
                continue
            operation_ids.add(envelope.event.operation_id)
        return sorted(operation_ids)

    def read_all(self, operation_id: str | None = None) -> list[dict[str, object]]:
        payloads: list[dict[str, object]] = []
        for path in sorted(self._root.glob("*.json")):
            envelope = self._load(path)
            if operation_id is not None and envelope.event.operation_id != operation_id:
                continue
            payloads.append(envelope.model_dump(mode="json"))
        return payloads

    def _find_by_dedupe(self, operation_id: str, dedupe_key: str | None) -> Path | None:
        if not dedupe_key:
            return None
        for path in self._root.glob("*.json"):
            envelope = self._load(path)
            if (
                envelope.event.operation_id == operation_id
                and envelope.event.dedupe_key == dedupe_key
                and envelope.status != "acked"
            ):
                return path
        return None

    def _path(self, event_id: str) -> Path:
        return self._root / f"{event_id}.json"

    def _load(self, path: Path) -> _WakeupEnvelope:
        return model_validate_json_file_with_retry(_WakeupEnvelope, path, encoding="utf-8")

    def _save(self, path: Path, envelope: _WakeupEnvelope) -> None:
        atomic_write_text(path, envelope.model_dump_json(indent=2), encoding="utf-8")

    def has_pending(self, operation_id: str) -> bool:
        """Return True if there is at least one pending wakeup for this operation."""
        now = datetime.now(UTC)
        for path in self._root.glob("*.json"):
            try:
                envelope = self._load(path)
            except Exception:
                continue
            if envelope.event.operation_id != operation_id or envelope.status != "pending":
                continue
            if envelope.event.not_before is not None and envelope.event.not_before > now:
                continue
            return True
        return False


class WakeupWatcher:
    """Background task that watches for wakeup files and signals an asyncio.Event.

    One instance is allocated per active operation. It polls the wakeup directory at
    ``poll_interval`` seconds (default 0.5) and sets ``wakeup_event`` when a pending
    wakeup file is found for the operation.

    Usage::

        wakeup_event = asyncio.Event()
        watcher = WakeupWatcher(inbox, operation_id, wakeup_event)
        task = asyncio.create_task(watcher.run())
        try:
            # await wakeup_event.wait() or asyncio.wait_for(wakeup_event.wait(), timeout=...)
            ...
        finally:
            task.cancel()
            await asyncio.shield(asyncio.gather(task, return_exceptions=True))
    """

    def __init__(
        self,
        inbox: FileWakeupInbox,
        operation_id: str,
        wakeup_event: asyncio.Event,
        *,
        poll_interval: float = 0.5,
    ) -> None:
        self._inbox = inbox
        self._operation_id = operation_id
        self._wakeup_event = wakeup_event
        self._poll_interval = poll_interval

    async def run(self) -> None:
        """Watch loop. Runs until cancelled."""
        try:
            # Startup scan — close TOCTOU window between event allocation and watcher start.
            await self._scan()
            while True:
                await asyncio.sleep(self._poll_interval)
                await self._scan()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error(
                "WakeupWatcher for operation %r exiting due to unhandled error",
                self._operation_id,
                exc_info=True,
            )

    async def _scan(self) -> None:
        try:
            found = await asyncio.get_event_loop().run_in_executor(
                None, self._inbox.has_pending, self._operation_id
            )
        except Exception:
            logger.warning(
                "WakeupWatcher: transient error scanning wakeup directory for operation %r",
                self._operation_id,
                exc_info=True,
            )
            return
        if found:
            self._wakeup_event.set()
