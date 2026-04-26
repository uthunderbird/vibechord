from __future__ import annotations

from pathlib import Path

from agent_operator.cli.command_inventory import COMMAND_INVENTORY

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DOC = REPO_ROOT / "docs" / "reference" / "cli-command-contracts.md"
SCHEMAS_DOC = REPO_ROOT / "docs" / "reference" / "cli-json-schemas.md"


def test_cli_command_contract_matrix_covers_inventory_paths() -> None:
    """Catches ADR 0210 contract-doc drift from the registered command inventory."""
    contracts_doc = CONTRACTS_DOC.read_text(encoding="utf-8")

    for record in COMMAND_INVENTORY:
        assert f"`{record.path}`" in contracts_doc


def test_cli_json_schema_reference_lists_current_json_surfaces() -> None:
    """Catches a JSON-capable CLI surface going undocumented by mistake."""
    schemas_doc = SCHEMAS_DOC.read_text(encoding="utf-8")

    required_headings = [
        "### `operator run --json`",
        "### `operator status --json`",
        "### `operator ask --json`",
        "### `operator fleet --once --json`",
        "### `operator list --json`",
        "### `operator history --json`",
        "### `operator agenda --json`",
        "### `operator inspect --json`",
        "### `operator report --json`",
        "### `operator dashboard --json`",
        "### `operator tasks --json`",
        "### `operator memory --json`",
        "### `operator artifacts --json`",
        "### `operator log --json`",
        "### `operator session --json`",
        "### `operator attention --json`",
        "### `operator answer --json`",
        "### `operator cancel --json`",
        "### `operator watch --once --json`",
        "### `operator agent list --json`",
        "### `operator agent show --json`",
        "### `operator config show --json`",
        "### `operator config set-root --json`",
        "### `operator project list --json`",
        "### `operator project create --json`",
        "### `operator project inspect --json`",
        "### `operator project resolve --json`",
        "### `operator project dashboard --json`",
        "### `operator policy projects --json`",
        "### `operator policy list --json`",
        "### `operator policy inspect --json`",
        "### `operator policy explain --json`",
        "### `operator debug daemon --json`",
        "### `operator debug recover --json`",
        "### `operator debug resume --json`",
        "### `operator debug wakeups --json`",
        "### `operator debug sessions --json`",
        "### `operator debug inspect --json`",
        "### `operator debug context --json`",
        "### `operator debug trace --json`",
        "### `operator debug event append --json`",
    ]

    for heading in required_headings:
        assert heading in schemas_doc


def test_cli_json_schema_reference_keeps_transitional_aliases_out_of_stable_section() -> None:
    """Catches a transitional alias being documented as a stable JSON surface."""
    schemas_doc = SCHEMAS_DOC.read_text(encoding="utf-8")

    stable_section, transitional_section = schemas_doc.split(
        "## Transitional And Debug JSON Surfaces", maxsplit=1
    )

    assert "### `operator inspect --json`" not in stable_section
    assert "### `operator inspect --json`" in transitional_section


def test_cli_json_schema_reference_does_not_duplicate_ask_contract() -> None:
    """Catches doc drift that invents extra JSON fields for `operator ask --json`."""
    schemas_doc = SCHEMAS_DOC.read_text(encoding="utf-8")

    assert schemas_doc.count("### `operator ask --json`") == 1
