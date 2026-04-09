# ADR 0121: Application Submodule Organization and Boundary Rules

- Date: 2026-04-09

## Status

Planned

## Context

The `application/` layer has already grown into several distinct families:

- operation command/application services
- delivery/query surfaces
- runtime reconciliation and runtime-backed orchestration
- traceability/projection/state-view logic
- event-sourcing services
- drive-loop orchestration

At the same time, several modules are already beyond or near the practical review boundary:

- `operation_commands.py`
- `operation_delivery_commands.py`
- `operation_projections.py`
- `operation_runtime_reconciliation.py`
- `operation_traceability.py`

Without an explicit organization rule, future work will keep accreting unrelated responsibilities
into these modules.

## Decision

The `application/` package should converge toward stable submodule families with explicit boundary
rules.

This ADR does not claim that the full refactor has already landed. It defines the intended
placement authority for new work and the target shape for future decomposition.

## Submodule Families

### 1. Facade and exports

- `application/__init__.py` remains a thin export surface.
- It may re-export selected public application services, but it must not own implementation logic.

### 2. Command / mutation services

Mutation-oriented application services live under an `application/commands/` family.

Typical contents:

- command payload building
- command application orchestration
- delivery-command surfaces
- cancellation / attention-answer / control-state mutation helpers

Rules:

- these modules coordinate domain mutations and persistent side effects;
- they do not own Rich/CLI/TUI rendering concerns;
- they do not own query projection formatting.

### 3. Query / projection services

Read-model and display-facing query services live under an `application/queries/` family.

Typical contents:

- agenda queries
- dashboard queries
- project dashboard queries
- projection assembly
- state-view building
- traceability summary payloads

Rules:

- query services shape persisted/runtime truth into stable payloads;
- they do not enqueue commands or mutate operation state;
- display-facing normalization belongs here, not in driving adapters.

### 4. Runtime orchestration

Runtime coordination and reconciliation services live under an `application/runtime/` family.

Typical contents:

- runtime context
- runtime-backed operation runtime
- runtime reconciliation
- process dispatch glue
- event relay glue

Rules:

- runtime orchestration may coordinate external process/session state;
- it should not absorb CLI/TUI concerns;
- it should not become the home for display projections.

### 5. Traceability and state views

State summary, traceability, and durable-state-view services live under an `application/views/`
or `application/queries/traceability*` family.

Rules:

- summarize and normalize domain/runtime truth;
- do not own command mutation behavior.

### 6. Event sourcing

Event-sourced services stay grouped under `application/event_sourcing/`.

Rules:

- event-sourced birth, replay, loop, and command application remain together;
- non-event-sourced orchestration should not be moved into this family just because it is adjacent.

### 7. Drive loop orchestration

Drive-loop services stay grouped under `application/drive/`.

Rules:

- drive coordination remains separate from generic command/query placement;
- CLI/TUI-specific flows must not leak into the drive package.

## Boundary Rules

Allowed dependencies:

- command services -> domain + runtime ports + shared query/projection helpers when needed
- query/projection services -> domain + stores/readers + runtime read models
- runtime orchestration -> domain + runtime/store/process adapters
- facades -> submodule families

Disallowed dependencies:

- query/projection services -> CLI/TUI adapters
- application modules importing `agent_operator.cli.*`
- command/mutation services depending on Rich or terminal rendering
- new “misc” application modules that mix mutation, query, runtime, and rendering glue

## Current Target Mapping

The current flat modules should converge toward these families:

- `operation_commands.py` -> `application/commands/operation_commands*.py`
- `operation_delivery_commands.py` -> `application/commands/delivery*.py`
- `operation_cancellation.py`, `operation_attention.py`, `operation_control_state.py`
  -> `application/commands/`
- `operation_agenda_queries.py`, `operation_dashboard_queries.py`,
  `operation_project_dashboard_queries.py`, `operation_projections.py`,
  `operation_state_views.py`, `operation_traceability.py`
  -> `application/queries/`
- `operation_runtime.py`, `operation_runtime_context.py`,
  `operation_runtime_reconciliation.py`, `operation_process_dispatch.py`,
  `operation_event_relay.py`
  -> `application/runtime/`
- `operation_entrypoints.py`, `operation_lifecycle.py`, `operation_turn_execution.py`,
  `decision_execution.py`, `agent_results.py`, `attached_turns.py`
  remain orchestration-oriented and may be decomposed further, but should not absorb
  query/rendering work.

## Consequences

Positive:

- future placement decisions become clearer;
- large application modules get an explicit decomposition direction;
- query/projection work and command/runtime work stay separated.

Tradeoffs:

- more packages and more explicit imports;
- some temporary facades or re-exports may be needed during decomposition waves.

## Verification

Changes touching `application/` should preserve these conditions:

- `application/__init__.py` remains export-only;
- new functionality is placed into the correct family instead of extending unrelated flat modules;
- application code does not import CLI/TUI modules;
- mutation and projection concerns remain separated.

## Related

- [ADR 0115](./0115-fleet-workbench-projection-and-cli-tui-parity.md)
- [ADR 0118](./0118-supervisory-surface-implementation-tranche.md)
- [ADR 0119](./0119-cli-main-module-decomposition-below-500-lines.md)
- [ADR 0120](./0120-cli-submodule-organization-and-boundary-rules.md)
