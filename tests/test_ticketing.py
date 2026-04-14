from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from agent_operator.application.commands.operation_attention import OperationAttentionCoordinator
from agent_operator.application.ticketing import (
    TicketIntakeService,
    TicketReportingService,
    parse_ticket_ref,
)
from agent_operator.config import GlobalGithubProviderConfig, GlobalProviderConfig, GlobalUserConfig
from agent_operator.domain import (
    ExternalTicketLink,
    OperationGoal,
    OperationOutcome,
    OperationState,
    OperationStatus,
    ProjectProfile,
    TicketReportingConfig,
)
from agent_operator.runtime import FileOperationStore


def test_parse_ticket_ref_supports_github_refs_and_urls() -> None:
    ref = parse_ticket_ref("github:owner/repo#123")
    url = parse_ticket_ref("https://github.com/owner/repo/issues/123")

    assert ref.provider == "github_issues"
    assert ref.project_key == "owner/repo"
    assert ref.ticket_id == "123"
    assert url.url == "https://github.com/owner/repo/issues/123"


@pytest.mark.anyio
async def test_ticket_intake_fetches_github_issue_goal() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer ghp_test"
        return httpx.Response(
            200,
            json={
                "title": "Fix the failing check",
                "body": "Reproduce and patch the regression.",
                "html_url": "https://github.com/owner/repo/issues/123",
            },
        )

    service = TicketIntakeService(
        global_config=GlobalUserConfig(
            providers=GlobalProviderConfig(github=GlobalGithubProviderConfig(token="ghp_test"))
        ),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    result = await service.resolve("github:owner/repo#123", profile=None)

    assert result.ticket.title == "Fix the failing check"
    assert result.goal_text == "Fix the failing check\n\nReproduce and patch the regression."


@pytest.mark.anyio
async def test_ticket_intake_runs_hook_for_non_native_provider(tmp_path: Path) -> None:
    hook = tmp_path / "intake-hook.sh"
    hook.write_text("#!/bin/sh\nprintf 'Hook goal for %s\\n' \"$1\"\n", encoding="utf-8")
    hook.chmod(0o755)
    profile = ProjectProfile(
        name="demo",
        ticket_reporting=TicketReportingConfig(intake_hook=hook),
    )
    service = TicketIntakeService(global_config=GlobalUserConfig())

    result = await service.resolve("linear:ABC-456", profile=profile)

    assert result.ticket.provider == "linear"
    assert result.goal_text == "Hook goal for linear:ABC-456"


@pytest.mark.anyio
async def test_ticket_reporting_posts_comment_and_marks_ticket_reported(tmp_path: Path) -> None:
    requests: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, str(request.url)))
        return httpx.Response(200, json={})

    store = FileOperationStore(tmp_path / "operations")
    state = OperationState(
        operation_id="op-1",
        goal=OperationGoal(
            objective="Close the issue.",
            metadata={
                "ticket_reporting": {
                    "on_success": "comment_and_close",
                    "on_failure": "silent",
                    "on_cancelled": "silent",
                }
            },
            external_ticket=ExternalTicketLink(
                provider="github_issues",
                project_key="owner/repo",
                ticket_id="123",
                title="Close the issue",
            ),
        ),
    )
    outcome = OperationOutcome(
        operation_id="op-1",
        status=OperationStatus.COMPLETED,
        summary="Completed cleanly.",
    )
    service = TicketReportingService(
        store=store,
        global_config=GlobalUserConfig(
            providers=GlobalProviderConfig(github=GlobalGithubProviderConfig(token="ghp_test"))
        ),
        attention_coordinator=OperationAttentionCoordinator(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    changed = await service.report_terminal_state(state, outcome)

    assert changed is True
    assert state.goal.external_ticket is not None
    assert state.goal.external_ticket.reported is True
    assert requests == [
        ("POST", "https://api.github.com/repos/owner/repo/issues/123/comments"),
        ("PATCH", "https://api.github.com/repos/owner/repo/issues/123"),
    ]


@pytest.mark.anyio
async def test_ticket_reporting_skips_duplicate_post_when_already_reported(tmp_path: Path) -> None:
    store = FileOperationStore(tmp_path / "operations")
    state = OperationState(
        operation_id="op-1",
        goal=OperationGoal(
            objective="Close the issue.",
            metadata={"ticket_reporting": {"on_success": "comment_only"}},
            external_ticket=ExternalTicketLink(
                provider="github_issues",
                project_key="owner/repo",
                ticket_id="123",
                reported=True,
            ),
        ),
    )
    outcome = OperationOutcome(
        operation_id="op-1",
        status=OperationStatus.COMPLETED,
        summary="Completed cleanly.",
    )
    service = TicketReportingService(
        store=store,
        global_config=GlobalUserConfig(),
        attention_coordinator=OperationAttentionCoordinator(),
    )

    changed = await service.report_terminal_state(state, outcome)

    assert changed is False


@pytest.mark.anyio
async def test_ticket_reporting_failure_creates_non_blocking_attention(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "boom"})

    store = FileOperationStore(tmp_path / "operations")
    state = OperationState(
        operation_id="op-1",
        goal=OperationGoal(
            objective="Close the issue.",
            metadata={"ticket_reporting": {"on_success": "comment_only"}},
            external_ticket=ExternalTicketLink(
                provider="github_issues",
                project_key="owner/repo",
                ticket_id="123",
            ),
        ),
    )
    outcome = OperationOutcome(
        operation_id="op-1",
        status=OperationStatus.COMPLETED,
        summary="Completed cleanly.",
    )
    service = TicketReportingService(
        store=store,
        global_config=GlobalUserConfig(
            providers=GlobalProviderConfig(github=GlobalGithubProviderConfig(token="ghp_test"))
        ),
        attention_coordinator=OperationAttentionCoordinator(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    changed = await service.report_terminal_state(state, outcome)

    assert changed is False
    assert state.goal.external_ticket is not None
    assert state.goal.external_ticket.reported is False
    assert len(state.attention_requests) == 2
    assert all(item.blocking is False for item in state.attention_requests)
