from __future__ import annotations

from pathlib import Path

from typer.main import get_command as typer_get_command

from agent_operator.cli.app import app
from agent_operator.cli.command_inventory import (
    ADR_0219_CANONICAL_ROOT_COMMANDS,
    ADR_0219_GROUPING_BACKLOG,
    COMMAND_INVENTORY,
)

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


def test_cli_command_inventory_keeps_grouped_compatibility_aliases_transitional() -> None:
    """Catches the mutation where grouped-family root aliases drift back to stable roots."""
    records = {item.path: item for item in COMMAND_INVENTORY}

    assert records["agenda"].stability == "transitional"
    assert records["history"].stability == "transitional"
    assert records["involvement"].stability == "transitional"
    assert records["list"].stability == "transitional"
    assert records["fleet agenda"].stability == "stable"
    assert records["fleet history"].stability == "stable"
    assert records["fleet list"].stability == "stable"
    assert records["edit involvement"].stability == "stable"
    assert records["artifacts"].stability == "transitional"
    assert records["attention"].stability == "transitional"
    assert records["dashboard"].stability == "transitional"
    assert records["log"].stability == "transitional"
    assert records["memory"].stability == "transitional"
    assert records["report"].stability == "transitional"
    assert records["session"].stability == "transitional"
    assert records["tasks"].stability == "transitional"
    assert records["show artifacts"].stability == "stable"
    assert records["show attention"].stability == "stable"
    assert records["show dashboard"].stability == "stable"
    assert records["show log"].stability == "stable"
    assert records["show memory"].stability == "stable"
    assert records["show report"].stability == "stable"
    assert records["show session"].stability == "stable"
    assert records["show tasks"].stability == "stable"
    assert records["converse"].stability == "transitional"


def test_cli_command_inventory_doc_lists_required_adr_0210_sections() -> None:
    inventory_doc = INVENTORY_DOC.read_text(encoding="utf-8")

    assert "Stable commands" in inventory_doc
    assert "Transitional commands" in inventory_doc
    assert "Debug-only commands" in inventory_doc
    assert "`run`" in inventory_doc
    assert "`resume`" in inventory_doc
    assert "`debug resume`" in inventory_doc


def test_adr_0219_canonical_root_surface_is_explicit_subset() -> None:
    """Catches the mutation where ADR 0219 root canon drifts back into a flat stable list."""
    records = {item.path: item for item in COMMAND_INVENTORY}

    assert ADR_0219_CANONICAL_ROOT_COMMANDS
    assert all(" " not in path for path in ADR_0219_CANONICAL_ROOT_COMMANDS)
    assert records.keys() >= ADR_0219_CANONICAL_ROOT_COMMANDS
    assert {
        path
        for path in ADR_0219_CANONICAL_ROOT_COMMANDS
        if records[path].stability != "stable"
    } == set()


def test_adr_0219_grouping_backlog_names_existing_stable_root_commands() -> None:
    """Catches the mutation where a non-empty grouping backlog stops matching stable roots."""
    records = {item.path: item for item in COMMAND_INVENTORY}
    grouped_paths = {
        path
        for paths in ADR_0219_GROUPING_BACKLOG.values()
        for path in paths
    }

    if not grouped_paths:
        return
    assert grouped_paths.isdisjoint(ADR_0219_CANONICAL_ROOT_COMMANDS)
    assert all(" " not in path for path in grouped_paths)
    assert grouped_paths <= records.keys()
    assert {path for path in grouped_paths if records[path].stability != "stable"} == set()


def test_adr_0219_accounts_for_all_stable_root_commands() -> None:
    """Catches the mutation where new stable root commands bypass root-surface classification."""
    stable_root_paths = {
        item.path
        for item in COMMAND_INVENTORY
        if item.stability == "stable" and " " not in item.path
    }
    grouped_paths = {
        path
        for paths in ADR_0219_GROUPING_BACKLOG.values()
        for path in paths
    }

    assert stable_root_paths == ADR_0219_CANONICAL_ROOT_COMMANDS | grouped_paths
