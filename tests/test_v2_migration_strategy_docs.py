from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = (
    REPO_ROOT / "design" / "adr" / "0194-v2-migration-strategy-full-rewrite.md"
)


def _load_adr() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def test_adr_0194_is_accepted_with_partial_implementation_truth() -> None:
    adr = _load_adr()

    assert "## Decision Status\n\nAccepted" in adr
    assert "## Implementation Status\n\nPartial" in adr


def test_adr_0194_references_current_v2_code_and_cutover_gate_artifacts() -> None:
    adr = _load_adr()

    required_strings = [
        "src/agent_operator/domain/aggregate.py",
        "src/agent_operator/application/drive/",
        "src/agent_operator/application/operator_service_v2.py",
        "src/agent_operator/cli/commands/run.py",
        "tests/test_operation_aggregate.py",
        "tests/test_operator_service_v2.py",
        "tests/test_runtime_reconciler.py",
        "tests/test_cli.py::test_v2_cli_smoke_creates_observes_and_cancels_without_runs_dir",
        "ADR 0209",
        "ADR 0213",
    ]

    for item in required_strings:
        assert item in adr
