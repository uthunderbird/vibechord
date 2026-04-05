# ADR 0092: Split `OperationConstraints` into policy, budget, and runtime hints

## Status

Accepted

## Extends

- [RFC 0009](../rfc/0009-operation-event-sourced-state-model-and-runtime-architecture.md)
- [ADR 0086](./0086-event-sourced-operation-birth-and-snapshot-legacy-retirement-policy.md)
- [ADR 0088](./0088-main-entrypoint-cutover-and-final-operator-service-shell-boundary.md)

## Context

`OperationConstraints` currently mixes several different kinds of state:

- durable operation governance such as `involvement_level`
- agent-selection boundary such as `allowed_agents`
- execution budget such as `max_iterations` and `timeout_seconds`
- runtime/prompt helpers such as `operator_message_window` and `metadata`

That aggregate shape was tolerable in the snapshot-first runtime, but it is a bad fit for
`RFC 0009` event sourcing.

The repository already shows this split in practice:

- `involvement_level` is now canonical checkpoint truth and has domain-event support
- `allowed_agents` participates in prompt assembly, policy matching, and execution filtering
- `max_iterations` and `timeout_seconds` control the live loop budget rather than replayed
  business truth
- `metadata` already contains volatile runtime hints such as `run_mode` and
  `available_agent_descriptors`

### Current truth

Today:

- the repository uses `OperationPolicy`, `ExecutionBudget`, and `RuntimeHints` as the active
  runtime and persistence-facing model
- `SET_ALLOWED_AGENTS` is the active policy command surface for allowlist updates
- `OperationCheckpoint` does not contain constraints as a single canonical substate
- `allowed_agents` lives in canonical operation policy and is folded into checkpoint truth
- `involvement_level` is canonical policy state with a dedicated event-sourced command path
- `max_iterations` and `timeout_seconds` are consumed directly by the live drive loop as execution
  limits rather than as replayed business state
- `metadata` carries volatile values such as `run_mode` and `available_agent_descriptors`, which
  are runtime/read-model glue rather than operation history

## Decision

`OperationConstraints` must be split into three distinct semantic families:

1. `OperationPolicy`
2. `ExecutionBudget`
3. `RuntimeHints`

The repository must stop treating the old aggregate as one cohesive architectural slice.

### Field classification

The split is normative for the current fields:

| Current field | New family | Canonical | Reason |
|---|---|---|---|
| `involvement_level` | `OperationPolicy` | yes | durable governance boundary |
| `allowed_agents` | `OperationPolicy` | yes | durable allowed execution surface and policy context |
| `max_iterations` | `ExecutionBudget` | no | per-run loop budget |
| `timeout_seconds` | `ExecutionBudget` | no | per-run wall-clock budget |
| `operator_message_window` | `RuntimeHints` | no | prompt/runtime tuning knob |
| `metadata` | `RuntimeHints` | no | host/read-model glue |

### `OperationPolicy`

`OperationPolicy` is operation-owned durable governance state.

It is canonical and event-sourced.

It includes:

- `involvement_level`
- `allowed_agents`

`allowed_agents` is classified as canonical policy state because it affects:

- the allowed execution surface
- policy applicability context
- prompt-visible decision boundaries

It is not merely a host-specific launch convenience.

It is the durable answer to:

- which agents this operation is allowed to use
- how autonomous the operator is allowed to be while executing it

### `ExecutionBudget`

`ExecutionBudget` is execution-owned runtime budget for one `run` / `resume` / `recover` flow.

It is not canonical operation checkpoint truth.

It includes:

- `max_iterations`
- `timeout_seconds`

These fields constrain how long or how far one live execution may continue. They do not describe
durable operation history.

They may be supplied:

- from CLI/profile defaults when a run starts
- from explicit `run` / `resume` / `recover` options
- from future execution-control surfaces

They must not be folded into the canonical checkpoint as operation-owned business truth.

### `RuntimeHints`

`RuntimeHints` is non-canonical runtime/read-model glue.

It is not part of canonical event-sourced truth.

It includes:

- `operator_message_window`
- `metadata`
- other derived or host-specific prompt/runtime helper values

This family may be stored in transient runtime state or in read-only derived views, but not in the
canonical checkpoint.

### Command-surface consequence

`PATCH_CONSTRAINTS` must be retired as a mixed-scope command.

It should be replaced by narrower surfaces:

- canonical policy commands for durable operation policy changes
- execution-control inputs for per-run budget changes

The current mixed payload shape:

- `allowed_agents`
- `max_iterations`

must not survive as one command family once this ADR is implemented.

### Event-model consequence

After implementation:

- policy changes must be represented by canonical domain events
- execution-budget changes must not require checkpoint projection
- runtime hints must not acquire canonical event types merely because they are currently stored
  under `constraints`

This ADR intentionally separates the decision to event-source `allowed_agents` from any idea of
event-sourcing the whole legacy aggregate.

### Entry-point consequence

Public entrypoints may still accept a convenience input object during migration, but repository
truth must change underneath:

- durable policy is loaded from canonical operation state
- execution budget is resolved per live entrypoint call
- runtime hints are assembled by the runtime/read-model layer

The convenience input shape must not be mistaken for the internal canonical model.

## Consequences

- `RFC 0009` can progress without smuggling runtime glue into canonical checkpoints.
- `allowed_agents` can be event-sourced honestly rather than piggybacking on a misleading
  constraints aggregate.
- `max_iterations` and `timeout_seconds` stop pretending to be operation-domain truth.
- `metadata` loses any accidental claim to canonicality.
- The repository had to remove `PATCH_CONSTRAINTS` and broad `OperationConstraints` mutation
  semantics from active code paths.
- `OperationState` and checkpoint-building code must stop mirroring the same semantic field across
  multiple families without an explicit compatibility reason.

## This ADR does not decide

- the exact replacement type names exposed at CLI boundaries during migration
- the final event catalog for `allowed_agents` updates
- whether `operator_message_window` remains grouped with other prompt settings or moves to a more
  specific runtime-hints object
- how old snapshot-era payloads are upgraded
- the final CLI UX for per-run budget overrides after `PATCH_CONSTRAINTS` is removed

## Migration notes

Implementation should proceed in this order:

1. introduce explicit internal families for policy, budget, and runtime hints
2. move `allowed_agents` and `involvement_level` onto the canonical policy path
3. stop routing `max_iterations` and `timeout_seconds` through operation-domain command mutation
4. retire `PATCH_CONSTRAINTS`
5. remove or narrow the old umbrella aggregate once tests and CLI surfaces are migrated

This sequence keeps the event-sourced rollout honest without forcing a one-shot public rename.

## Alternatives Considered

### Canonicalize the full existing `OperationConstraints` aggregate

Rejected. The current aggregate mixes policy, execution budget, and runtime glue. Moving it into
the checkpoint as-is would preserve architectural confusion rather than remove it.

### Keep `allowed_agents` non-canonical as an execution envelope input

Rejected. The repository already uses `allowed_agents` as a durable decision boundary for prompt
construction, policy evaluation, and execution filtering. Making it non-canonical would leave
replay behavior dependent on external caller inputs rather than operation history.

### Keep `PATCH_CONSTRAINTS` but canonicalize only part of its payload

Rejected. That preserves a misleading command surface that crosses semantic families and would
continue to blur policy updates with execution-budget changes.

## Verification

- `verified`: code inspection shows `involvement_level` is already checkpoint-backed while
  `max_iterations` and `timeout_seconds` are consumed directly by the live operation loop.
- `verified`: code inspection shows `allowed_agents` affects execution filtering, prompt assembly,
  and policy matching rather than only launch-time wiring.
- `verified`: code inspection shows `metadata` already carries volatile runtime values such as
  `run_mode` and `available_agent_descriptors`, which fail the canonical-checkpoint bar.
- `implemented`: the repository now defines explicit `OperationPolicy`, `ExecutionBudget`, and
  `RuntimeHints` models in place of treating `OperationConstraints` as the primary internal truth.
- `implemented`: `OperationCheckpoint` now stores canonical `allowed_agents`, and the default
  projector folds both `operation.created` and `operation.allowed_agents.updated` into checkpoint
  state.
- `implemented`: the live runtime now reads allowlist policy from `state.policy.allowed_agents`
  and execution limits from `state.execution_budget`, while runtime metadata is assembled under
  `state.runtime_hints`.
- `implemented`: the command surface now uses `SET_ALLOWED_AGENTS`; active runtime and CLI paths
  no longer depend on `PATCH_CONSTRAINTS`.
- `verified`: `UV_CACHE_DIR=/tmp/uv-cache PYTHONPATH=src uv run pytest -q` passes with
  `326 passed, 11 skipped`.

## Closure Notes

This ADR is `Accepted` because the compatibility layer it previously tracked has been removed:

- `OperationConstraints` no longer exists in active code.
- `OperationState.constraints` no longer exists as a compatibility projection.
- `OperatorService.run(..., constraints=...)` no longer exists.
- `OperationCommandType.PATCH_CONSTRAINTS` no longer exists.

The remaining `RFC 0009` tail is therefore no longer the constraints split itself. It is the final
event-sourced live-runtime cutover tracked by `ADR 0086` and `ADR 0088`.
