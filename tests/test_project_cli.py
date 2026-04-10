from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from agent_operator.cli.main import app
from agent_operator.config import OperatorSettings
from agent_operator.domain import InvolvementLevel, ProjectProfile, RunMode
from agent_operator.runtime import load_project_profile, write_project_profile

runner = CliRunner()


def _settings(tmp_path: Path) -> OperatorSettings:
    settings = OperatorSettings()
    settings.data_dir = tmp_path / ".operator"
    return settings


def test_project_list_is_inventory_shaped_by_default(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(settings.data_dir))
    monkeypatch.chdir(tmp_path)

    write_project_profile(
        settings,
        ProjectProfile(name="alpha", cwd=tmp_path / "alpha", default_agents=["codex_acp"]),
        local=True,
    )
    write_project_profile(
        settings,
        ProjectProfile(name="beta", cwd=tmp_path / "beta", default_agents=["claude_acp"]),
        local=False,
        cwd=tmp_path,
    )

    result = runner.invoke(app, ["project", "list"])

    assert result.exit_code == 0
    assert "Projects" in result.stdout
    assert "- alpha" in result.stdout
    assert "- beta" in result.stdout
    assert "Path:" not in result.stdout
    assert "Default objective:" not in result.stdout

    json_result = runner.invoke(app, ["project", "list", "--json"])

    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload["project_profiles"] == [
        {
            "name": "alpha",
            "path": str(settings.data_dir / "profiles" / "alpha.yaml"),
            "scope": "local",
            "cwd": str(tmp_path / "alpha"),
            "default_agents": ["codex_acp"],
            "default_objective": None,
            "default_involvement_level": None,
        },
        {
            "name": "beta",
            "path": str(tmp_path / "operator-profiles" / "beta.yaml"),
            "scope": "committed",
            "cwd": str(tmp_path / "beta"),
            "default_agents": ["claude_acp"],
            "default_objective": None,
            "default_involvement_level": None,
        },
    ]


def test_project_inspect_defaults_to_human_readable_local_profile(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path / ".operator"))
    (tmp_path / "operator-profile.yaml").write_text(
        "\n".join(
            [
                "name: operator",
                "cwd: .",
                "default_objective: Inspect the repo",
                "default_agents:",
                "  - codex_acp",
                "default_success_criteria:",
                "  - capture the main boundaries",
                "default_run_mode: attached",
                "default_involvement_level: auto",
                "default_message_window: 5",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["project", "inspect"])

    assert result.exit_code == 0
    assert "Profile: operator" in result.stdout
    assert f"Path: {tmp_path / 'operator-profile.yaml'}" in result.stdout
    assert "Default objective:" in result.stdout
    assert "Inspect the repo" in result.stdout
    assert "Default agents:" in result.stdout
    assert "- codex_acp" in result.stdout
    assert "Message window: 5" in result.stdout
    assert '"name"' not in result.stdout

    json_result = runner.invoke(app, ["project", "inspect", "--json"])

    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload["name"] == "operator"
    assert payload["default_objective"] == "Inspect the repo"
    assert payload["default_run_mode"] == "attached"
    assert payload["default_involvement_level"] == "auto"


def test_project_resolve_surfaces_effective_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path / ".operator"))
    (tmp_path / "operator-profile.yaml").write_text(
        "\n".join(
            [
                "name: operator",
                "cwd: .",
                "default_objective: Ship the smallest verified slice",
                "default_agents:",
                "  - codex_acp",
                "default_harness_instructions: Stay within repo truth.",
                "default_success_criteria:",
                "  - add verification",
                "default_max_iterations: 12",
                "default_run_mode: attached",
                "default_involvement_level: auto",
                "default_message_window: 7",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["project", "resolve"])

    assert result.exit_code == 0
    assert "Profile: operator" in result.stdout
    assert "Profile source: local_profile_file" in result.stdout
    assert "Resolved run defaults:" in result.stdout
    assert "- Objective: Ship the smallest verified slice" in result.stdout
    assert "- Agents: codex_acp" in result.stdout
    assert "- Harness: Stay within repo truth." in result.stdout
    assert "- Success criteria:" in result.stdout
    assert "  - add verification" in result.stdout
    assert "- Max iterations: 12" in result.stdout
    assert "- Run mode: attached" in result.stdout
    assert "- Involvement: auto" in result.stdout
    assert "- Message window: 7" in result.stdout
    assert "default_objective" not in result.stdout
    assert "default_harness_instructions" not in result.stdout

    json_result = runner.invoke(app, ["project", "resolve", "--json"])

    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload["profile_source"] == "local_profile_file"
    assert payload["resolved"] == {
        "profile_name": "operator",
        "cwd": str(tmp_path),
        "objective_text": "Ship the smallest verified slice",
        "default_agents": ["codex_acp"],
        "harness_instructions": "Stay within repo truth.",
        "success_criteria": ["add verification"],
        "max_iterations": 12,
        "run_mode": RunMode.ATTACHED.value,
        "involvement_level": InvolvementLevel.AUTO.value,
        "message_window": 7,
        "overrides": [],
    }


def test_project_create_remains_explicit_profile_mutation(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(settings.data_dir))
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "project",
            "create",
            "alpha",
            "--local",
            "--cwd",
            str(tmp_path / "workspace"),
            "--agent",
            "codex_acp",
            "--objective",
            "Ship the smallest verified slice",
            "--harness",
            "Stay within repo truth.",
            "--success-criterion",
            "add focused verification",
            "--max-iterations",
            "9",
            "--involvement",
            "approval_heavy",
        ],
    )

    assert result.exit_code == 0
    expected_path = settings.data_dir / "profiles" / "alpha.yaml"
    assert result.stdout == f"Wrote project profile: {expected_path}\n"

    stored = load_project_profile(settings, "alpha")
    assert stored.name == "alpha"
    assert stored.cwd == tmp_path / "workspace"
    assert stored.default_agents == ["codex_acp"]
    assert stored.default_objective == "Ship the smallest verified slice"
    assert stored.default_harness_instructions == "Stay within repo truth."
    assert stored.default_success_criteria == ["add focused verification"]
    assert stored.default_max_iterations == 9
    assert stored.default_involvement_level is InvolvementLevel.APPROVAL_HEAVY

    json_result = runner.invoke(
        app,
        [
            "project",
            "create",
            "beta",
            "--json",
        ],
    )

    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload["profile_scope"] == "committed"
    assert payload["profile"]["name"] == "beta"
    assert payload["profile_path"] == str(tmp_path / "operator-profiles" / "beta.yaml")


def test_project_dashboard_is_project_scoped_entry_surface(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(settings.data_dir))
    monkeypatch.chdir(tmp_path)
    write_project_profile(
        settings,
        ProjectProfile(name="operator", cwd=tmp_path, default_agents=["codex_acp"]),
        local=True,
    )

    captured: dict[str, object] = {}

    async def _fake_dashboard_async(
        name: str | None, once: bool, json_mode: bool, poll_interval: float
    ) -> None:
        captured["name"] = name
        captured["once"] = once
        captured["json_mode"] = json_mode
        captured["poll_interval"] = poll_interval

    monkeypatch.setattr(
        "agent_operator.cli.commands.project.project_dashboard_async",
        _fake_dashboard_async,
    )

    result = runner.invoke(
        app,
        ["project", "dashboard", "operator", "--once", "--json", "--poll-interval", "0.25"],
    )

    assert result.exit_code == 0
    assert result.stdout == ""
    assert captured == {
        "name": "operator",
        "once": True,
        "json_mode": True,
        "poll_interval": 0.25,
    }
