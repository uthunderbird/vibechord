# Critique: RFC 0006 — Event Model (Round 1)

**Target**: `/Users/thunderbird/Projects/operator/design/rfc/0006-event-model.md`
**Round**: 1 of 3
**Focus**: Completeness and correctness — missing producers/consumers, incorrect or incomplete state
transitions, interface gaps, events present in code but absent from the catalog, consumers claimed
but not grounded, state effects that are wrong or underspecified.
**Grounding files read**:
- `src/agent_operator/domain/events.py`
- `src/agent_operator/domain/enums.py`
- `src/agent_operator/application/service.py` (read in full via targeted sections)

---

## Summary Assessment

The RFC identifies a genuine and important problem (observability gaps, RunEvent overloading) and
proposes a coherent taxonomy. Its architecture section is clear and well-reasoned. However, the
document contains a significant number of internal contradictions and gaps that would cause ambiguity
or errors when the repair round implements the spec:

**Strengths**:
- The three-category taxonomy (domain / trace / wakeup) is well-motivated and correctly diagnosises the root problem.
- The loop invariants section (§4) is the clearest and most actionable part of the document.
- The background on `RunEvent` overloading is accurate and matches the code.

**Weaknesses**:
- The RFC's central structural change (`category` field on `RunEvent`) is specified in prose but never reconciled with the existing `kind: RunEventKind` field on the same model. The relationship between the two fields is underspecified at the data-model level.
- `background_run.cancelled` is classified as `domain` in the catalog but emitted as `kind=RunEventKind.WAKEUP` in the existing code — a direct contradiction that the RFC does not resolve or even acknowledge.
- Several planned emit call sites target synchronous methods (`_open_attention_request`, `_append_operator_message`, `_apply_task_mutations`). The RFC does not address the refactoring required to convert these to async.
- The RFC references the non-existent `OperationStatus.NEEDS_HUMAN` value.
- `SchedulerState.DRAINING` — a real, actively-used state — is missing from the `scheduler.state.changed` state effect description.
- The task status transition table is incomplete and contains one unsupported transition.

---

## Red Team Composition

| Critic | Role and Focus |
|---|---|
| Event Catalog Auditor | Cross-checks every `_emit()` call in `service.py` against the RFC catalog; finds events in code missing from the RFC and vice versa |
| State Machine Analyst | Verifies state transition tables against `OperationStatus`, `TaskStatus`, and `SchedulerState` enums |
| Interface Contracts Inspector | Checks that claimed producers/consumers are grounded in `service.py`; flags async/sync mismatches |
| Completeness Enforcer | Looks for fields, semantics, and side-effects that are omitted or underspecified |
| Internal Consistency Checker | Detects contradictions between the RFC's own sections and between the RFC and the code |

---

## Critical Findings

### C-1: `category` field is absent from `RunEvent` and `_emit()` — the RFC's core change is unspecified at the model level

**Location**: RFC §Decision 1; `domain/events.py` line 12-23; `service.py` `_emit()` line 5050-5074.

The RFC states:

> A `category: Literal["domain", "trace"]` field is added to `RunEvent`.

The actual `RunEvent` model has no `category` field. The existing `kind: RunEventKind` field has
values `TRACE` and `WAKEUP` only — it does not have a `DOMAIN` value and is not the same as
`category`. The `_emit()` helper signature also has no `category` parameter.

The RFC never defines:
- Whether `category` is added alongside `kind` as a second field, or replaces `kind`.
- How wakeup events carry their classification (they are excluded from `category` by the RFC, yet
  `kind=WAKEUP` would still need to coexist with the new field).
- Whether `category` is optional or required, and what the Pydantic default should be.
- Whether the type error on construction (stated: "Event construction without a category should be
  a type error") applies to wakeup events too.

This is the foundational data-model change; without it being fully specified, the entire catalog
section is unimplementable without guesswork.

**Fix required**: Add a dedicated "Data model changes" subsection to RFC §Decision 1 showing the
exact updated `RunEvent` field set (both `kind` and `category`), their types, defaults, and the
relationship between them for each event category.

---

### C-2: `background_run.cancelled` is classified as `domain` but emitted as `kind=WAKEUP`

**Location**: RFC §5 "Background run events" table; `service.py` lines 235-243.

The RFC's domain event table classifies `background_run.cancelled` as `category: domain`. The
existing code emits it with `kind=RunEventKind.WAKEUP`:

```python
await self._emit(
    "background_run.cancelled",
    ...
    kind=RunEventKind.WAKEUP,
)
```

`WAKEUP` events are "ephemeral, consumed-once" by the RFC's own taxonomy. A `domain` event is
"permanent, append-only, all consumers." These two classifications are mutually exclusive.

The RFC does not acknowledge this existing WAKEUP usage, does not explain whether the WAKEUP
emission should be removed or retained alongside the domain classification, and does not describe
the migration.

**Fix required**: Explicitly resolve the classification. If `background_run.cancelled` is to become
a domain event, state that the `kind=WAKEUP` argument at the existing emit site must be changed to
the domain category. If it must remain a wakeup signal (to trigger loop re-entry), explain how
domain classification and ephemeral delivery coexist, or split it into two separate events.

---

### C-3: `NEEDS_HUMAN` does not exist in `OperationStatus`

**Location**: RFC §Context "Aggregate state transitions are unobservable," line 32.

The RFC states:

> A component that wants to know when an operation becomes `NEEDS_HUMAN` [...]

`OperationStatus` in `enums.py` contains: `RUNNING`, `COMPLETED`, `BLOCKED`, `FAILED`,
`CANCELLED`. There is no `NEEDS_HUMAN` value. The closest concept in the codebase is the operation
entering `BLOCKED` state because of a blocking attention request, combined with
`current_focus.kind = ATTENTION_REQUEST`.

Using a non-existent status value in a specification is a precision error that would confuse
implementers.

**Fix required**: Replace `NEEDS_HUMAN` with the correct description: `BLOCKED` (with focus on an
attention request), or explain that `NEEDS_HUMAN` is intended as a new status value to be introduced
by this RFC (in which case it must appear in the Decision section with an explicit enum addition).

---

## High-Priority Findings

### H-1: Planned emit call sites target synchronous methods — async refactoring is unmentioned

**Location**: RFC §Consequences "Immediate changes required"; `service.py` lines 2265-2281,
2559-2601, 3442-3493.

The RFC requires adding emits in:
- `_open_attention_request()` (for `attention.request.created`) — method is `def`, not `async def`
- `_append_operator_message()` (for `operator_message.received`) — method is `def`
- `_apply_task_mutations()` (for `task.created`) — method is `def`

`_emit()` is `async def`. Calling it from a synchronous method is not possible without `asyncio.run()`
(which cannot be used from within an event loop) or converting these methods to `async def`.

The RFC does not mention this refactoring. Callers of these three methods are numerous (e.g.
`_apply_task_mutations` is called at `service.py:310` inside an `async` loop, so conversion is
feasible but must be explicitly scoped).

**Fix required**: For each of the three methods listed above, the RFC's "Immediate changes required"
section must specify whether the method is to be converted to `async def` or whether a different
emit strategy (e.g. returning an event object to the caller for async emission) will be used.

---

### H-2: `SchedulerState.DRAINING` is absent from `scheduler.state.changed` state effect

**Location**: RFC §5 "Operation aggregate events" table, `scheduler.state.changed` row;
`enums.py` line 170-175.

`SchedulerState` has four values: `ACTIVE`, `PAUSE_REQUESTED`, `PAUSED`, `DRAINING`. The RFC's
state effect for `scheduler.state.changed` says:

> `state.scheduler_state` → `new_state`; loop exits or resumes on next drain

The word "drain" appears but `DRAINING` is never enumerated as a valid `new_state`. In the code,
`DRAINING` is set when `STOP_AGENT_TURN` is applied (line 1776) and cleared when the attached turn
completes (line 1552). It is a legitimate transition emitted through the same command path that
would trigger `scheduler.state.changed`.

Additionally, the RFC does not specify a full valid-transitions graph for `scheduler.state.changed`,
leaving it unclear whether every `scheduler_state` assignment should emit this event or only the
pause/resume path.

**Fix required**: Add `DRAINING` to the list of `new_state` values in the state effect description.
Add a transition table analogous to the task status transition table showing which
`SchedulerState` → `SchedulerState` moves emit `scheduler.state.changed`.

---

### H-3: Task status transition table is incomplete and contains one unsupported transition

**Location**: RFC §5 "Task events" transition rules.

**Missing transitions not in the table**:

1. `PENDING → READY` via `_reconcile_state` (dependency-free or all deps met at create time). The
   RFC table lists this, but `_apply_task_mutations` always sets new tasks to `PENDING` regardless
   of dependencies. The actual initial READY promotion happens in `_reconcile_state`, not at task
   creation. The RFC conflates task creation with immediate promotion to READY, creating ambiguity
   about when `task.status.changed` fires for the initial PENDING→READY transition.

2. Brain `TaskPatch` can set `task.status` to values other than `RUNNING` via `_apply_task_mutations`
   (line 3473-3474). This is a second producer for `task.status.changed` that is absent from the
   RFC's producer column (which only lists "OperatorService · any `task.status` assignment").
   Technically this is the same service, but the RFC's table implies it is always the result of
   agent execution, not a direct brain patch.

3. `RUNNING → BLOCKED` from `_handle_agent_result` when the operation enters BLOCKED (line 1520) —
   this path is listed in the table but the trigger description ("evaluation halts; or operation
   enters BLOCKED") does not distinguish the two sub-cases.

**Unsupported transition**:
- `FAILED → READY` when user issues a retry command is listed as `* (future)`. The enum supports
  it, but the RFC should mark this more visibly as not implemented in this RFC to avoid implementers
  adding it prematurely.

**Fix required**: Separate task creation (always `PENDING`) from initial READY promotion
(done by `_reconcile_state`). Add `Brain TaskPatch` as a second producer path in the task table
note. Mark `FAILED → READY` as explicitly deferred (not in scope of this RFC).

---

### H-4: `background_run.cancelled` table uses 5 columns; all other domain event tables use 4

**Location**: RFC §5 "Background run events" table.

The other domain tables have columns: `event_type | Producer | Consumers | State effect`. The
background run table adds a `Category` column between `event_type` and `Producer`:

```
| event_type | Category | Producer | Consumers | State effect |
```

This is the only table with 5 columns and is the only place where category appears inline in a
table. Either all domain event tables should have a Category column, or this one should remove it
(since all events in Section B are domain by definition, category is redundant here). The
inconsistency will confuse readers trying to extend the catalog.

**Fix required**: Either add a `Category` column to all domain event tables (appropriate if the
RFC wants to make `trace` events explicit in later tables), or remove the `Category` column from
the background run table (since all events in §5 are already domain-classified).

---

## Lower-Priority Findings

### L-1: `session.force_recovered` state effect says `session.status = IDLE` — this is not correct

**Location**: RFC §5 "Session events" table, `session.force_recovered` state effect.

The state effect listed is: "Session record reset; `session.status = IDLE`; existing execution
cleared."

`SessionStatus` in `enums.py` has `IDLE`, but the force-recovery code (`_force_recover_operation`,
lines 437-488) calls `_set_session_idle(record)` via `_handle_agent_result` → various paths. The
session status resulting from force-recovery depends on what `_handle_agent_result` sets it to
based on the synthetic result. Depending on the result status, the session could end up IDLE,
FAILED, or COMPLETED. The RFC's blanket claim of `IDLE` is imprecise.

**Fix required**: Correct the state effect to reflect the actual final session status after
force-recovery, or qualify it as "session execution cleared; session status set per reconciled
result."

---

### L-2: `operator_message.dropped` has no known emit call site in the code

**Location**: RFC §5 "Operation aggregate events" table; `service.py` `_append_operator_message`.

The RFC requires emitting `operator_message.dropped` at "buffer cap or context window expiry."
`_append_operator_message` does silently truncate the message list at 50 items (line 2280-2281):

```python
if len(state.operator_messages) > 50:
    state.operator_messages = state.operator_messages[-50:]
```

But there is no emit here and the method is synchronous (see H-1). The RFC also mentions "context
window expiry" as a drop path but there is no corresponding code path identifiable in
`service.py`. This second drop trigger is ungrounded.

**Fix required**: Identify the context-window expiry drop path explicitly (file + method name), or
acknowledge it as a future path. Confirm whether the 50-item cap path is the only current drop
path.

---

### L-3: `policy.evaluated` trigger description does not match `_refresh_policy_context` behavior

**Location**: RFC §2B "Required new domain events" table, `policy.evaluated` row.

The RFC says: trigger is "`_refresh_policy_context()` with new or changed policy."

`_refresh_policy_context` (lines 2470-2496) always overwrites `state.active_policies` — it has no
comparison against the previous policy set to determine whether anything changed. It is called
multiple times per loop cycle (before the brain call, after command drain, etc.). Emitting
`policy.evaluated` on every call would be noisy. Emitting it only when policies change requires
adding a diff check that does not currently exist.

**Fix required**: Specify whether `policy.evaluated` fires on every `_refresh_policy_context` call
or only when `state.active_policies` or `state.policy_coverage` changes. If the latter, the RFC
must require adding a change-detection step.

---

### L-4: Trace event `session.cooldown_expired` emitted as WAKEUP — category assignment missing

**Location**: RFC §2A catalog, `session.cooldown_expired` classified as `domain`; `service.py`
line 4467-4481.

`session.cooldown_expired` is listed as `domain` in the reclassification table. However, it is
emitted with `kind=RunEventKind.WAKEUP` in `_schedule_cooldown_expiry_wakeup` (line 4467-4481).
This is the same contradiction as C-2 for `background_run.cancelled`, but for a trace-labelled event.

Additionally, in `_apply_wakeup_event` (line 3309-3337), the system responds to a
`session.cooldown_expired` wakeup event by emitting `session.cooldown.reconciled`. This event is
in the catalog as `trace`. The chain of domain → wakeup → trace events here is legitimate but not
explained.

**Fix required**: Explicitly note in the catalog that `session.cooldown_expired` is a
dual-purpose event: its first emission is a WAKEUP delivery; upon consumption it produces a
`session.cooldown.reconciled` trace record. Clarify how the domain `category` interacts with
`kind=WAKEUP` for this event.

---

### L-5: Loop invariant §4.1 is inconsistent with pre-loop state mutations in `_drive_state`

**Location**: RFC §4 "Loop invariants," invariant 1; `service.py` lines 253-279.

Invariant 1 states: "`state.status ∈ {RUNNING}` at every loop iteration entry."

`_drive_state` performs several state-mutating operations before the `while` loop begins:
`_reconcile_background_wakeups`, `_drain_commands`, `_resume_blocked_operation_for_replan`,
etc. These can change `state.status` (e.g. `ANSWER_ATTENTION_REQUEST` in drain sets
`state.status = RUNNING` at line 1707, implying it could also have been non-RUNNING before).
The `while` loop condition checks `state.status is OperationStatus.RUNNING`, so if status is
not RUNNING on entry, the loop simply does not execute — the invariant is vacuously true.

More precisely: the invariant is only meaningful inside the loop body after the `while` guard has
passed. The RFC's phrasing "at every loop iteration entry" implies this, but the guarantee is
weaker than stated: it is enforced by the loop guard, not by a pre-condition on the operation's
state when `_drive_state` is called.

**Fix required**: Rephrase invariant 1 to clarify that it is enforced by the `while` guard, not
guaranteed by a pre-condition. Note that `resume()` (line 153) re-enters `_drive_state` on
operations that may be `BLOCKED`, which only proceed through the loop if commands bring them back
to `RUNNING` before the guard check.

---

### L-6: `TraceStore` listed as consumer of command events — grounding is partially wrong

**Location**: RFC §5 "Command events" table, Consumers column.

The RFC lists `TraceStore` as a consumer of `command.applied`, `command.accepted_pending_replan`,
and `command.rejected`. The code confirms this: `_mark_command_applied` (line 2153),
`_mark_command_pending_replan` (line 2191), and `_reject_command` (line 2228) all call
`self._trace_store.append_trace_record(...)` after emitting the event.

However, the RFC says consumers are those that "react to" the event. `TraceStore` here does not
react to the emitted `RunEvent` — it is called directly from the same code path as the emit, not
as an event subscriber. The description of `TraceStore` as a "consumer" is architecturally
misleading: it is a side-effectful parallel write, not an event consumer.

**Fix required**: Clarify in the Consumer roles note that `TraceStore` writes happen in the same
call frame as the emit, not via event subscription. This distinction matters if the RFC is meant
to be the basis for a future event-bus or pub/sub architecture.

---

## Recommendations

1. Add an explicit data-model diff table (showing before/after field set for `RunEvent` and
   `_emit()` signature) as a dedicated subsection before the event catalog. This is the single
   highest-leverage addition the RFC is missing.

2. Resolve the `kind=WAKEUP` vs `category=domain` conflict for `background_run.cancelled` and
   `session.cooldown_expired` before the repair round. Both require a conscious classification
   decision, not a silent fix.

3. Add an "async conversion required" note to each planned emit call site that targets a currently
   synchronous method, naming the method and its callers.

4. Add `SchedulerState.DRAINING` to the transition graph and document its emit semantics.

5. Fix the `NEEDS_HUMAN` reference in the Context section to use the correct `BLOCKED` status.

6. Normalize the Background run events table to match the column structure of all other tables.

---

## Ledger

| Field | Value |
|---|---|
| Target document | `/Users/thunderbird/Projects/operator/design/rfc/0006-event-model.md` |
| Focus | Completeness and correctness: missing producers/consumers, incorrect/incomplete state transitions, interface gaps, events in code absent from catalog, ungrounded consumers, wrong/underspecified state effects |
| Round | 1 of 3 |

**Main findings** (summary):
- `RunEvent` has no `category` field and `_emit()` has no `category` parameter — the RFC's core data-model change is unspecified at the implementation level (C-1).
- `background_run.cancelled` is classified as `domain` but emitted as `kind=WAKEUP` — direct contradiction (C-2).
- `OperationStatus.NEEDS_HUMAN` does not exist in the codebase (C-3).
- Three planned emit call sites (`_open_attention_request`, `_append_operator_message`, `_apply_task_mutations`) are synchronous — async refactoring is unaddressed (H-1).
- `SchedulerState.DRAINING` is absent from the `scheduler.state.changed` state effect (H-2).
- Task status transition table has incomplete triggers and one unsupported future transition presented as current (H-3).
- Background run events table has an inconsistent 5-column structure (H-4).
- Additional lower-priority gaps: `session.force_recovered` state effect incorrectly says `IDLE`; `operator_message.dropped` second trigger is ungrounded; `policy.evaluated` change-detection logic unspecified; `session.cooldown_expired` dual-purpose WAKEUP/domain classification unexplained; loop invariant 1 phrasing misleading; `TraceStore` as consumer is architecturally misleading.

**Ordered fix list for the repair round**:

1. Add a "Data model changes" subsection to RFC §Decision 1 with the exact updated `RunEvent` field list (both `kind` and `category`), types, defaults, and the explicit relationship between the two fields for domain, trace, and wakeup events. Include the updated `_emit()` signature.
2. Resolve the `kind=WAKEUP` vs `category=domain` conflict for `background_run.cancelled`: decide whether to remove WAKEUP, retain it alongside domain classification (with explanation), or split into two events.
3. Replace `NEEDS_HUMAN` in the Context section with `BLOCKED` (focus on attention request) or explicitly add `NEEDS_HUMAN` as a new enum value in the Decision section.
4. For each of the three synchronous methods targeted by new emits (`_open_attention_request`, `_append_operator_message`, `_apply_task_mutations`), add an explicit conversion note to the "Immediate changes required" section.
5. Add `SchedulerState.DRAINING` to the `scheduler.state.changed` state effect description and add a transition table for all `SchedulerState` moves.
6. Revise the task status transition table: separate task creation (always `PENDING`) from READY promotion (via `_reconcile_state`); add Brain `TaskPatch` as a producer path; mark `FAILED → READY` as explicitly out-of-scope for this RFC.
7. Normalize the Background run events table to 4 columns matching all other domain event tables (remove inline `Category` column or add it to all tables consistently).
8. Correct `session.force_recovered` state effect from blanket `session.status = IDLE` to reflect the actual result-dependent outcome.
9. Identify or acknowledge the "context window expiry" drop path for `operator_message.dropped`; confirm whether the 50-item cap is the only current path.
10. Clarify `policy.evaluated` emission frequency: every call vs change-detected; if change-detected, require a diff step.
11. Clarify the dual-purpose nature of `session.cooldown_expired` (WAKEUP delivery + domain record) and how `category` applies.
12. Rephrase loop invariant 1 to note it is enforced by the `while` guard, not a pre-condition on operation status when `_drive_state` is entered.
13. Add an architectural note to the command events table clarifying that `TraceStore` writes are parallel in-frame writes, not event subscriptions.
