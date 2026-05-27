"""Release-readiness checks used by the full verification rail."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vibechord.harness import run_fake_harness


@dataclass(frozen=True)
class ReleaseCheckResult:
    """Result of local release-readiness checks."""

    passed: bool
    messages: tuple[str, ...]


HARNESS_WORKFLOWS = (
    "happy",
    "attention",
    "chat",
    "cancel",
    "adapter_failure",
    "agent",
)


def run_release_checks(root: Path) -> ReleaseCheckResult:
    """Run full-rail checks that are not ordinary lint/type/test commands."""

    messages: list[str] = []
    _check_fake_harness(root, messages)
    _check_verification_matrix(root, messages)
    return ReleaseCheckResult(not messages, tuple(messages))


def _check_fake_harness(root: Path, messages: list[str]) -> None:
    for workflow in HARNESS_WORKFLOWS:
        summary = run_fake_harness(root, workflow)
        if summary.status != "passed":
            messages.append(
                f"harness {workflow} failed: {summary.failure_message or 'unknown'}"
            )
        if not summary.operation_ids:
            messages.append(f"harness {workflow} did not record an operation id")
        if "VS-004" not in summary.rails_exercised:
            messages.append(f"harness {workflow} did not exercise VS-004")


def _check_verification_matrix(root: Path, messages: list[str]) -> None:
    matrix_path = root / "docs" / "verification-matrix.md"
    if not matrix_path.exists():
        messages.append("docs/verification-matrix.md is missing")
        return

    text = matrix_path.read_text(encoding="utf-8")
    required_fragments = (
        "Status: `verified`",
        "uv run vibechord verify full",
        "Public Python SDK uses shared command/query contracts",
        "MCP tools/resources/prompts/progress surface uses shared SDK contracts",
        "MCP HTTP POST/SSE transport persists and resumes events",
        "REST scoped hashed-token auth, production guard, and security headers exist",
        "TUI render/reducer/full-screen runtime",
        "Process-backed agent and brain adapters fail explicitly",
        "OpenAI Responses brain adapter maps structured decisions and failures",
        "None currently documented for the verified local release gate.",
    )
    for fragment in required_fragments:
        if fragment not in text:
            messages.append(f"verification matrix missing: {fragment}")

    for line in text.splitlines():
        if "`tests/" not in line:
            continue
        evidence = line.split("`", maxsplit=2)[1]
        if not (root / evidence).exists():
            messages.append(
                f"verification matrix references missing evidence: {evidence}"
            )

    if not (root / "docs" / "sdk.md").exists():
        messages.append("docs/sdk.md is missing")
    if not (root / "docs" / "mcp.md").exists():
        messages.append("docs/mcp.md is missing")
    if not (root / "docs" / "adapters.md").exists():
        messages.append("docs/adapters.md is missing")
