# ADR 0001: Operation Loop And Event Authority

- Date: 2026-05-23

## Decision Status

Accepted

## Implementation Status

Verified

Scope: local JSONL-backed first slice.

## Context

`vibechord` is intended to inherit `operator`'s useful operation-loop model
without inheriting late authority repairs. The largest correctness risk is
split-brain state: command paths, live surfaces, and read models disagreeing
about the same operation.

## Decision

`vibechord` will use one central operation loop and one canonical operation
event authority from the first implementation tranche.

Application command handlers are the only writers of canonical operation
events. Read models, fleet rows, checkpoints, live feeds, and TUI state are
derived.

## Required Properties

- Every observable operation state transition emits a canonical event.
- Events have operation id, sequence, event id, kind, timestamp, and payload.
- Replay reconstructs operation state deterministically.
- Command ids provide idempotency for command-caused events.
- Sequence gaps and corrupt events are surfaced explicitly.
- Runtime overlays never outrank canonical replay.

## Consequences

### Positive

- Delivery surfaces share one source of truth.
- Replay and artifact inspection become first-class verification tools.
- Fleet and live views can label stale projections instead of hiding drift.

### Negative

- The first implementation must build event storage and replay earlier.
- Simple features need event tests even when local state mutation would be
  faster.

## Verification Plan

- Scenario coverage: VS-003 and VS-004 in
  [VERIFICATION-SCENARIOS.md](../VERIFICATION-SCENARIOS.md).
- Event-store contract tests.
- Replay reconstruction tests.
- Command idempotency tests.
- Sequence-gap/corruption tests.
- E2E fake harness proving operation run, command application, and replay.
