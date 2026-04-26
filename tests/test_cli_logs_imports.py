import agent_operator.cli.main as cli_main
from agent_operator.cli.helpers import logs as log_helpers
from agent_operator.runtime import iter_claude_log_events, iter_codex_log_events


def test_cli_log_helpers_reexport_runtime_follow_iterators() -> None:
    assert log_helpers.iter_claude_log_events is iter_claude_log_events
    assert log_helpers.iter_codex_log_events is iter_codex_log_events


def test_cli_main_imports_cleanly() -> None:
    assert cli_main.app is not None
