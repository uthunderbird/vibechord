# ADR 0098: History ledger and `history` command contract

## Status

Implemented

## Extends

- [CLI UX Vision](../CLI-UX-VISION.md)
- [Workflow UX Vision](../WORKFLOW-UX-VISION.md)

## Context

The workflow vision now gives committed operation history a larger product role:

- a committed `operator-history.jsonl` ledger
- a user-facing `history` command
- a distinction between historical record and live `.operator/` runtime state

Those decisions need a narrow ADR so that implementation does not drift between workflow docs and
CLI behavior.

### Current truth

Today:

- the workflow vision already treats `operator-history.jsonl` as the committed ledger
- the intended CLI includes `history [OP]` as a primary surface
- PM/ticket integration is intentionally broader than this CLI closure wave and must stay deferred

## Decision

The CLI/workflow layer must treat committed history as a distinct user-facing ledger with one
canonical command.

### Ledger file

`operator-history.jsonl` at the git root is the canonical project history ledger.

It is:

- committed by default
- append-only
- written on terminal operation state only

### `history` command

`operator history [OP]` is the user-facing history command.

Its responsibilities are:

- project-level history listing when `OP` is omitted
- operation-specific history lookup when `OP` is provided
- human-readable default output
- `--json` for machine-readable output

### Relationship to other surfaces

`history` is not the same as `list`.

- `history` reads committed ledger truth
- `list` reads persisted operation inventory and is still useful for live/local runtime inspection

`history` is also distinct from direct `.operator/` inspection.

The committed ledger is a workflow-visible durable record, not an alias for runtime internals.

### Opt-out

Projects may opt out of the ledger explicitly through project configuration.

When disabled, `history` must explain that the ledger is not enabled rather than silently falling
back to local runtime state.

## Consequences

- The CLI gains a stable workflow-facing historical surface independent of live runtime internals.
- The workflow vision can be implemented without conflating committed record and local runtime
  state.
- Projects that do not want committed history retain an explicit opt-out.
- PM/ticket reporting can later extend the ledger without having to redefine its core purpose.

## Verification

- `tests/test_cli.py`
  - `history`
  - `history last --json`
  - disabled-ledger messaging
- `tests/test_operator_service_shell.py`
  - terminal completion appends ledger entry
- `tests/test_operation_cancellation_service.py`
  - whole-operation cancellation appends ledger entry

## Implementation Notes

- The ledger is implemented as committed `operator-history.jsonl` at the discovered workspace root.
- Entries are appended only on terminal outcomes.
- Current schema is the minimal CLI/workflow slice:
  - `op_id`
  - `goal`
  - `profile`
  - `started`
  - `ended`
  - `status`
  - `stop_reason`
- PM/ticket fields remain intentionally deferred.

## This ADR does not decide

- ticket linkage fields
- PM-provider-specific reporting behavior
- webhook payloads
- history retention or archival policy beyond append-only ledger semantics
- whether future fleet history can aggregate across repositories

## Alternatives Considered

### Treat `.operator/` state as the only history source

Rejected. The workflow vision explicitly distinguishes live runtime state from committed project
history.

### Write ledger entries at run start

Rejected. The intended historical record is about terminal outcomes, not speculative in-flight
attempts.

### Make history purely local and never committed

Rejected. The workflow vision explicitly treats shared project history as part of the product
surface, with opt-out instead of local-only default.
