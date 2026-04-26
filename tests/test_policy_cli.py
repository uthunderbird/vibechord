from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import anyio
from typer.testing import CliRunner

from agent_operator.cli.main import app
from agent_operator.domain import (
    ObjectiveState,
    OperationCheckpoint,
    OperationCheckpointRecord,
    OperationGoal,
    OperationPolicy,
    OperationState,
    PolicyApplicability,
    PolicyCategory,
    PolicyEntry,
    PolicyStatus,
    RunMode,
    TaskState,
)
from agent_operator.runtime import FileOperationStore, FilePolicyStore

runner = CliRunner()


def _seed_policy_entries(tmp_path: Path) -> None:
    store = FilePolicyStore(tmp_path / "policies")

    async def _seed() -> None:
        await store.save(
            PolicyEntry(
                policy_id="policy-alpha-testing",
                project_scope="profile:alpha",
                title="Manual test notes",
                category=PolicyCategory.TESTING,
                rule_text="Record manual-only checks in MANUAL_TESTING_REQUIRED.md.",
                applicability=PolicyApplicability(objective_keywords=["testing"]),
            )
        )
        await store.save(
            PolicyEntry(
                policy_id="policy-alpha-release",
                project_scope="profile:alpha",
                title="Release approval",
                category=PolicyCategory.RELEASE,
                rule_text="Require explicit release approval before deployment.",
                applicability=PolicyApplicability(objective_keywords=["release"]),
                status=PolicyStatus.REVOKED,
                revoked_reason="replaced by deployment checklist",
            )
        )
        await store.save(
            PolicyEntry(
                policy_id="policy-beta-workflow",
                project_scope="profile:beta",
                title="Planning first",
                category=PolicyCategory.WORKFLOW,
                rule_text="Write a short plan before editing multiple files.",
                applicability=PolicyApplicability(task_keywords=["plan"]),
            )
        )

    anyio.run(_seed)


def _seed_operation_with_policy_scope(tmp_path: Path) -> str:
    operation_id = "op-policy-explain"
    store = FileOperationStore(tmp_path / "runs")

    async def _seed() -> None:
        await store.save_operation(
            OperationState(
                operation_id=operation_id,
                goal=OperationGoal(
                    objective="Prepare the testing checklist.",
                    harness_instructions="Keep deployment steps explicit.",
                    metadata={"policy_scope": "profile:alpha"},
                ),
                policy=OperationPolicy(allowed_agents=["codex_acp"]),
                runtime_hints={"metadata": {"run_mode": RunMode.ATTACHED.value}},
                tasks=[
                    TaskState(
                        title="Write the test plan",
                        goal="Plan release testing work before editing.",
                        definition_of_done="Test plan captured.",
                        notes=["Include the release checklist."],
                    )
                ],
            )
        )

    anyio.run(_seed)
    return operation_id


def _seed_event_sourced_operation_with_policy_scope(tmp_path: Path) -> str:
    operation_id = "op-policy-explain-v2"
    checkpoint = OperationCheckpoint.initial(operation_id)
    checkpoint.objective = ObjectiveState(
        objective="Prepare the testing checklist.",
        harness_instructions="Keep deployment steps explicit.",
        metadata={"policy_scope": "profile:alpha"},
    )
    checkpoint.allowed_agents = ["codex_acp"]
    checkpoint.policy_coverage = checkpoint.policy_coverage.model_copy(
        update={"project_scope": "profile:alpha"}
    )
    checkpoint.updated_at = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)
    checkpoint.created_at = checkpoint.updated_at
    checkpoint_record = OperationCheckpointRecord(
        operation_id=operation_id,
        checkpoint_payload=checkpoint.model_dump(mode="json"),
        last_applied_sequence=0,
        checkpoint_format_version=1,
    )
    checkpoint_path = tmp_path / "operation_checkpoints" / f"{operation_id}.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text(
        json.dumps({**checkpoint_record.model_dump(mode="json"), "epoch_id": 0}, indent=2),
        encoding="utf-8",
    )
    event_dir = tmp_path / "operation_events"
    event_dir.mkdir(exist_ok=True)
    (event_dir / f"{operation_id}.jsonl").write_text("", encoding="utf-8")
    return operation_id


def test_policy_projects_is_project_aggregation_surface(tmp_path: Path, monkeypatch) -> None:
    _seed_policy_entries(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["policy", "projects"])

    assert result.exit_code == 0
    assert "Projects With Policies" in result.stdout
    assert "- alpha" in result.stdout
    assert "- beta" in result.stdout
    assert "policy-alpha-testing" not in result.stdout
    assert "category:" not in result.stdout

    json_result = runner.invoke(app, ["policy", "projects", "--json"])

    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload["policy_projects"] == [
        {
            "project": "alpha",
            "project_scope": "profile:alpha",
            "policy_count": 2,
            "active_policy_count": 1,
            "categories": ["release", "testing"],
        },
        {
            "project": "beta",
            "project_scope": "profile:beta",
            "policy_count": 1,
            "active_policy_count": 1,
            "categories": ["workflow"],
        },
    ]


def test_policy_list_is_active_inventory_by_default(tmp_path: Path, monkeypatch) -> None:
    _seed_policy_entries(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["policy", "list", "--project", "alpha"])

    assert result.exit_code == 0
    assert "Project scope: alpha" in result.stdout
    assert "Policy entries:" in result.stdout
    assert "policy-alpha-testing [active] Manual test notes" in result.stdout
    assert "category: testing" in result.stdout
    assert "Record manual-only checks" in result.stdout
    assert "policy-alpha-release" not in result.stdout

    json_result = runner.invoke(app, ["policy", "list", "--project", "alpha", "--json"])

    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload["project_scope"] == "alpha"
    assert [entry["policy_id"] for entry in payload["policy_entries"]] == [
        "policy-alpha-testing"
    ]


def test_policy_inspect_is_entry_focused_by_default(tmp_path: Path, monkeypatch) -> None:
    _seed_policy_entries(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["policy", "inspect", "policy-beta-workflow"])

    assert result.exit_code == 0
    assert "Policy: policy-beta-workflow" in result.stdout
    assert "Project scope: profile:beta" in result.stdout
    assert "Title: Planning first" in result.stdout
    assert "Category: workflow" in result.stdout
    assert "Rule:" in result.stdout
    assert "Write a short plan before editing multiple files." in result.stdout
    assert "Applicability details:" in result.stdout
    assert "- Task keywords: plan" in result.stdout
    assert "Projects With Policies" not in result.stdout

    json_result = runner.invoke(app, ["policy", "inspect", "policy-beta-workflow", "--json"])

    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload["policy_id"] == "policy-beta-workflow"
    assert payload["project_scope"] == "profile:beta"
    assert payload["category"] == "workflow"


def test_policy_explain_is_deterministic_and_distinguishes_matched_from_skipped(
    tmp_path: Path, monkeypatch
) -> None:
    _seed_policy_entries(tmp_path)
    operation_id = _seed_operation_with_policy_scope(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["policy", "explain", operation_id])

    assert result.exit_code == 0
    assert f"Operation {operation_id}" in result.stdout
    assert "Project scope: profile:alpha" in result.stdout
    assert "Matched policy:" in result.stdout
    assert "policy-alpha-testing [active] Manual test notes" in result.stdout
    assert "matched_by: objective keyword=testing" in result.stdout
    assert "Skipped policy:" in result.stdout
    assert "policy-alpha-release" not in result.stdout

    json_result = runner.invoke(app, ["policy", "explain", operation_id, "--all", "--json"])

    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload["operation_id"] == operation_id
    assert payload["project_scope"] == "profile:alpha"
    assert payload["has_policy_scope"] is True
    assert [entry["policy_id"] for entry in payload["matched_policy_entries"]] == [
        "policy-alpha-testing"
    ]
    assert payload["matched_policy_entries"][0]["applies_now"] is True
    assert payload["matched_policy_entries"][0]["match_reasons"] == ["objective keyword=testing"]
    assert [entry["policy_id"] for entry in payload["skipped_policy_entries"]] == [
        "policy-alpha-release"
    ]
    assert payload["skipped_policy_entries"][0]["applies_now"] is False
    assert payload["skipped_policy_entries"][0]["skip_reasons"] == [
        "objective missing release"
    ]


def test_policy_explain_reads_event_sourced_operation_without_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    _seed_policy_entries(tmp_path)
    operation_id = _seed_event_sourced_operation_with_policy_scope(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["policy", "explain", "op-policy-explain", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["operation_id"] == operation_id
    assert payload["project_scope"] == "profile:alpha"
    assert [entry["policy_id"] for entry in payload["matched_policy_entries"]] == [
        "policy-alpha-testing"
    ]
