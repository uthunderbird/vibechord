from __future__ import annotations

from pathlib import Path

import pytest

from agent_operator.cli.helpers.services import load_settings
from agent_operator.config import load_global_config
from agent_operator.domain import InvolvementLevel, ProjectProfile
from agent_operator.runtime import resolve_project_run_config


def test_load_global_config_returns_empty_config_when_file_is_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPERATOR_GLOBAL_CONFIG", str(tmp_path / "missing.yaml"))

    loaded = load_global_config()

    assert loaded.project_roots == []
    assert loaded.defaults.involvement_level is None
    assert loaded.defaults.message_window is None
    assert loaded.providers.github.token is None


def test_load_global_config_parses_defaults_roots_and_provider_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "project_roots:",
                "  - ~/Projects",
                "defaults:",
                "  involvement_level: collaborative",
                "  brain_model: gpt-5.4-mini",
                "  message_window: 9",
                "providers:",
                "  github:",
                "    token: ghp_test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPERATOR_GLOBAL_CONFIG", str(config_path))

    loaded = load_global_config()

    assert loaded.project_roots == [Path("~/Projects")]
    assert loaded.defaults.involvement_level == "collaborative"
    assert loaded.defaults.brain_model == "gpt-5.4-mini"
    assert loaded.defaults.message_window == 9
    assert loaded.providers.github.token == "ghp_test"


def test_resolve_project_run_config_uses_global_defaults_as_lowest_priority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "defaults:",
                "  involvement_level: collaborative",
                "  message_window: 8",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPERATOR_GLOBAL_CONFIG", str(config_path))

    from agent_operator.config import OperatorSettings

    settings = OperatorSettings()
    resolved = resolve_project_run_config(
        settings,
        profile=None,
        objective=None,
        harness=None,
        success_criteria=None,
        allowed_agents=None,
        max_iterations=None,
        run_mode=None,
        involvement_level=None,
    )

    assert resolved.involvement_level is InvolvementLevel.COLLABORATIVE
    assert resolved.message_window == 8


def test_resolve_project_run_config_keeps_profile_and_cli_precedence_over_global_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "defaults:",
                "  involvement_level: collaborative",
                "  message_window: 8",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPERATOR_GLOBAL_CONFIG", str(config_path))

    from agent_operator.config import OperatorSettings

    settings = OperatorSettings()
    profile = ProjectProfile(
        name="operator",
        default_involvement_level=InvolvementLevel.UNATTENDED,
        default_message_window=4,
    )
    resolved = resolve_project_run_config(
        settings,
        profile=profile,
        objective=None,
        harness=None,
        success_criteria=None,
        allowed_agents=None,
        max_iterations=None,
        run_mode=None,
        involvement_level=InvolvementLevel.APPROVAL_HEAVY,
    )

    assert resolved.involvement_level is InvolvementLevel.APPROVAL_HEAVY
    assert resolved.message_window == 4


def test_load_settings_applies_global_brain_model_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "defaults:\n  brain_model: gpt-5.4-mini\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPERATOR_GLOBAL_CONFIG", str(config_path))

    settings = load_settings()

    assert settings.codex_brain.model == "gpt-5.4-mini"
