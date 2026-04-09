# ADR 0117: Public Session-Scope CLI Surface

## Status

Implemented

## Context

`ADR 0116` establishes that CLI parity with the TUI display family is incomplete and that the
weakest area is `Session View` parity.

The repository now has an explicit TUI `Session View` contract:

- recent timeline
- compact session brief
- selected-event detail
- explicit transcript escalation path

The repository also now has an explicit CLI scope model:

- `fleet`
- `operation`
- `session`
- `forensic`

But without a public `session`-scope CLI surface, that model remains incomplete.

Current building blocks are insufficient:

- `watch` is operation-scoped, not session-scoped
- `status` is the canonical operation-scoped summary
- `dashboard` is operation-scoped and richer than a session surface should be
- `log` is the raw transcript surface
- hidden `trace` and `inspect` are not a substitute for a public session-scoped workflow

The repository also has a hard addressing constraint from the core product model:

- users address work through the operation and task
- users do not address internal session UUIDs directly

Therefore any public session-scoped surface must be addressed by:

- operation reference
- task reference

not by session id.

## Decision

The public CLI must add a dedicated session-scoped surface:

```text
operator session OP --task TASK [--once] [--follow] [--json] [--poll-interval SECS]
```

This command is the public `session`-scope summary/live surface.

### Addressing rule

The command is addressed by:

- `OP` = operation reference
- `--task TASK` = task short id or task UUID

It must not require a session UUID.

The task reference identifies the task-bound session to supervise.

### Behavioral modes

- default:
  - render one human-readable session snapshot
- `--follow`:
  - render the live textual Level 2 surface
- `--json`:
  - emit the machine-readable session payload

`--once` is permitted for symmetry with other live/snapshot surfaces.

### Required semantics

The default human-readable surface must mirror the session-level contract, in textual form:

- session identity and state
- `Now`
- `Wait`
- `Attention`
- `Latest output`
- recent event list
- selected or latest event detail
- explicit transcript hint

This command must not collapse into:

- raw transcript output
- a full forensic trace
- a second operation dashboard

### Relationship to adjacent surfaces

- `status` remains the canonical operation-scope shell summary
- `watch` remains the lightweight operation-scope live textual follower
- `session` becomes the public session-scope summary/live surface
- `log` remains the transcript surface
- `trace` and `inspect` remain deeper forensic/debug surfaces unless separately promoted

## Consequences

### 1. The CLI scope model becomes real

With `session`, the public CLI now has an explicit surface for each intended scope:

- `fleet`
- `operation`
- `session`
- `forensic`

Without this command, `session` would remain only a conceptual placeholder.

### 2. `watch` is not stretched beyond its role

This ADR explicitly rejects solving the gap by overloading `watch` with session-specific semantics.

`watch` remains:

- operation-scoped
- concise
- lightweight

It should not become a disguised Level 2 session browser.

### 3. `dashboard` is not overloaded further

This ADR also rejects using `dashboard` as the public session-scope answer.

`dashboard` remains richer operation-scoped live/detail surface.

### 4. Transcript and session remain distinct

This ADR rejects solving the gap by treating `log` as the session surface.

`log` remains:

- transcript-oriented
- rawer
- more forensic

`session` is the human-first session supervision surface.

## Explicit non-goals

This ADR does not require:

- session UUIDs to become public user-facing identifiers
- replacing `status`
- replacing `watch`
- replacing `dashboard`
- promoting hidden forensic commands to public surfaces
- designing the full JSON schema in this ADR

## First implementation tranche

### P0

1. Add the public `session` command shape to the CLI surface.
2. Add a normalized `session_brief` payload block.
3. Expose recent session timeline semantics in a shared payload shape.
4. Render human-readable `session` output without leaking transcript or forensic internals.
5. Keep transcript escalation explicit via `log`.

### P1

1. Add session-specific CLI tests for:
   - addressing by task short id
   - snapshot output
   - follow/live output
   - transcript hint behavior
2. Add `--json` payload tests once the shared session payload contract exists.

## File-by-file implementation plan

This plan is the intended tranche shape, not a rigid naming mandate.

### Application/query layer

Add normalized session-scoped display semantics on top of the existing one-operation substrate.

Likely touch points:

- [operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_projections.py)
- [operation_dashboard_queries.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_dashboard_queries.py)

Expected work:

- add a normalized `session_brief` block
- make session timeline rows explicit and display-oriented
- make selected/latest event detail explicit enough that CLI and TUI do not both have to invent
  separate assembly logic

This ADR does not require a totally separate session query service in the first tranche if the
existing one-operation dashboard/query path can carry the normalized session block cleanly.

### CLI driving adapter

Add the public `session` command and keep it thin over the shared query/projection layer.

Likely touch points:

- [main.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/main.py)

Expected work:

- add `session` command signature:
  - `OP`
  - `--task TASK`
  - `--once`
  - `--follow`
  - `--json`
  - `--poll-interval`
- resolve the task by short id or UUID
- map task to the bound session without surfacing session UUIDs as the user-facing address
- render human-readable session output from shared session payload semantics

### TUI alignment

The session payload work should align with, not duplicate, the TUI contract.

Likely touch points:

- [tui.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui.py)

Expected work:

- let the TUI consume the same normalized session semantics where possible
- reduce local session-brief assembly from broader dashboard payload pieces
- keep transcript escalation separate from session summary/live semantics

### Tests

Add or update tests in three layers:

- projection tests for `session_brief` and timeline normalization
- CLI tests for `operator session`
- TUI tests where shared session payload semantics replace local assembly assumptions

Likely touch points:

- [test_operation_projections.py](/Users/thunderbird/Projects/operator/tests/test_operation_projections.py)
- [test_cli.py](/Users/thunderbird/Projects/operator/tests/test_cli.py)
- [test_tui.py](/Users/thunderbird/Projects/operator/tests/test_tui.py)

## Implementation checklist

1. **Normalize session-level shared semantics**
   - add `session_brief`
   - add normalized recent session timeline items
   - add explicit selected/latest event detail semantics

2. **Keep addressing task-first**
   - resolve `--task` by short id or UUID
   - map it to the bound session internally
   - do not require session UUIDs in the public command

3. **Add the public `session` CLI command**
   - snapshot mode by default
   - `--follow` for live textual mode
   - `--json` for machine-readable mode

4. **Render session output with strict guardrails**
   - include `Now / Wait / Attention / Latest output`
   - include recent events
   - include selected/latest event detail
   - include explicit transcript hint
   - do not collapse into transcript or forensic dump

5. **Add tests before polish**
   - task short-id addressing
   - no-session / ambiguous-task failure cases
   - snapshot output shape
   - follow/live output behavior
   - transcript hint presence

6. **Polish only after parity shape is real**
   - truncation behavior
   - narrow-terminal formatting
   - richer JSON payload details if still needed

## Verification criteria

This ADR is materially satisfied only when all of the following are true:

1. A user can run `operator session OP --task TASK` without needing a session UUID.
2. The command renders a human-readable session-scoped summary/live surface.
3. The command does not degrade into raw transcript or full forensic trace.
4. `status`, `watch`, `session`, and `log` have non-overlapping public roles.
5. The session-scoped output is backed by shared normalized session semantics rather than a
   CLI-local ad hoc assembly layer.

## Verification Notes (2026-04-10)

Repository evidence for the implemented session scope now includes:

- normalized shared session semantics in
  [operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_projections.py)
- the public task-addressed `session` command in
  [commands_operation_detail.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/commands_operation_detail.py)
- focused CLI verification in
  [test_cli.py](/Users/thunderbird/Projects/operator/tests/test_cli.py)

The human-readable session surface now renders:

- session identity and state
- `Now / Wait / Attention / Latest output`
- recent event list
- selected/latest event detail including summary
- explicit transcript escalation via `operator log`

## Implementation outcome

- `src/agent_operator/application/operation_projections.py` now emits task-addressed
  `session_views` inside the shared dashboard payload, including normalized `session_brief`,
  timeline rows, selected-event detail, and transcript hints.
- `src/agent_operator/cli/commands_operation_detail.py` now renders `operator session` from that
  shared payload instead of reconstructing Level 2 semantics from broader operation fields.
- `src/agent_operator/cli/tui_models.py` now prefers the same `session_views` payload for Session
  View rendering, reducing CLI/TUI duplication for session scope.
- Repository evidence:
  - `tests/test_operation_projections.py::test_build_dashboard_payload_emits_normalized_session_views`
  - `tests/test_cli.py::test_session_command_prints_session_snapshot_for_task_short_id`
  - `tests/test_cli.py::test_session_command_json_emits_machine_readable_payload`
  - `tests/test_tui.py::test_session_view_renders_session_brief_and_selected_event_sections`
