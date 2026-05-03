from __future__ import annotations

import importlib.util
from pathlib import Path

LIVE_TEST_PATH = Path(__file__).with_name("test_live_codex_acp.py")
SPEC = importlib.util.spec_from_file_location("test_live_codex_acp_module", LIVE_TEST_PATH)
assert SPEC is not None
LIVE_TEST_MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(LIVE_TEST_MODULE)
_codex_acp_readiness_command = LIVE_TEST_MODULE._codex_acp_readiness_command
_codex_acp_live_timeout_seconds = LIVE_TEST_MODULE._codex_acp_live_timeout_seconds


def test_codex_acp_readiness_command_ignores_npx_separator() -> None:
    """Catches passing readiness `--help` through the ACP stdio separator."""

    command = _codex_acp_readiness_command("npx @zed-industries/codex-acp --")

    assert command == ["npx", "@zed-industries/codex-acp", "--help"]


def test_codex_acp_readiness_command_appends_help_to_direct_executable() -> None:
    """Catches dropping direct executable readiness checks."""

    command = _codex_acp_readiness_command("/tmp/codex-acp")

    assert command == ["/tmp/codex-acp", "--help"]


def test_codex_acp_live_timeout_defaults_to_bounded_value(monkeypatch) -> None:
    """Catches live ACP roundtrip losing its bounded timeout."""

    monkeypatch.delenv("OPERATOR_CODEX_ACP_LIVE_TIMEOUT_SECONDS", raising=False)

    assert _codex_acp_live_timeout_seconds() == 120
