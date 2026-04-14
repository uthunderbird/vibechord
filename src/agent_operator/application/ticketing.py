from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from agent_operator.application.commands.operation_attention import OperationAttentionCoordinator
from agent_operator.config import GlobalUserConfig
from agent_operator.domain import (
    AttentionType,
    CommandTargetScope,
    ExternalTicketLink,
    OperationOutcome,
    OperationState,
    OperationStatus,
    ProjectProfile,
)
from agent_operator.protocols import OperationStore


def parse_ticket_ref(ticket_ref: str) -> ExternalTicketLink:
    """Parse a supported ticket reference into a typed external ticket link."""

    raw = ticket_ref.strip()
    if raw.startswith("github:"):
        body = raw.removeprefix("github:")
        if "#" not in body or "/" not in body:
            raise RuntimeError(f"Unsupported GitHub ticket reference: {ticket_ref!r}.")
        project_key, ticket_id = body.split("#", 1)
        return ExternalTicketLink(
            provider="github_issues",
            project_key=project_key,
            ticket_id=ticket_id,
            url=f"https://github.com/{project_key}/issues/{ticket_id}",
        )
    if raw.startswith("linear:"):
        return ExternalTicketLink(
            provider="linear",
            project_key="linear",
            ticket_id=raw.removeprefix("linear:"),
        )
    if raw.startswith("jira:"):
        ticket_id = raw.removeprefix("jira:")
        project_key = ticket_id.split("-", 1)[0]
        return ExternalTicketLink(
            provider="jira",
            project_key=project_key,
            ticket_id=ticket_id,
        )
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.netloc == "github.com":
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 4 and parts[2] == "issues":
            project_key = f"{parts[0]}/{parts[1]}"
            ticket_id = parts[3]
            return ExternalTicketLink(
                provider="github_issues",
                project_key=project_key,
                ticket_id=ticket_id,
                url=raw,
            )
    raise RuntimeError(f"Unsupported ticket reference: {ticket_ref!r}.")


@dataclass(slots=True)
class TicketIntakeResult:
    ticket: ExternalTicketLink
    goal_text: str


class TicketIntakeService:
    """Resolve ticket references into operation goal text and ticket metadata."""

    def __init__(
        self,
        *,
        global_config: GlobalUserConfig,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._global_config = global_config
        self._client = client

    async def resolve(
        self,
        ticket_ref: str,
        *,
        profile: ProjectProfile | None,
    ) -> TicketIntakeResult:
        ticket = parse_ticket_ref(ticket_ref)
        if ticket.provider == "github_issues":
            title, body = await self._fetch_github_issue(ticket)
            ticket.title = title
            goal_text = title if not body else f"{title}\n\n{body}"
            return TicketIntakeResult(ticket=ticket, goal_text=goal_text)
        hook_path = profile.ticket_reporting.intake_hook if profile is not None else None
        if hook_path is None:
            raise RuntimeError(
                f"No intake hook is configured for {ticket.provider!r} ticket intake."
            )
        goal_text = self._run_intake_hook(hook_path, ticket_ref)
        return TicketIntakeResult(ticket=ticket, goal_text=goal_text)

    async def _fetch_github_issue(self, ticket: ExternalTicketLink) -> tuple[str, str]:
        token = self._global_config.providers.github.token
        if token is None or not token.strip():
            raise RuntimeError("Global GitHub token is required for --from github: intake.")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        url = f"https://api.github.com/repos/{ticket.project_key}/issues/{ticket.ticket_id}"
        if self._client is not None:
            response = await self._client.get(url, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
        response.raise_for_status()
        payload = response.json()
        title = str(payload.get("title") or "").strip()
        body = str(payload.get("body") or "").strip()
        html_url = payload.get("html_url")
        if isinstance(html_url, str) and html_url.strip():
            ticket.url = html_url.strip()
        if not title:
            raise RuntimeError(
                f"GitHub issue {ticket.project_key}#{ticket.ticket_id} has no title."
            )
        return title, body

    def _run_intake_hook(self, hook_path: Path, ticket_ref: str) -> str:
        completed = subprocess.run(
            [str(hook_path), ticket_ref],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            raise RuntimeError(
                stderr or f"Ticket intake hook exited with status {completed.returncode}."
            )
        goal_text = completed.stdout.strip()
        if not goal_text:
            raise RuntimeError("Ticket intake hook produced empty goal text.")
        return goal_text


class TicketReportingService:
    """Handle terminal ticket reporting and explicit retry flows."""

    def __init__(
        self,
        *,
        store: OperationStore,
        global_config: GlobalUserConfig,
        attention_coordinator: OperationAttentionCoordinator,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._store = store
        self._global_config = global_config
        self._attention_coordinator = attention_coordinator
        self._client = client

    async def report_terminal_state(
        self,
        state: OperationState,
        outcome: OperationOutcome,
    ) -> bool:
        ticket = state.goal.external_ticket
        if ticket is None or ticket.reported:
            return False
        if outcome.status not in {
            OperationStatus.COMPLETED,
            OperationStatus.FAILED,
            OperationStatus.CANCELLED,
        }:
            return False
        return await self._report(state, outcome)

    async def retry(self, state: OperationState, outcome: OperationOutcome) -> bool:
        ticket = state.goal.external_ticket
        if ticket is None:
            raise RuntimeError("Operation has no external ticket to report.")
        if ticket.reported:
            return False
        return await self._report(state, outcome)

    async def _report(self, state: OperationState, outcome: OperationOutcome) -> bool:
        config = state.goal.metadata.get("ticket_reporting")
        if not isinstance(config, dict):
            return False
        native_mode = self._mode_for_status(config, outcome.status)
        native_error: str | None = None
        draft_comment = self._build_comment(state, outcome)
        if (
            state.goal.external_ticket is not None
            and state.goal.external_ticket.provider == "github_issues"
            and native_mode != "silent"
        ):
            self._attention_coordinator.open_attention_request(
                state,
                attention_type=AttentionType.QUESTION,
                title="Ticket report draft",
                question=draft_comment,
                context_brief="Non-blocking review window before GitHub issue reporting.",
                target_scope=CommandTargetScope.OPERATION,
                target_id=state.operation_id,
                blocking=False,
            )
            try:
                await self._post_github_comment(state.goal.external_ticket, draft_comment)
                if native_mode == "comment_and_close":
                    await self._close_github_issue(state.goal.external_ticket)
            except Exception as exc:
                native_error = str(exc)
        webhook_url = config.get("webhook_url")
        webhook_error: str | None = None
        if isinstance(webhook_url, str) and webhook_url.strip():
            try:
                await self._post_webhook(
                    webhook_url.strip(),
                    self._build_webhook_payload(state, outcome),
                )
            except Exception as exc:
                webhook_error = str(exc)
        if native_error is not None or webhook_error is not None:
            detail = native_error or webhook_error or "Unknown reporting failure."
            self._attention_coordinator.open_attention_request(
                state,
                attention_type=AttentionType.QUESTION,
                title="Ticket reporting failed",
                question=detail,
                context_brief=draft_comment,
                target_scope=CommandTargetScope.OPERATION,
                target_id=state.operation_id,
                blocking=False,
            )
            await self._store.save_operation(state)
            return False
        if native_mode != "silent" or (isinstance(webhook_url, str) and webhook_url.strip()):
            assert state.goal.external_ticket is not None
            state.goal.external_ticket.reported = True
            await self._store.save_operation(state)
            return True
        return False

    def _mode_for_status(self, config: dict[str, object], status: OperationStatus) -> str:
        if status is OperationStatus.COMPLETED:
            value = config.get("on_success", "silent")
        elif status is OperationStatus.CANCELLED:
            value = config.get("on_cancelled", "silent")
        else:
            value = config.get("on_failure", "silent")
        return str(value)

    def _build_comment(self, state: OperationState, outcome: OperationOutcome) -> str:
        return "\n".join(
            [
                "operator completed this ticket-linked run.",
                "",
                f"- operation_id: {state.operation_id}",
                f"- status: {outcome.status.value}",
                f"- summary: {outcome.summary.strip()}",
            ]
        )

    def _build_webhook_payload(
        self,
        state: OperationState,
        outcome: OperationOutcome,
    ) -> dict[str, object]:
        ticket = state.goal.external_ticket
        assert ticket is not None
        return {
            "schema_version": "1",
            "event": "operation.completed",
            "operation_id": state.operation_id,
            "goal_summary": state.goal.objective_text,
            "status": outcome.status.value,
            "stop_reason": outcome.status.value,
            "ticket": {
                "provider": ticket.provider,
                "project_key": ticket.project_key,
                "ticket_id": ticket.ticket_id,
                "url": ticket.url,
                "title": ticket.title,
            },
            "started_at": (state.run_started_at or state.created_at).isoformat(),
            "ended_at": outcome.ended_at.isoformat() if outcome.ended_at is not None else None,
        }

    async def _post_github_comment(self, ticket: ExternalTicketLink, body: str) -> None:
        token = self._global_config.providers.github.token
        if token is None or not token.strip():
            raise RuntimeError("Global GitHub token is required for GitHub ticket reporting.")
        url = (
            f"https://api.github.com/repos/{ticket.project_key}/issues/{ticket.ticket_id}/comments"
        )
        await self._post_json(
            url,
            {"body": body},
            token=token,
        )

    async def _close_github_issue(self, ticket: ExternalTicketLink) -> None:
        token = self._global_config.providers.github.token
        if token is None or not token.strip():
            raise RuntimeError("Global GitHub token is required for GitHub ticket reporting.")
        url = f"https://api.github.com/repos/{ticket.project_key}/issues/{ticket.ticket_id}"
        await self._patch_json(
            url,
            {"state": "closed"},
            token=token,
        )

    async def _post_webhook(self, webhook_url: str, payload: dict[str, object]) -> None:
        if self._client is not None:
            response = await self._client.post(webhook_url, json=payload)
        else:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(webhook_url, json=payload)
        response.raise_for_status()

    async def _post_json(self, url: str, payload: dict[str, object], *, token: str) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._client is not None:
            response = await self._client.post(url, json=payload, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()

    async def _patch_json(self, url: str, payload: dict[str, object], *, token: str) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._client is not None:
            response = await self._client.patch(url, json=payload, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.patch(url, json=payload, headers=headers)
        response.raise_for_status()
