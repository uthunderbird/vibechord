# Backlog

This file records cleanup or follow-up work that is intentionally not closed in the current ADR
wave.

## RFC 0009 closure tail

- Cut over the live operation loop to canonical event-sourced mutation.
  Current truth: new operations are born as `event_sourced`, but the main loop still persists
  mutable `OperationState` snapshots through `save_operation()` and still applies some business
  mutation outside the canonical event-append path.

- Route the full live command set through `EventSourcedCommandApplicationService`.
  Current truth: the service exists, but the live runtime still depends on snapshot-era command
  mutation for part of the command surface.

- Remove snapshot-first live persistence from `OperationDriveService` and adjacent services.
  Current truth: checkpoint/replay services exist, but the orchestration loop still treats mutable
  snapshot state as the working write path.

- Promote `ADR 0086` and `ADR 0088` from `Implemented` to `Accepted` only after the live runtime is
  event-sourced-only by repository truth.

- Promote `RFC 0009` from `Proposed` only after the event stream plus checkpoint model becomes the
  canonical live operation truth for run/resume/recover/cancel.
