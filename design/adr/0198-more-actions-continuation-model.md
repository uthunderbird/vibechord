# ADR 0198: more_actions Continuation Model — MemGPT-Style Multi-Action Wake Cycles

- Date: 2026-04-21

## Decision Status

Accepted

## Implementation Status

Verified

Skim-safe status on 2026-04-23:

- `implemented`: `BrainDecision` carries `more_actions`
- `implemented`: `PolicyExecutor` records `more_actions` and `wake_cycle_id` in
  `brain.decision.made`
- `implemented`: `DriveService` continues within one wake cycle without an intermediate
  checkpoint when `more_actions=True`, bounded by `max_consecutive_actions`
- `implemented`: brain-facing `recent_decisions` context is now seeded from replayed
  `brain.decision.made` events and extended across in-wake-cycle continuation sub-calls
- `verified`: targeted drive-loop tests cover shared wake-cycle ids, skipped intermediate
  checkpoints, the continuation guardrail, and `recent_decisions` continuity across replay and
  `more_actions` sub-calls
- `verified`: decision prompting now exposes explicit recent-decision history so the brain can see
  its own near-term action loop context
- `verified`: full repository suite passed on 2026-04-23 via `uv run pytest`
  (`894 passed, 11 skipped`)

## Context

In v1 and early v2 design, each brain call produces exactly one action, after which the drive loop:
1. Executes the action
2. Saves a checkpoint
3. Returns to the wakeup/sleep cycle (in RESUMABLE mode) or continues to the next iteration (in ATTACHED mode)

This one-action-per-cycle model creates a specific problem: a brain that wants to perform a short sequence of actions before sleeping — e.g. "send intermediate message to user, then check agent status, then sleep" — must either:

- Encode the multi-step intent in a single action type (forces action proliferation), or
- Accept that each step requires a separate wake cycle, adding latency and intermediate checkpoint writes for what is logically a single cognitive unit

The problem is visible in practice: when an operator wants to acknowledge a user message and then wait for an agent, it currently requires two separate wake cycles, each with its own checkpoint.

### MemGPT's solution

MemGPT (Packer et al., 2023) uses a `yield` / `continue` signal: the agent sends an action along with a flag indicating whether it wants to be called again immediately or yield control to the external scheduler. This allows multi-step cognitive sequences without requiring the external scheduler to decide when the agent is "done thinking."

## Decision

Add `more_actions: bool = False` to `NextActionDecision`. When `True`, the drive loop calls `brain.decide()` again in the same wake cycle after re-running `RuntimeReconciler.reconcile()`, without saving a checkpoint between calls.

### Exact loop semantics

```
for each while-loop iteration:
    1. reconcile(agg, ctx) → events (always; even between more_actions sub-calls)
    2. decide_and_execute(agg, ctx, config) → (decision, events, agent_result, iteration_brief)
    3. apply events, append to event log, append to read model
    4. if decision.more_actions AND consecutive_actions < max_consecutive_actions AND not terminal:
         consecutive_actions += 1
         continue  ← back to step 1, NO checkpoint
    5. reset consecutive_actions = 0
    6. save checkpoint
    7. check terminal / STOP conditions
```

Key properties:
- **Re-reconcile always**: aggregate state may have changed between sub-calls (e.g. wakeup arrived). The brain always sees fresh state.
- **No checkpoint between sub-calls**: all actions in a `more_actions=True` series form one transactional unit. Crash recovery replays from the last checkpoint; all events are in the event log.
- **Safety limit**: `DriveService.max_consecutive_actions = 10` (configurable, not per-operation). Brain cannot override this limit via any action.
- **`fast_cycle` interaction**: if `more_actions=True`, `fast_cycle` on the same decision is ignored (re-reconcile always happens regardless).
- **Budget/timeout priority**: `LifecycleGate.should_continue()` is checked at the top of every while iteration, including `more_actions` sub-calls. Budget/timeout fires even mid-series.

### Decision history for brain self-awareness

Brain needs to see its own recent decisions to avoid loops (e.g., detecting "I called START_AGENT three times in a row"). `BrainContext.recent_decisions: list[DecisionRecord]` provides the last N brain calls, including `more_actions` sub-calls. This is finer-grained than `recent_iterations` (one per while-loop cycle) precisely because `more_actions` sub-calls need to be visible.

## Alternatives Considered

**Expand action types** (e.g. `SEND_THEN_WAIT`, `CHECK_THEN_REPLY`). Rejected: action proliferation — every multi-step combination requires a new action type. Does not scale as the brain's capabilities expand.

**Multi-action list response** (brain returns `list[NextActionDecision]`). Rejected: changes the brain protocol more drastically; requires the drive loop to handle partial execution failures mid-list; makes crash recovery more complex.

**Caller-controlled batching** (service layer calls brain multiple times). Rejected: removes the decision about "continue vs sleep" from the brain (which has the context) and gives it to the infrastructure (which doesn't).

**No continuation model; require explicit wakeup between steps.** Rejected: for simple two-step sequences (acknowledge → wait), this doubles latency and adds unnecessary checkpoint writes.

## Write-Ahead Invariant for Crash Safety

Actions within a `more_actions` series may have externally visible side effects — most notably `START_BACKGROUND_AGENT`, which spawns an `asyncio.Task` in `InProcessAgentRunSupervisor`. If the process crashes after the task is spawned but before the corresponding domain event (`AgentSessionStarted`) is written to the event log, the next drive call will replay the action and spawn the task again, producing duplicate agent runs.

**Invariant**: Any action with an externally visible side effect must write its domain event to the event log **before** the side effect is executed. This is the write-ahead invariant for `more_actions` crash safety.

Concretely for `START_BACKGROUND_AGENT`:
1. `PolicyExecutor.decide_and_execute()` appends `AgentSessionStarted` to `event_log` first.
2. Only after a successful append does it call `supervisor.spawn(coro, ...)`.
3. If the process crashes between step 1 and step 2, the next resume sees `AgentSessionStarted` in the aggregate and detects the session as orphaned (ADR 0201) — no re-spawn. If the crash happens before step 1, neither event nor task exists — the action is replayed cleanly.

This invariant applies to all side-effect-bearing actions, not just `START_BACKGROUND_AGENT`. Any future action type that communicates with an external system must follow the same write-first order. Concretely, `SEND_MESSAGE_TO_USER` must append `OperatorMessageSent` to the event log before delivering the message to the transport layer — otherwise a crash after delivery but before event write causes a duplicate message on replay. `PolicyExecutor.decide_and_execute()` is the single enforcement point for all such actions.

## Consequences

- `NextActionDecision` gets a new field `more_actions: bool = False` — backward compatible (defaults to False)
- `DriveService` constructor gets `max_consecutive_actions: int = 10` — infrastructure-level guardrail, not exposed to brain
- `BrainContext` gets `recent_decisions: list[DecisionRecord]` for self-awareness
- Brain prompt must include decision history and explain the `more_actions` signal
- `OperationOutcome.iterations_executed` counts each brain call, including sub-calls — documented in §47
- `PolicyExecutor.decide_and_execute()` must enforce the write-ahead invariant: domain events are appended to the event log before any externally visible side effect is executed
