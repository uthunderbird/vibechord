# Critique: RFC 0006 — Event Model (Round 2)

**Target document**: `design/rfc/0006-event-model.md`
**Focus**: Execution order, failure modes, and implementation adequacy
**Method**: Swarm Red Team — 5 experts, round-robin + Q&A + sub-group
**Round**: 2 of 3

---

## Summary Assessment

RFC 0006 has a sound architectural intent: separating observability domain events from ephemeral
wakeup signals and ensuring all aggregate state transitions are observable. The taxonomy and
event catalog are clear. However, the RFC is under-specified in three areas that will produce
incorrect implementations if not addressed:

**Strengths**:
- Three-category taxonomy (`domain` / `trace` / `wakeup`) is coherent and well-motivated
- Loop invariants (section 4) provide a useful contract frame
- Complete event catalog with producer/consumer/state-effect is implementer-friendly
- Tech debt section is honest about deferred items

**Critical weaknesses**:
- No atomicity model for the emit+save pair; failure modes in both directions are unaddressed
- Async conversion scope is severely understated (6 call sites for `_open_attention_request` alone;
  RFC implies one)
- `WakeupWatcher` proposed without workable specification (lifecycle, startup scan, filtering,
  mechanism all absent)

**Lower-priority weaknesses**:
- Factual error: RFC says "replace `asyncio.sleep(0.05)`"; actual code uses `anyio.sleep(1.0)`
- Proposed `_emit()` signature omits `state: OperationState` and `iteration: int` — incomplete
- `operator_message.dropped` does not specify per-event vs. batch emission
- `JsonlEventSink` blocking I/O grows more acute as RFC adds ~47 new emit call sites
- No idempotency requirement on `EventSink`; double-emission from partial-failure retry is silent

---

## Red Team Composition

| Expert | Role | Focus |
|---|---|---|
| DSS — Distributed Systems Skeptic | Ordering guarantees, atomicity, partial failure | Emit+save pair, event log consistency |
| PR — Protocol Rigorist | Spec completeness and precision | Invariant language, async conversion scope, actionability |
| ACA — Async/Concurrency Auditor | Coroutine safety, wakeup races, scheduler interaction | WakeupWatcher spec, sleep interval, blocking I/O |
| FMA — Failure-Mode Analyst | Rollback, error propagation, in-memory vs on-disk split | Ack failures, in-memory mutation without save, command event loss |
| IGR — Implementation Grounding Reviewer | RFC vs live code discrepancies | Call-site counts, actual sleep value, `_emit` signature |

---

## Critical Findings

### C-1: No atomicity model for the emit+save pair

**Invariant 2** establishes emit-before-save as required ordering for `operation.status.changed`.
The RFC does not specify what happens when this two-step sequence partially fails.

**Failure direction A: emit succeeds, save fails**

Event is written to the JSONL log. `save_operation()` raises. Store still holds the old state.
On crash-and-restart, the store is reloaded (it is the source of truth for replay). The service
will re-apply the transition and emit the event again. Consumers see the domain event twice.
`JsonlEventSink` has no deduplication. The RFC claims "any reader that wants to reconstruct
operation state must be able to do so from domain events alone" — but that claim is violated if
events can be duplicated without any idempotency marker.

**Failure direction B: save succeeds, emit raises**

Store holds the new state. Event log is silent. There is no catch-up mechanism. The RFC's
observability guarantee is permanently broken for this transition. No reconciliation path exists
and the RFC does not register this as tech debt.

**What the RFC should state**: Either (a) adopt store-then-emit order and require that emits be
idempotent (or silently dropped on retry), or (b) adopt emit-then-store order and declare that
duplicate events are possible and readers must be idempotent. Neither is stated. The RFC should
also specify the required behaviour when `_emit()` itself raises.

### C-2: Async conversion scope is severely understated

The Consequences section says: "Callers of `_open_attention_request` (e.g. inside the
decision-execution path in `service.py`) must be updated to `await` the converted method."

**Actual call sites of `_open_attention_request` in `service.py`** (verified via grep):
- Line 688 — decision execution path
- Line 2628 — `_attention_from_incomplete_result` (incomplete result code=`agent_waiting_input`)
- Line 2645 — `_attention_from_incomplete_result` (incomplete result, second path)
- Line 2703 — dedicated helper method
- Line 2730 — dedicated helper method
- Plus the definition at line 2559

There are at least **5 call sites** that must be converted to `await`. The RFC's "e.g." framing
implies one. Any implementer who updates only the decision-execution path will produce runtime
`TypeError: object NoneType is not awaitable` errors in the other four paths.

The same understatement applies to `_append_operator_message` and `_apply_task_mutations`:
the RFC lists their callers as a generic "must be updated" without enumerating them. Implementers
must perform a full call-graph audit that the RFC should have already done.

Additionally, the RFC does not address callers outside `service.py`. Tests, fakes, and any
integration harness that calls these methods synchronously will break silently or raise at runtime.

### C-3: WakeupWatcher proposed without workable specification

The RFC introduces `WakeupWatcher` as the replacement for `asyncio.sleep(0.05)` but provides
only five sentences of description. The following are unspecified:

1. **Lifecycle**: Which component creates the `asyncio.Task`? Where is it started (in `run()`,
   `_drive_state()`, or the bootstrap)? What supervision context owns it? When is it cancelled?
   If not cancelled when `_drive_state` exits, the task leaks and may set the `asyncio.Event`
   after the operation loop has exited, triggering a spurious re-entry on the next run.

2. **Startup scan**: There is a TOCTOU window between "run context created" and "watcher task
   begins watching the directory." If a wakeup file was written during a previous shutdown, the
   `asyncio.Event` will never be set (the watcher only reacts to new files). The RFC does not
   specify whether the watcher performs an initial scan on startup or whether this gap is covered
   by the existing `list_pending` poll in `_wait_for_attached_wakeup`.

3. **Operation filtering**: `FileWakeupInbox` uses a flat directory shared by all operations
   (all files in one `root` directory). The `WakeupWatcher` must filter by `operation_id` when
   scanning. This is not mentioned in the RFC.

4. **Watch mechanism**: "Monitors the wakeup directory" does not specify how. Options include
   polling, `inotify`/`kqueue`, or a library like `watchfiles`. The RFC does not state which
   mechanism is required, at what poll interval, or what fallback applies on platforms that do
   not support filesystem events.

5. **Error handling**: If the watcher task raises (directory not found, permission error,
   cancelled from outside), does the operation silently stop receiving wakeups? Does it crash?
   The RFC does not specify.

---

## Lower-Priority Findings

### L-1: Factual error — sleep interval

The Consequences section states: "Replace `asyncio.sleep(0.05)` in `_wait_for_attached_wakeup`
with `asyncio.Event.wait(timeout=)` driven by a `WakeupWatcher` background task."

The actual code at service.py line 1055 uses `anyio.sleep(1.0)`, not `asyncio.sleep(0.05)`.
The RFC is describing an outdated state of the codebase. The motivation ("eliminates the 50 ms
polling interval") is therefore incorrect — the actual polling interval being eliminated is 1
second. This does not change the validity of the proposal, but it undermines confidence in the
RFC's grounding.

### L-2: Proposed `_emit()` signature is incomplete

The RFC's proposed signature is:

```python
async def _emit(
    self,
    event_type: str,
    payload: dict | None = None,
    *,
    kind: RunEventKind = RunEventKind.TRACE,
    category: Literal["domain", "trace"] | None = None,
) -> None: ...
```

The live signature at service.py line 5050 is:

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
) -> None: ...
```

The RFC's snippet omits `state`, `iteration`, `task_id`, `session_id`, `not_before`, and
`dedupe_key`. An implementer following only the RFC's code block will produce an incompatible
signature. The RFC should either show the complete updated signature or explicitly label the
snippet as partial.

### L-3: `operator_message.dropped` — per-event vs. batch ambiguity

The Consequences section says "Add `operator_message.dropped` emit at each drop path (50-item
buffer cap)." The actual drop logic at service.py line 2281 is:

```python
if len(state.operator_messages) > 50:
    state.operator_messages = state.operator_messages[-50:]
```

Because `_append_operator_message` appends one message and then truncates, the overflow is always
exactly 1 item per call. The RFC's phrase "oldest messages removed" (plural) is misleading. More
importantly, the RFC does not state whether one `operator_message.dropped` event should be emitted
per dropped message or one aggregate event per truncation call. This ambiguity affects both the
implementation and any reader that counts dropped messages.

### L-4: `JsonlEventSink` blocking I/O grows with RFC additions

`JsonlEventSink.emit()` performs synchronous file open/write/close inside an `async def` without
`asyncio.to_thread` or `anyio.to_thread.run_sync`. This blocks the event loop on every emit call.

RFC 0006 proposes adding approximately 47 new domain event emit calls (28 `operation.status.changed`
+ 19 `task.status.changed` + 10 new domain events). Under any I/O pressure, each of these will
block the loop. The RFC does not mention this concern, does not require the `EventSink`
implementation to be non-blocking, and does not register it as tech debt.

`ProjectingEventSink` in `events.py` has the same issue: `self._on_event(event)` is called
synchronously after the underlying async emit.

### L-5: No idempotency requirement on `EventSink`

`JsonlEventSink` is a plain append with no deduplication. The RFC does not require or define
idempotency semantics for `EventSink.emit()`. If a partial failure (Finding C-1) triggers a
retry, the event is appended twice. Readers have no way to detect this. The RFC should either
require `EventSink` implementations to be idempotent (e.g., via deduplication on `event_id`) or
explicitly declare that duplicate events are possible and define reader responsibility.

### L-6: `_open_attention_request` idempotency interacts with emit

`_open_attention_request` has an idempotency guard: if a matching open/answered attention request
already exists, it returns the existing one without creating a new one. After the async conversion,
the emit for `attention.request.created` must fire only when a new request is actually created,
not on the idempotent return path. The RFC does not call this out. An implementer who places the
emit unconditionally after the call (rather than inside the creation branch) will double-emit
`attention.request.created` on idempotent calls.

### L-7: In-memory vs. on-disk state split is unacknowledged

If `_emit()` is added between a state mutation and `save_operation()`, a failure in `_emit()`
leaves the in-memory `state` object mutated but the on-disk store unchanged. `state` is passed
by reference throughout `service.py`. Subsequent code in the same call frame sees the mutated
in-memory state. On the next loop iteration, state is not re-loaded from the store — the
in-memory object is the working state. This creates a silent inconsistency: in-memory says the
task is COMPLETED; the store says it is RUNNING. The RFC does not acknowledge this split or
specify whether the implementation should snapshot before mutating, abort the loop on emit
failure, or accept the inconsistency.

---

## Recommendations

1. **Add an atomicity section** to the Consequences block. State explicitly: (a) the failure
   model (emit-then-save; duplicates possible on retry), (b) that `EventSink` implementations
   must be idempotent or duplicate-tolerant, and (c) what happens when `_emit()` raises (log and
   continue vs. abort loop vs. retry). Until this is specified, implementers will make different
   choices, producing divergent behaviour.

2. **Enumerate all call sites for each async conversion**. For `_open_attention_request`, list
   all 5+ call sites. For `_append_operator_message` and `_apply_task_mutations`, do the same.
   For each, note whether tests and fakes also need updates.

3. **Write a `WakeupWatcher` mini-spec** (even a single paragraph per bullet):
   - Creation point and supervision context
   - Cancellation contract (tied to operation lifecycle)
   - Startup initial scan requirement
   - Operation-id filtering requirement
   - Watch mechanism choice (polling interval or filesystem event library)
   - Error-handling contract

4. **Correct the sleep interval claim**: Change "Replace `asyncio.sleep(0.05)`" to
   "Replace `anyio.sleep(1.0)`" in the Consequences section.

5. **Show the complete updated `_emit()` signature** (all parameters, not just the added one).

6. **Clarify `operator_message.dropped` cardinality**: Specify that exactly one event is emitted
   per dropped message (even though in practice this is always one per `_append_operator_message`
   call that overflows).

7. **Add a note on `_open_attention_request` emit placement**: The emit for
   `attention.request.created` must be placed inside the creation branch (not on the idempotent
   return path). Explicitly state this in the Consequences bullet.

8. **Register blocking `EventSink` I/O as tech debt**: The RFC adds ~47 new emit calls to a
   synchronous-I/O event sink. This should be registered under Tech Debt with a forward note
   that `JsonlEventSink.emit()` should eventually use `anyio.to_thread.run_sync`.

---

## Compact Ledger

**Target document**: `design/rfc/0006-event-model.md`

**Focus used**: Execution order, failure modes, and implementation adequacy: emit-before-save
ordering hazards, partial-failure scenarios, missing rollback semantics, async method conversion
requirement, WakeupWatcher spec adequacy, Consequences section actionability.

**Main findings**:

| ID | Severity | Finding |
|---|---|---|
| C-1 | Critical | No atomicity model for emit+save; both failure directions (emit-OK/save-fails and save-OK/emit-fails) are unaddressed; no rollback semantics; no idempotency spec |
| C-2 | Critical | Async conversion scope understated: `_open_attention_request` has 5+ call sites; RFC implies one with "e.g."; other two converted methods similarly underspecified |
| C-3 | Critical | `WakeupWatcher` lacks: lifecycle/cancellation, startup scan, operation-id filtering, watch mechanism, error handling |
| L-1 | Low | Factual error: RFC says `asyncio.sleep(0.05)`; code uses `anyio.sleep(1.0)` |
| L-2 | Low | Proposed `_emit()` signature omits 6 existing parameters; incomplete |
| L-3 | Low | `operator_message.dropped` cardinality (per-event vs. batch) unspecified |
| L-4 | Low | `JsonlEventSink` blocking I/O grows from ~47 new emit calls; not registered as tech debt |
| L-5 | Low | No `EventSink` idempotency requirement; double-emission on retry is silent |
| L-6 | Low | Emit for `attention.request.created` must be inside creation branch, not on idempotent return; RFC does not call this out |
| L-7 | Low | In-memory vs. on-disk state split after emit failure is unacknowledged |

**Exact ordered fix list for the repair round**:

1. Add an atomicity/failure-model section to Consequences: choose emit-then-save or save-then-emit, specify duplicate/idempotency contract, specify behaviour when `_emit()` raises.
2. Enumerate all call sites for `_open_attention_request` (5+), `_append_operator_message`, and `_apply_task_mutations`; note test/fake impact.
3. Write a `WakeupWatcher` mini-spec covering: creation + supervision context, cancellation contract, startup initial scan, operation-id filtering, watch mechanism, error handling.
4. Fix sleep interval claim: `anyio.sleep(1.0)` not `asyncio.sleep(0.05)`.
5. Show complete updated `_emit()` signature (all parameters, not just `category`).
6. Clarify `operator_message.dropped` cardinality: one event per dropped message.
7. Add note in Consequences: emit for `attention.request.created` goes inside the creation branch only (not on idempotent return path).
8. Register blocking `JsonlEventSink.emit()` as tech debt with note that ~47 new emit calls are added by this RFC.
