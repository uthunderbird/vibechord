from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = (
    REPO_ROOT
    / "design"
    / "adr"
    / "0213-v2-cutover-governance-and-legacy-removal-acceptance-gate.md"
)
CHECKLIST_PATH = REPO_ROOT / "design" / "internal" / "v2-cutover-governance-checklist.md"


def _load_checklist() -> str:
    return CHECKLIST_PATH.read_text(encoding="utf-8")


def _load_adr() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def test_cutover_governance_checklist_exists_and_is_referenced_by_adr_0213() -> None:
    checklist = _load_checklist()
    adr = _load_adr()

    assert CHECKLIST_PATH.exists()
    assert "design/internal/v2-cutover-governance-checklist.md" in adr
    assert "Current Legacy Inventory" in checklist


def test_cutover_governance_checklist_includes_required_gate_sections() -> None:
    checklist = _load_checklist()

    required_sections = [
        "Pinned Repository State",
        "Drain Or Explicit Terminal Disposition",
        "Canonical v2 Authority Preconditions",
        "Legacy Removal Inventory",
        "Removal Order",
        "Rollback Boundary",
        "Rehearsal",
    ]

    for section in required_sections:
        assert section in checklist


def test_cutover_governance_checklist_records_inventory_and_rehearsal_commands() -> None:
    checklist = _load_checklist()

    required_strings = [
        "retained temporarily as migration-only or forensic-only",
        "deferred with named blocker",
        "docs/reference/cli-command-contracts.md",
        "UV_CACHE_DIR=/tmp/uv-cache uv run pytest",
        "UV_CACHE_DIR=/tmp/uv-cache uv run operator status last --json",
        "UV_CACHE_DIR=/tmp/uv-cache uv run operator watch last --once --json",
        "UV_CACHE_DIR=/tmp/uv-cache uv run operator debug inspect last --json --full",
        "allowed only through git history, not runtime compatibility",
    ]

    for item in required_strings:
        assert item in checklist
