from __future__ import annotations

from pathlib import Path

CLI_DIR = Path(__file__).resolve().parents[1] / "src" / "agent_operator" / "cli"


def test_control_workflow_modules_stay_under_500_lines() -> None:
    """ADR 0119: the control workflow split stays under the CLI line budget."""
    targets = {
        "control.py": CLI_DIR / "workflows" / "control.py",
        "control_converse.py": CLI_DIR / "workflows" / "control_converse.py",
    }
    line_counts = {
        name: sum(1 for _ in path.open(encoding="utf-8")) for name, path in targets.items()
    }

    for name, count in line_counts.items():
        assert count < 500, f"{name} regressed to {count} lines"
