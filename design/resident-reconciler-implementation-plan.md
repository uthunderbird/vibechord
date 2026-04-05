# Resident Reconciler Implementation Plan

## Goal

Remove the need for routine manual `resume` calls in resumable mode by introducing a long-lived
reconciler over the existing persisted control plane.

## Constraints

- Attached mode remains the preferred runtime surface.
- Resumable mode remains a substrate and recovery/control path.
- Persisted operation state, wakeups, commands, and background run records remain authoritative.
- No daemon-only hidden source of truth.

## Phase 1: Reconciler Loop Extraction

Extract an internal long-lived reconciler loop that can:

- load an operation from the store,
- reconcile terminal background runs,
- claim and apply wakeups,
- drain command inboxes,
- run bounded scheduler cycles,
- persist state after each meaningful change,
- stop on terminal outcome, pause, explicit attention stop, or lease loss.

This phase should not yet require a global daemon.

## Phase 2: Public Drive Surface

Add a first CLI surface:

```bash
operator drive <operation-id>
```

Behavior:

- keep the reconciler loop alive for one operation,
- continuously consume wakeups and commands,
- automatically re-enter scheduling when the operation becomes runnable,
- exit only when the operation is terminal, explicitly paused, blocked on human attention, or the
  driver is superseded.

This is the first end-user fix for the current `resume` pain.

## Phase 3: Start-And-Drive Surface

Add a start surface that uses the same mechanism:

```bash
operator run --until-idle ...
```

Behavior:

- start a resumable operation,
- immediately attach the same drive loop,
- continue until idle / terminal / attention-required,
- keep all truth persisted exactly as in ordinary resumable mode.

This should reuse the same reconciler implementation as `drive`, not fork the runtime model.

## Phase 4: Driver Ownership And Safety

Add explicit ownership semantics for one-operation driving:

- lease or lock per operation,
- heartbeat for the current driver,
- duplicate-driver detection,
- clean lease release on exit,
- stale lease recovery.

This is required before calling the reconciler a true resident service.

## Phase 5: Resident Service Form

Promote the reconciler into a hardened resident service form over persisted truth.

Capabilities:

- continue one operation without foreground CLI babysitting,
- eventually support multiple operations,
- allow `fleet`, `dashboard`, and future TUI to observe a genuinely live substrate.

The resident service must still:

- read from the same operation store,
- consume the same wakeup and command inboxes,
- write back to the same state files,
- and expose enough metadata to remain inspectable.

## Phase 6: Observability

Surface reconciler state in CLI read models:

- current driver owner
- last driver heartbeat
- last claimed wakeup
- lease state
- last reconciliation timestamp

Targets:

- `report`
- `dashboard`
- `fleet`
- `sessions`

## Phase 7: Cleanup Bugs After Runtime Fix

After the resident consumption path exists, clean up stale read-model bugs that currently make the
runtime look more broken than it is:

- stale `outcome.summary`
- stale `runtime_alert_brief`
- terminal background runs still shown as blocking after reconciliation
- artifact/result selection drift

These should be treated as follow-up correctness work, not as substitutes for the reconciler.

## Testing Plan

Add explicit tests for:

- background completion without manual `resume`
- wakeup claim and reconciliation through the drive loop
- duplicate driver rejection
- stale lease recovery
- `run --until-idle` advancing across multiple background turns
- no second source of truth introduced by the reconciler

## Delivery Order

Recommended order:

1. internal reconciler loop extraction
2. `operator drive <operation-id>`
3. locking / lease semantics
4. `operator run --until-idle`
5. resident service hardening
6. read-model cleanup

## Non-Goals

- Do not make resumable mode the new primary user story.
- Do not replace attached mode with more background machinery.
- Do not introduce an opaque daemon-owned in-memory control plane.
