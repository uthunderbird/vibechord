from __future__ import annotations

import json
from pathlib import Path

import anyio
from typer.testing import CliRunner

from agent_operator.cli.main import app
from agent_operator.domain import (
    OperationGoal,
    OperationPolicy,
    OperationState,
    PolicyApplicability,
    PolicyCategory,
    PolicyCoverageStatus,
    PolicyEntry,
)
from agent_operator.runtime import FileOperationStore, FilePolicyStore

runner = CliRunner()


def _seed_policy_coverage_operation(tmp_path: Path) -> str:
    operation_id = "op-policy-coverage"
    store = FileOperationStore(tmp_path / "runs")

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(
                objective="Document the manual testing workflow",
                metadata={
                    "project_profile_name": "femtobot",
                    "policy_scope": "profile:femtobot",
                },
            ),
            policy=OperationPolicy(allowed_agents=["claude_acp"]),
        )
        state.policy_coverage.status = PolicyCoverageStatus.UNCOVERED
        state.policy_coverage.project_scope = "profile:femtobot"
        state.policy_coverage.scoped_policy_count = 2
        state.policy_coverage.summary = (
            "This scope has project policy, but none of it currently applies."
        )
        await store.save_operation(state)

    anyio.run(_seed)
    return operation_id


def test_context_json_surfaces_policy_coverage(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_policy_coverage_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["context", operation_id, "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["policy_coverage"]["status"] == "uncovered"
    assert payload["policy_coverage"]["scoped_policy_count"] == 2
    assert payload["policy_coverage"]["summary"] == (
        "This scope has project policy, but none of it currently applies."
    )


def test_dashboard_once_renders_policy_coverage_and_policy_hint(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_policy_coverage_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["dashboard", operation_id, "--once"])

    assert result.exit_code == 0
    assert "policy_coverage: uncovered" in result.stdout
    assert "coverage_summary: This scope has project policy" in result.stdout
    assert "operator policy list --project femtobot" in result.stdout


def test_policy_explain_surfaces_matched_and_skipped_entries(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_policy_coverage_operation(tmp_path)
    policy_store = FilePolicyStore(tmp_path / "policies")

    async def _seed() -> None:
        await policy_store.save(
            PolicyEntry(
                policy_id="policy-testing",
                project_scope="profile:femtobot",
                title="Manual testing debt",
                category=PolicyCategory.TESTING,
                rule_text="Record manual-only checks in MANUAL_TESTING_REQUIRED.md.",
                applicability=PolicyApplicability(objective_keywords=["testing"]),
            )
        )
        await policy_store.save(
            PolicyEntry(
                policy_id="policy-release",
                project_scope="profile:femtobot",
                title="Release approvals",
                category=PolicyCategory.RELEASE,
                rule_text="Require explicit release approval.",
                applicability=PolicyApplicability(objective_keywords=["release"]),
            )
        )

    anyio.run(_seed)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["policy", "explain", operation_id])

    assert result.exit_code == 0
    assert "Matched policy:" in result.stdout
    assert "policy-testing [active] Manual testing debt" in result.stdout
    assert "matched_by: objective keyword=testing" in result.stdout
    assert "Skipped policy:" in result.stdout
    assert "policy-release [active] Release approvals" in result.stdout
    assert "skipped_by: objective missing release" in result.stdout
