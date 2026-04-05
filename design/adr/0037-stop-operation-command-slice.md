# ADR 0037: Live Operation-Stop Command Slice

## Status

Accepted

## Context

The live command control plane already accepts a durable command inbox and deterministic
reducer for multiple operator interventions, including:

- pause/resume
- stop-agent-turn
- constraints and objective patching
- attention/policy/message flows

Users still need an explicit, non-side-path way to stop an attached operation as a whole.
Prior behavior relied on the `cancel` API for that, which is direct and outside the command
intake/runtime seam.

## Decision

`operator` will support a first-class `stop_operation` command through the existing command
command architecture and attached wait-loop control path.

The command:

- is scoped to `operation`
- requires a matching operation target
- transitions `OperationState.status` to `CANCELLED`
- sets `objective_state` status/summary consistently
- marks the command as `APPLIED` after deterministic reducer execution
- attempts to cancel the active attached session when one exists

When consumed during an attached poll loop, the loop becomes the same truth-bearing path as
other command effects and stops work once the command has changed operation status away from
`running`.

## Alternatives Considered

- Continue relying on `cancel` as the main operator-facing stop path.

Rejected because it bypasses the deterministic command lifecycle and does not keep command
history surfaced through the existing command-inbox and command inspection surfaces.

- Add a dedicated `stop` CLI verb without command enum support.

Rejected because it duplicates command payload/envelope plumbing that already exists and
does not compose cleanly with replay and trace surfaces.

## Consequences

- stop-operation is now observable, reproducible, and persisted as a command artifact.
- attached command draining now has a bounded path to terminate runs via command truth instead of
  side-channel control.
- operation stop semantics now remain within the same deterministic command architecture as pause,
  resume, and patching.
