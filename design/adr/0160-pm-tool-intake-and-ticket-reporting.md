# ADR 0160: PM tool intake and ticket reporting

- Date: 2026-04-13

## Decision Status

Accepted

## Implementation Status

Partial

## Context

Operations today are always started with an explicit goal string on the command line or from a
project profile default. There is no way to source a goal from an external PM ticket, and no
mechanism for posting results back to a ticket after completion.

WORKFLOW-UX-VISION.md defines a PM integration model:

- **Issue intake:** `operator run --from github:owner/repo#123` fetches the ticket and
  populates the operation goal from it.
- **Result reporting:** on terminal state, operator optionally posts a summary back to the
  source ticket (comment, close, or silent), configured per-project in `operator-profile.yaml`.
- **Native for GitHub Issues only.** All other providers (Linear, Jira, Trello, custom) receive
  a versioned webhook payload.
- **`ExternalTicketLink`** — a typed field on operation state storing the ticket reference,
  display URL, fetched title, and `reported` flag to prevent duplicate posts on resume.

## Decision

Implement PM tool intake and terminal reporting as a two-phase addition.

### Phase 1 — ExternalTicketLink domain model and --from flag

#### `ExternalTicketLink` model

Add to `src/agent_operator/domain/`:

```python
class ExternalTicketLink(BaseModel):
    provider: Literal["github_issues", "linear", "jira", "trello", "custom"]
    project_key: str      # "owner/repo" for GitHub; project key for Linear/Jira
    ticket_id: str        # "123" for GitHub; "ABC-456" for Linear; etc.
    url: str | None = None
    title: str | None = None
    reported: bool = False
```

Add `external_ticket: ExternalTicketLink | None = None` to `OperationGoal` (or directly to
`OperationState` — place TBD during implementation based on where `goal` lives).

#### `--from` flag on `operator run`

```
operator run [--from TICKET_REF] [GOAL]
```

`TICKET_REF` formats:
- `github:owner/repo#123`
- `https://github.com/owner/repo/issues/123`
- `linear:ABC-456` (hook provider)
- `jira:PROJ-789` (hook provider)

Resolution:
1. Parse `TICKET_REF` to identify provider and ticket ID.
2. For `github_issues`: fetch issue title + body via GitHub REST API using the token from
   `~/.operator/config.yaml` (ADR 0158). Construct goal from `title + "\n\n" + body`.
3. For hook providers: run the user-configured intake hook script if present
   (`operator-profile.yaml` `intake_hook: path/to/script.sh`). The script receives the
   ticket ref as `$1` and must print the goal text to stdout.
4. Store the resolved `ExternalTicketLink` on the operation at creation.
5. If `--goal` is also given, that overrides the fetched text; the ticket provides context only.

#### Domain event

Emit `operation.ticket_linked` at operation creation when `ExternalTicketLink` is set:

```python
{
    "provider": str,
    "project_key": str,
    "ticket_id": str,
    "url": str | None,
    "title": str | None,
}
```

### Phase 2 — Terminal result reporting

#### Profile schema extension

Add `ticket_reporting` to `ProjectProfile`:

```python
class TicketReportingConfig(BaseModel):
    on_success: Literal["comment_and_close", "comment_only", "silent"] = "silent"
    on_failure: Literal["comment_only", "silent"] = "silent"
    on_cancelled: Literal["comment_only", "silent"] = "silent"
    webhook_url: str | None = None
    intake_hook: str | None = None   # path to intake script for non-native providers
```

#### Reporting logic

When an operation reaches terminal state and `state.external_ticket` is not None and
`state.external_ticket.reported is False`:

1. Determine reporting mode from `TicketReportingConfig` based on `stop_reason`.
2. For `github_issues` + `comment_and_close` or `comment_only`:
   - Before posting: create a non-blocking attention request (`[!N]`) with the draft comment
     text, giving the user a brief review window (1 planning cycle auto-proceed).
   - After auto-proceed or attention resolved: POST the comment via GitHub REST API.
   - On `comment_and_close`: close the issue via GitHub REST API.
   - Set `state.external_ticket.reported = True`.
3. For any provider with `webhook_url` configured: POST the versioned webhook payload.
4. On failure: create a non-blocking attention with the error; leave `reported = False` for
   retry on next `operator run` resume.

#### Webhook payload (v1 schema)

```json
{
  "schema_version": "1",
  "event": "operation.completed",
  "operation_id": "...",
  "goal_summary": "...",
  "status": "completed",
  "stop_reason": "explicit_success",
  "ticket": { "provider": "...", "project_key": "...", "ticket_id": "...", "url": "...", "title": "..." },
  "started_at": "...",
  "ended_at": "..."
}
```

#### `operator report OP --ticket` retry command

Manual retry trigger for when automatic reporting failed. Checks `reported` flag before
posting. Posts and sets `reported = True` on success.

## Prerequisites for resolution

### Phase 1
1. Add `ExternalTicketLink` domain model.
2. Add `external_ticket` field to `OperationGoal`/`OperationState`.
3. Add `--from` CLI flag to `operator run`.
4. Implement GitHub Issues fetcher (requires `httpx` or `aiohttp` + GitHub REST API).
5. Implement hook provider intake (subprocess call).
6. Emit `operation.ticket_linked` event; add projector slice.
7. Add `providers.github.token` to `GlobalUserConfig` (ADR 0158).

### Phase 2
8. Add `TicketReportingConfig` to `ProjectProfile`.
9. Implement reporting in the terminal-state path of the drive loop.
10. Implement `operator report OP --ticket` command.
11. Tests: GitHub intake populates goal; `--goal` overrides fetched text; reporting posts on
    success; `reported` flag prevents duplicate; failure creates attention.

## Non-goals

- Bidirectional sync (operator does not update ticket state mid-run).
- Native adapters for Linear, Jira, Trello (webhook hooks only).
- Browser OAuth flow for GitHub (PAT only in v1).

## Consequences

- Operations can be sourced from GitHub Issues without copying text.
- Terminal reports close the loop back to the PM system automatically.
- `reported` flag makes reporting safe to retry after resume — no duplicates.
- Credentials remain in `~/.operator/config.yaml` and never touch committed files.

## Related

- `src/agent_operator/domain/` — `ExternalTicketLink`
- `src/agent_operator/cli/commands/run.py` — `--from` flag
- `src/agent_operator/domain/profile.py` — `TicketReportingConfig`
- [WORKFLOW-UX-VISION.md §PM Tool Integration](../WORKFLOW-UX-VISION.md)
- [ADR 0158](./0158-global-user-config.md)
