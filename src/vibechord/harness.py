"""Deterministic local fake harness."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from vibechord.adapters import AdapterGateway, ScriptedAgentAdapter, ScriptedBrain
from vibechord.command import CommandApplication
from vibechord.domain import (
    BrainAction,
    BrainDecision,
    CommandName,
    HarnessSummary,
    OperationCommand,
)
from vibechord.driver import OperationDriver
from vibechord.jsonutil import to_jsonable
from vibechord.projection import ProjectionService
from vibechord.store import JsonlEventStore
from vibechord.time import FakeClock


def run_fake_harness(root: Path, workflow: str = "happy") -> HarnessSummary:
    """Run a deterministic fake workflow and write a machine-readable summary."""

    run_id = str(uuid.uuid4())
    started_at = FakeClock().now()
    harness_dir = root / ".vibechord-harness" / run_id
    harness_dir.mkdir(parents=True, exist_ok=True)
    event_path = harness_dir / "events.jsonl"
    clock = FakeClock()
    store = JsonlEventStore(event_path, clock)
    command_app = CommandApplication(store)
    projection = ProjectionService(store)
    gateway = _gateway_for(workflow)
    driver = OperationDriver(store, projection, gateway)
    operation_ids: list[str] = []
    failed_rail: str | None = None
    failure_message: str | None = None

    try:
        start = command_app.apply(
            OperationCommand(
                name=CommandName.START,
                command_id=f"{run_id}:start",
                payload={"goal": f"harness {workflow}"},
            )
        )
        if start.operation_id is None:
            raise RuntimeError("start did not return operation id")
        operation_ids.append(start.operation_id)
        driver.run_until_blocked_or_terminal(start.operation_id)
        if workflow == "attention":
            snapshot = projection.snapshot(start.operation_id)
            if snapshot.open_attention_id is None:
                raise RuntimeError("attention workflow did not block")
            command_app.apply(
                OperationCommand(
                    name=CommandName.ANSWER_ATTENTION,
                    command_id=f"{run_id}:answer",
                    operation_id=start.operation_id,
                    payload={"attention_id": snapshot.open_attention_id, "text": "yes"},
                )
            )
            driver.run_until_blocked_or_terminal(start.operation_id)
        if workflow == "chat":
            command_app.apply(
                OperationCommand(
                    name=CommandName.POST_MESSAGE,
                    command_id=f"{run_id}:message",
                    operation_id=start.operation_id,
                    payload={"text": "operator says continue"},
                )
            )
        if workflow == "cancel":
            command_app.apply(
                OperationCommand(
                    name=CommandName.CANCEL,
                    command_id=f"{run_id}:cancel",
                    operation_id=start.operation_id,
                )
            )
    except RuntimeError as exc:
        failed_rail = "VS-004"
        failure_message = str(exc)

    sequences = {
        operation_id: projection.snapshot(operation_id).source_sequence
        for operation_id in operation_ids
    }
    status = "failed" if failed_rail else "passed"
    summary = HarnessSummary(
        schema_version="1",
        run_id=run_id,
        workflow=workflow,
        status=status,
        operation_ids=tuple(operation_ids),
        event_artifact_paths=(str(event_path),),
        last_event_sequence_by_operation=sequences,
        rails_exercised=("VS-001", "VS-003", "VS-004", "VS-005", "VS-012"),
        failed_rail=failed_rail,
        failure_message=failure_message,
        started_at=started_at,
        finished_at=clock.now(),
    )
    summary_path = harness_dir / "summary.json"
    summary_path.write_text(
        json.dumps(to_jsonable(summary), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def _gateway_for(workflow: str) -> AdapterGateway:
    if workflow == "attention":
        decisions = [
            BrainDecision(BrainAction.REQUEST_ATTENTION, prompt="approve?"),
            BrainDecision(BrainAction.COMPLETE, message="after attention"),
        ]
    elif workflow == "adapter_failure":
        decisions = [
            BrainDecision(
                BrainAction.INVOKE_AGENT,
                agent_name="fake-agent",
                agent_input="fail please",
            )
        ]
    elif workflow == "agent":
        decisions = [
            BrainDecision(
                BrainAction.INVOKE_AGENT,
                agent_name="fake-agent",
                agent_input="do work",
            ),
            BrainDecision(BrainAction.COMPLETE, message="agent done"),
        ]
    else:
        decisions = [BrainDecision(BrainAction.COMPLETE, message="done")]
    return AdapterGateway(ScriptedBrain(decisions), ScriptedAgentAdapter())
