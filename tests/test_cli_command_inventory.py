from __future__ import annotations

from pathlib import Path

from typer.main import get_command as typer_get_command

from agent_operator.cli.app import app
from agent_operator.cli.command_inventory import COMMAND_INVENTORY

REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_DOC = REPO_ROOT / "docs" / "reference" / "cli-command-inventory.md"


def _iter_command_paths(command, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    commands = getattr(command, "commands", None)
    if not isinstance(commands, dict):
        return paths
    for name, child in commands.items():
        path = f"{prefix} {name}".strip()
        paths.add(path)
        paths.update(_iter_command_paths(child, path))
    return paths


def test_cli_command_inventory_covers_registered_typer_tree() -> None:
    """Catches unclassified command registration drift in the Typer tree."""
    click_command = typer_get_command(app)
    discovered_paths = _iter_command_paths(click_command)
    declared_paths = {item.path for item in COMMAND_INVENTORY}

    assert declared_paths == discovered_paths


def test_cli_command_inventory_keeps_debug_aliases_out_of_stable_set() -> None:
    """Catches a hidden alias being promoted to stable inventory by mistake."""
    records = {item.path: item for item in COMMAND_INVENTORY}

    assert records["resume"].stability == "transitional"
    assert records["tick"].stability == "transitional"
    assert records["recover"].stability == "transitional"
    assert records["debug resume"].stability == "debug-only"
    assert records["debug tick"].stability == "debug-only"
    assert records["debug recover"].stability == "debug-only"


def test_cli_command_inventory_doc_lists_required_adr_0210_sections() -> None:
    inventory_doc = INVENTORY_DOC.read_text(encoding="utf-8")

    assert "Stable commands" in inventory_doc
    assert "Transitional commands" in inventory_doc
    assert "Debug-only commands" in inventory_doc
    assert "`run`" in inventory_doc
    assert "`resume`" in inventory_doc
    assert "`debug resume`" in inventory_doc
