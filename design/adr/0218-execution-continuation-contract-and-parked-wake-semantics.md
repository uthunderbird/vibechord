# ADR 0218: Execution Continuation Contract And Parked Wake Semantics

- Date: 2026-04-27

## Decision Status

Proposed

## Implementation Status

Partial

Implementation grounding on 2026-05-02:

- `implemented`: the brain action taxonomy includes `wait_for_material_change`; the drive policy
  executor persists `operation.parked.updated` and breaks the wake cycle for that action. Evidence:
  `src/agent_operator/domain/enums.py`,
  `src/agent_operator/application/drive/policy_executor.py`.
- `implemented`: authoritative parked execution state is part of operation/checkpoint replay and
  can represent runtime-drained and dependency-barrier waits. Evidence:
  `src/agent_operator/domain/operation.py`, `src/agent_operator/domain/checkpoints.py`,
  `src/agent_operator/application/drive/drive_service.py`.
- `implemented`: session continuation/reuse checks desired versus observed execution profiles and
  rejects stale or missing observed contracts. Evidence:
  `src/agent_operator/application/loaded_operation.py`,
  `src/agent_operator/application/decision_execution.py`.
- `implemented`: operation, live, and dashboard read payloads expose parked execution state so
  user-facing surfaces can distinguish non-human parked waits from ordinary running state.
  Evidence: `src/agent_operator/application/queries/operation_projections.py`,
  `src/agent_operator/cli/rendering/operation.py`.
- `verified`: focused tests cover no-spin parking for stable dependency barriers, continuation
  profile mismatch rejection, idle-session reuse profile mismatch rejection, and parked-state
  read/render payloads. Evidence: `tests/test_drive_service_v2.py`,
  `tests/test_attached_turn_service.py`, `tests/test_operation_projections.py`.
- `planned`: material wake predicate handling remains intentionally coarse; the current
  implementation records wake predicates but does not yet provide a typed predicate evaluator for
  every predicate family named below.

## Context

Recent v2/operator-control failures exposed one shared architectural gap rather than isolated
adapter bugs:

- resumed or reused agent sessions could continue under a stale or weaker capability profile than
  the operation believed it had requested;
- stable non-human dependency barriers could keep the operation in an active control loop,
  consuming iterations without any new executable work becoming available;
- human approval, policy application, runtime health, and capability regrant could be rendered as
  if they were interchangeable forms of "progress" even when they were not.

These failures appeared in different forms:

- `approval_policy` / `sandbox_mode` could be lost or go stale across background
  `continue_agent` / `resume` flows;
- repeated `apply_policy` decisions could spin indefinitely while the operation was actually
  waiting on an external runtime dependency;
- an answered attention request could be treated as if execution had become possible even when the
  resumed agent session still lacked the required capability contract.

The common root cause is that the system does not yet have a single, enforceable model for the
conditions under which execution may continue.

Today those conditions are split across:

- operation/task intent,
- execution-profile overrides,
- session handle metadata,
- runtime/session observations,
- and focus / attention / policy control paths.

That fragmentation makes it too easy for the control plane to:

- continue a session without proving that the observed runtime contract still matches the desired
  contract,
- or iterate repeatedly under a stable barrier instead of parking until a material wakeup occurs.

## Decision

The operator will adopt an explicit execution continuation contract and parked wake semantics.

This has four parts:

1. **Desired versus observed execution contract**
   - The operation/task side owns the authoritative desired execution contract for a runnable
     agent turn.
   - Session/runtime state owns only the observed execution contract of the concrete bound session.
   - Continuation, reuse, and resume are legal only when the observed contract is compatible with
     the desired contract.

2. **Explicit parked waiting action**
   - `apply_policy` will no longer serve as a generic "nothing executable changed" action.
   - A new explicit brain action will represent stable non-human waiting:
     `wait_for_material_change`.

3. **Authoritative parked execution state**
   - A stable non-human barrier will be persisted as authoritative operation state, not only as
     transient focus or narrative rationale.

4. **Wake-driven, non-spinning control semantics**
   - When the operation is parked on a stable barrier, the wake cycle ends.
   - The operation is reconsidered only when a material wake predicate fires.
   - Stable barriers must not consume unbounded iterations.

## Desired Versus Observed Execution Contract

The continuation contract answers:

> "Under what conditions may the operator legitimately continue execution now?"

### Desired execution contract

The desired execution contract is authoritative and owned by operation/task state.

For code agents this includes the load-bearing execution-profile semantics required to make the
next action legitimate, including when relevant:

- adapter key
- model
- effort / reasoning effort
- approval policy
- sandbox mode
- other future capability-bearing execution attributes

`ExecutionProfileStamp` or its successor should be treated as the canonical desired capability
contract, not merely as display metadata.

### Observed execution contract

The observed execution contract is what the currently bound session/runtime actually provides.

It is derived from runtime/session observations and may be cached on session records or handles for
traceability and projections, but it is not authoritative for what the operator intended.

### Continuation rule

`start_agent`, `continue_agent`, and `resume` may continue against an existing session only if the
observed contract is compatible with the desired contract.

If the contracts are incompatible:

- the operator must either launch a new session under the desired contract,
- or fail / re-escalate / reopen attention explicitly.

Silent continuation under a stale or weaker contract is forbidden.

## New Brain Action: `wait_for_material_change`

The brain decision taxonomy must distinguish between:

- applying or refreshing policy context,
- and explicitly parking because no executable repository-progress action is currently legal.

To do that, add a new structured action:

- `wait_for_material_change`

This action means:

> "No executable progress action is currently available. Persist the current barrier and stop the
> wake cycle until a material change occurs."

### Required payload

The action should carry at least:

- `barrier_kind`
- `barrier_fingerprint`
- `blocking_reason`
- `wake_predicates`
- `focus_task_id` or equivalent task linkage when relevant
- `target_agent` when the barrier is agent/runtime-specific

### Relation to `apply_policy`

`apply_policy` should remain only for actual policy/context application work.

It must not remain a catch-all no-op action for stable dependency barriers.

## Authoritative Parked Execution State

The aggregate should persist a first-class parked execution record for stable non-human waiting.

Illustrative minimal fields:

- `kind`
- `fingerprint`
- `reason`
- `wake_predicates`
- `related_task_id`
- `related_agent`
- `created_at`
- `last_confirmed_at`

This state is distinct from:

- focus, which remains a control/view emphasis concept,
- attention requests, which remain human-facing action requests,
- and active session state, which remains runtime/session truth.

## Wake Predicates

Parked execution must be resumed only by material wake predicates, not by generic loop turnover.

The exact enum can evolve, but the minimum predicate families should cover:

- `human_answered`
- `policy_changed`
- `runtime_health_changed`
- `allowed_agents_changed`
- `session_contract_changed`
- `external_dependency_resolved`

Wakeup handling must be idempotent and fingerprint-aware:

- replaying the same stable barrier without a new wake predicate must not restart the same
  ineffective iteration sequence.

## No-Spin Invariant

The system must enforce the following invariant:

> No wake cycle may repeatedly consume iterations when the same stable barrier fingerprint remains
> true and no material wake predicate has fired.

Concretely:

- the same dependency barrier cannot be re-decided indefinitely under unchanged conditions;
- a parked operation must quiesce once blocked state is durably recorded;
- rescheduling is justified only by a material wake signal or by an explicit operator override.

## Human Versus Non-Human Blocking

The operator must distinguish human-blocked states from non-human parked states.

Examples:

- `request_clarification` / approval / policy gap needing the operator remain human-blocked
- runtime health loss, external dependency barriers, and capability-contract mismatch are non-human
  blocked states

The exact status-enum strategy may be staged, but user-facing surfaces must not imply "running"
when the operation is actually parked on a stable non-human barrier.

## Consequences

### Positive

- Resume and reuse become contract-checked rather than metadata-assumed.
- Stable external/runtime barriers stop consuming iteration budget.
- The brain decision taxonomy becomes less overloaded and more auditable.
- Human attention and non-human waiting become easier to reason about and render truthfully.
- Future control-plane bugs of the same family become structurally harder.

### Negative

- The domain model gains at least one additional explicit state concept.
- The brain protocol and decision execution path must be updated together.
- Query/rendering surfaces must be taught how to expose parked non-human barriers clearly.
- Existing tests and prompting will need migration to the new action taxonomy.

## Implementation Tranche

The intended implementation order is:

1. Add red tests for:
   - repeated stable dependency barriers must park instead of spin,
   - resumed/reused sessions must satisfy the desired execution contract,
   - answered approval that cannot be enacted under the current contract must fail or re-escalate,
     not silently continue.
2. Add the new brain action `wait_for_material_change`.
3. Introduce authoritative parked execution aggregate state.
4. Make continuation/reuse/resume validate desired versus observed execution contracts.
5. Update drive/reconciliation/query/rendering surfaces to honor parked wake semantics and expose
   blocked-non-human truth.

## Alternatives Considered

### Option A: Treat these as unrelated bugfixes

Rejected because the observed failures all derive from the same missing continuation contract.
Patch-only handling would leave the architecture vulnerable to future variants.

### Option B: Keep `apply_policy`, but tighten its implementation semantics

Not preferred because it leaves one action type overloaded across two different meanings:

- actual policy/context application
- explicit non-human waiting

That ambiguity invites recurrence of hot no-op loops.

### Option C: Add only a new blocked status without changing continuation semantics

Rejected because status labels alone do not prevent stale-contract continuation or spin loops.

## Related

- ADR 0003
- ADR 0005
- ADR 0007
- ADR 0202
- ADR 0208
- ADR 0214
