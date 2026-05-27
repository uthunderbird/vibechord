"""Central operation loop."""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass

from vibechord.adapters import AdapterGateway
from vibechord.domain import (
    AgentRequest,
    AgentResult,
    BrainAction,
    BrainDecision,
    ExecutionBudget,
    OperationStatus,
)
from vibechord.projection import ProjectionService
from vibechord.protocols import EventStore


@dataclass(frozen=True)
class DriverResult:
    """Result of running an operation driver."""

    operation_id: str
    status: str
    iterations: int
    stop_reason: str | None


class OperationDriver:
    """Run operation iterations under deterministic guardrails."""

    def __init__(
        self,
        event_store: EventStore,
        projection_service: ProjectionService,
        adapter_gateway: AdapterGateway,
    ) -> None:
        """Create an operation driver."""

        self.event_store = event_store
        self.projection_service = projection_service
        self.adapter_gateway = adapter_gateway

    def run_until_blocked_or_terminal(
        self, operation_id: str, budget: ExecutionBudget | None = None
    ) -> DriverResult:
        """Run an operation until terminal, blocked, paused, or guardrail stop."""

        effective_budget = budget or ExecutionBudget()
        while True:
            snapshot = self.projection_service.snapshot(operation_id)
            if snapshot.status in {
                OperationStatus.BLOCKED,
                OperationStatus.PAUSED,
                OperationStatus.COMPLETED,
                OperationStatus.FAILED,
                OperationStatus.CANCELLED,
                OperationStatus.INTERRUPTED,
            }:
                return DriverResult(
                    operation_id=operation_id,
                    status=snapshot.status.value,
                    iterations=snapshot.iterations,
                    stop_reason=snapshot.stop_reason,
                )
            if snapshot.iterations >= effective_budget.max_iterations:
                self.event_store.append(
                    operation_id,
                    "operation.failed",
                    {"reason": "iteration_limit"},
                )
                continue
            if snapshot.agent_calls >= effective_budget.max_agent_calls:
                self.event_store.append(
                    operation_id,
                    "operation.failed",
                    {"reason": "agent_call_limit"},
                )
                continue

            self.event_store.append(
                operation_id,
                "operation.iteration",
                {"iteration": snapshot.iterations + 1},
            )
            refreshed = self.projection_service.snapshot(operation_id)
            decision = self.adapter_gateway.decide(refreshed)
            if decision.action is BrainAction.COMPLETE:
                self.event_store.append(
                    operation_id,
                    "operation.completed",
                    {"reason": decision.message or "completed"},
                )
            elif decision.action is BrainAction.FAIL:
                self.event_store.append(
                    operation_id,
                    "operation.failed",
                    {"reason": decision.message or "failed"},
                )
            elif decision.action is BrainAction.REQUEST_ATTENTION:
                attention_id = f"attn-{refreshed.source_sequence + 1}"
                self.event_store.append(
                    operation_id,
                    "attention.requested",
                    {"attention_id": attention_id, "prompt": decision.prompt},
                )
            elif decision.action is BrainAction.INVOKE_AGENT:
                if refreshed.agent_calls + 1 > effective_budget.max_agent_calls:
                    self.event_store.append(
                        operation_id,
                        "operation.failed",
                        {"reason": "agent_call_limit"},
                    )
                    continue
                self._invoke_agent(
                    operation_id, decision.agent_name, decision.agent_input
                )
            elif decision.action is BrainAction.INVOKE_AGENTS:
                if (
                    refreshed.agent_calls + len(decision.agent_requests)
                    > effective_budget.max_agent_calls
                ):
                    self.event_store.append(
                        operation_id,
                        "operation.failed",
                        {"reason": "agent_call_limit"},
                    )
                    continue
                self._invoke_agents(operation_id, decision)
            elif decision.action is BrainAction.WAIT:
                self.event_store.append(
                    operation_id, "operation.paused", {"reason": "wait"}
                )

    def _invoke_agent(
        self, operation_id: str, agent_name: str, agent_input: str
    ) -> None:
        self.event_store.append(
            operation_id,
            "agent.invocation.started",
            {"agent_name": agent_name, "input": agent_input},
        )
        result = self.adapter_gateway.invoke_agent(agent_name, agent_input)
        if result.success:
            self.event_store.append(
                operation_id,
                "agent.invocation.finished",
                {"agent_name": agent_name, "output": result.output},
            )
        else:
            self.event_store.append(
                operation_id,
                "agent.invocation.failed",
                {"agent_name": agent_name, "error": result.error},
            )

    def _invoke_agents(self, operation_id: str, decision: BrainDecision) -> None:
        if not decision.agent_requests:
            self.event_store.append(
                operation_id,
                "operation.failed",
                {"reason": "invoke_agents decision had no agent requests"},
            )
            return
        for request in decision.agent_requests:
            self.event_store.append(
                operation_id,
                "agent.invocation.started",
                {"agent_name": request.agent_name, "input": request.agent_input},
            )
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(decision.agent_requests)
        ) as executor:
            results = tuple(
                executor.map(self._invoke_agent_request, decision.agent_requests)
            )
        for request, result in results:
            if result.success:
                self.event_store.append(
                    operation_id,
                    "agent.invocation.finished",
                    {"agent_name": request.agent_name, "output": result.output},
                )
            else:
                self.event_store.append(
                    operation_id,
                    "agent.invocation.failed",
                    {"agent_name": request.agent_name, "error": result.error},
                )

    def _invoke_agent_request(
        self, request: AgentRequest
    ) -> tuple[AgentRequest, AgentResult]:
        return (
            request,
            self.adapter_gateway.invoke_agent(request.agent_name, request.agent_input),
        )
