# RFC 0014: CLI output contract and example corpus

## Status

Draft

## Implementation Status

Partial

Skim-safe current truth on 2026-04-10:

- `implemented`: the current CLI/TUI slice already has a real cross-operation fleet snapshot, a
  one-operation shell summary, a task-addressed session surface, transcript escalation, and the
  interactive fleet workbench
- `implemented`: current docs and tests now treat the package-shaped CLI delivery surface
  (`commands/`, `helpers/`, `rendering/`, `tui/`, `workflows/`) as repository truth
- `partial`: this RFC's full command-family example corpus is ahead of shipped output in places,
  especially for the broader next-wave CLI refinement ADR set
- `planned`: the remaining output-contract closure should land incrementally by command family,
  with tests and docs updated together

## Purpose

Define one repository-wide output contract for the public `operator` CLI and provide concrete,
human-readable examples for each command family in the current CLI vision.

This RFC is not a command-taxonomy RFC and not a transport/schema RFC.

Its purpose is narrower:

- make default human-readable output concrete
- align `--brief`, `--json`, and live/follow behavior across commands
- prevent drift between CLI vision prose and actual rendered output
- give implementation and review work a stable example corpus to validate against
- preserve command-specific UX identity rather than forcing one repeated report template everywhere

## Scope

In scope:

- default human-readable output
- `--brief` output where the vision calls for it
- `--json` expectations at the output-shape level
- live/follow rendering expectations
- confirmation and refusal text for destructive or gated commands

Out of scope:

- exact internal JSON field schemas for every command
- shell completion
- ANSI color choices
- Typer-specific implementation details
- TUI layout contracts

When `operator` or `operator fleet` opens the interactive fleet workbench in a TTY, the TUI owns
that layout contract. This RFC governs textual CLI output:

- non-TTY snapshots
- `--once` snapshots
- human-readable command output
- `--brief`
- `--json`
- textual live followers such as `watch` and `session --follow`

## Core Output Rules

### 1. Human-readable by default

Every public command must produce human-readable output by default.

Default output should:

- optimize for operator comprehension
- prefer stable labeled sections
- avoid raw dict / Python repr / accidental JSON
- avoid implementation jargon when a user-facing phrase exists

### 2. `--json` is machine-readable, not a second prose mode

When a command supports `--json`, the default human-readable contract does not weaken.

`--json` should emit:

- one JSON object for one-object snapshot commands
- a JSON array or JSONL stream for list/stream commands, whichever the command already owns

### 3. `--brief` is a compact scriptable summary

When a command supports `--brief`, it should:

- fit on one line
- remain semantically aligned with the default output
- not become a second undocumented schema language

### 4. Live/follow surfaces redraw idempotently

Polling-based follow commands should:

- redraw unchanged state rather than append duplicate meaning
- append or visibly change output only when user-visible meaning changed
- stay compact and bounded

### 5. Public supervisory surfaces and forensic surfaces differ

Human-first supervisory commands should not degrade into:

- raw transcript output
- trace/event dumps
- debug payloads

Forensic commands may be denser, but they still must avoid accidental implementation leakage when a
stable explanatory label exists.

### 6. Shared vocabulary does not imply shared layout

The CLI should reuse a small shared vocabulary where it improves transfer:

- `Goal`
- `Now`
- `Wait`
- `Progress`
- `Attention`
- `Recent`

But commands must not all collapse into the same default layout just because they share some
labels.

The output contract is defined by command family first, then by individual command examples.

## Global Style Rules

Preferred output style:

- 1-line headline where useful
- short labeled sections
- bounded lists
- action hints only when materially helpful

Avoid:

- raw UUID noise when a short ref exists
- duplicate restatement of unchanged objective text
- implementation flags like `scheduler=active`
- inline dicts such as `summary={...}`

## Command Families

This RFC uses command families as the primary normative layer.

Examples are illustrative within these family contracts. If an example conflicts with its family
rule, the family rule wins.

### Family A1: Cross-Operation Supervisory Snapshot

Commands:

- `operator` non-TTY snapshot
- `operator fleet --once`

Job:

- answer "what matters now across operations?" in one bounded read

Default budget:

- roughly 10-16 visible non-empty lines in a normal terminal
- prefer one compact headline, 1-3 rows, and a compact selected-operation brief

Required properties:

- one clear headline
- 1-3 operation rows
- a compact selected-operation brief
- explicit next action only when materially helpful

Optional sections:

- `Now`
- `Wait`
- `Attention`
- `Recent`
- `Progress`
- `Goal`

Forbidden as default:

- raw transcript bodies
- full event timelines
- large task boards
- debug/internal state blocks
- a full six-section report stack

Compression rule:

- keep the headline and rows first
- then keep `Now`
- then `Wait` or `Attention`
- then drop `Recent`, then `Progress`, then `Goal`

### Family A2: One-Operation Shell Summary

Commands:

- `operator status OP`

Job:

- answer "what does this operation need me to know right now?" as the decisive shell-native
  summary

Default budget:

- roughly 8-14 visible non-empty lines

Required properties:

- one clear headline
- one operation anchor line
- one current-state line (`Now` or `Wait`)
- one attention line or explicit `none`

Optional sections:

- `Goal`
- `Progress`
- `Recent`
- `Action`

Forbidden as default:

- fleet-style row lists
- session-level event detail
- transcript-oriented blocks unless directly relevant

Compression rule:

- keep the headline
- keep the operation anchor
- keep `Wait` or `Now`
- keep `Attention`
- keep `Action` when blocked
- then drop `Progress`, then `Goal`, then `Recent`

### Family A3: Session Investigation Snapshot

Commands:

- `operator session OP --task TASK`

Job:

- give a bounded level-2 session view without collapsing into transcript or forensic output

Default budget:

- roughly 12-18 visible non-empty lines

Required properties:

- session header
- `Now`
- `Wait` or `Attention`
- `Latest`
- 2-3 recent timeline rows
- transcript escalation hint

Optional sections:

- one selected/latest event detail block

Forbidden as default:

- full transcript body
- full forensic trace
- large operation-level summary blocks

Compression rule:

- keep header
- keep `Now`
- keep `Wait` or `Attention`
- keep `Latest`
- keep 2 recent rows
- keep transcript hint
- drop selected-event detail first

### Family B1: One-Operation Live Follow

Commands:

- `operator watch OP`

Job:

- answer "what changed in this operation?" without becoming a transcript tail or a pseudo-TUI

Default budget:

- roughly 6-10 visible non-empty lines
- fewer sections than the corresponding snapshot family

Required properties:

- idempotent redraw
- compact live state
- no repeated unchanged churn

Optional sections:

- one headline
- one current focus line
- one small progress or attention block

Forbidden as default:

- full retrospective summaries
- transcript bodies
- growing append-only status spam

Compression rule:

- prefer fewer stable blocks over more explanatory prose

### Family B2: Session Live Follow

Commands:

- `operator session OP --task TASK --follow`

Job:

- answer "what changed in this session?" with slightly more local context than one-operation follow

Default budget:

- roughly 8-14 visible non-empty lines

Required properties:

- session header
- `Now`
- `Wait` or `Attention`
- latest meaningful output line

Optional sections:

- 1-2 recent timeline rows
- transcript hint

Forbidden as default:

- full selected-event detail on every refresh
- transcript body
- retrospective report sections

Compression rule:

- keep header
- keep `Now`
- keep `Wait` or `Attention`
- keep `Latest`
- keep 1-2 recent rows
- keep transcript hint last

### Family C: Retrospective / Ledger

Commands:

- `operator history [OP]`
- `operator report OP`

Job:

- answer "what happened?" after or across runs

Default budget:

- may be longer than a live/snapshot view
- still should remain skim-friendly

Required properties:

- clear time/outcome orientation
- concise summaries rather than dense live-state detail

Forbidden as default:

- live follow semantics
- transcript dumps
- debug payloads

### Family D: Inventory / Detail List

Commands:

- `operator tasks OP`
- `operator memory OP`
- `operator artifacts OP`
- `operator attention OP`
- `operator list`
- `operator project list`
- `operator policy list`
- `operator policy projects`

Job:

- enumerate one specific kind of object cleanly

Default budget:

- mostly list-oriented
- minimal prose above or below the list

Required properties:

- strong list label
- stable row grammar within the command

Forbidden as default:

- unrelated summary sections like `Goal / Progress / Recent`
- long explanatory paragraphs

### Family E: Mutation / Lifecycle Confirmation

Commands:

- `operator run`
- `operator answer`
- `operator cancel`
- `operator pause`
- `operator unpause`
- `operator interrupt`
- `operator message`
- `operator init`
- `operator clear`
- `operator project create`
- `operator policy record`
- `operator policy revoke`
- `operator debug tick`
- `operator debug recover`
- `operator debug resume`
- `operator debug command`

Job:

- confirm what changed, what will happen next, or why the command refused

Default budget:

- 1-8 lines
- usually shorter than supervisory snapshots

Required properties:

- explicit action result
- explicit refusal reason when relevant
- brief next-step hint only when it materially reduces confusion

Forbidden as default:

- large summary cards
- detailed state snapshots

### Family F: Profile / Policy Inspection

Commands:

- `operator project inspect`
- `operator project resolve`
- `operator policy inspect`
- `operator policy explain`

Job:

- explain one object or one applicability decision

Default budget:

- short labeled sections are acceptable
- denser than mutation confirmations, lighter than reports

Required properties:

- strong object header
- scoped labeled fields

Forbidden as default:

- live supervision sections
- transcript-like content

### Family G: Transcript

Commands:

- `operator log OP`

Job:

- show raw conversational or tool transcript material

Default budget:

- unbounded by nature, but should still have a compact header

Required properties:

- transcript-first rendering
- minimal wrapper prose

Forbidden as default:

- supervisory summary card replacing the transcript

### Family H: Forensic / Debug Inspection

Commands:

- `operator debug daemon`
- `operator debug wakeups`
- `operator debug sessions`
- `operator debug context`
- `operator debug trace`
- `operator debug inspect`

Job:

- expose operational internals legibly without pretending to be the public supervisory UX

Default budget:

- may be structurally denser than public surfaces

Required properties:

- direct structural information
- explicit labels
- compact but not over-sanitized presentation

Forbidden as default:

- raw dict/JSON when not in `--json`
- misleadingly polished supervision-style summaries that hide the debugging nature of the surface

## Family-Specific Section Guidance

Not every command should render the same section family.

### Shared supervisory labels

The labels below are reusable, but not universally required:

- `Goal`
- `Now`
- `Wait`
- `Progress`
- `Attention`
- `Recent`

Use them mainly in Families A1-A3 and, more selectively, in Families B1-B2.

### Family-specific priorities

- Family A1 should prioritize row scanability and a compact selected-operation brief.
- Family A2 should prioritize decisive operation summary and next action.
- Family A3 should prioritize bounded session investigation and transcript escalation.
- Family B1 should prioritize liveness and compactness over explanatory completeness.
- Family B2 should prioritize live session context without becoming a transcript tail.
- Family C should prioritize outcome/time orientation.
- Family D should prioritize clean list scanning.
- Family E should prioritize action result and refusal clarity.
- Family F should prioritize object explanation.
- Family G should prioritize transcript truth.
- Family H should prioritize structural debugging clarity.

## Budget And Precedence Rules

### Visible line counting

- Count non-empty rendered lines.
- Blank spacer lines do not count toward the family budget.
- Examples should fit the family budget under normal terminal width.

### Default vs expanded output

- This RFC specifies default output only.
- Expanded or verbose variants are out of scope unless a future RFC adds them explicitly.

### Narrow-width behavior

- Truncate before adding new sections.
- Drop lower-priority optional sections before wrapping into a longer report-like layout.
- Preserve row scanability and subject anchors over prose completeness.

### Rule precedence

- If an example conflicts with a family rule, the family rule wins.
- If a future command-specific normative subsection conflicts with the family, the
  command-specific subsection wins.

## Command Example Corpus

The examples below are normative illustrations of expected output shape, not byte-for-byte test
fixtures.

They are grouped under the family rules above. They show plausible defaults, not a requirement that
every command adopt the same section stack.

## Top-Level Entry

### `operator`

TTY with active operations:

- opens the interactive fleet workbench instead of printing a static block

Non-TTY or `--once` snapshot:

```text
Fleet  7 active · 2 needs human · 4 running · 1 paused

> [!!2] checkout-redesign
  RUNNING · codex_acp · 8s
  now: session drill-down

  [ ] docs-cleanup
  PAUSED · claude_acp · 4m
  paused: by operator

Now
- Implementing session drill-down

Attention
- 2 blocking

Recent
- session resumed
- next turn started
```

No active operations and non-TTY:

- falls back to `operator --help`

## Primary Commands

### `operator run [GOAL]`

Success:

```text
Started operation op-7d3a9c21
Project: operator
Mode: attached
Agents: codex_acp
Goal: Complete ADR 0124 orchestration package split

Next
- operator status op-7d3a9c21
- operator watch op-7d3a9c21
```

`--json`:

```json
{
  "operation_id": "op-7d3a9c21",
  "project": "operator",
  "mode": "attached",
  "agents": ["codex_acp"],
  "goal": "Complete ADR 0124 orchestration package split"
}
```

### `operator fleet`

Human-readable snapshot:

```text
Fleet  7 active · 2 needs human · 4 running · 1 paused

> [!!2] checkout-redesign
  RUNNING · codex_acp · 8s
  now: session drill-down

  [!1] docs-cleanup
  NEEDS_HUMAN · claude_acp · 31s
  waiting: answer needed

Now
- Implementing session drill-down

Wait
- Agent turn running

Attention
- 2 blocking

Recent
- session resumed
- next turn started
```

`--json`:

- emits the normalized fleet workbench payload rather than agenda-era raw fields

### `operator status OP`

Default:

```text
RUNNING · iter 14/100 · last activity 8s ago

Operation
- op-7d3a9c21 · checkout-redesign

Now
- Implementing session drill-down

Attention
- none

Progress
- Doing: Level 1 operation view
```

Blocked example:

```text
NEEDS_HUMAN · iter 14/100 · last activity 26s ago

Operation
- op-7d3a9c21 · checkout-redesign

Now
- Waiting for human answer on policy_gap

Attention
- [!!1] policy_gap: choose canonical package path

Action
- operator answer op-7d3a9c21 att-7f2a
```

`--brief`:

```text
op-7d3a9c21 RUNNING iter=14/100 tasks=2r·3q·1b att=[ ] last=8s
```

`--json`:

- one JSON object for the operation summary payload

### `operator answer OP [ATT]`

Interactive prompt success:

```text
Answering attention att-7f2a for op-7d3a9c21
Remaining blocking attentions: 0
Queued answer for next scheduler cycle.
```

Omitted `ATT` with auto-selection:

```text
Selected oldest blocking attention att-7f2a for op-7d3a9c21
Queued answer for next scheduler cycle.
```

No open blocking attention:

```text
No blocking attention is open for op-7d3a9c21.
Use 'operator attention op-7d3a9c21' to inspect all open attention items.
```

`--json`:

```json
{
  "operation_id": "op-7d3a9c21",
  "attention_id": "att-7f2a",
  "status": "queued"
}
```

### `operator cancel OP`

Confirmation prompt:

```text
Cancel operation op-7d3a9c21 (checkout-redesign)? [y/N]
```

Confirmed:

```text
Cancellation requested for op-7d3a9c21.
The operation will stop and move to TERMINAL once cancellation completes.
```

`--json`:

```json
{
  "operation_id": "op-7d3a9c21",
  "status": "cancellation_requested"
}
```

### `operator pause OP`

```text
Pause requested for op-7d3a9c21.
The operation will pause at the next safe iteration boundary.
```

### `operator unpause OP`

```text
Resumed op-7d3a9c21.
```

### `operator interrupt OP [--task TASK]`

Operation-scoped:

```text
Interrupt requested for the active turn in op-7d3a9c21.
The operator will re-evaluate next steps on the next scheduler cycle.
```

Task-scoped:

```text
Interrupt requested for task task-3a7f2b1c in op-7d3a9c21.
```

### `operator message OP TEXT`

```text
Queued operator message for op-7d3a9c21.
Message window: 3 planning cycles.
```

### `operator history [OP]`

Project-wide:

```text
History · operator

- op-7d3a9c21 · completed · 2026-04-10 18:42 · checkout-redesign
- op-a12be91f · failed    · 2026-04-10 15:11 · session parity tranche
- op-21f34aa0 · cancelled · 2026-04-10 13:02 · docs cleanup
```

Single operation:

```text
History · op-7d3a9c21

State
- completed

Goal
- Finish TUI UX, then docs

Stop reason
- completed

Started
- 2026-04-10 17:58

Finished
- 2026-04-10 18:42
```

`--json`:

- emits JSONL records from `operator-history.jsonl`

### `operator init`

Success:

```text
Initialized operator for /path/to/project

Created
- operator-profile.yaml

Updated
- .gitignore

Next
- operator run "..."
- operator project inspect
```

Already configured:

```text
Project already configured.
Existing file: operator-profile.yaml
```

### `operator clear`

Confirmation prompt:

```text
Clear operator runtime state for /path/to/project? [y/N]
```

Success:

```text
Cleared operator state for /path/to/project

Deleted
- .operator/runs/
- .operator/operation_events/
- .operator/operation_checkpoints/
- operator-history.jsonl

Preserved
- operator-profile.yaml
- operator-profiles/
- .operator/profiles/
```

Refusal:

```text
Refusing to clear operator state because active or recoverable operations still exist.
Use 'operator list' or 'operator fleet --once' to inspect current state.
```

## Secondary Commands

### `operator watch OP`

Default follow view:

```text
● Running   iter 4/100   last activity 8s ago

Task    task-3a7f2b1c  Implement Level 1 operation view
Agent   codex_acp      editing TUI drill-down and focused tests
Now     Waiting for current agent turn to finish

Attention
- none
```

Requirements:

- redraw idempotently
- no repeated unchanged churn lines
- no leaked scheduler internals

### `operator session OP --task TASK`

Snapshot:

```text
Session  task-3a7f2b1c  codex_acp  RUNNING
Now      validating token refresh flow
Wait     agent turn running
Attention 1 open policy_gap
Latest   implemented refresh handler; moving to validation

Recent
- 14:32 ▸ agent output
- 14:31 ● brain decision: continue

Selected
- [14:32] agent output · auth/session.py, tests/auth.py

Transcript
- operator log op-7d3a9c21 --follow
```

`--follow`:

- same semantic blocks, refreshed live

`--json`:

- one JSON object carrying the normalized session payload

### `operator log OP`

Human-readable:

```text
Log · op-7d3a9c21 · codex_acp

[18:41:02] user
Implement the next ADR tranche.

[18:41:18] agent
I updated the session payload and added focused tests.

[18:41:26] tool
uv run pytest tests/test_cli.py -q
```

`--follow`:

- tails new transcript entries

`--json`:

- emits structured transcript records

### `operator tasks OP`

```text
Tasks · op-7d3a9c21

RUNNING
- ▶ task-3a7f2b1c  Implement Level 1 operation view

READY
- ○ task-7b3f1e9d  adapter cleanup

BLOCKED
- ! task-9ac11b22  docs update
  waiting on task-3a7f2b1c

COMPLETED
- ✓ task-a1d4e7c2  domain model notes
```

### `operator memory OP`

```text
Memory · op-7d3a9c21

- [operation] ARCHITECTURE.md
  read 2 cycles ago
  summary: current delivery boundary and CLI/TUI split

- [project] CLI-UX-VISION.md
  active
  summary: canonical command taxonomy and output rules
```

### `operator artifacts OP`

```text
Artifacts · op-7d3a9c21

- design/adr/0124-application-orchestration-submodule-organization.md
  type: adr

- docs/tui-workbench.md
  type: documentation
```

### `operator attention OP`

```text
Attention · op-7d3a9c21

Blocking
- [!!1] att-7f2a · policy_gap
  Choose canonical package path for orchestration modules

Non-blocking
- [!1] att-81b4 · doc_update_proposal
  Update CLI docs after tranche lands
```

### `operator report OP`

```text
Report · op-7d3a9c21

Outcome
- implemented fleet workbench projection tranche

Summary
- completed shared fleet payload
- updated CLI/TUI consumers
- added focused regression coverage

Artifacts
- design/adr/0115-fleet-workbench-projection-and-cli-tui-parity.md
- tests/test_cli.py
- tests/test_tui.py
```

### `operator list`

```text
Operations · current workspace

- op-7d3a9c21 · RUNNING · checkout-redesign
- op-a12be91f · NEEDS_HUMAN · session parity tranche
- op-21f34aa0 · TERMINAL · docs cleanup
```

## `project` Subgroup

### `operator project list`

```text
Projects

- operator
- telemetry
- docs-site
```

### `operator project inspect [NAME]`

```text
Project Profile · operator

Path
- /Users/thunderbird/Projects/operator

Defaults
- agent: codex_acp
- mode: attached
- max_iterations: 100

Objective
- unset
```

### `operator project resolve [NAME]`

```text
Resolved Run Defaults · operator

Project
- operator

Effective values
- agent: codex_acp
- mode: attached
- max_iterations: 100
- involvement: auto
```

### `operator project create [NAME]`

```text
Saved project profile 'operator'.
Path: operator-profile.yaml
```

### `operator project dashboard [NAME]`

```text
Project Dashboard · operator

Active operations
- 7

Needs human
- 2

Recent
- checkout-redesign resumed
- docs-cleanup completed
- policy tranche started
```

## `policy` Subgroup

### `operator policy list [PROJECT]`

```text
Policy Entries · operator

- pol-7c1a · active   · session retry guidance
- pol-8dd2 · active   · package naming convention
- pol-a118 · revoked  · obsolete adapter preference
```

### `operator policy inspect POLICY-ID`

```text
Policy · pol-7c1a

Status
- active

Scope
- project: operator

Rule
- prefer codex_acp for repository-wide refactors

Source
- recorded from attention att-91be
```

### `operator policy explain OBJECTIVE`

```text
Policy Explanation

Objective
- Split CLI rendering into dedicated package modules

Applies
- pol-8dd2 · package naming convention
- pol-7c1a · codex_acp preference

Why
- objective mentions package movement
- project defaults prefer codex_acp for repository refactors
```

### `operator policy record`

```text
Recorded policy entry pol-b221.
```

### `operator policy revoke POLICY-ID`

Prompt:

```text
Revoke policy pol-7c1a? [y/N]
```

Success:

```text
Revoked policy pol-7c1a.
```

### `operator policy projects`

```text
Projects With Policies

- operator
- telemetry
```

## Hidden Debug Surfaces

These remain denser and more implementation-facing, but they should still produce legible output by
default.

### `operator debug daemon`

```text
Daemon mode active.
Watching pending wakeups for the current workspace.
```

### `operator debug tick OP`

```text
Advanced one scheduler cycle for op-7d3a9c21.
```

### `operator debug recover OP`

```text
Recovery requested for op-7d3a9c21.
```

### `operator debug resume OP`

```text
Resumed run for op-7d3a9c21 with scheduler control.
```

### `operator debug wakeups OP`

```text
Wakeups · op-7d3a9c21

- wake-001 · due now · reason=session_timeout
- wake-002 · due in 12s · reason=rate_limit_cooldown
```

### `operator debug sessions OP`

```text
Sessions · op-7d3a9c21

- sess-81be · codex_acp · RUNNING · bound task task-3a7f2b1c
- sess-91ad · claude_acp · TERMINAL · bound task task-a1d4e7c2
```

### `operator debug command OP`

```text
Queued typed command for op-7d3a9c21.
```

### `operator debug context OP`

```text
Context · op-7d3a9c21

Scheduler
- running

Pause state
- none

Control hints
- no pending recovery
```

### `operator debug trace OP`

```text
Trace · op-7d3a9c21

- 18:41:02 operation.started
- 18:41:18 brain.decision.continue
- 18:41:26 agent.turn.completed
```

### `operator debug inspect OP`

```text
Inspect · op-7d3a9c21

State
- RUNNING

Runs
- 1 active run

Sessions
- 2 known sessions

Recent events
- operation.started
- brain.decision.continue
- agent.turn.completed
```

## Cross-Command Consistency Rules

The example corpus implies these consistency requirements:

1. Commands should share a small vocabulary where it helps transfer, but not one repeated universal
   section stack.
2. Cross-operation snapshot, one-operation summary, session snapshot, live follow, retrospective,
   transcript, and debug surfaces are intentionally different output classes.
3. `watch` and `session --follow` are live textual surfaces, not transcript tails.
4. `log` is the transcript surface, not a human-summary surface.
5. hidden debug commands may be denser and more structural than public supervisory surfaces, but
   should still avoid accidental raw dict output.
6. confirmation and refusal text should be explicit and operator-actionable.

## Related

- [../CLI-UX-VISION.md](../CLI-UX-VISION.md)
- [../VISION.md](../VISION.md)
- [../ARCHITECTURE.md](../ARCHITECTURE.md)
- [../adr/0093-cli-command-taxonomy-visibility-tiers-and-default-operator-entry-behavior.md](../adr/0093-cli-command-taxonomy-visibility-tiers-and-default-operator-entry-behavior.md)
- [../adr/0096-one-operation-control-and-summary-surface.md](../adr/0096-one-operation-control-and-summary-surface.md)
- [../adr/0097-forensic-log-unification-and-debug-surface-relocation.md](../adr/0097-forensic-log-unification-and-debug-surface-relocation.md)
- [../adr/0117-public-session-scope-cli-surface.md](../adr/0117-public-session-scope-cli-surface.md)
