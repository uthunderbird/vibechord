from __future__ import annotations

import builtins
from datetime import datetime
from typing import Protocol

from agent_operator.domain import (
    AgentResult,
    AgentSessionHandle,
    AgentTurnBrief,
    BackgroundRunStatus,
    CommandBrief,
    CommandStatus,
    DecisionMemo,
    EvaluationBrief,
    ExecutionState,
    IterationBrief,
    MemoryEntry,
    OperationBrief,
    OperationCommand,
    OperationOutcome,
    OperationState,
    OperationSummary,
    PolicyEntry,
    PolicyStatus,
    RunEvent,
    TraceBriefBundle,
    TraceRecord,
)
from agent_operator.dtos.requests import AgentRunRequest


class OperationStore(Protocol):
    async def save_operation(self, state: OperationState) -> None: ...

    async def save_outcome(self, outcome: OperationOutcome) -> None: ...

    async def load_operation(self, operation_id: str) -> OperationState | None: ...

    async def load_outcome(self, operation_id: str) -> OperationOutcome | None: ...

    async def list_operation_ids(self) -> list[str]: ...

    async def list_operations(self) -> list[OperationSummary]: ...


class EventSink(Protocol):
    async def emit(self, event: RunEvent) -> None: ...


class WakeupInbox(Protocol):
    async def enqueue(self, event: RunEvent) -> None: ...

    async def claim(self, operation_id: str, limit: int = 100) -> list[RunEvent]: ...

    async def ack(self, event_ids: list[str]) -> None: ...

    async def release(self, event_ids: list[str]) -> None: ...

    async def requeue_stale_claims(self) -> int: ...

    async def list_pending(self, operation_id: str) -> list[RunEvent]: ...


class OperationCommandInbox(Protocol):
    async def enqueue(self, command: OperationCommand) -> None: ...

    async def list(self, operation_id: str) -> builtins.list[OperationCommand]: ...

    async def list_pending(self, operation_id: str) -> builtins.list[OperationCommand]: ...

    async def update_status(
        self,
        command_id: str,
        status: CommandStatus,
        *,
        rejection_reason: str | None = None,
        applied_at: datetime | None = None,
    ) -> OperationCommand | None: ...


class PolicyStore(Protocol):
    async def save(self, entry: PolicyEntry) -> None: ...

    async def load(self, policy_id: str) -> PolicyEntry | None: ...

    async def list(
        self,
        *,
        project_scope: str | None = None,
        status: PolicyStatus | None = None,
    ) -> list[PolicyEntry]: ...


class AgentRunSupervisor(Protocol):
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
    ) -> ExecutionState: ...

    async def poll_background_turn(self, run_id: str) -> ExecutionState | None: ...

    async def collect_background_turn(self, run_id: str) -> AgentResult | None: ...

    async def cancel_background_turn(self, run_id: str) -> None: ...

    async def finalize_background_turn(
        self,
        run_id: str,
        status: BackgroundRunStatus,
        *,
        error: str | None = None,
    ) -> None: ...

    async def list_runs(self, operation_id: str) -> list[ExecutionState]: ...


class TraceStore(Protocol):
    async def save_operation_brief(self, brief: OperationBrief) -> None: ...

    async def append_iteration_brief(self, operation_id: str, brief: IterationBrief) -> None: ...

    async def append_agent_turn_brief(self, operation_id: str, brief: AgentTurnBrief) -> None: ...

    async def append_command_brief(self, operation_id: str, brief: CommandBrief) -> None: ...

    async def append_evaluation_brief(self, operation_id: str, brief: EvaluationBrief) -> None: ...

    async def save_decision_memo(self, operation_id: str, memo: DecisionMemo) -> None: ...

    async def append_trace_record(self, operation_id: str, record: TraceRecord) -> None: ...

    async def write_report(self, operation_id: str, report: str) -> None: ...

    async def load_brief_bundle(self, operation_id: str) -> TraceBriefBundle | None: ...

    async def load_trace_records(self, operation_id: str) -> list[TraceRecord]: ...

    async def load_decision_memos(self, operation_id: str) -> list[DecisionMemo]: ...

    async def load_report(self, operation_id: str) -> str | None: ...


class ProjectMemoryStore(Protocol):
    async def save(self, entry: MemoryEntry) -> None: ...

    async def load(self, memory_id: str) -> MemoryEntry | None: ...

    async def list_active(self, *, project_scope: str) -> list[MemoryEntry]: ...

    async def expire(self, memory_id: str) -> None: ...


class Clock(Protocol):
    def now_iso(self) -> str: ...


class Console(Protocol):
    def print(self, message: str) -> None: ...
