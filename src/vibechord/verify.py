"""Local verification command runner."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from vibechord.release_checks import run_release_checks


@dataclass(frozen=True)
class VerificationRun:
    """Summary of a verification command family."""

    tier: str
    commands: tuple[tuple[str, ...], ...]
    return_code: int


def commands_for(tier: str) -> tuple[tuple[str, ...], ...]:
    """Return concrete local commands for a verification tier."""

    if tier == "fast":
        return (("uv", "run", "ruff", "check", "."), ("uv", "run", "mypy", "."))
    if tier == "focused":
        return (
            ("uv", "run", "pytest", "tests/test_core.py", "tests/test_delivery.py"),
        )
    if tier == "full":
        return (
            ("uv", "run", "ruff", "check", "."),
            ("uv", "run", "mypy", "."),
            ("uv", "run", "pytest"),
        )
    raise ValueError(f"unknown verification tier: {tier}")


def run_verification(tier: str, root: Path) -> VerificationRun:
    """Run one verification tier and return the aggregate result."""

    commands = commands_for(tier)
    for command in commands:
        completed = subprocess.run(command, cwd=root, check=False)  # noqa: S603
        if completed.returncode != 0:
            return VerificationRun(tier, commands, completed.returncode)
    if tier == "full":
        release_checks = run_release_checks(root)
        if not release_checks.passed:
            for message in release_checks.messages:
                print(f"release-check failed: {message}", file=sys.stderr)
            return VerificationRun(tier, commands, 1)
    return VerificationRun(tier, commands, 0)


def main(argv: list[str] | None = None) -> int:
    """Run verification as a standalone module."""

    args = argv or sys.argv[1:]
    tier = args[0] if args else "full"
    return run_verification(tier, Path.cwd()).return_code


if __name__ == "__main__":
    raise SystemExit(main())
