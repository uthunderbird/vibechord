#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_command(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    """Run one release-smoke command and fail with captured context."""

    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        joined = " ".join(command)
        raise RuntimeError(f"Command failed ({completed.returncode}): {joined}\n{completed.stdout}")


def find_single(path: Path, pattern: str) -> Path:
    matches = sorted(path.glob(pattern))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {pattern!r} under {path}, found {len(matches)}.")
    return matches[0]


def verify_release_artifacts(*, keep_artifacts: Path | None = None) -> dict[str, str]:
    """Build package artifacts and smoke-test the public CLI and SDK from the wheel."""

    with tempfile.TemporaryDirectory(prefix="operator-release-smoke-") as tmp:
        work_dir = Path(tmp)
        dist_dir = work_dir / "dist"
        venv_dir = work_dir / "venv"

        run_command(
            [
                "uv",
                "build",
                "--clear",
                "--out-dir",
                str(dist_dir),
                "--no-create-gitignore",
            ],
            cwd=REPO_ROOT,
        )

        wheel = find_single(dist_dir, "agent_operator-*.whl")
        sdist = find_single(dist_dir, "agent_operator-*.tar.gz")

        run_command(["uv", "venv", str(venv_dir)], cwd=REPO_ROOT)
        run_command(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(venv_dir / "bin" / "python"),
                str(wheel),
            ],
            cwd=REPO_ROOT,
        )
        run_command([str(venv_dir / "bin" / "operator"), "--help"], cwd=REPO_ROOT)
        run_command(
            [
                str(venv_dir / "bin" / "python"),
                "-c",
                "from agent_operator import OperatorClient; print(OperatorClient.__name__)",
            ],
            cwd=REPO_ROOT,
        )

        if keep_artifacts is not None:
            keep_artifacts.mkdir(parents=True, exist_ok=True)
            shutil.copy2(wheel, keep_artifacts / wheel.name)
            shutil.copy2(sdist, keep_artifacts / sdist.name)

        return {
            "verified_at": datetime.now(UTC).isoformat(),
            "wheel": wheel.name,
            "sdist": sdist.name,
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build release artifacts and smoke-test public CLI/SDK entrypoints."
    )
    parser.add_argument(
        "--keep-artifacts",
        type=Path,
        help="Optional directory where built wheel and sdist should be copied.",
    )
    args = parser.parse_args()

    result = verify_release_artifacts(keep_artifacts=args.keep_artifacts)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
