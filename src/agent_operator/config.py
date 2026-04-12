from __future__ import annotations

from pathlib import Path
from typing import Literal

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
