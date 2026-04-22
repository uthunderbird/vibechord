"""AgentRunSupervisorV2 — asyncio-in-process background run management (ADR 0200).

Owns the task registry. All background agent runs are asyncio Tasks registered here.
Provides orphan detection support via get_all_tracked_session_ids() (ADR 0201).
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Coroutine
from typing import Any


class AgentRunSupervisorV2:
    """Centralized asyncio Task registry for background agent runs.

    One supervisor instance per operator process, shared across all operations.
    Thread-safety is a non-issue — single-threaded asyncio event loop.

    Task registry is keyed by (operation_id, session_id). The session_id set is
    retained after task completion to support orphan detection on restart (ADR 0201).
    """

    def __init__(self) -> None:
        # active tasks: run_id → Task
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        # (operation_id, session_id) → run_id; retained after completion
        self._session_to_run: dict[tuple[str, str], str] = {}
        # operation_id → set[session_id]; all ever-registered, retained post-completion
        self._tracked_session_ids: dict[str, set[str]] = defaultdict(set)
        self._draining: bool = False

    def spawn(
        self,
        coro: Coroutine[Any, Any, Any],
        *,
        operation_id: str,
        session_id: str,
        run_id: str | None = None,
    ) -> asyncio.Task[Any]:
        """Create and register a background asyncio Task.

        Args:
            coro: Coroutine to run as a background task.
            operation_id: Owning operation identifier.
            session_id: Session identifier for orphan detection.
            run_id: Optional stable run identifier; defaults to session_id.

        Returns:
            The created asyncio Task.

        Raises:
            RuntimeError: If the supervisor is draining and rejects new spawns.
        """
        if self._draining:
            raise RuntimeError(
                "AgentRunSupervisorV2 is draining — no new tasks will be spawned."
            )
        rid = run_id or session_id
        task = asyncio.create_task(coro)
        self._tasks[rid] = task
        self._session_to_run[(operation_id, session_id)] = rid
        self._tracked_session_ids[operation_id].add(session_id)

        def _on_done(t: asyncio.Task[Any]) -> None:
            self._tasks.pop(rid, None)

        task.add_done_callback(_on_done)
        return task

    def get_tasks_for_operation(self, operation_id: str) -> list[asyncio.Task[Any]]:
        """Return active (non-done) tasks registered for operation_id."""
        result = []
        for (oid, _sid), rid in self._session_to_run.items():
            if oid != operation_id:
                continue
            task = self._tasks.get(rid)
            if task is not None and not task.done():
                result.append(task)
        return result

    def get_active_tasks(self) -> list[asyncio.Task[Any]]:
        """Return all active (non-done) tasks across all operations."""
        return [t for t in self._tasks.values() if not t.done()]

    def get_all_tracked_session_ids(self, operation_id: str) -> set[str]:
        """Return all session IDs ever registered for operation_id.

        Includes completed and cancelled sessions — used by orphan detection (ADR 0201)
        to distinguish sessions that were never registered in this process lifetime.
        """
        return set(self._tracked_session_ids.get(operation_id, set()))

    def is_session_known(self, operation_id: str, session_id: str) -> bool:
        """Return True if session_id was ever spawned for operation_id in this process."""
        return session_id in self._tracked_session_ids.get(operation_id, set())

    def mark_draining(self) -> None:
        """Signal that no new tasks should be spawned (shutdown sequence step 2)."""
        self._draining = True

    def cancel_all(self) -> None:
        """Cancel all active tasks (shutdown sequence step 4).

        Called after drive loops have exited (asyncio.gather on _drive_tasks completed).
        Tasks handle CancelledError and post SessionCancelled wakeups, which are
        discarded since drive loops are already stopped.
        """
        for task in list(self._tasks.values()):
            if not task.done():
                task.cancel()
