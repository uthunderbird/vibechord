# ADR 0009: Explicit Failure Action For The Operator Brain

## Status

Accepted

## Context

The operator brain previously had no explicit way to terminate an objective as failed.

The available terminal actions were:

- `stop`
- `request_clarification`

This created an ambiguity:

- `stop` implicitly meant success in the runtime,
- but the brain sometimes needed to surface a terminal failure with a concrete reason.

In practice this led to awkward outcomes where the operator could only emulate failure through a
successful stop summary or by relying on secondary evaluation behavior.

## Decision

The brain contract now includes an explicit `fail` action.

`fail` means:

- end the operation with `OperationStatus.FAILED`,
- surface the rationale as the terminal failure reason,
- and mark the focused task as failed when a task is in focus.

`stop` now means successful completion only.

## Alternatives Considered

### Option A: Keep using `stop` for both success and failure

Rejected because:

- it hides an important semantic distinction,
- weakens reports and traces,
- and makes it too easy to mislabel a failed objective as completed.

### Option B: Encode failure only through evaluation

Rejected because:

- evaluation is not the only place where terminal failure can become clear,
- and the brain sometimes needs to explicitly terminate with failure before another evaluation
  cycle adds value.

### Option C: Add an explicit `fail` terminal action

Accepted because:

- it makes success vs failure unambiguous,
- improves traceability,
- and matches how operators actually reason about terminal blockers.

## Consequences

### Positive

- The brain can surface terminal failure honestly.
- Reports and traces can distinguish success from failure directly.
- Task state can stay consistent with failed objectives.

### Negative

- Prompting, DTOs, and runtime handling all need to preserve the stronger semantic distinction.

### Follow-Up Implications

- Prompts should explicitly instruct the brain to use `stop` for success and `fail` for failure.
- Tests should cover terminal failure as a first-class path.
