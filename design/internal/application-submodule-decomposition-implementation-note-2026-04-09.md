# Application Submodule Decomposition Implementation Note

Date: 2026-04-09
Related:

- [ADR 0121](../adr/0121-application-submodule-organization-and-boundary-rules.md)
- [ADR 0115](../adr/0115-fleet-workbench-projection-and-cli-tui-parity.md)
- [ADR 0118](../adr/0118-supervisory-surface-implementation-tranche.md)

## Goal

Turn the current mostly-flat `src/agent_operator/application/` package into a stable family of
submodules without changing application semantics.

This note is implementation-facing. It defines the preferred decomposition map and execution order
so future refactors do not make placement decisions ad hoc.

## Current Pressure Points

The main oversized or pressure-prone modules today are:

- `operation_commands.py`
- `operation_delivery_commands.py`
- `operation_projections.py`
- `operation_runtime_reconciliation.py`
- `operation_traceability.py`

There are also several medium-sized orchestration modules that should not accumulate unrelated work:

- `operation_turn_execution.py`
- `decision_execution.py`
- `operation_entrypoints.py`
- `operation_lifecycle.py`
- `agent_results.py`
- `attached_turns.py`

## Target Package Map

Preferred target shape:

- `application/__init__.py`
  - re-export facade only

- `application/commands/`
  - `operation_commands.py`
  - `delivery_commands.py`
  - `cancellation.py`
  - `attention.py`
  - `control_state.py`
  - `policy_mutations.py` if needed later

- `application/queries/`
  - `agenda.py`
  - `dashboard.py`
  - `project_dashboard.py`
  - `projections_fleet.py`
  - `projections_operation.py`
  - `projections_traceability.py`
  - `state_views.py`

- `application/runtime/`
  - `runtime_context.py`
  - `runtime_reconciliation.py`
  - `runtime_dispatch.py`
  - `runtime_event_relay.py`
  - `supervisor_runtime.py`

- `application/orchestration/`
  - `entrypoints.py`
  - `lifecycle.py`
  - `turn_execution.py`
  - `decision_execution.py`
  - `agent_results.py`
  - `attached_turns.py`
  - `loaded_operation.py`

- existing packages retained:
  - `application/drive/`
  - `application/event_sourcing/`

## Boundary Decisions

### Commands

`commands/` is for mutation-oriented application services.

Place here:

- enqueue/apply/live-command logic
- delivery command service logic
- cancellation and attention-answering mutation paths
- control-state mutation helpers

Do not place here:

- dashboard payload assembly
- fleet/workbench projection logic
- Rich/TUI formatting

### Queries

`queries/` is for read-model shaping.

Place here:

- agenda and dashboard query services
- fleet/operation/session projection assembly
- inspect/traceability summary shaping
- state-view payload construction

Do not place here:

- command mutation orchestration
- runtime process reconciliation

### Runtime

`runtime/` is for reconciliation and runtime-backed coordination.

Place here:

- runtime context
- reconciliation logic
- process/signal/relay glue
- runtime-backed operation service implementations

Do not place here:

- CLI/TUI adapters
- durable display projections

### Orchestration

`orchestration/` is for higher-level application sequencing that is not purely mutation-only or
query-only.

Place here:

- operation entrypoints
- lifecycle coordination
- turn execution and decision execution
- agent result integration
- attached turn handling

## Preferred Extraction Order

### Wave 1: Queries first

Lowest-risk and highest-value first split:

- split `operation_projections.py` into:
  - `queries/projections_fleet.py`
  - `queries/projections_operation.py`
  - `queries/projections_traceability.py`
- keep a thin compatibility facade at the old import path while callers are migrated

Why first:

- this module is already display-facing and growing;
- ADR 0115 and 0118 depend on clearer projection boundaries;
- the split does not require mutation-semantic changes.

### Wave 2: Delivery and commands

- split `operation_delivery_commands.py` into `commands/delivery_commands.py` plus extracted helper
  modules if needed
- split `operation_commands.py` into mutation-focused submodules inside `commands/`

Why second:

- command payload and enqueue logic is one of the largest mutation clusters;
- it should be separated before more CLI/TUI parity work lands.

### Wave 3: Runtime reconciliation

- move `operation_runtime.py`, `operation_runtime_context.py`,
  `operation_runtime_reconciliation.py`, `operation_process_dispatch.py`,
  `operation_event_relay.py` under `runtime/`
- split reconciliation further if the module still remains too large

Why third:

- runtime reconciliation has a different dependency shape from query/projection work;
- pulling it into a dedicated family clarifies the rest of the package.

### Wave 4: Orchestration family

- move `operation_entrypoints.py`, `operation_lifecycle.py`, `operation_turn_execution.py`,
  `decision_execution.py`, `agent_results.py`, `attached_turns.py`, `loaded_operation.py`
  under `orchestration/`

Why fourth:

- these modules are not yet the worst line-budget offenders, but they are the most likely future
  dumping grounds once queries and commands are decomposed.

### Wave 5: Facade cleanup

- reduce `application/__init__.py` to stable export-only behavior
- remove temporary compatibility facades when import sites are migrated

## First Concrete Cuts

Recommended first concrete cuts inside the biggest modules:

### `operation_projections.py`

Split by output family:

- fleet / agenda / list-oriented payload builders
- operation dashboard / inspect / durable-truth payload builders
- traceability / turn-summary helper functions

### `operation_delivery_commands.py`

Split by responsibility:

- status/output rendering helpers
- enqueue/cancel/answer/control command flows
- runtime alert / projection glue

### `operation_commands.py`

Split by command family:

- run/start/resume/tick/daemon/recover surfaces
- answer/attention/control mutations
- policy-related command payload building if it continues to grow

### `operation_runtime_reconciliation.py`

Split by runtime concern:

- wakeup reconciliation
- background-run reconciliation
- attached-turn reconciliation
- shared reconciliation helpers

### `operation_traceability.py`

Split by traceability concern:

- trace record writing
- decision memo writing
- turn summary assembly
- brief-bundle loading helpers

## Compatibility Strategy

During each wave:

- keep the old import path as a thin facade module until callers are migrated;
- do not break `application/__init__.py` exports in the same step as the internal split unless all
  import sites are updated together;
- prefer “move implementation, keep facade” over mass call-site churn in one patch.

## Verification Expectations

After each wave:

- existing application tests continue to pass
- CLI/TUI tests that depend on application exports continue to pass
- `application/__init__.py` still exports the same public symbols unless a separate ADR changes the
  public surface
- no new `application` module should mix command/query/runtime responsibilities again

## Non-Goals

This decomposition note does not:

- redesign domain models
- change CLI or TUI contracts directly
- change event-sourcing or drive-loop semantics
- require all `application/` files to immediately drop below a hard global LOC ceiling in one wave

The immediate purpose is correct family placement and controlled decomposition, not speculative
rewriting.
