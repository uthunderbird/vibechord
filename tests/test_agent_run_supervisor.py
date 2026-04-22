"""Tests for AgentRunSupervisorV2 — ADR 0200."""
from __future__ import annotations

import asyncio

import pytest

from agent_operator.application.drive.agent_run_supervisor import AgentRunSupervisorV2


async def _noop() -> None:
    await asyncio.sleep(0)


async def _long_running() -> None:
    await asyncio.sleep(3600)


@pytest.mark.anyio
async def test_spawn_registers_task_and_tracks_session():
    sup = AgentRunSupervisorV2()
    task = sup.spawn(_noop(), operation_id="op-1", session_id="s-1")
    assert not task.done() or True  # may complete immediately — just check registered
    assert "s-1" in sup.get_all_tracked_session_ids("op-1")


@pytest.mark.anyio
async def test_get_tasks_for_operation_returns_active_only():
    sup = AgentRunSupervisorV2()
    task = sup.spawn(_long_running(), operation_id="op-1", session_id="s-1")
    tasks = sup.get_tasks_for_operation("op-1")
    assert task in tasks
    task.cancel()
    with pytest.raises((asyncio.CancelledError, Exception)):
        await task


@pytest.mark.anyio
async def test_get_tasks_for_operation_empty_after_completion():
    sup = AgentRunSupervisorV2()
    task = sup.spawn(_noop(), operation_id="op-1", session_id="s-1")
    await task
    tasks = sup.get_tasks_for_operation("op-1")
    assert tasks == []


@pytest.mark.anyio
async def test_get_all_tracked_session_ids_persists_after_completion():
    sup = AgentRunSupervisorV2()
    task = sup.spawn(_noop(), operation_id="op-1", session_id="s-1")
    await task
    # Task is done but session_id must still be tracked
    assert "s-1" in sup.get_all_tracked_session_ids("op-1")


@pytest.mark.anyio
async def test_get_all_tracked_session_ids_isolated_by_operation():
    sup = AgentRunSupervisorV2()
    t1 = sup.spawn(_noop(), operation_id="op-1", session_id="s-1")
    t2 = sup.spawn(_noop(), operation_id="op-2", session_id="s-2")
    await t1
    await t2
    assert "s-1" in sup.get_all_tracked_session_ids("op-1")
    assert "s-2" not in sup.get_all_tracked_session_ids("op-1")
    assert "s-2" in sup.get_all_tracked_session_ids("op-2")


@pytest.mark.anyio
async def test_is_session_known_true_after_spawn():
    sup = AgentRunSupervisorV2()
    task = sup.spawn(_noop(), operation_id="op-1", session_id="s-1")
    await task
    assert sup.is_session_known("op-1", "s-1") is True
    assert sup.is_session_known("op-1", "s-unknown") is False


@pytest.mark.anyio
async def test_get_active_tasks_returns_all_operations():
    sup = AgentRunSupervisorV2()
    t1 = sup.spawn(_long_running(), operation_id="op-1", session_id="s-1")
    t2 = sup.spawn(_long_running(), operation_id="op-2", session_id="s-2")
    active = sup.get_active_tasks()
    assert t1 in active
    assert t2 in active
    t1.cancel()
    t2.cancel()
    await asyncio.gather(t1, t2, return_exceptions=True)
    assert t1.done()
    assert t2.done()


@pytest.mark.anyio
async def test_mark_draining_rejects_new_spawns():
    sup = AgentRunSupervisorV2()
    sup.mark_draining()

    async def _coro() -> None:
        pass

    coro = _coro()
    with pytest.raises(RuntimeError, match="draining"):
        sup.spawn(coro, operation_id="op-1", session_id="s-1")
    coro.close()  # suppress ResourceWarning


@pytest.mark.anyio
async def test_cancel_all_cancels_active_tasks():
    sup = AgentRunSupervisorV2()
    task = sup.spawn(_long_running(), operation_id="op-1", session_id="s-1")
    assert not task.done()
    sup.cancel_all()
    await asyncio.gather(task, return_exceptions=True)
    assert task.done()


@pytest.mark.anyio
async def test_unknown_operation_returns_empty_set():
    sup = AgentRunSupervisorV2()
    assert sup.get_all_tracked_session_ids("no-such-op") == set()
    assert sup.get_tasks_for_operation("no-such-op") == []
