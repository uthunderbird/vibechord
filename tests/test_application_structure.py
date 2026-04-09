from __future__ import annotations

import ast
from pathlib import Path

APPLICATION_DIR = (
    Path(__file__).resolve().parents[1] / "src" / "agent_operator" / "application"
)


def _python_sources(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def test_application_init_remains_export_only() -> None:
    module = ast.parse((APPLICATION_DIR / "__init__.py").read_text(encoding="utf-8"))

    for node in module.body:
        assert not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))


def test_application_modules_do_not_import_cli() -> None:
    offenders: list[str] = []

    for path in _python_sources(APPLICATION_DIR):
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("agent_operator.cli"):
                        offenders.append(f"{path.relative_to(APPLICATION_DIR)} -> {alias.name}")
            if (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.startswith("agent_operator.cli")
            ):
                offenders.append(f"{path.relative_to(APPLICATION_DIR)} -> {node.module}")

    assert offenders == []


def test_application_keeps_drive_and_event_sourcing_subpackages() -> None:
    assert (APPLICATION_DIR / "drive" / "__init__.py").exists()
    assert (APPLICATION_DIR / "event_sourcing" / "__init__.py").exists()


def test_application_keeps_commands_queries_and_runtime_subpackages() -> None:
    assert (APPLICATION_DIR / "commands" / "__init__.py").exists()
    assert (APPLICATION_DIR / "queries" / "__init__.py").exists()
    assert (APPLICATION_DIR / "runtime" / "__init__.py").exists()


def test_migrated_flat_application_family_modules_are_removed() -> None:
    retired = {
        "operation_agenda_queries.py",
        "operation_attention.py",
        "operation_cancellation.py",
        "operation_commands.py",
        "operation_control_state.py",
        "operation_dashboard_queries.py",
        "operation_delivery_commands.py",
        "operation_event_relay.py",
        "operation_fleet_workbench_queries.py",
        "operation_policy_context.py",
        "operation_process_dispatch.py",
        "operation_project_dashboard_queries.py",
        "operation_projections.py",
        "operation_runtime.py",
        "operation_runtime_context.py",
        "operation_runtime_reconciliation.py",
        "operation_state_views.py",
        "operation_traceability.py",
    }

    present = {path.name for path in APPLICATION_DIR.glob("*.py")}
    assert retired.isdisjoint(present)


def test_queries_do_not_import_commands_family() -> None:
    offenders: list[str] = []
    queries_dir = APPLICATION_DIR / "queries"

    for path in _python_sources(queries_dir):
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("agent_operator.application.commands"):
                        offenders.append(f"{path.relative_to(APPLICATION_DIR)} -> {alias.name}")
            if (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.startswith("agent_operator.application.commands")
            ):
                offenders.append(f"{path.relative_to(APPLICATION_DIR)} -> {node.module}")

    assert offenders == []
