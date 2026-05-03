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
OPERATOR_ON_OPERATOR_EVIDENCE_PATH = (
    REPO_ROOT
    / "design"
    / "internal"
    / "v2-verification-evidence-2026-05-03-operator-on-operator-smoke.md"
)
EXTERNAL_625_EVIDENCE_PATH = (
    REPO_ROOT
    / "design"
    / "internal"
    / "v2-verification-evidence-2026-05-04-external-625-smoke.md"
)
PERMISSION_SLICE_EVIDENCE_PATH = (
    REPO_ROOT
    / "design"
    / "internal"
    / "v2-verification-evidence-2026-05-04-permission-slice.md"
)
NO_RUNS_EVIDENCE_PATH = (
    REPO_ROOT
    / "design"
    / "internal"
    / "v2-verification-evidence-2026-05-04-no-runs-dependency.md"
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
    assert "1106 passed, 12 skipped" in evidence


def test_v2_verification_reference_points_to_recorded_live_acp_evidence() -> None:
    """Catches hiding live ACP preflight evidence as an unrecorded skip."""

    procedure = _load_procedure()
    evidence = LIVE_CODEX_ACP_EVIDENCE_PATH.read_text(encoding="utf-8")

    assert (
        "design/internal/v2-verification-evidence-2026-05-03-live-codex-acp-preflight.md"
        in procedure
    )
    assert LIVE_CODEX_ACP_EVIDENCE_PATH.exists()
    assert "Matrix row: live Codex ACP preflight" in evidence
    assert "Result: `passed`" in evidence
    assert "ACP subprocess closed before completing all pending requests" in evidence
    assert "ENOTFOUND registry.npmjs.org" in evidence


def test_v2_verification_reference_points_to_operator_on_operator_evidence() -> None:
    """Catches dropping the fresh operator-on-operator smoke evidence note."""

    procedure = _load_procedure()
    evidence = OPERATOR_ON_OPERATOR_EVIDENCE_PATH.read_text(encoding="utf-8")

    assert (
        "design/internal/v2-verification-evidence-2026-05-03-operator-on-operator-smoke.md"
        in procedure
    )
    assert OPERATOR_ON_OPERATOR_EVIDENCE_PATH.exists()
    assert "Matrix row: operator-on-operator v2 smoke" in evidence
    assert "Result: `passed`" in evidence
    assert "2d4bd45f-68fb-4709-a91c-6cb587591689" in evidence
    assert "silent type coercion" in evidence
    assert "forgotten branch/missed case" in evidence


def test_v2_verification_reference_points_to_external_625_evidence() -> None:
    """Catches dropping the fresh external problem 625 smoke evidence note."""

    procedure = _load_procedure()
    evidence = EXTERNAL_625_EVIDENCE_PATH.read_text(encoding="utf-8")

    assert "design/internal/v2-verification-evidence-2026-05-04-external-625-smoke.md" in procedure
    assert EXTERNAL_625_EVIDENCE_PATH.exists()
    assert "Matrix row: external project smoke against `../erdosreshala/problems/625`" in evidence
    assert "Result: `passed`" in evidence
    assert "b77cfdca-6991-4869-af9d-5c71100be3fc" in evidence
    assert "no-`.operator/runs` independence" in evidence
    assert "leaked resource" in evidence


def test_v2_verification_reference_points_to_permission_slice_evidence() -> None:
    """Catches hiding the permission slice outcome after a bounded write probe."""

    procedure = _load_procedure()
    evidence = PERMISSION_SLICE_EVIDENCE_PATH.read_text(encoding="utf-8")

    assert "design/internal/v2-verification-evidence-2026-05-04-permission-slice.md" in procedure
    assert PERMISSION_SLICE_EVIDENCE_PATH.exists()
    assert "Matrix row: external project permission slice" in evidence
    assert "Result: `passed`" in evidence
    assert "9dae40c7-b49c-4e54-a184-4094d0c827c2" in evidence
    assert "Permission-path outcome: no permission event observed" in evidence
    assert "not enough to" in procedure
    assert "promote ADR 0202" in procedure


def test_v2_verification_reference_points_to_no_runs_evidence() -> None:
    """Catches dropping the outcome-based no-.operator/runs dependency evidence."""

    procedure = _load_procedure()
    evidence = NO_RUNS_EVIDENCE_PATH.read_text(encoding="utf-8")

    assert "design/internal/v2-verification-evidence-2026-05-04-no-runs-dependency.md" in procedure
    assert NO_RUNS_EVIDENCE_PATH.exists()
    assert "Matrix row: no `.operator/runs` dependency" in evidence
    assert "Result: `passed`" in evidence
    assert "9dae40c7-b49c-4e54-a184-4094d0c827c2" in evidence
    assert "printed no files" in evidence
    assert "operator list --json" in evidence


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
