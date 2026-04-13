from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from agent_operator.cli.main import app
from agent_operator.config import load_global_config

runner = CliRunner()


def test_config_show_redacts_provider_tokens(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "project_roots:",
                "  - /tmp/projects",
                "providers:",
                "  github:",
                "    token: ghp_secret",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPERATOR_GLOBAL_CONFIG", str(config_path))

    result = runner.invoke(app, ["config", "show", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["project_roots"] == ["/tmp/projects"]
    assert payload["providers"]["github"]["token"] == "[REDACTED]"


def test_config_edit_creates_missing_file_and_opens_editor(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    editor_log = tmp_path / "editor-path.txt"
    editor = tmp_path / "editor.sh"
    editor.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                f"printf '%s' \"$1\" > {editor_log}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    editor.chmod(0o755)
    monkeypatch.setenv("OPERATOR_GLOBAL_CONFIG", str(config_path))
    monkeypatch.setenv("EDITOR", str(editor))

    result = runner.invoke(app, ["config", "edit"])

    assert result.exit_code == 0
    assert config_path.exists()
    assert editor_log.read_text(encoding="utf-8") == str(config_path)
    assert f"Opened global config: {config_path}" in result.stdout


def test_config_set_root_appends_root_and_persists_json_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    project_root = tmp_path / "projects" / "alpha"
    project_root.mkdir(parents=True)
    monkeypatch.setenv("OPERATOR_GLOBAL_CONFIG", str(config_path))

    result = runner.invoke(app, ["config", "set-root", str(project_root), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["added"] is True
    assert payload["project_root"] == str(project_root.resolve())
    assert payload["project_roots"] == [str(project_root.resolve())]
    assert load_global_config(config_path).project_roots == [project_root.resolve()]


def test_config_set_root_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    project_root = tmp_path / "projects" / "alpha"
    project_root.mkdir(parents=True)
    config_path.write_text(
        f"project_roots:\n  - {project_root.resolve()}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPERATOR_GLOBAL_CONFIG", str(config_path))

    result = runner.invoke(app, ["config", "set-root", str(project_root)])

    assert result.exit_code == 0
    assert f"Already present project root: {project_root.resolve()}" in result.stdout
    assert load_global_config(config_path).project_roots == [project_root.resolve()]
