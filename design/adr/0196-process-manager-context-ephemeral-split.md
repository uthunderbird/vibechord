# ADR 0196: ProcessManagerContext as Ephemeral Drive-Call State

- Date: 2026-04-21

## Decision Status

Accepted

## Implementation Status

Partial

Skim-safe status on 2026-04-23:

- `implemented`: `DriveService` constructs `ProcessManagerContext` once per drive call and passes
  it through the v2 loop
- `implemented`: `build_pm_context()` now rebuilds policy coverage from policy-store scope at
  drive-call start instead of reusing stale aggregate policy coverage
- `implemented`: the v2 brain bridge now prefers per-call `ctx.policy_context` when seeding
  `OperationState.policy_coverage`
- `partial`: `OperationAggregate` still carries `policy_coverage`, `active_policies`, and
  `involvement_level`, so the aggregate/ephemeral split is not yet complete
- `verified`: targeted regression coverage now exists for policy-context reconstruction and the
  brain-context wiring in the v2 drive path

## Context

In v1, `OperationState` contains a set of fields that serve the drive loop's coordination needs but are not business domain facts:

- `policy_coverage`, `active_policies`, `involvement_level` — rebuilt from `PolicyStore` on every resume
- `processed_command_ids` — idempotency deduplication, reset on every drive call (at-least-once delivery is safe)
- `pending_replan_command_ids` — scheduling signal for the next cycle
- `pending_attention_resolution_ids` — signal that an attention answer arrived and must be processed
- `current_focus` — the drive loop's current attention target

These fields are persisted in the `OperationState` snapshot even though some of them (e.g. `policy_coverage`) are fully reconstructible from external sources and others (e.g. `pending_wakeups`) are maintained by the `WakeupInbox` and should not be duplicated in the aggregate.

The cost: every checkpoint write carries this coordination data even when only domain state changed.

### What changed in v2 (ADR 0193)

ADR 0193 classifies aggregate fields into domain canonical, coordination state, and read model. The coordination state fields that must survive crashes stay in `OperationAggregate` as event-sourced. But a distinct set of fields — the runtime caches — should never be in the aggregate at all.

## Decision

`ProcessManagerContext` is an explicitly ephemeral struct, created once per `DriveService.drive()` call and destroyed when `drive()` returns.

### Fields that move OUT of the aggregate into ProcessManagerContext

| v1 field | v2 location | Reason |
|---|---|---|
| `policy_coverage` | `ProcessManagerContext.policy_context` | Rebuilt from `PolicyStore` at drive-call start via `build_pm_context()` |
| `active_policies` | (removed) | Subsumed by `policy_context` |
| `involvement_level` | (removed from aggregate) | Derived from policy at runtime |
| `pending_wakeups` | `WakeupInbox` only | WakeupInbox is durable; no need to duplicate in aggregate |

### Fields that stay in OperationAggregate (coordination state, event-sourced)

| Field | Event that produces it |
|---|---|
| `current_focus` | `FocusSet`, `FocusCleared` |
| `scheduler_state` | `SchedulerPauseRequested`, `SchedulerPaused`, `SchedulerResumed` |
| `operator_messages` | `OperatorMessageReceived` |
| `attention_requests` | `AttentionRequestCreated`, `AttentionRequestAnswered` |
| `processed_command_ids` | `CommandProcessed` |
| `pending_replan_command_ids` | `ReplanScheduled`, `ReplanConsumed` |
| `pending_attention_resolution_ids` | `AttentionAnswerQueued`, `AttentionAnswerConsumed` |

These stay in the aggregate because they must be reconstructible after a crash at any point in the drive cycle — they are not safely reconstructible from external sources.

### ProcessManagerContext fields

```python
@dataclass
class ProcessManagerContext:
    policy_context: PolicyCoverage | None = None
    available_agents: list[AgentDescriptor] = field(default_factory=list)
    session_contexts: dict[str, RuntimeSessionContext] = field(default_factory=dict)
    current_focus: FocusState | None = None   # derived from agg.current_focus at call start
    processed_command_ids: set[str] = field(default_factory=set)  # per-call dedup, starts empty
    pending_replan_command_ids: list[str] = field(default_factory=list)
    draining: bool = False
```

`build_pm_context(agg, *, policy_store, adapter_registry, wakeup_inbox) -> ProcessManagerContext` reconstructs this at the start of each `drive()` call.

## Alternatives Considered

**Keep all fields in the aggregate, mark cache fields as non-persisted.** Add a `@derived` annotation and skip serialization for those fields. Rejected: the serialization boundary is the aggregate/checkpoint boundary — adding "skip this field" logic reintroduces ad-hoc dual-truth.

**Persist ProcessManagerContext separately.** Write it to a coordination store. Rejected: adds a third persistence surface with its own atomicity requirements. The fields that must survive crashes are already in the aggregate via events.

## Consequences

- Checkpoint writes are smaller — no policy caches, no wakeup lists
- `build_pm_context()` adds one async round-trip (policy store lookup) at the start of each drive call — acceptable since drive calls are wake-cycle-scoped, not per-iteration
- `ProcessManagerContext` is independently testable (constructed with test doubles for policy store, adapter registry)
- v1 `OperationState` snapshot fields `policy_coverage`, `active_policies`, `involvement_level`, `pending_wakeups` are deleted — no migration path (ADR 0194)

## Repository Evidence

- `src/agent_operator/application/drive/process_manager_context.py` rebuilds per-drive-call policy
  coverage from replayed operation metadata plus `PolicyStore`
- `src/agent_operator/application/drive/policy_executor.py` now seeds the brain bridge from
  `ctx.policy_context` instead of relying only on aggregate-carried policy coverage
- `src/agent_operator/application/drive/drive_service.py` remains the construction boundary for
  one ephemeral `ProcessManagerContext` per drive call

## Remaining Blockers

- `OperationAggregate` still owns `policy_coverage`, `active_policies`, and `involvement_level`,
  so the runtime-only fields are not fully evicted from aggregate truth yet
- The v1 service shell and command path still refresh and persist policy context on `OperationState`
- Query/projection surfaces still read involvement and policy state from aggregate-backed views

## Verification

Verified locally on 2026-04-23 with:

- `pytest -q tests/test_lifecycle_gate.py tests/test_drive_service_v2.py tests/test_operator_service_v2.py`
- `ruff check src/agent_operator/application/drive/process_manager_context.py src/agent_operator/application/drive/policy_executor.py tests/test_lifecycle_gate.py tests/test_drive_service_v2.py`
- `mypy src/agent_operator/application/drive/process_manager_context.py src/agent_operator/application/drive/policy_executor.py`
