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
