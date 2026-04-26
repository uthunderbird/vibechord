from __future__ import annotations

from pathlib import Path

CLI_DIR = Path(__file__).resolve().parents[1] / "src" / "agent_operator" / "cli"


def test_adr_0119_split_cli_modules_stay_under_500_lines() -> None:
    """Catch split CLI tranche modules regressing above the ADR ceiling."""
    targets = {
        "operation_detail.py": CLI_DIR / "commands" / "operation_detail.py",
        "operation_detail_log.py": CLI_DIR / "commands" / "operation_detail_log.py",
        "operation_detail_session.py": CLI_DIR / "commands" / "operation_detail_session.py",
        "text.py": CLI_DIR / "rendering" / "text.py",
        "text_context.py": CLI_DIR / "rendering" / "text_context.py",
        "text_live.py": CLI_DIR / "rendering" / "text_live.py",
        "text_status.py": CLI_DIR / "rendering" / "text_status.py",
        "tui/models.py": CLI_DIR / "tui" / "models.py",
        "tui/model_types.py": CLI_DIR / "tui" / "model_types.py",
        "tui/model_attention.py": CLI_DIR / "tui" / "model_attention.py",
        "tui/model_fleet.py": CLI_DIR / "tui" / "model_fleet.py",
        "tui/model_sessions.py": CLI_DIR / "tui" / "model_sessions.py",
        "tui/model_text.py": CLI_DIR / "tui" / "model_text.py",
        "tui/model_display.py": CLI_DIR / "tui" / "model_display.py",
        "tui/model_views.py": CLI_DIR / "tui" / "model_views.py",
        "tui/rendering.py": CLI_DIR / "tui" / "rendering.py",
        "tui/rendering_lists.py": CLI_DIR / "tui" / "rendering_lists.py",
        "tui/rendering_chrome.py": CLI_DIR / "tui" / "rendering_chrome.py",
        "tui/rendering_detail.py": CLI_DIR / "tui" / "rendering_detail.py",
    }
    line_counts = {
        name: sum(1 for _ in path.open(encoding="utf-8")) for name, path in targets.items()
    }

    for name, count in line_counts.items():
        assert count < 500, f"{name} regressed to {count} lines"
