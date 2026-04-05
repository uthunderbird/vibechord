# RFC 0006: Event Model

## Status

Accepted

## Context

### RunEvent is overloaded

`RunEvent` currently serves two distinct purposes that carry different semantics:

1. **Observability trace record** — a permanent, append-only log entry recording that something
   happened during an operation. Consumers (CLI, tests, future projections) may read these at any
   time without side effects.

2. **Wakeup delivery signal** — a consumed-once cross-process notification that the main loop
   should re-enter. `RunEvent(kind=WAKEUP)` is written to the event log and then consumed by the
   background worker to wake the loop. This is ephemeral: once consumed it has no further meaning.

These two uses share a single type and a single file, conflating permanence with ephemerality and
delivery to all consumers via the append-only event log with single-consumer delivery. The result is that the event log contains wakeup
records that are operationally meaningless after consumption, and readers cannot distinguish
observability records from delivery artefacts without inspecting `kind`.

### Aggregate state transitions are unobservable

There are 28 `state.status =` assignments and 19 `task.status =` assignments in `service.py`. The
overwhelming majority of these are not followed by an `_emit()` call. The consequence is that
external observers — the CLI, integration tests, and any future projection or read-model — cannot
react to state changes without polling the operation store. A component that wants to know when an
operation becomes `BLOCKED` (e.g. because a blocking attention request is open), or when a task
transitions from `PENDING` to `READY`, must
periodically re-read the store and diff the result. This is a correctness problem, not merely a
debugging inconvenience: the event log does not faithfully represent what the aggregate has done.

## Decision

### 1. Three-category event taxonomy

All events fall into exactly one of three categories:

| Event bucket | Purpose | Durability | Delivery |
|---|---|---|---|
| `domain` | Observable aggregate state transition | Permanent, append-only | All consumers |
| `trace` | Implementation-level operational record | Permanent, best-effort | Forensic/debug readers |
| `wakeup` | Cross-process loop re-entry signal | Ephemeral, consumed-once | Single consumer (loop) |

The `category` field on `RunEvent` uses only the values `"domain"` and `"trace"`; `"wakeup"` is a conceptual bucket only, not a field value.

`domain` events are the authoritative record of what the aggregate did. Any reader that wants to
reconstruct or project operation state must be able to do so from domain events alone.

`trace` events record how the system reached a decision — brain inputs and outputs, adapter
invocation details, policy evaluations, reconciliation steps. They are valuable for forensics and
debugging but do not carry semantic obligations.

`wakeup` signals are not observability records. They are delivery primitives. The tech debt path
`RunEvent(kind=WAKEUP)` is retained for now; `WakeupSignal` as a separate first-class type is
explicitly deferred until cross-restart durability requirements are revisited.

A `category: Literal["domain", "trace"]` field is added to `RunEvent`. Wakeup events continue to
use `kind=WAKEUP` and are not assigned a category.

#### Data model changes

The following shows the updated `RunEvent` field set after this RFC:

| Field | Type | Default | Notes |
|---|---|---|---|
| `kind` | `RunEventKind` (`"trace"` \| `"wakeup"`) | required | Retained as-is. Domain events use `kind="trace"` (they are not wakeup signals). `kind="wakeup"` continues to mark ephemeral delivery signals. (`RunEventKind` is defined in `domain/enums.py` as a `str`-based enum with members `TRACE` and `WAKEUP`.) |
| `category` | `Literal["domain", "trace"] \| None` | `None` | Added by this RFC. `"domain"` for observable aggregate state transitions; `"trace"` for implementation-level records. Wakeup events (`kind="wakeup"`) leave `category=None` — they are not observability records. |

Relationship between `kind` and `category`:

- `kind="trace"`, `category="domain"` — a domain event: permanent, fan-out, authoritative aggregate record.
- `kind="trace"`, `category="trace"` — a trace event: permanent, best-effort, forensic/debug record.
- `kind="wakeup"`, `category=None` — a wakeup signal: ephemeral, consumed-once, no observability role.

`category` is optional at the model level (default `None`) to preserve backwards compatibility with
existing `events.jsonl` files. However, constructing a `RunEvent` with `kind="trace"` and no
`category` must be a type error in new code — enforced via a Pydantic validator or `__init__`
guard. Wakeup events are exempt from this requirement.

The `_emit()` helper signature is updated to accept a `category` parameter. The complete
updated signature (showing all parameters, not only the new one) is:

```python
async def _emit(
    self,
    event_type: str,
    state: OperationState,
    iteration: int,
    payload: dict[str, object],
    *,
    task_id: str | None = None,
    session_id: str | None = None,
    kind: RunEventKind = RunEventKind.TRACE,
    not_before: datetime | None = None,
    dedupe_key: str | None = None,
    category: Literal["domain", "trace"] | None = None,
) -> None: ...
```

`category` is the only parameter added by this RFC. All other parameters are pre-existing and
must not be removed or reordered. Pre-existing parameter notes: `not_before` — earliest allowed
emit time, used for scheduling deferred events (e.g. cooldown expiry); `dedupe_key` — idempotency
key to suppress duplicate emits across retries. Both are defined in `service.py`.

Callers emitting domain events pass `category="domain"`. Callers emitting trace events pass
`category="trace"`. Wakeup emit sites continue to pass `kind=RunEventKind.WAKEUP` and omit
`category`.

### 2. Complete domain event catalog

#### A. Currently emitted events, reclassified by category

| event_type | category |
|---|---|
| `operation.started` | domain |
| `operation.cycle_finished` | trace |
| `brain.decision.made` | trace |
| `evaluation.completed` | trace |
| `agent.invocation.started` | trace |
| `agent.invocation.background_started` | trace |
| `agent.invocation.completed` | trace |
| `session.force_recovered` | domain |
| `session.cooldown_expired` | domain |
| `session.cooldown.reconciled` | trace |
| `command.applied` | domain |
| `command.accepted_pending_replan` | domain |
| `command.rejected` | domain |
| `background_run.cancelled` | domain |
| `background_run.reconciled_from_supervisor` | trace |
| `background_run.stale_detected` | trace |
| `background_wakeup.reconciled` | trace |
| `attached_turn.recovered` | trace |

#### B. Required new domain events

| event_type | Trigger | Priority |
|---|---|---|
| `operation.status.changed` | Any `state.status` assignment | Critical |
| `task.status.changed` | Any `task.status` assignment | Critical |
| `task.created` | Brain `new_tasks` applied | Critical |
| `attention.request.created` | `_open_attention_request()` | High |
| `attention.request.answered` | `ANSWER_ATTENTION_REQUEST` command applied | High |
| `attention.request.resolved` | Attention resolved, expired, or superseded | Medium |
| `operator_message.received` | `_append_operator_message()` | High |
| `operator_message.dropped` | 50-item buffer cap in `_append_operator_message()` (context-window expiry path deferred — no current code path) | Medium |
| `scheduler.state.changed` | Pause/resume transitions | High |
| `policy.evaluated` | `_refresh_policy_context()` — only when `state.active_policies` or `state.policy_coverage` changes relative to the previous call (change-detected, not on every call) | Medium |

**Note on `policy.evaluated`**: The Section 5 detail entry for this event is deferred. The
trigger requires adding a change-detection diff step to `_refresh_policy_context` before the
emit site can be defined precisely. The payload schema and consumer list will be specified when
that implementation work is scoped.

### 3. Loop architecture — pull-loop with in-process wakeup bridge

The main loop remains a `while` loop inside `_drive_state`. The brain is called pull-style at each
iteration: the loop assembles current state, calls the brain, receives a decision, and executes it.
There is no push path to the brain.

The polling sleep in `_wait_for_attached_wakeup` (`anyio.sleep(1.0)`) is replaced as follows:

- The file-based `WakeupInbox` is retained for cross-restart durability. Wakeup files remain the
  durable source of truth for pending signals. (`FileWakeupInbox` is the concrete implementation
  of `WakeupInbox` backed by a filesystem directory.)
- A per-operation `asyncio.Event` (in-process) is allocated when the operation's run context is
  created.
- A `WakeupWatcher` background task monitors the wakeup directory for new files belonging to the
  operation and sets the `asyncio.Event` when one lands.
- `_wait_for_attached_wakeup` awaits the `asyncio.Event` with a timeout instead of
  `anyio.sleep(1.0)`.

This eliminates the 1-second polling interval (`anyio.sleep(1.0)`) without introducing an actor
mailbox or changing the pull-loop structure.

#### WakeupWatcher specification

**Creation and supervision context**: The `asyncio.Task` for `WakeupWatcher` is created by
`run()` (or the entry point that sets up the per-operation run context — the per-operation object
allocated by `run()` that holds the `asyncio.Event` and `WakeupWatcher` task), immediately after the
per-operation `asyncio.Event` is allocated. It is owned by the same supervision scope (e.g.
`anyio.create_task_group`) that owns `_drive_state`. If no task group is in use, the task must
be stored on the run context and explicitly cancelled in a `finally` block when `_drive_state`
exits.

**Cancellation contract**: The watcher task must be cancelled (and awaited for clean teardown)
before the run context is torn down. If the task is not cancelled before the operation loop
exits, it may set the `asyncio.Event` after the loop has already returned — triggering a
spurious wakeup on a subsequent run of the same operation. Cancellation must happen in the same
`finally` block that performs other run-context cleanup.

**Startup initial scan**: On startup, before entering the watch loop, the `WakeupWatcher` must
perform a startup scan of the wakeup directory for any files belonging to this operation
that were written before the watcher task started. If any are found, the `asyncio.Event` is set
immediately. This scan may use blocking I/O only if wrapped in `anyio.to_thread.run_sync` or
equivalent; it must not block the event loop directly. This closes the TOCTOU (time-of-check/time-of-use) window between "run context created" and "watcher task
begins watching."

**Operation-id filtering**: `FileWakeupInbox` uses a flat directory shared by all operations.
The watcher must filter directory entries by `operation_id`, accepting only files whose names or
content match the current operation. The exact filename convention is defined by `FileWakeupInbox`
and must be respected by the watcher's filter predicate.

**Watch mechanism**: The watcher polls the wakeup directory at a configurable interval (default
0.5 seconds). Filesystem-event APIs (`inotify`, `kqueue`, `watchfiles`) are not required and
must not be assumed — they are not portable across all deployment targets. The polling interval
is a configuration parameter; the default is chosen to be short enough to avoid perceptible
latency while still yielding the event loop between polls.

**Error handling**: If the watcher encounters a recoverable error (e.g. a transient filesystem
read failure), it logs the error at `WARNING` level and continues. If it encounters a fatal
error (directory not found, permission denied), it logs at `ERROR` level and exits the task
without setting the event. The operation loop will eventually time out via the
`asyncio.Event.wait(timeout=)` fallback and proceed as if no wakeup arrived. The watcher must
never propagate an unhandled exception to the event loop's default exception handler.

Deferred: per-operation `asyncio.Queue` actor mailbox — explicitly deferred until parallel sessions
per operation are implemented, at which point push-to-brain semantics may become necessary.

### 4. Loop invariants

The following invariants must hold after this RFC is implemented:

1. `state.status ∈ {RUNNING}` at every loop iteration entry. This invariant is enforced by the
   `while state.status is OperationStatus.RUNNING` guard, not by a pre-condition on the
   operation's status when `_drive_state` is entered. `_drive_state` may be called on operations
   that are not yet `RUNNING` (e.g. `resume()` is called on a `BLOCKED` operation); the loop
   body simply never executes if the guard is false. Transitions out of `RUNNING` exit the loop
   before the next iteration begins.
2. Every `state.status` mutation is followed by `operation.status.changed` emission before
   `save_operation()` is called. No status assignment is silent.
3. Every `task.status` mutation is followed by `task.status.changed` emission. No task status
   assignment is silent.
4. `_drain_commands()` is idempotent — a command is applied at most once regardless of how many
   times drain is called.
5. The brain is called at most once per loop iteration. Multiple brain calls within a single
   iteration are a bug.
6. `evaluation.completed` is emitted if and only if `_execute_decision` returns without raising.
7. A wakeup signal is acked if and only if the corresponding agent result has been integrated into
   state. Acking before integration, or failing to ack after integration, violates exactly-once
   delivery.

### 5. Domain event details

This section covers domain events only. Trace events are not given detail entries; their payloads
are documented inline at their emit sites.

For each domain event: the producer (what code path emits it), the consumers (what reacts to it),
and the state effect (what aggregate field changes as a result).

Producer roles:
- **OperatorService** — the main service loop and command drain in `service.py`
- **Brain** — the LLM decision layer (via the service, not directly)
- **User/CLI** — commands submitted via `OperationCommandInbox`
- **Timer/Wakeup** — scheduled wakeup signals or cooldown expiry

Consumer roles:
- **EventSink** — always; all domain events are appended to the per-operation JSONL log
- **TraceStore** — for events that accompany a `TraceRecord` (noted explicitly below)
- **CLI / Watch** — reads the event log to render operation state without polling the store
- **OperationStore** — state is saved after the mutation that the event records
- **Future projections** — any read-model or reactive component that subscribes to the log

#### Operation aggregate events

| event_type | Producer | Consumers | State effect |
|---|---|---|---|
| `operation.started` | OperatorService · `run()` | EventSink, OperationStore | `state.status = RUNNING`; initial goal persisted |
| `operation.status.changed` | OperatorService · any status assignment | EventSink, CLI/Watch | `state.status` → `new_status`; payload carries `previous_status` (`OperationStatus`), `new_status` (`OperationStatus`), and `reason: str \| None` (optional free-text description of why the transition occurred; `None` when the cause is self-evident from context) |
| `scheduler.state.changed` | OperatorService · pause/resume/drain command handler | EventSink, CLI/Watch | `state.scheduler_state` → `new_state` (valid values: `ACTIVE`, `PAUSE_REQUESTED`, `PAUSED`, `DRAINING`); loop exits on PAUSED/DRAINING, resumes on ACTIVE |
| `attention.request.created` | OperatorService · `_open_attention_request()` | EventSink, CLI/Watch | `state.attention_requests.append(attention)`; if `blocking=True` → operation enters `BLOCKED` on next evaluate |
| `attention.request.answered` | OperatorService · `ANSWER_ATTENTION_REQUEST` handler | EventSink, CLI/Watch | `attention.status = ANSWERED`; `attention.answer` set; if was blocking → replan queued (a brain re-evaluation cycle is scheduled via the command inbox for the next loop iteration) |
| `attention.request.resolved` | OperatorService · resolve/expire/supersede paths | EventSink | `attention.status = RESOLVED / EXPIRED / SUPERSEDED`; no loop effect |
| `operator_message.received` | OperatorService · `_append_operator_message()` | EventSink, CLI/Watch | `state.operator_messages.append(msg)`; replan queued |
| `operator_message.dropped` | OperatorService · buffer cap (50-item list truncation) | EventSink | Oldest messages removed when list exceeds 50 items; `msg.dropped_from_context = True`. The `dropped_from_context: bool` field on `OperatorMessage` (defaulting `False`) is set to `True` when the message is evicted from the active context window; it does not affect routing or context building for other messages. This field is introduced by this RFC. **Cardinality**: exactly one `operator_message.dropped` event must be emitted per dropped message — do not emit a single aggregate event for multiple drops; do not batch. The current drop logic in `_append_operator_message` appends one message then truncates, so overflow is always exactly 1 item per call. |

Scheduler state transition rules (all moves emit `scheduler.state.changed`):

```
ACTIVE           → PAUSE_REQUESTED  when PAUSE_OPERATOR command applied
PAUSE_REQUESTED  → PAUSED           when the in-progress agent turn drains
PAUSE_REQUESTED  → ACTIVE           when RESUME_OPERATOR command applied before drain completes
PAUSED           → ACTIVE           when RESUME_OPERATOR command applied
ACTIVE           → DRAINING         when STOP_AGENT_TURN command applied
DRAINING         → ACTIVE           when the attached turn completes and is cleared
```

#### Task events (embedded in Operation aggregate)

| event_type | Producer | Consumers | State effect |
|---|---|---|---|
| `task.created` | OperatorService · `_apply_task_mutations()` from Brain | EventSink, CLI/Watch | `state.tasks.append(task)`; task always enters `PENDING`; promotion to `READY` occurs later via `_reconcile_state` |
| `task.status.changed` | OperatorService · any `task.status` assignment | EventSink, CLI/Watch | `task.status` → `new_status`; payload carries `task_id`, `previous_status`, `new_status`; COMPLETED propagates to dependents |

Task status transition rules (enforced by the service, recorded by `task.status.changed`):

```
(creation)  → PENDING    always, when brain new_tasks are applied via _apply_task_mutations
PENDING     → READY      when _reconcile_state determines all dependencies are COMPLETED
             (not at creation time; promotion happens at reconcile, not at task creation)
PENDING     → CANCELLED  when operation is cancelled
READY       → RUNNING    when brain assigns an agent and starts a turn
RUNNING     → COMPLETED  when agent result is SUCCESS and brain accepts it
RUNNING     → FAILED     when agent result is FAILED or brain rejects after max retries
RUNNING     → BLOCKED    (sub-case A) when evaluation halts and the operation enters BLOCKED
             (sub-case B) when the operation independently transitions to BLOCKED status
BLOCKED     → READY      when a blocking attention request is answered and replan runs
* → CANCELLED            when operation is cancelled
```

Note: Brain `TaskPatch` (via `_apply_task_mutations`) is a second producer path for
`task.status.changed`. The Brain may directly patch `task.status` to values other than `RUNNING`
through this path. The RFC's table producer column covers this because the service always mediates
Brain decisions, but implementers should be aware that the origin may be a Brain patch rather than
an agent execution outcome.

`FAILED → READY` (retry command) is explicitly **out of scope for this RFC**. The enum supports
the transition but no command handler implements it. Implementers must not add this path when implementing this RFC.

#### Session events (sub-entity of Operation)

| event_type | Producer | Consumers | State effect |
|---|---|---|---|
| `session.force_recovered` | OperatorService · `recover()` | EventSink | Session execution cleared; session status set per reconciled synthetic result (IDLE, FAILED, or COMPLETED depending on result path) |
| `session.cooldown_expired` | Timer wakeup · `_schedule_cooldown_expiry_wakeup()` | EventSink, loop | `session.cooldown_until` cleared; session becomes eligible for new turns. **Dual-purpose**: the event is initially emitted with `kind=WAKEUP` to trigger loop re-entry; upon consumption in `_apply_wakeup_event`, a `session.cooldown.reconciled` trace event is emitted. The first emission is ephemeral delivery; the `domain` category applies to the intent (the cooldown expired and the session state changed), but `kind=WAKEUP` remains on the emit to preserve the delivery mechanism. This duality is an acknowledged tech debt; see Tech debt section. |

#### Command events (input, not an aggregate)

Commands are user intent. The event records the outcome of applying the command to the operation
state. Commands do not carry state themselves — the state effect is always on an aggregate.

| event_type | Producer | Consumers | State effect |
|---|---|---|---|
| `command.applied` | OperatorService · `_mark_command_applied()` | EventSink, TraceStore | Command acknowledged; aggregate mutation already complete at emit time |
| `command.accepted_pending_replan` | OperatorService · `_mark_command_pending_replan()` | EventSink, TraceStore | Command recorded; mutation will be applied at next brain decision cycle |
| `command.rejected` | OperatorService · `_reject_command()` | EventSink, TraceStore | No state change; rejection reason recorded |

**Note on TraceStore as consumer**: `TraceStore` is listed as a consumer of command events because
`_mark_command_applied`, `_mark_command_pending_replan`, and `_reject_command` each call
`self._trace_store.append_trace_record(...)` alongside the `_emit()` call. However, `TraceStore`
does **not** subscribe to the event bus — it is written in the same call frame as the emit, as a
parallel side-effect, not as a downstream event consumer. If this RFC is later used as the basis
for a pub/sub or event-bus architecture, `TraceStore` must be treated as a direct write dependency,
not an event subscriber.

#### Background run events

| event_type | Producer | Consumers | State effect |
|---|---|---|---|
| `background_run.cancelled` | OperatorService · `cancel()` | EventSink | `session.status = CANCELLED`; run record closed |

**Note on `background_run.cancelled` classification**: The existing emit site uses
`kind=RunEventKind.WAKEUP`. This RFC reclassifies the event as `category="domain"` — it is a
permanent aggregate record, not an ephemeral delivery signal. The `kind=WAKEUP` argument at the
existing emit site must be changed to `kind=RunEventKind.TRACE, category="domain"` as part of the
Immediate changes required in this RFC. The loop re-entry effect that was previously triggered by
the WAKEUP kind at this site should be verified and, if needed, replaced with an explicit wakeup
signal emitted separately rather than piggy-backing on the domain event.

#### Aggregate event ownership summary

```
Operation aggregate owns:
  operation.started, operation.status.changed, scheduler.state.changed,
  attention.request.created, attention.request.answered, attention.request.resolved,
  operator_message.received, operator_message.dropped

Task (embedded in Operation) owns:
  task.created, task.status.changed

Session (sub-entity of Operation) owns:
  session.force_recovered, session.cooldown_expired

Command input owns:
  command.applied, command.accepted_pending_replan, command.rejected

Background run sub-entity owns:
  background_run.cancelled
```

Trace events are not owned by an aggregate. They record the behaviour of the service layer and
infrastructure components and are attributed to an operation by `operation_id` only.

## Consequences

### Atomicity and failure model

`_emit()` and `save_operation()` are two distinct I/O steps. This RFC adopts **emit-then-save** ordering (Invariant 2). The following failure contract applies:

**Failure direction A — emit succeeds, save fails**: The event is written to the JSONL log; the store retains the old state. On crash-and-restart the service re-applies the same transition and emits the event again. Consumers will see the domain event twice. This is **the accepted trade-off**: `EventSink` implementations must be idempotent or duplicate-tolerant. Readers that reconstruct operation state from the domain event log must handle duplicate events (e.g. by keying on `event_id` or accepting last-write-wins for status fields). The event-sourcing guarantee ("reconstruct state from domain events alone") holds only for readers that handle duplicates.

**Failure direction B — save succeeds, emit raises**: The store holds the new state; the event log is silent. This is the worse failure direction. The implementation must treat an `_emit()` raise as a non-fatal error: log the error, do **not** abort the loop, and do not roll back the in-memory state. Observability is degraded for that transition; correctness of the loop is preserved. Implementers must not place `_emit()` inside a transaction that also covers `save_operation()`.

**Behaviour when `_emit()` raises**: Catch the exception, log it at `ERROR` level, and continue. Do not re-raise from the call site. Do not retry automatically (retrying may produce duplicates under Failure direction A semantics).

**In-memory vs. on-disk state split**: Between a state mutation and `save_operation()`, the in-memory `state` object is ahead of the on-disk store. If `_emit()` raises in this window, the state is already mutated in memory but not yet persisted. Subsequent code in the same call frame will see the mutated in-memory state (the loop does not reload from the store on each iteration). This split is accepted: the loop is the only writer, and in-memory state is authoritative within a single run. The risk is loss of the transition if the process crashes after the mutation but before `save_operation()` — this is pre-existing behaviour, not introduced by this RFC.

### Immediate changes required

- Add `category: Literal["domain", "trace"]` field to `RunEvent`. Existing `_emit()` call sites
  must be updated to supply the correct category. Event construction without a category should be
  a type error.
- Wrap all 28 `state.status =` mutations in `service.py` with an `operation.status.changed`
  domain event emit immediately before `save_operation()`. The payload must include at minimum
  `previous_status` and `new_status`.
- Wrap all 19 `task.status =` mutations with a `task.status.changed` domain event emit. The
  payload must include `task_id`, `previous_status`, and `new_status`.
- Add `task.created` emit in the path where brain `new_tasks` are applied.
  **Async note**: `_apply_task_mutations()` is currently `def`, not `async def`. It must be
  converted to `async def`. Its caller must be updated to `await` it. Known call site in
  `service.py` that requires updating:
  - Line 310 — inside the async loop in `service.py` (the only call site).
- Add `attention.request.created`, `attention.request.answered`, and
  `attention.request.resolved` emits at the corresponding call sites in `service.py`.
  **Emit placement for `attention.request.created`**: `_open_attention_request` contains an
  idempotency guard — if a matching open or answered attention request already exists, it returns
  the existing one without creating a new one. The `attention.request.created` emit must be
  placed **inside the creation branch only** (the path where a new request object is constructed
  and appended). Placing the emit unconditionally after the call, or at the call sites, will
  produce double-emission on every idempotent invocation.
  **Async note**: `_open_attention_request()` is currently `def`, not `async def`. It must be
  converted to `async def` before `_emit()` can be called inside it. All known call sites in
  `service.py` that require updating:
  - Line 688 — decision-execution path
  - Line 2628 — `_attention_from_incomplete_result` (first path, `agent_waiting_input`)
  - Line 2645 — `_attention_from_incomplete_result` (second path)
  - Line 2703 — dedicated helper method
  - Line 2730 — dedicated helper method
  All five call sites must be converted to `await self._open_attention_request(...)`. If any new
  call site is added before this RFC is implemented, it must also be converted.
- Add `operator_message.received` emit in `_append_operator_message()`.
  **Async note**: `_append_operator_message()` is currently `def`, not `async def`. It must be
  converted to `async def`. Known call site in `service.py` that requires updating:
  - Line 2107 — inside the command handler that processes operator messages.

**Note on async conversions above**: For all async conversions listed in this section
(`_apply_task_mutations`, `_open_attention_request`, `_append_operator_message`), no test or fake
files call these methods directly; all changes are confined to `service.py`.
- Add `operator_message.dropped` emit at each drop path (50-item buffer cap). See Tech debt
  section for the context-window expiry path.
  **Cardinality**: Exactly one `operator_message.dropped` event must be emitted per dropped
  message. The current drop logic in `_append_operator_message` appends one message then
  truncates, so overflow is always exactly 1 item per call — emit exactly one event carrying the
  identity of the dropped message. Do not emit a single aggregate event for multiple drops; do
  not batch.
  **Async note**: The `operator_message.dropped` emit also requires `_append_operator_message`
  to be `async def` (see above).
- Add `scheduler.state.changed` emit at each pause and resume transition.
- Replace `anyio.sleep(1.0)` in `_wait_for_attached_wakeup` with `asyncio.Event.wait(timeout=)`
  driven by a `WakeupWatcher` background task.
- **`policy.evaluated` (deferred)**: The `policy.evaluated` domain event listed in Section 2B
  is not implemented as part of this RFC. Implementation requires adding a change-detection diff
  step to `_refresh_policy_context` to compare `state.active_policies` and `state.policy_coverage`
  against their previous values. This work is deferred until the Section 5 detail entry is
  completed. Do not add the emit call when implementing the other changes above.

### Tech debt registered

- `operation.cycle_finished` should eventually be renamed `operation.process_run_ended` to
  reflect that it records the end of a single process run within a potentially multi-run
  operation, not the completion of a planning cycle. Rename is deferred to avoid churn; the
  event type string is not yet relied upon by external consumers.
- `RunEvent(kind=WAKEUP)` should become a separate `WakeupSignal` type with its own storage path,
  removing it from the domain event log entirely. Deferred until the wakeup delivery mechanism is
  redesigned for parallel session support.

  **Normative resolution for `session.cooldown_expired` today**: Until the wakeup delivery
  mechanism is redesigned, implementations must emit two separate events at the cooldown expiry
  point: (1) a `kind=WAKEUP, category=None` signal for loop re-entry (delivery), and (2) a
  separate `kind=RunEventKind.TRACE, category="domain"` event with `event_type="session.cooldown_expired"`
  for observability (the authoritative domain record that the cooldown expired and session state
  changed). The wakeup signal is ephemeral and consumed-once; the domain record is permanent and
  fan-out. Do not conflate the two into a single emit call.

- `operator_message.dropped` is currently triggered only by the 50-item buffer cap in
  `_append_operator_message`. A second trigger — "context window expiry" — was originally cited
  in this RFC but no corresponding code path exists in `service.py`. The context-window expiry
  drop path is deferred as a future item and should be added to this event's trigger description
  when implemented.

- `JsonlEventSink.emit()` performs synchronous file open/write/close inside an `async def`
  without `anyio.to_thread.run_sync` or equivalent. This blocks the event loop on every emit
  call. RFC 0006 adds approximately 47 new domain event emit calls (28 `operation.status.changed`
  + 19 `task.status.changed` + ~10 new domain events), making this I/O contention materially
  worse. `ProjectingEventSink` in `events.py` has the same issue: `self._on_event(event)` is
  called synchronously after the underlying async emit. Both sinks should eventually use
  `anyio.to_thread.run_sync` (or an async I/O path) for their write operations. Deferred until
  event volume under load is profiled and the blocking behaviour causes a measurable regression.

### No migration needed

There are no external consumers of the event log. The `category` field addition is additive.
Existing `events.jsonl` files written before this change lack the field; readers should treat
absent `category` as `"trace"` for backwards compatibility.

**Silent-downgrade caveat**: Pre-existing domain events in historical `events.jsonl` files —
including `operation.started`, `command.applied`, `command.accepted_pending_replan`,
`command.rejected`, `session.force_recovered`, `session.cooldown_expired`, and
`background_run.cancelled` — were emitted before this RFC and carry no `category` field. The
backwards-compat default of `"trace"` will cause readers to skip them when filtering for domain
events. Readers that reconstruct operation state from the event log must also process events
whose `event_type` matches any domain event listed in Section 2A regardless of the absent
`category` field, using `event_type` as the discriminator. The schema is backwards-compatible;
the semantic guarantee for historical logs requires this additional discriminator logic.
