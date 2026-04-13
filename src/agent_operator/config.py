from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenAIProviderSettings(BaseModel):
    model: str = "gpt-4.1"
    base_url: str = "https://api.openai.com/v1"
    api_key: str | None = None
    timeout_seconds: float = 1800.0


class CodexBrainSettings(BaseModel):
    model: str = "gpt-5.4"
    base_url: str = "https://chatgpt.com/backend-api/codex/responses"
    originator: str = "agent_operator"
    reasoning_effort: Literal["low", "medium", "high"] = "low"
    timeout_seconds: float = 1800.0


class ClaudeAdapterSettings(BaseModel):
    command: str = "claude"
    model: str = "claude-sonnet-4-6"
    effort: Literal["low", "medium", "high", "max"] = "low"
    permission_mode: str = "default"
    setting_sources: str = "local"
    no_session_persistence: bool = True
    working_directory: Path = Field(default_factory=Path.cwd)


class ClaudeAcpAdapterSettings(BaseModel):
    command: str = "npx @agentclientprotocol/claude-agent-acp"
    model: str | None = None
    effort: Literal["none", "low", "medium", "high", "max"] | None = None
    permission_mode: str | None = "bypassPermissions"
    timeout_seconds: float | None = None
    mcp_servers: list[dict[str, object]] = Field(default_factory=list)
    substrate_backend: Literal["bespoke", "sdk"] = "sdk"
    stdio_limit_bytes: int = 1_048_576
    working_directory: Path = Field(default_factory=Path.cwd)


class CodexAcpAdapterSettings(BaseModel):
    command: str = "codex-acp"
    model: str | None = None
    reasoning_effort: Literal["low", "medium", "high", "xhigh"] | None = None
    approval_policy: Literal["untrusted", "on-request", "never"] | None = None
    sandbox_mode: Literal["read-only", "workspace-write", "danger-full-access"] | None = None
    timeout_seconds: float | None = None
    mcp_servers: list[dict[str, object]] = Field(default_factory=list)
    substrate_backend: Literal["bespoke", "sdk"] = "bespoke"
    stdio_limit_bytes: int = 1_048_576
    working_directory: Path = Field(default_factory=Path.cwd)


class OpencodeAcpAdapterSettings(BaseModel):
    command: str = "opencode acp"
    model: str | None = None
    timeout_seconds: float | None = None
    mcp_servers: list[dict[str, object]] = Field(default_factory=list)
    substrate_backend: Literal["bespoke", "sdk"] = "bespoke"
    stdio_limit_bytes: int = 1_048_576
    working_directory: Path = Field(default_factory=Path.cwd)


class GlobalUserDefaults(BaseModel):
    involvement_level: str | None = None
    brain_model: str | None = None
    message_window: int | None = Field(default=None, ge=0)


class GlobalGithubProviderConfig(BaseModel):
    token: str | None = None


class GlobalProviderConfig(BaseModel):
    github: GlobalGithubProviderConfig = Field(default_factory=GlobalGithubProviderConfig)


class GlobalUserConfig(BaseModel):
    project_roots: list[Path] = Field(default_factory=list)
    defaults: GlobalUserDefaults = Field(default_factory=GlobalUserDefaults)
    providers: GlobalProviderConfig = Field(default_factory=GlobalProviderConfig)


def global_config_path() -> Path:
    """Return the user-level operator config path.

    Returns:
        Canonical `~/.operator/config.yaml` path, or the override from
        `OPERATOR_GLOBAL_CONFIG` when provided for tests and tooling.
    """

    override = os.environ.get("OPERATOR_GLOBAL_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".operator" / "config.yaml"


def load_global_config(path: Path | None = None) -> GlobalUserConfig:
    """Load optional global user config from disk.

    Args:
        path: Explicit config path override.

    Returns:
        Parsed global config, or an empty config when the file is absent.
    """

    candidate = (path or global_config_path()).expanduser()
    if not candidate.exists():
        return GlobalUserConfig()
    payload = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise RuntimeError(f"Global config {candidate} must deserialize to a mapping.")
    return GlobalUserConfig.model_validate(payload)


def write_global_config(config: GlobalUserConfig, path: Path | None = None) -> Path:
    """Persist global user config to disk.

    Args:
        config: Global config payload to write.
        path: Explicit config path override.

    Returns:
        The path written to disk.
    """

    candidate = (path or global_config_path()).expanduser()
    candidate.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump(mode="json", exclude_none=True)
    candidate.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return candidate


def redacted_global_config_payload(config: GlobalUserConfig) -> dict[str, object]:
    """Return a JSON-safe global config payload with secret values redacted."""

    payload = config.model_dump(mode="json", exclude_none=True)
    providers = payload.get("providers")
    if not isinstance(providers, dict):
        return payload
    github = providers.get("github")
    if isinstance(github, dict) and isinstance(github.get("token"), str):
        github["token"] = "[REDACTED]"
    return payload


def ensure_global_config_exists(path: Path | None = None) -> Path:
    """Create an empty global config file when absent and return its path."""

    candidate = (path or global_config_path()).expanduser()
    if candidate.exists():
        return candidate
    write_global_config(GlobalUserConfig(), candidate)
    return candidate


def open_global_config_in_editor(path: Path | None = None, *, editor: str | None = None) -> Path:
    """Open the global config in the configured editor.

    Args:
        path: Explicit config path override.
        editor: Explicit editor override. Defaults to `$EDITOR`.

    Returns:
        The config path opened in the editor.
    """

    candidate = ensure_global_config_exists(path)
    selected_editor = editor or os.environ.get("EDITOR")
    if not selected_editor:
        raise RuntimeError("$EDITOR is not set.")
    command = [*shlex.split(selected_editor), str(candidate)]
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Editor exited with status {completed.returncode}.")
    return candidate


def add_global_project_root(root: Path, path: Path | None = None) -> tuple[GlobalUserConfig, bool]:
    """Append a project root to global config when it is not already present."""

    config = load_global_config(path)
    normalized = root.expanduser().resolve()
    if normalized not in config.project_roots:
        config.project_roots.append(normalized)
        write_global_config(config, path)
        return config, True
    return config, False


def apply_global_user_defaults(
    settings: OperatorSettings,
    global_config: GlobalUserConfig,
) -> OperatorSettings:
    """Apply global user defaults to runtime settings without overriding env/config input.

    Args:
        settings: Runtime settings assembled from environment and direct initialization.
        global_config: Parsed global config payload.

    Returns:
        The mutated `settings` instance for fluent call sites.
    """

    brain_model = global_config.defaults.brain_model
    if brain_model is not None:
        if (
            settings.brain_provider == "openai_codex"
            and "codex_brain" not in settings.model_fields_set
        ):
            settings.codex_brain.model = brain_model
        if settings.brain_provider == "openai" and "openai" not in settings.model_fields_set:
            settings.openai.model = brain_model
    return settings


class OperatorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPERATOR_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    data_dir: Path = Path(".operator")
    brain_provider: str = "openai_codex"
    default_allowed_agents: list[str] = Field(default_factory=lambda: ["claude_acp"])
    openai: OpenAIProviderSettings = Field(default_factory=OpenAIProviderSettings)
    codex_brain: CodexBrainSettings = Field(default_factory=CodexBrainSettings)
    claude: ClaudeAdapterSettings = Field(default_factory=ClaudeAdapterSettings)
    claude_acp: ClaudeAcpAdapterSettings = Field(default_factory=ClaudeAcpAdapterSettings)
    codex_acp: CodexAcpAdapterSettings = Field(default_factory=CodexAcpAdapterSettings)
    opencode_acp: OpencodeAcpAdapterSettings = Field(default_factory=OpencodeAcpAdapterSettings)
    attached_turn_timeout_minutes: int = 30
