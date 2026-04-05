# CLI UX Vision

## Purpose

This document specifies the design of the `operator` command-line interface. It covers command structure, naming conventions, output formats, the relationship between CLI and TUI, and the interaction model for all user-facing workflows.

Implementation decomposition for this vision lives in:

- [ADR 0093](./adr/0093-cli-command-taxonomy-visibility-tiers-and-default-operator-entry-behavior.md)
- [ADR 0094](./adr/0094-run-init-project-create-workflow-and-project-profile-lifecycle.md)
- [ADR 0095](./adr/0095-operation-reference-resolution-and-command-addressing-contract.md)
- [ADR 0096](./adr/0096-one-operation-control-and-summary-surface.md)
- [ADR 0097](./adr/0097-forensic-log-unification-and-debug-surface-relocation.md)
- [ADR 0098](./adr/0098-history-ledger-and-history-command-contract.md)

The existing CLI is treated as input data, not as a constraint. Commands that should change are named explicitly with rationale.

This is a design specification. Implementation details (Typer internals, shell completion mechanics) are noted but not adjudicated here.

---

## Design Principles

**P1 — User intent, not service architecture.**
Commands are organized by what the user is trying to do, not by which internal service method they invoke. Internal abstractions (`OperationCommandType`, scheduler cycles) never surface at the user level.

**P2 — Progressive disclosure, not hiding.**
The default `--help` shows the 10 most important commands. A secondary section shows 5 forensic/detail commands. Debug and internal commands are hidden (`hidden=True`) but remain reachable and tab-completable. `operator --help --all` reveals everything.

**P3 — Flat is better than artificially grouped.**
No `op` subgroup for operation management. Those commands are top-level. `project` and `policy` are genuine domain subgroups that earn their prefix.

**P4 — Fleet is the default surface.**
`operator` with no arguments and a TTY opens the fleet view (live, polling). With no TTY or `--once`, shows a single snapshot. Falls back to `--help` if no operations exist and no TTY is attached.

**P5 — Hyphen-case everywhere.**
No underscores in command names. All commands follow `kebab-case`. `stop_turn` → `interrupt`. `claude-log` / `codex-log` → `log`.

**P6 — Every command has human-readable default output.**
`--json` for machine-readable. `--brief` for single-line scriptable output. No command outputs raw JSON in non-`--json` mode.

**P7 — Destructive commands confirm.**
`cancel` prompts "Cancel operation op-abc123? [y/N]" unless `--yes` is passed. `policy revoke` same.

**P8 — `last` and short IDs as operation references.**
Every command accepting an operation ID also accepts the short prefix (first 8+ chars), `last` (most recently started in this project), and an unambiguous profile name.

---

## Command Structure

### Primary commands (shown in default `--help`)

```
operator                    Fleet view (TTY) or fleet snapshot (non-TTY)
operator run [GOAL]         Start an operation toward a goal
operator fleet              All active operations across projects
operator status OP          Operation state and attention summary
operator answer OP [ATT]    Answer a blocking attention request
operator cancel OP          Cancel an operation
operator pause OP           Pause a running operation
operator unpause OP         Resume a paused operation
operator interrupt OP       Interrupt the current agent turn
operator message OP TEXT    Send a durable message to a running operation
operator history [OP]       Operation history ledger
operator init               Set up operator in the current project
operator project ...        Project profile management
```

### Secondary commands (shown in `--help`, below separator)

```
operator log OP             Agent session log (auto-selects agent)
operator tasks OP           Task board for an operation
operator memory OP          Memory entries for an operation
operator artifacts OP       Durable artifacts for an operation
operator attention OP       Attention requests detail (merged into status output; retained for detail)
operator report OP          Operation summary report
operator policy ...         Policy management
operator list               List all persisted operations
```

### Hidden commands (debug — not shown in `--help`, reachable and completable)

```
operator debug daemon       Background wakeup daemon
operator debug tick OP      Advance one scheduler cycle
operator debug recover OP   Force-recover a stuck session
operator debug resume OP    Resume with scheduler cycle control
operator debug wakeups OP   Show pending wakeup records
operator debug sessions OP  Show session and background run records
operator debug command OP   Enqueue a typed command
operator debug context OP   Effective control-plane context
operator debug trace OP     Forensic trace data
operator debug inspect OP   Full forensic dump
```

---

## Command Specifications

### `operator` (no arguments)

Opens the fleet TUI when a TTY is attached and operations are active.
Falls back to a single fleet snapshot when non-TTY (pipe, redirect) or when `--once` is passed.
Falls back to `--help` when no operations exist and no TTY is attached.

TTY detection is required: `operator` piped into another command must not attempt to open the interactive fleet view.

---

### `operator run`

```
operator run [GOAL]
  [--project PROFILE]
  [--harness TEXT]
  [--success-criterion TEXT]...   repeatable
  [--max-iterations N]
  [--agent ADAPTER]...            repeatable; replaces --allowed-agent
  [--mode attached|background]
  [--involvement auto|minimal|active]
  [--from TICKET]                 PM intake: github:owner/repo#N or linear:ABC-123
  [--yes]                         skip confirmation prompts
  [--json]
```

Behavior:
- If `--from` is given without `GOAL`, the ticket title and body become the goal.
- If `GOAL` is not provided and no `--project` with a `default_objective` is active, prompts interactively.
- Writes the new operation ID to `.operator/last` on start.

---

### `operator status OP`

```
operator status OP [--json] [--brief]
```

Default output: rich multi-section summary — status, iteration count, task summary, active attention requests, recent events. Ends with an action line when blocked:

```
→ Action required: operator answer OP att-7f2a
```

`--brief` output (single line, for scripts and dashboards):
```
op-abc123  RUNNING  iter=14/100  tasks=2r·3q·1b  att=[!!1]
```

---

### `operator answer OP [ATT]`

```
operator answer OP [ATT] [--text TEXT] [--json]
```

- If `ATT` is omitted: auto-selects the oldest blocking attention (creation time ascending). Errors if none open. If multiple blocking attentions exist, selects the oldest and shows the count of remaining after answering. Use `operator attention OP` to see all open attentions and select by ID.
- If `--text` is omitted: opens `$EDITOR` if set, otherwise prompts inline.

Policy promotion is a separate workflow: `operator policy record --from-attention ATT-ID`. The `answer` command does not handle policy promotion.

---

### `operator cancel OP`

```
operator cancel OP [--yes] [--json]
```

Prompts for confirmation unless `--yes` is passed:
```
Cancel operation op-abc123 (auth module refactor)? [y/N]
```

Session and run-level cancellation are moved to `operator debug`.

---

### `operator pause OP` / `operator unpause OP`

```
operator pause OP
operator unpause OP
```

`pause`: requests a soft pause of the running operation. The operation stops at the next safe iteration boundary.
`unpause`: resumes a paused operation. Also has the effect of flushing a pause-requested state.

---

### `operator interrupt OP`

```
operator interrupt OP [--task TASK] [--yes]
```

Stops the current agent turn without cancelling the operation. The operator re-evaluates next steps on the following scheduler cycle.

`--task TASK`: scopes the interrupt to a specific task's session (UUID or `task-XXXX` short ID).

Distinct from `pause` (which halts the whole operation) and `cancel` (which terminates it).

---

### `operator message OP TEXT`

```
operator message OP TEXT
```

Injects a durable operator message into the operation's brain context. The message persists for the configured message window (default 3 planning cycles) and is visible in `status` output while active.

---

### `operator log OP`

```
operator log OP [--follow] [--limit N] [--agent claude|codex|auto] [--json]
```

Replaces `claude-log` and `codex-log`. Auto-detects the active agent from the operation's sessions. `--agent` overrides auto-detection. `--follow` tails the log live.

---

### `operator history [OP]`

```
operator history [OP] [--limit N] [--json]
```

Reads from `operator-history.jsonl` — the committed operation ledger at the project root. Without `OP`, shows all entries for this project (newest first). With `OP`, shows the single ledger entry for that operation.

This is distinct from `operator list`, which reads live operation state from `.operator/runs/`.

`--json` emits JSONL (one record per line).

---

### `operator fleet`

```
operator fleet [--project PROFILE] [--once] [--json] [--poll-interval SECS]
```

TUI fleet view when TTY is attached. Single snapshot when non-TTY or `--once`. `--project` filters by profile name.

---

### `operator init`

```
operator init [--name NAME] [--cwd PATH] [--agent ADAPTER] [--yes]
```

Creates `operator-profile.yaml` in the current directory with sensible defaults. Adds `.operator/` to `.gitignore`. Safe to run in any git repo.

If `operator-profile.yaml` already exists: reports "project already configured" and exits without overwriting (unless `--yes --force`).

This is the primary entry point for new project setup. `operator project create` is the lower-level command for managing named profiles.

---

## `project` Subgroup

```
operator project list               List available profiles
operator project inspect [NAME]     Show a profile (human-readable)
operator project resolve [NAME]     Show resolved run defaults (human-readable)
operator project create [NAME]      Create or update a committed profile
operator project dashboard [NAME]   Live project-scoped dashboard
```

Notes:
- `project inspect` and `project resolve` must produce human-readable output by default, not raw JSON. `--json` for machine-readable.
- `project create` replaces `project init` for named profile management. Top-level `operator init` is the first-run UX.

---

## `policy` Subgroup

```
operator policy list [PROJECT]            List active policy entries
operator policy inspect POLICY-ID         Inspect one policy entry
operator policy explain OBJECTIVE         Which policies apply to an objective
operator policy record                    Manually create a policy entry
operator policy revoke POLICY-ID          Revoke a policy (confirms unless --yes)
operator policy projects                  List projects that have policies
```

---

## Operation Reference Conventions

Every command that accepts an operation ID also accepts:

| Form | Resolves to |
|------|-------------|
| Full ID | `op-abc123-def456-...` — exact match |
| Short prefix | `op-abc123` — first 8+ characters |
| `last` | Most recently started operation in this project's `.operator/` data dir |
| Profile name | Unambiguous: exactly one running operation with that profile |

`last` is persisted to `.operator/last` on each `operator run` start. Scoped to the current project's data dir. Errors gracefully with a clear message if no last operation exists.

---

## Output Format Conventions

| Mode | Flag | Format |
|------|------|--------|
| Human-readable (default) | none | Rich multi-section text with labels |
| Machine-readable | `--json` | Single JSON object (or JSONL for streaming/list commands) |
| Single-line scriptable | `--brief` | `KEY=VALUE ...` inline format |
| Non-TTY (live commands) | auto-detected | Falls back to `--once` snapshot mode |

All commands must produce human-readable output by default. Commands that currently output raw JSON in non-`--json` mode are bugs — specifically `project inspect` and `project resolve`.

---

## Naming Changes from Current CLI

| Current name | New name | Reason |
|-------------|----------|--------|
| `stop_turn` | `interrupt` | Clearer intent; hyphen-case; `stop_turn` requires knowing what a "turn" is |
| `codex-log` | `log --agent codex` | Unified; auto-detects agent by default. *Note: this overrides the deliberate exception in VISION.md §Protocol-oriented integration, which preserved vendor-named forensic commands for transparency. Rationale: `--agent` makes the vendor explicit when required (`operator log --agent claude`); unified `log` is more consistent with P5 (hyphen-case) and P2 (progressive disclosure); auto-detect is unambiguous when one agent session is active; the TUI already uses `log OP --follow` rather than vendor-named commands. VISION.md §Protocol-oriented integration deliberate exception is superseded by this document for the CLI surface.* |
| `claude-log` | `log --agent claude` | Unified (see `codex-log` note above) |
| `--allowed-agent` | `--agent` | Shorter, natural |
| `resume` | `debug resume` | Internal; `unpause` is the user-facing resume-from-pause |
| `tick` | `debug tick` | Internal scheduler operation |
| `recover` | `debug recover` | Internal recovery operation |
| `daemon` | `debug daemon` | Internal background process |
| `wakeups` | `debug wakeups` | Internal scheduler state |
| `sessions` | `debug sessions` | Internal session state |
| `command` | `debug command` | Internal command injection |
| `context` | `debug context` | Internal control-plane context |
| `trace` | `debug trace` | Internal forensic trace |
| `inspect` | `debug inspect` | Internal full forensic dump |
| `project init` | `operator init` (top-level) | First-run UX; `project create` for named profiles |
| `answer --promote + policy flags` | `answer` + `policy record --from-attention` | Separation of concerns; `answer` is too complex at 13 parameters |

---

## CLI ↔ TUI Relationship

The CLI and TUI share the same application layer. All CLI commands route through the same `_enqueue_command_async` and service paths as TUI actions. The CLI is the scriptable, pipe-friendly surface; the TUI is the interactive supervision surface.

| TUI action | CLI equivalent |
|-----------|----------------|
| Fleet view | `operator fleet --once` |
| Answer blocking attention | `operator answer OP [ATT]` |
| Pause / unpause | `operator pause OP` / `operator unpause OP` |
| Cancel operation | `operator cancel OP` |
| Interrupt agent turn | `operator interrupt OP [--task TASK]` |
| Send message | `operator message OP TEXT` |
| View task board | `operator tasks OP` |
| View raw transcript | `operator log OP --follow` |
| Open TUI explicitly | `operator fleet` (with TTY) |
| View DecisionMemo (`d` key at Level 1) | `operator debug inspect OP` (full forensic dump includes DecisionMemos) — a dedicated `operator decision-memo OP [--json]` secondary command is a roadmap item |

`operator` with no arguments and a TTY is the recommended entry point for interactive supervision.

---

## Relationship to Existing CLI Commands

| Existing command | Disposition |
|-----------------|-------------|
| `run` | Retained; `--allowed-agent` → `--agent`; add `--from` |
| `fleet` | Retained; becomes default for `operator` with no args + TTY |
| `status` (new) | Replaces `dashboard --once` as the primary status command |
| `dashboard` | Deprecated in favor of `status` (human) and `fleet` (live multi-op) |
| `watch` | Deprecated; `log --follow` covers the use case |
| `answer` | Simplified to 3 parameters; policy promotion separated |
| `pause` / `unpause` | Retained |
| `stop_turn` | Renamed to `interrupt` |
| `message` | Retained |
| `cancel` | Retained; add confirmation prompt |
| `tasks` | Retained; secondary visibility |
| `memory` | Retained; secondary visibility |
| `artifacts` | Retained; secondary visibility |
| `attention` | Merged into `status` output; retained as secondary for detail |
| `list` | Retained; secondary visibility |
| `agenda` | Removed — functionality fully covered by `fleet` output |
| `report` | Retained as secondary; `status` covers the summary |
| `resume` | Moved to `debug resume` |
| `tick` | Moved to `debug tick` |
| `recover` | Moved to `debug recover` |
| `daemon` | Moved to `debug daemon` |
| `wakeups` | Moved to `debug wakeups` |
| `sessions` | Moved to `debug sessions` |
| `command` | Moved to `debug command` |
| `context` | Moved to `debug context` |
| `trace` | Moved to `debug trace` |
| `inspect` | Moved to `debug inspect` |
| `codex-log` | Replaced by `log --agent codex` |
| `claude-log` | Replaced by `log --agent claude` |
| `project list/inspect/resolve/dashboard` | Retained with human-readable output fix |
| `project init` | Replaced by top-level `operator init`; `project create` for named profiles |
| `policy *` | Retained; `policy record --from-attention` added |
| `smoke *` | Retained as internal; not shown in help |

---

## Known Open Items

- Custom help formatter for primary / secondary section separator in Typer
- TTY detection for `fleet` default behavior and zero-argument `operator`
- `last` operation ID persistence (`.operator/last` write on `operator run`)
- `operator init` top-level command implementation
- `operator run --from TICKET` PM intake integration
- `operator history` ledger reader (reads `operator-history.jsonl`)
- `operator log` unified agent log command (replaces `codex-log` / `claude-log`)
- `operator answer` interactive `$EDITOR` prompt when `--text` omitted
- Confirmation prompts in `cancel` and `policy revoke`
- Human-readable output for `project inspect` and `project resolve`
- `--brief` output mode for `status`
- `operator status` as a new command (currently covered by `dashboard --once`)
- `debug` subgroup with hidden visibility
- `operator converse [OP]` — NL REPL session; new primary command (specified in NL-UX-VISION.md)
- `operator ask OP "..."` — single-shot NL query, read-only; new primary command (specified in NL-UX-VISION.md)
- `operator mcp` — MCP stdio server; new secondary command (specified in AGENT-INTEGRATION-VISION.md)
- `operator project create [NAME]` — create or update a committed named profile (replaces `operator project init`)
- Semantic exit codes for `run`, `status`, and terminal-state-reporting commands (specified in AGENT-INTEGRATION-VISION.md)
- `--wait [--timeout N]` flag on `operator run` (specified in AGENT-INTEGRATION-VISION.md)
- `operator status` ambient observation section (specified in NL-UX-VISION.md)
