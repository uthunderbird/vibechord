from __future__ import annotations

import json
from pathlib import Path

from vibechord.harness import run_fake_harness


def test_fake_harness_writes_summary_shape(tmp_path: Path) -> None:
    summary = run_fake_harness(tmp_path, "attention")
    assert summary.status == "passed"
    assert "VS-004" in summary.rails_exercised
    summary_paths = list((tmp_path / ".vibechord-harness").glob("*/summary.json"))
    assert summary_paths
    payload = json.loads(summary_paths[0].read_text(encoding="utf-8"))
    assert {
        "schema_version",
        "run_id",
        "workflow",
        "status",
        "operation_ids",
        "event_artifact_paths",
        "last_event_sequence_by_operation",
        "rails_exercised",
        "failed_rail",
        "failure_message",
        "started_at",
        "finished_at",
    } <= payload.keys()


def test_fake_harness_covers_adapter_failure_workflow(tmp_path: Path) -> None:
    summary = run_fake_harness(tmp_path, "adapter_failure")
    assert summary.status == "passed"
    assert summary.last_event_sequence_by_operation


def test_architecture_mentions_six_core_parts() -> None:
    root = Path(__file__).resolve().parents[1]
    moving_parts = (root / "design" / "MOVING-PARTS.md").read_text(encoding="utf-8")
    for name in (
        "Domain Model",
        "CommandApplication",
        "OperationDriver",
        "EventStore",
        "ProjectionService",
        "AdapterGateway",
    ):
        assert name in moving_parts
    assert "per-surface command handlers" in moving_parts
