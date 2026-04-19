# ADR 0008: Attached Run As Primary Runtime Mode

## Status

Accepted

## Context

The project already has a resumable persisted control plane:

- file-backed `OperationState`,
- resumable `resume` and `tick`,
- background workers and wakeup reconciliation,
- and explicit traceability for long-running work.

That substrate is valuable for recovery and inspection, but it drifted toward becoming the
primary user-facing mental model.

This created two problems:

- the normal story for using the operator started to sound like "keep resuming it,"
- and the product shape moved away from the more natural model of "run the operator until the
  goal is done or clearly blocked."

The architecture needs a clearer center of gravity:

- a preferred runtime mode for normal use,
- and a separate recovery/control mode for crash handling and inspection.

## Decision

The preferred runtime mode is now an attached long-lived `operator run`.

The resumable persisted control plane remains authoritative, but it is treated as recovery and
control substrate rather than the default product story.

### 1. Primary runtime surface

`operator run` should stay alive and keep driving the operator loop until one of:

- the objective completes,
- the objective fails,
- the operator reaches a real blocked state,
- or the process is explicitly interrupted.

**Blocking attention is a transient wait, not an exit condition.** When a blocking attention
request fires in attached mode, the attached process stays alive and polls — draining the command
inbox — until the operator answers via `operator answer <id> "..."` from a separate terminal.
When the last blocking attention is answered, the loop resumes automatically.

The process exits only on:

- terminal operation state (COMPLETED, FAILED, or CANCELLED),
- explicit user interrupt (Ctrl-C),
- or a genuine unresolvable block (e.g. the brain's evaluation decided to stop and there is no
  open attention to answer).

**Invariant for future contributors:** every `break` or early return from the attached drive loop
should be audited to confirm it falls into one of these exit categories. A break that fires on a
state that is resolvable by human command input is a UX regression.

**`operator resume` should not be run against an operation with a live attached process.** There
is no IPC channel between processes; a second `operator resume` starts a concurrent drive loop
against the same state file, risking write conflicts. While the attached process is live, use
`operator answer` to respond to blocking attention, and Ctrl-C to interrupt.

### 2. Recovery surface

`resume`, `tick`, `cancel`, `sessions`, `wakeups`, and related persisted-runtime tools remain
supported.

Their role is:

- recovery after interruption or crash,
- explicit control,
- and forensic inspection.

They are not the preferred normal-use path.

### 3. Attached-mode execution model

The first attached long-lived mode is intentionally simple:

- one active agent turn at a time,
- in-process waiting,
- no background worker subprocess for the active attached turn,
- and no reliance on `WAIT_FOR_AGENT`.

In attached mode, the operator directly starts or continues the agent turn, polls it in-process,
and collects the result before planning the next iteration.

### 4. Resumable mode

Background workers, wakeup inboxes, and reconciliation remain the mechanism for resumable mode.

They remain important because:

- persisted truth is still authoritative,
- crash recovery is still required,
- and long-lived orchestration must still be inspectable and recoverable.

### 5. `WAIT_FOR_AGENT`

`WAIT_FOR_AGENT` remains meaningful only for the resumable/background runtime.

In attached mode it is invalid, because attached runs directly await the active agent turn rather
than parking on a background dependency.

## Alternatives Considered

### Option A: Keep resumable CLI as the primary runtime model

Rejected because:

- it overweights the recovery path,
- makes the product feel more fragmented than necessary,
- and hides the more natural execution story behind repeated `resume` cycles.

### Option B: Make a long-lived process the only source of truth

Rejected because:

- crash recovery would still be required in practice,
- persisted inspectable state would become secondary,
- and existing long-lived orchestration and traceability work would lose too much value.

### Option C: Keep persisted truth authoritative, but make attached `run` the preferred runtime

Accepted because:

- it preserves recovery and transparency,
- restores the natural "operator stays alive" product shape,
- and avoids making the recovery path the center of the whole system.

## Consequences

### Positive

- The primary UX becomes simpler and more natural.
- The resumable substrate remains useful without dominating the mental model.
- The architecture gets a clearer distinction between normal execution and recovery tooling.

### Negative

- The runtime now has two execution modes that must stay behaviorally coherent.
- Tests must cover both attached and resumable mode explicitly.
- Some logic that was previously implicit in `supports_background_waits` now needs an explicit
  runtime-mode split.

### Follow-Up Implications

- `RunOptions` should carry an explicit run mode.
- `operator run` should default to attached mode.
- `resume` and `tick` should stay resumable-mode tools.
- `design/ARCHITECTURE.md` should describe attached mode as the preferred runtime surface and
  resumable mode as recovery/control substrate.
