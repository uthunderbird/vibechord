from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from agent_operator.cli.main import app

runner = CliRunner()


def test_default_help_frames_workspace_lifecycle_family(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Workspace lifecycle shell for operator." in result.stdout
    assert "run" in result.stdout
    assert "Start a new operation in the current workspace" in result.stdout
    assert "init" in result.stdout
    assert "Prepare this workspace for operator" in result.stdout
    assert "clear" in result.stdout
    assert "Reset project-local operator runtime state" in result.stdout
