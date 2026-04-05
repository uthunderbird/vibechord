# RFC 0005: Session/Execution Data Model For Operator Runtime

## Status

Proposed

## Context

`operator` currently persists session, background-run, focus, scheduler, and operation lifecycle
state in overlapping forms.

That overlap is most visible in cancel, pause, and recovery paths:

- `OperationState.status`
- `SessionRecord.status`
- `BackgroundRunHandle.status`
- runtime supervisor run files
- wakeups and events
- `current_focus`
- scheduler control state

All of these influence whether a run appears active, blocked, paused, cancelled, or complete.

The current model has two structural problems:

1. It mixes logical workstream state with concrete execution state.
2. It mixes desired control intent with observed runtime fact.

This makes several failure modes more likely:

- cancelling a session or background turn without fully cancelling the operation
- stale `running` projections after a turn was already cancelled or lost
- focus and scheduler projection outliving the execution they describe
- background-run files and embedded operation state acting as competing truth sources

The repository already has accepted ADRs that push in a clearer direction:

- [ADR 0007](/Users/thunderbird/Projects/operator/design/adr/0007-event-wakeup-and-wait-semantics.md)
  says events are wakeup triggers, not state authority.
- [ADR 0015](/Users/thunderbird/Projects/operator/design/adr/0015-scheduler-state-and-pause-semantics-for-attached-runs.md)
  separates scheduler control from coarse operation truth.
- [ADR 0047](/Users/thunderbird/Projects/operator/design/adr/0047-attached-background-turns-owned-by-the-live-run.md)
  makes attached/background a runtime ownership distinction, not a separate product story.

This RFC proposes a smaller canonical model for session lifecycle that fits those decisions better.

## Decision

`operator` should model session lifecycle around three canonical entities:

- `Operation`
- `Session`
- `Execution`

The runtime should also split:

- desired control intent
- observed runtime state

Attached and background execution should be modeled as execution mode, not as separate session
ontologies.

`current_focus`, blocking summaries, and scheduler state should remain persisted if useful, but they
should be treated as derived control projection rather than canonical lifecycle truth.

## Proposed Model

### 1. Operation

`Operation` remains the top-level aggregate.

It owns:

- objective and task graph
- operator control state
- sessions
- attention and command history
- derived control projection for inspection surfaces

It should not treat low-level runtime execution records as an equal peer truth source for session
lifecycle.

### 2. Session

`Session` is the durable logical workstream.

It represents:

- one reusable agent conversation or workstream identity
- adapter binding
- working directory
- external conversation reference when applicable
- operator intent for that workstream
- last observed lifecycle state for that workstream

Minimum shape:

- `session_id`
- `adapter_key`
- `working_directory`
- `conversation_ref | None`
- `reuse_policy`
- `desired_state`
- `observed_state`
- `current_execution_id | None`
- `last_terminal_execution_id | None`
- `waiting_reason | None`

`Session` must not carry a second embedded runtime ontology for background jobs.

### 3. Execution

`Execution` is one concrete turn attempt for a session.

This is the runtime unit that is closest to OS process/job semantics while still staying
cross-platform.

Minimum shape:

- `execution_id`
- `session_id`
- `mode`
- `launch_kind`
- `handle_ref`
- `observed_state`
- `started_at | None`
- `last_heartbeat_at | None`
- `ended_at | None`
- `waiting_reason | None`
- `result_ref | None`
- `error_ref | None`

Where:

- `mode` is `attached | background`
- `launch_kind` is `new | continue | recover`
- `handle_ref` is a typed runtime handle reference, not a Unix-specific PID model

### 4. Execution Handle

`ExecutionHandle` should be treated as runtime metadata attached to an execution, not as a
top-level lifecycle entity.

Examples:

- supervisor background run id
- subprocess pid
- ACP session id
- ACP prompt id
- external worker id

The domain model should not assume every execution has the same handle shape.

### 5. Control Projection

The following should be treated as derived control projection:

- `current_focus`
- scheduler state
- blocking reason
- waiting summary for `inspect`
- runnable-session or reusable-session counts

These may still be persisted for transparency and crash recovery, but they should not be the
canonical source of truth for lifecycle.

## Desired State vs Observed State

This split is required.

### Session desired state

`Session.desired_state` expresses operator intent.

Minimum states:

- `active`
- `paused`
- `stopped`

### Session observed state

`Session.observed_state` expresses reconciled runtime fact.

Minimum states:

- `idle`
- `running`
- `waiting`
- `terminal`

### Execution observed state

`Execution.observed_state` expresses the state of the current or historical concrete turn.

Minimum states:

- `starting`
- `running`
- `waiting`
- `completed`
- `failed`
- `cancelled`
- `lost`

`lost` is intentional. It covers the case where runtime truth disappeared or became unrecoverable
without a clean terminal artifact. This is more honest than silently treating disappearance as
cancelled or completed.

## Invariants

The model should preserve these invariants:

1. A session has at most one active execution at a time.
2. An execution belongs to exactly one session.
3. Session observed state is derived from:
   - current execution state
   - latest terminal execution
   - waiting reason when relevant
4. Attached vs background changes execution mode, not session identity.
5. Events and wakeups trigger reconciliation, but do not override persisted state authority.
6. Control projection must be recomputable from canonical session and execution state plus runtime
   evidence.

## Flows Covered By This Model

### Start a session turn

1. Choose a session.
2. Assert there is no active execution.
3. Create an execution with `mode=attached` or `mode=background`.
4. Launch runtime work and attach handle metadata.
5. Set:
   - `Session.desired_state = active`
   - `Session.observed_state = running`

### Poll or reconcile an execution

1. Read runtime truth from the adapter or supervisor layer.
2. Update execution observed state.
3. Derive session observed state.
4. Recompute control projection.

### Execution waits for approval or input

1. Execution remains active.
2. Execution observed state becomes `waiting`.
3. Session observed state becomes `waiting`.
4. Waiting reason records the block type.

This avoids lying by prematurely marking a session paused, cancelled, or terminal.

### Continue a logical session

Continuing the same conversation may:

- reuse the underlying external session
- or start a new concrete execution

Either way, the logical `Session` stays stable and the concrete work happens through a new or
continued `Execution`.

### Cancel a running turn

1. Set `Session.desired_state = stopped`.
2. Send termination intent to the active execution.
3. Keep execution observed state non-terminal until runtime truth confirms terminal outcome.
4. Reconcile final execution outcome.
5. Derive final session observed state from the reconciled result.

This makes cancellation a two-step control-and-observation flow rather than a blind status rewrite.

### Pause the scheduler

Scheduler pause remains an operation-level control concern.

It should not directly rewrite session or execution observed state.

This matches the intent of ADR 0015 more closely than the current mixed status model.

### Recover or reconcile orphaned work

If runtime truth still exists, reconcile it into the existing execution.

If runtime truth is gone and no clean terminal result exists, mark the execution `lost` and derive
session truth honestly from that fact.

## Relationship To Current Models

The likely migration target is:

- `SessionRecord` becomes the seed of the new `Session`
- `BackgroundRunHandle` stops being a peer lifecycle entity and becomes execution handle metadata
- active-turn runtime cache currently spread across session records and background-run maps moves
  into `Execution`
- `current_focus` and scheduler state become explicit derived projection

This RFC does not claim that current code already follows this shape.

It is a target model.

## What This RFC Intentionally Does Not Decide

This RFC does not define:

- the exact persistence schema rewrite
- exact `OperationStatus` replacement rules
- ACP-specific session semantics
- final CLI output shape
- final human approval flow

Those should be follow-up design and implementation slices.

## Alternatives Considered

### Option A: Keep the current model and tighten reducer logic

Rejected because:

- it leaves multiple competing lifecycle truth sources in place
- and would likely keep cancel/recovery semantics fragile

### Option B: Make the model entirely process or job centric

Rejected because:

- it is too close to raw runtime machinery
- and it does not represent reusable logical sessions cleanly

### Option C: Use a session/execution split with desired vs observed state

Accepted because:

- it minimizes moving parts without collapsing logical and concrete runtime identities
- it matches the accepted ADR direction
- and it gives cancel, pause, and recovery a clearer semantic foundation

## Consequences

### Positive

- Cancel, pause, and recovery can become deterministic multi-step flows instead of status rewrites.
- Attached and background modes stop competing as parallel session ontologies.
- Runtime files and handles can be reconciled into execution state instead of duplicated as peer
  lifecycle truth.
- `inspect` and list surfaces can be driven by explicit derived projection.

### Negative

- This requires a real migration of persistent state shape.
- Several current enums and summaries will need to be split or redefined.
- Existing code that assumes `SessionRecord` is both logical session and active runtime cache will
  need refactoring.

### Follow-Up Implications

- A follow-up ADR should lock the precise migration strategy from `SessionRecord` and
  `BackgroundRunHandle` to `Session` and `Execution`.
- `design/ARCHITECTURE.md` should be updated when this model moves from RFC to implementation.
- Cancel/pause/recover tests should be rewritten around invariants on desired vs observed state.
