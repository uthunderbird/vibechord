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
    }
    line_counts = {
        name: sum(1 for _ in path.open(encoding="utf-8")) for name, path in targets.items()
    }

    for name, count in line_counts.items():
        assert count < 500, f"{name} regressed to {count} lines"
