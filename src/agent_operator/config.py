from __future__ import annotations

import os
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
