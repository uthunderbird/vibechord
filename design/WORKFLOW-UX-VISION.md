# Workflow UX Vision

## Purpose

This document specifies the design of `operator`'s workspace management, project lifecycle, and external integration model. It covers the three-level mental model, what persists to git vs. stays local, multi-project fleet discovery, the history ledger, and PM tool integration.

The core CLI/workflow implementation slices for the non-PM portion of this vision are tracked in:

- [ADR 0094](./adr/0094-run-init-project-create-workflow-and-project-profile-lifecycle.md)
- [ADR 0095](./adr/0095-operation-reference-resolution-and-command-addressing-contract.md)
- [ADR 0098](./adr/0098-history-ledger-and-history-command-contract.md)

This is a design specification. Implementation technology choices and migration paths are noted but not adjudicated here.

---

## Mental Model: Three Levels

```
fleet view          ← command center; spans all configured project roots
  └─ project        ← git repo with operator-profile.yaml
       └─ operation ← iterative goal-directed attempt
```

**"Workspace" as a user-visible concept is not introduced.** The fleet view *is* the workspace. There are no workspace objects, no `workspace create` / `workspace delete` commands.

A **project** is a git repository that has an `operator-profile.yaml` at its root. A **project root** is a directory tree that operator scans to discover projects. The **fleet view** aggregates active operations across all configured project roots.

---

## What's Committed vs. What Stays Internal

| Artifact | Location | Committed? | Purpose |
|----------|----------|-----------|---------|
| `operator-profile.yaml` | `<git-root>/` | **Yes** | Project defaults: agents, harness, success criteria, run mode, ticket reporting config |
| `operator-history.jsonl` | `<git-root>/` | **Yes (default-on, opt-out)** | Ledger of past operations: ID, goal summary, start, end, status, stop reason |
| `operator-profiles/` | `<git-root>/` | **Yes** | Named committed profile variants for this project |
| `.operator/` | `<git-root>/` | **No — gitignored** | All runtime state: operation runs, sessions, logs, wakeups, background state |
| `.operator/profiles/` | `<git-root>/.operator/` | **No** | Local-only profile variants (per-developer or per-machine overrides) |
| `~/.operator/config.yaml` | user home | **No** | Global user config: project roots to scan, PM provider credentials, global defaults |

### Rules

**`operator-profile.yaml`** is the project's committed default. Every developer who clones the repo gets the same operator behavior. It is analogous to `.editorconfig` — committed alongside the code, versioned with it.

**`operator-history.jsonl`** is the project's committed operation ledger. It is append-only: new entries are added as operations reach terminal states. Concurrent git merges do not conflict because appends don't overlap with prior lines. It can be disabled per-project: `history_ledger: false` in `operator-profile.yaml`.

**Named committed profiles** (`operator-profiles/*.yaml`) are reusable run configurations committed to the repo. Example: `operator-profiles/high-effort.yaml` or `operator-profiles/codex-only.yaml`. They are available to all developers on the project and can be selected at run time with `--profile high-effort`.

**Local profiles** (`.operator/profiles/*.yaml`) are per-developer or per-machine overrides. They are gitignored and never shared. They override committed profiles on the local machine only.

**`.operator/`** contains all ephemeral runtime state. It is gitignored by default. It is analogous to `.next/` or `node_modules/` — a machine-local build artifact, not source.

### Profile Precedence

```
CLI flags                   ← highest priority
local profile (.operator/profiles/)
named committed profile (operator-profiles/)
operator-profile.yaml default
global defaults (~/.operator/config.yaml)  ← lowest priority
```

**Merge semantics for list fields:** CLI flag precedence for list fields (`--agent`, `--success-criterion`) is replacement semantics — specifying any value via CLI flag replaces the profile's list entirely. To combine profile defaults with additional CLI values, re-specify the full desired list. For example: if the profile has `default_agents: [claude_acp, codex_acp]`, running with `--agent claude_acp` results in only `[claude_acp]`, not `[claude_acp, codex_acp, claude_acp]`.

### First-Time Setup

`operator init` run in a git repo:
1. Creates `operator-profile.yaml` with project-appropriate defaults
2. Creates `operator-profiles/` directory
3. Adds `.operator/` to `.gitignore`
4. Adds `operator-history.jsonl` to git tracking (opt-in message)

If `operator-profile.yaml` already exists, `operator init` reports "project already configured" and exits without overwriting.

---

## Operator History Ledger

File: `operator-history.jsonl` at the git root. One JSONL record per operation completion.

```jsonl
{"op_id": "op-abc123", "goal": "Add OAuth support to auth module", "profile": "default", "started": "2026-04-03T10:00:00Z", "ended": "2026-04-03T11:23:00Z", "status": "completed", "stop_reason": "explicit_success"}
{"op_id": "op-def456", "goal": "Fix flaky tests in test_auth.py", "profile": "default", "started": "2026-04-03T14:00:00Z", "ended": "2026-04-03T14:47:00Z", "status": "failed", "stop_reason": "iteration_limit_exhausted"}
{"op_id": "op-ghi789", "goal": "Fix: auth tokens expire silently", "profile": "default", "started": "2026-04-03T15:00:00Z", "ended": "2026-04-03T16:12:00Z", "status": "completed", "stop_reason": "explicit_success", "ticket": {"provider": "github_issues", "project_key": "my-org/my-repo", "ticket_id": "234", "url": "https://github.com/my-org/my-repo/issues/234", "title": "Fix: auth tokens expire silently"}}
```

The `ticket` field, when present, serializes `provider`, `project_key`, `ticket_id`, `url`, and `title` from the `ExternalTicketLink` model. The `reported` field is an operational state field and is excluded from the ledger record.

**Fields:**

| Field | Description |
|-------|-------------|
| `op_id` | Operation identifier |
| `goal` | Goal text summary (truncated to ~200 chars if longer) |
| `profile` | Profile name used for this run |
| `started` | ISO 8601 UTC timestamp of run start |
| `ended` | ISO 8601 UTC timestamp of terminal state |
| `status` | `completed`, `failed`, or `cancelled` |
| `stop_reason` | The specific stop reason from the domain model (e.g., `explicit_success`, `iteration_limit_exhausted`, `user_cancelled`) |
| `ticket` | Optional — `ExternalTicketLink` summary if the operation was sourced from a PM ticket |

**Write point:** the ledger append happens when an operation transitions to a terminal state, not at run start. If an operation is interrupted mid-run and resumed, it produces one ledger entry when it eventually terminates.

**Opt-out:** set `history_ledger: false` in `operator-profile.yaml` to disable. The file is simply not written.

---

## Multi-Project Fleet View

### Discovery Model

The fleet view aggregates operations from all configured project roots. Roots are configured in `~/.operator/config.yaml`:

```yaml
# ~/.operator/config.yaml
project_roots:
  - ~/Projects/
  - ~/work/client-a/
```

Operator scans each root for directories containing a `.operator/` data dir or an `operator-profile.yaml`. Scan depth is configurable (default: 4 levels). Discovered projects and their active operations are shown in the fleet view.

### First-Run UX

If `operator fleet` is invoked with no roots configured and no local `.operator/` dir, operator auto-discovers projects by scanning under `~/` (depth-limited to 3 levels) and prompts:

```
Found 3 projects with operator data:
  ~/Projects/my-repo
  ~/Projects/other-repo
  ~/work/client-a/project

Add them to your fleet view? [Y/n]
```

Accepting writes the discovered roots to `~/.operator/config.yaml`. The user can edit this file at any time to add or remove roots.

### Filtering

The fleet view `/` filter (specified in TUI-UX-VISION.md) filters by project name, operation status, and agent type. No separate workspace grouping concept is needed — filtering handles "show me only client-A's operations."

---

## PM Tool Integration

### Design Principles

1. **One-way intake:** a ticket becomes a goal. Operator does not write back to the PM system mid-operation — only on terminal state.
2. **One-way reporting:** when an operation reaches a terminal state, operator optionally posts a summary back to the source ticket.
3. **Native for GitHub Issues:** the only natively implemented provider. GitHub is developer-native, has a simple REST API, and is where the project code typically already lives.
4. **Hooks for everything else:** Linear, Jira, Trello, and any other PM system receive a webhook payload. The user writes a small integration script or uses a pre-built template. Operator does not maintain adapters for every PM tool.

### Issue Intake

```bash
# GitHub Issues — native
operator run --from github:owner/repo#123
operator run --from https://github.com/owner/repo/issues/123

# Any other provider — URL or shorthand
operator run --from linear:ABC-456
operator run --from jira:PROJ-789
```

When `--from` is used:
- Operator fetches the ticket title and description (for native providers; for hook providers, the user's intake hook script runs)
- The fetched text becomes the operation goal unless `--goal` is also specified
- If both `--from` and `--goal` are specified, `--goal` overrides and the ticket provides context only
- The `ExternalTicketLink` is stored on the operation state

### Result Reporting

Reporting behavior is configured per-project in `operator-profile.yaml`:

```yaml
# operator-profile.yaml
ticket_reporting:
  on_success: comment_and_close   # post summary comment; close/resolve the ticket
  on_failure: comment_only        # post summary comment including stop_reason
  on_cancelled: silent            # no action
  webhook_url: https://hooks.example.com/operator  # optional; used for non-native providers
```

For GitHub Issues (native):
- `comment_and_close`: posts a comment with the operation summary and closes the issue. **Note:** this is an irreversible external action. Configure deliberately — closing a ticket may affect linked PRs or ongoing discussion. When `comment_and_close` is configured, operator creates a non-blocking attention (`[!N]`) with the intended comment text before posting; the operation auto-proceeds after 1 planning cycle if the attention is not dismissed, giving the user a brief review window.
- `comment_only`: posts a comment with the operation summary and stop reason
- `silent`: no action

For all other providers: if `webhook_url` is configured, operator POSTs the hook payload (see below) on terminal state.

### ExternalTicketLink Data Model

```python
class ExternalTicketLink(BaseModel):
    provider: Literal["github_issues", "linear", "jira", "trello", "custom"]
    project_key: str        # "owner/repo" for GitHub; project key for Linear/Jira; board ID for Trello
    ticket_id: str          # "123" for GitHub; "ABC-456" for Linear; etc.
    url: str | None = None  # canonical URL for display in trace and TUI
    title: str | None = None  # fetched at intake time, stored for display
    reported: bool = False  # whether result reporting has been sent (prevents duplicate posts on resume)
```

This is a typed field on `OperationState` (or `OperationGoal`), not embedded in the goal text string.

**Reporting failure handling:** If result reporting fails at terminal state (e.g., GitHub API unavailable), a non-blocking attention (`[!N]`) is created with the failure reason and the text of the intended report. The `reported` field remains `false`. The user can retry by resolving the attention or by running `operator report OP --ticket` (see CLI secondary commands). The `reported` field prevents duplicate posts — a second reporting attempt checks it before posting.

### Hook Payload (versioned)

The webhook payload schema is versioned from day one to enable future changes without breaking user integrations.

```json
{
  "schema_version": "1",
  "event": "operation.completed",
  "operation_id": "op-abc123",
  "goal_summary": "Add OAuth support to auth module",
  "status": "completed",
  "stop_reason": "explicit_success",
  "ticket": {
    "provider": "linear",
    "project_key": "ABC",
    "ticket_id": "ABC-456",
    "url": "https://linear.app/team/issue/ABC-456",
    "title": "Implement OAuth2 for auth module"
  },
  "started_at": "2026-04-03T10:00:00Z",
  "ended_at": "2026-04-03T11:23:00Z"
}
```

### Credentials

PM provider credentials (GitHub PAT, Linear API key, etc.) live in `~/.operator/config.yaml` only. They are never written to `operator-profile.yaml`, which is committed to git.

```yaml
# ~/.operator/config.yaml
providers:
  github:
    token: ghp_...
  linear:
    api_key: lin_...
```

---

## User Workflow — Before and After

### Before (current)

The user `cd`s to a repo, runs `operator run --goal "..."`, and checks status with `operator fleet` or `operator watch`. Operations are scoped to the current directory. No cross-project visibility. No persistent history. No connection to issue trackers.

### After

**Morning triage:** Open terminal anywhere. Run `operator fleet`. See all active operations across all configured projects — status glyphs, blocking attention badges, iteration counts. Answer a blocking attention in `~/Projects/auth-service` without changing directories.

**Starting work from an issue:**
```bash
operator run --from github:my-org/my-repo#234
```
Operator fetches "Fix: auth tokens expire silently", shows you the goal, starts the operation. When the operation completes, posts a summary comment to the issue and closes it.

**Code review context:** Reviewer opens `operator-history.jsonl` in the diff. Sees that yesterday's commit followed three failed operations (iteration_limit_exhausted twice, then explicit_success). The history is there without reading full logs.

**New teammate onboarding:**
```bash
git clone https://github.com/my-org/my-repo
cd my-repo
operator init
# → "Project already configured (operator-profile.yaml found)"
# → ".operator/ added to .gitignore"
operator run
# → uses committed profile defaults immediately
```

---

## Known Open Items

- `operator init` command — creates `operator-profile.yaml`, updates `.gitignore`, optional ledger setup
- `operator project create [NAME] [--local]` — writes to `operator-profiles/` (committed) vs. `.operator/profiles/` (local). *Note: canonical name is `operator project create`, consistent with the `project` subgroup in CLI-UX-VISION.md. The `--local` flag writes to `.operator/profiles/` instead of `operator-profiles/`.*
- Fleet view first-run auto-discovery prompt
- GitHub Issues adapter — OAuth or PAT credential flow, issue fetch, comment + close on completion
- Hook payload schema documentation page
- History ledger write point in the operator loop — on terminal state transition in `OperatorService`
- `--from URL` URL parsing for GitHub, Linear, and custom providers
