from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_v2_verification_reference_points_to_real_evidence_template() -> None:
    procedure = (REPO_ROOT / "docs" / "reference" / "v2-verification.md").read_text(
        encoding="utf-8"
    )
    needle = "design/internal/v2-verification-evidence-template.md"

    assert needle in procedure
    assert (REPO_ROOT / "design" / "internal" / "v2-verification-evidence-template.md").exists()
