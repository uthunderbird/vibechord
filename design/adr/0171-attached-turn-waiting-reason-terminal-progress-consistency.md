# ADR 0171: Attached-Turn Waiting-Reason Terminal Progress Consistency

## Decision Status

Accepted

## Implementation Status

Verified

Implementation grounding on 2026-04-14:

- `implemented`: `AttachedTurnService.collect_turn()` no longer copies terminal progress messages
  into durable `SessionRecord.waiting_reason`; live waiting/progress states still update the field
  in `src/agent_operator/application/attached_turns.py`
- `verified`: terminal-placeholder regression coverage now exists in
  `tests/test_attached_turn_service.py::test_collect_turn_does_not_persist_terminal_placeholder_waiting_reason`
- `verified`: targeted verification passed for the attached-turn slice, and full `uv run pytest`
  passed at current repository truth

## Context

The operator can currently surface an impossible-looking live-session summary such as:

- `session_status: running`
- `waiting_reason: "Agent session completed."`

This shows up in live `operator status` output for attached turns and makes the runtime look
stale or contradictory even when the underlying session/result flow is otherwise healthy.

The underlying cause is a transient inconsistency in the attached-turn polling path:

1. `AttachedTurnService.collect_turn()` polls `AgentSessionManager.poll(session)`.
2. It writes `record.waiting_reason = progress.message` before it knows whether the progress
   snapshot is still genuinely live or already terminal.
3. For a terminal attached session, `AttachedSessionRuntimeRegistry.poll()` synthesizes the
   placeholder message `"Agent session completed."`.
4. The same polling path does **not** synchronously update `record.status` to a terminal session
   status; it calls `collect()` and relies on later result folding/reconciliation to do that.

This creates a window where durable session truth says:

- `status = RUNNING`
- `waiting_reason = "Agent session completed."`

The query layer is not the root problem. It simply renders the `SessionState` it receives.

## Decision

Treat `waiting_reason` as a live-progress field only. Do not persist a terminal placeholder
message into the session record during attached-turn polling.

Specifically:

- attached-turn polling may keep writing `waiting_reason` for genuinely live progress states
  such as `PENDING`, `RUNNING`, and `WAITING_INPUT`
- attached-turn polling must not write `"Agent session completed."` or any equivalent terminal
  placeholder into the durable session record
- terminal session state should become visible through terminal result folding and canonical
  session status updates, not through an early mutation of `waiting_reason`

If a terminal-progress snapshot needs a user-facing message before reconciliation completes, that
message should stay inside the ephemeral `AgentProgress`/runtime surface rather than being copied
into durable session truth as a waiting field.

## Consequences

### Positive

- `operator status` and related projections stop showing contradictory pairs like
  `running + "Agent session completed."`
- `waiting_reason` regains a narrow, readable meaning: why the live session is currently waiting
  or what it is actively doing
- the attached-turn pipeline becomes easier to reason about because terminal meaning is carried by
  terminal status/result flow, not by a waiting field

### Negative

- there may be a shorter-lived or less descriptive live message in the narrow gap before terminal
  result folding completes
- tests that currently tolerate or implicitly rely on terminal placeholder text in session
  summaries will need updating

### Neutral / Follow-on

- this ADR does not change the `AgentSessionManager` ownership boundary from ADR 0170
- this ADR does not by itself solve stale projection lag; it removes one specific contradictory
  transient state

## Alternatives Considered

### 1. Keep the current behavior and treat it as a harmless presentation quirk

Rejected.

The contradiction is not merely cosmetic. It leaks an invalid mixed state into durable truth and
obscures whether a session is actually still live.

### 2. Force terminal session status synchronously during polling

Rejected for now.

That would couple the polling path more tightly to terminal state transitions and risks creating a
second terminal-write path alongside canonical result folding. The smaller and safer fix is to stop
persisting terminal placeholder text into `waiting_reason`.

### 3. Hide `waiting_reason` in the renderer whenever status is `running`

Rejected.

The renderer is not the source of truth. Papering over the contradiction in presentation would
leave the invalid state in the model and make debugging harder.

## Implementation Notes

The intended implementation slice is narrow:

- update `AttachedTurnService.collect_turn()` so it does not copy terminal placeholder progress
  messages into `record.waiting_reason`
- keep `waiting_reason` updates for `PENDING`, `RUNNING`, and `WAITING_INPUT`
- add regression coverage for the contradictory-state case at the attached-turn/service or
  projection layer

The expected repository-truth outcome is:

- no persisted session record remains `RUNNING` with `waiting_reason == "Agent session completed."`
- status/query output can still report normal live running or waiting-input states
- terminal completion remains surfaced through result folding and final session status
