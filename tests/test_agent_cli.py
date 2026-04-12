from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from agent_operator.cli.main import app

runner = CliRunner()


def test_agent_list_is_inventory_shaped_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["agent", "list"])

    assert result.exit_code == 0
    assert "Agents" in result.stdout
    assert "- claude_acp: Claude Code via ACP" in result.stdout
    assert "- codex_acp: Codex via ACP" in result.stdout
    assert "- opencode_acp: OpenCode via ACP" in result.stdout
    assert "Configured settings:" not in result.stdout
    assert "Capabilities:" not in result.stdout

    json_result = runner.invoke(app, ["agent", "list", "--json"])

    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    agents = payload["agents"]
    assert [item["key"] for item in agents] == ["claude_acp", "codex_acp", "opencode_acp"]
    assert [item["display_name"] for item in agents] == [
        "Claude Code via ACP",
        "Codex via ACP",
        "OpenCode via ACP",
    ]
    for item in agents:
        assert item["supports_follow_up"] is True
        assert item["supports_cancellation"] is True
        assert item["capability_names"][:2] == ["acp", "follow_up"]
        assert "edit_files" in item["capability_names"]


def test_agent_show_defaults_to_human_readable_configuration(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPERATOR_CODEX_ACP__MODEL", "gpt-5.4")
    monkeypatch.setenv("OPERATOR_CODEX_ACP__REASONING_EFFORT", "high")
    monkeypatch.setenv("OPERATOR_CODEX_ACP__APPROVAL_POLICY", "never")

    result = runner.invoke(app, ["agent", "show", "codex_acp"])

    assert result.exit_code == 0
    assert "Agent: codex_acp" in result.stdout
    assert "Display name: Codex via ACP" in result.stdout
    assert "Supports follow-up: yes" in result.stdout
    assert "Supports cancellation: yes" in result.stdout
    assert "Capabilities:" in result.stdout
    assert "- acp: ACP session over stdio" in result.stdout
    assert "Configured settings:" in result.stdout
    assert '"model": "gpt-5.4"' in result.stdout
    assert '"reasoning_effort": "high"' in result.stdout
    assert '"approval_policy": "never"' in result.stdout

    json_result = runner.invoke(app, ["agent", "show", "codex_acp", "--json"])

    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload["key"] == "codex_acp"
    assert payload["display_name"] == "Codex via ACP"
    assert payload["supports_follow_up"] is True
    assert payload["supports_cancellation"] is True
    assert payload["capabilities"][0] == {
        "name": "acp",
        "description": "ACP session over stdio",
    }
    assert payload["configured_settings"]["model"] == "gpt-5.4"
    assert payload["configured_settings"]["reasoning_effort"] == "high"
    assert payload["configured_settings"]["approval_policy"] == "never"


def test_agent_show_rejects_unknown_agent_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["agent", "show", "missing_agent"])

    assert result.exit_code != 0
    assert "Unknown agent: missing_agent" in result.output
