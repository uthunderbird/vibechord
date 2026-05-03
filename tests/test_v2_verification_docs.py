from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROCEDURE_PATH = REPO_ROOT / "docs" / "reference" / "v2-verification.md"
FULL_SUITE_EVIDENCE_PATH = (
    REPO_ROOT / "design" / "internal" / "v2-verification-evidence-2026-05-03-full-suite.md"
)
LIVE_CODEX_ACP_EVIDENCE_PATH = (
    REPO_ROOT
    / "design"
    / "internal"
    / "v2-verification-evidence-2026-05-03-live-codex-acp-preflight.md"
)


def _load_procedure() -> str:
    return PROCEDURE_PATH.read_text(encoding="utf-8")


def test_v2_verification_reference_points_to_real_evidence_template() -> None:
    procedure = _load_procedure()
    needle = "design/internal/v2-verification-evidence-template.md"

    assert needle in procedure
    assert (REPO_ROOT / "design" / "internal" / "v2-verification-evidence-template.md").exists()


def test_v2_verification_reference_points_to_recorded_full_suite_evidence() -> None:
    """Catches dropping the pinned repository-wide baseline evidence note."""

    procedure = _load_procedure()
    evidence = FULL_SUITE_EVIDENCE_PATH.read_text(encoding="utf-8")

    assert "design/internal/v2-verification-evidence-2026-05-03-full-suite.md" in procedure
    assert FULL_SUITE_EVIDENCE_PATH.exists()
    assert "Matrix row: full `uv run pytest`" in evidence
    assert "Result: `passed`" in evidence
    assert "1100 passed, 11 skipped" in evidence


def test_v2_verification_reference_points_to_recorded_live_acp_blocker_evidence() -> None:
    """Catches hiding a blocked live ACP preflight as an unrecorded skip."""

    procedure = _load_procedure()
    evidence = LIVE_CODEX_ACP_EVIDENCE_PATH.read_text(encoding="utf-8")

    assert (
        "design/internal/v2-verification-evidence-2026-05-03-live-codex-acp-preflight.md"
        in procedure
    )
    assert LIVE_CODEX_ACP_EVIDENCE_PATH.exists()
    assert "Matrix row: live Codex ACP roundtrip" in evidence
    assert "Result: `blocked`" in evidence
    assert "ACP subprocess closed before completing all pending requests" in evidence
    assert "ENOTFOUND registry.npmjs.org" in evidence


def test_v2_verification_matrix_lists_required_adr_0211_rows() -> None:
    procedure = _load_procedure()

    required_rows = [
        "targeted query/read-model tests",
        "stream/TUI visibility smoke",
        "restart/resume smoke",
        "operator-on-operator mixed-code smoke",
        "external project permission slice",
        "no `.operator/runs` dependency",
    ]

    for row in required_rows:
        assert row in procedure


def test_v2_verification_procedure_includes_canonical_visibility_commands() -> None:
    procedure = _load_procedure()

    assert "uv run operator status last --json" in procedure
    assert "uv run operator watch last --once --json" in procedure
    assert "uv run operator debug inspect last --json --full" in procedure
