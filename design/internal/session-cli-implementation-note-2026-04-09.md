# Session CLI Implementation Note

## Status

Internal implementation note.

This note translates:

- [0117-public-session-scope-cli-surface.md](/Users/thunderbird/Projects/operator/design/adr/0117-public-session-scope-cli-surface.md)
- [session-view-ui-contract-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/session-view-ui-contract-2026-04-09.md)

into a narrower implementation-oriented sketch for the first `operator session OP --task TASK`
tranche.

## Goal

Introduce a public session-scoped CLI surface without:

- requiring session UUIDs
- duplicating TUI-only logic
- degrading into transcript or forensic dump

## Proposed command shape

```text
operator session OP --task TASK [--once] [--follow] [--json] [--poll-interval SECS]
```

## Addressing flow

The command should resolve in this order:

1. resolve `OP` to an operation id using existing operation-ref rules
2. load the operation state
3. resolve `--task TASK` by:
   - task short id
   - or task UUID
4. map the resolved task to its bound session
5. build session-scoped payload from shared operation/session truth

Failure cases that must be explicit:

- operation not found
- task not found
- task exists but has no bound session
- task resolves ambiguously

## First payload sketch

The first tranche does not need a wholly separate session query service if the existing one-operation
query path can expose a normalized session block cleanly.

Recommended display-facing payload shape:

```json
{
  "operation_id": "op-...",
  "task": {
    "task_id": "...",
    "task_short_id": "task-3a7f2b1c",
    "title": "Implement ACP session runner"
  },
  "session": {
    "session_id": "...",
    "adapter_key": "codex_acp",
    "status": "running",
    "session_name": "sess-8f2a"
  },
  "session_brief": {
    "now": "validating token refresh flow",
    "wait": "agent turn running",
    "attention": "1 open policy_gap",
    "latest_output": "implemented refresh handler; moving to validation"
  },
  "timeline": [
    {
      "timestamp": "14:32",
      "glyph": "▸",
      "event_type": "agent_output",
      "summary": "agent output",
      "suffix": null
    }
  ],
  "selected_event": {
    "timestamp": "14:32",
    "event_type": "agent_output",
    "title": "agent output",
    "source": "codex_acp · sess-8f2a",
    "body": "Implemented token refresh handler. Moving to validation.",
    "changes": [
      "auth/session.py",
      "tests/auth.py"
    ],
    "artifacts": []
  },
  "transcript_hint": {
    "command": "operator log OP --follow"
  }
}
```

## Session brief sketch

`session_brief` should be normalized, not a free-form dump.

Required fields:

- `now`
- `wait`
- `attention`
- `latest_output`

Preferred rules:

- `now` should come from the best available current activity summary
- `wait` should prefer an explicit waiting reason
- `attention` should summarize only session-scoped or task-bound open attention
- `latest_output` should be short and human-readable, not raw transcript

## Timeline sketch

Timeline items should be display-oriented rather than raw event objects.

Required fields:

- `timestamp`
- `glyph`
- `event_type`
- `summary`
- optional `suffix`

Selection policy for the first tranche:

- newest first
- session-filtered where possible
- bounded list length

If session filtering is incomplete in the first tranche, the implementation must prefer task-bound
and session-bound events over generic operation-wide events.

## Selected event sketch

The CLI snapshot should show one selected event by default.

For the first tranche, default selection can simply be:

- newest relevant timeline event

Required fields:

- title / time
- source line
- concise body
- scoped changes if known
- artifacts if known

This section must stay smaller than a forensic dump.

## Renderer expectations

### Default snapshot

Must include:

- session identity
- session brief lines
- short recent event list
- one selected/latest event block
- transcript hint

Must not include:

- raw JSON
- full transcript body
- scheduler internals
- full trace record payloads

### `--follow`

The first tranche does not need a completely different semantic model for `--follow`.

It can reuse the same session snapshot blocks while:

- refreshing on poll
- redrawing idempotently
- appending only meaningfully changed live lines if a streaming mode is used

### `--json`

`--json` should emit the structured session payload directly.

The JSON contract should prefer stable field names over copying raw internal event objects.

## Reuse guidance

Prefer reuse from existing one-operation substrate:

- task resolution helpers
- session records already present in dashboard payload
- timeline events already present in dashboard payload

Do not:

- create a second session truth in the CLI layer
- make the CLI renderer reconstruct everything from raw trace records if the projection layer can do
  it once

## Suggested first file touch set

- [operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_projections.py)
- [operation_dashboard_queries.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_dashboard_queries.py)
- [main.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/main.py)
- [test_operation_projections.py](/Users/thunderbird/Projects/operator/tests/test_operation_projections.py)
- [test_cli.py](/Users/thunderbird/Projects/operator/tests/test_cli.py)

## Test targets

Minimum test targets for the first tranche:

1. resolves task short id to the bound session
2. errors cleanly when the task has no bound session
3. emits human-readable snapshot with:
   - session line
   - `Now`
   - `Wait`
   - `Recent`
   - `Selected`
   - transcript hint
4. emits JSON payload with `session_brief`, `timeline`, and `selected_event`
5. does not require session UUID in the CLI input

## Deliberate deferrals

The first tranche can defer:

- richer event selection controls
- multi-session disambiguation UX beyond `--task`
- transcript excerpt rendering beyond short summaries
- dedicated session query service extraction if the shared operation query path remains clean
