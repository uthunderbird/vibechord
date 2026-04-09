# ADR 0115: Fleet Workbench Projection and CLI/TUI Parity

## Status

Implemented

## Context

`ADR 0109`, `ADR 0113`, and `ADR 0114` establish the intended boundary:

- `status` is the canonical shell-native one-operation summary surface
- TUI is the preferred interactive live supervision surface
- CLI and TUI must remain thin driving adapters over the same persisted truth and shared
  application-facing command/query contracts

The current repository already has enough substrate to support TUI directionally:

- `AgendaSnapshot` / `AgendaItem` provide a fleet-oriented runtime summary
- operation-level dashboard queries provide deeper drill-down data
- fleet TUI actions already route through shared command/use-case paths for `pause`, `unpause`,
  `interrupt`, and `cancel`

However, the current fleet implementation is still architecturally incomplete for the agreed
human-first `Fleet` contract:

1. the fleet list still derives from an agenda/dashboard-oriented payload shape rather than a
   dedicated workbench projection
2. the current fleet row data is not normalized around the new UI contract
3. the selected-operation brief in fleet is assembled indirectly from broader dashboard payloads
4. CLI fleet snapshots and TUI fleet rendering do not yet clearly consume the same normalized
   fleet projection

This creates a risk of exactly the drift the ADR chain is trying to avoid:

- TUI grows a workbench-specific local state model
- CLI retains an older dashboard projection shape
- the product ends up with separate fleet truths rather than one projection with multiple renderers

## Decision

`operator` must introduce a dedicated fleet workbench projection and query path that serves both:

- the interactive TUI fleet workbench
- and the CLI fleet snapshot / `--json` output

This projection is the shared application-facing read model for the fleet surface. It must not be
implemented as:

- a TUI-local data model
- a Rich-rendering helper shape
- or an accidental reuse of the broader one-operation dashboard payload

### Required contracts

The fleet workbench projection must normalize three layers of data:

1. **Fleet header summary**
   - active operation counts
   - needs-human / running / paused counts
   - optional compact operator-load summary only when strongly grounded

2. **Fleet rows**
   - one row per operation with normalized row semantics:
     - attention badge
     - display label
     - state label
     - agent cue
     - recency brief
     - normalized row hint (`now: ...`, `waiting: ...`, `paused: ...`, `failed: ...`)

3. **Selected-operation fleet brief**
   - concise right-pane brief with fixed semantic sections:
     - `Goal`
     - `Now`
     - `Wait`
     - `Progress`
     - `Attention`
     - `Recent`

This fleet brief is not the same contract as the richer operation dashboard payload used at deeper
zoom levels.

### Adapter boundary

The delivery split is:

- **fleet workbench query/projection**
  - shared by CLI and TUI
  - owns normalized fleet rows and fleet brief
- **operation dashboard query/projection**
  - shared by CLI and TUI
  - owns deeper operation/session drill-down data

Therefore:

- Fleet View must not assemble its primary semantics by reusing the whole operation dashboard payload
- deeper TUI levels may still use the existing dashboard query path until a narrower dedicated
  operation-view contract becomes necessary

### CLI/TUI parity requirement

The same fleet workbench projection must be renderable through:

- TUI interactive fleet rendering
- textual CLI fleet snapshot output
- `--json` fleet payload output

Parity here means shared projection truth, not identical visual formatting.

Equivalent CLI and TUI fleet surfaces must therefore be explainable by:

- the same persisted operation/runtime truth
- the same fleet workbench query
- the same normalized row and brief semantics

## Explicit non-goals

This ADR does not require:

- replacing the existing operation dashboard query service
- redesigning `status`
- introducing arbitrary configurable fleet layouts
- implementing full operator-load modeling in the first tranche
- implementing a full multi-agent fleet grammar in the first tranche
- removing specialized future modes such as `dense` or `attention`

## First implementation tranche

The first tranche should be intentionally narrow.

### P0

1. Introduce a dedicated fleet workbench query/projection contract.
2. Normalize fleet row semantics around the agreed 3-line row shape.
3. Normalize selected-operation fleet brief semantics around the agreed brief sections.
4. Switch the TUI fleet workbench to the new projection.
5. Switch CLI fleet snapshot / `--json` output to the same projection.
6. Keep fleet action handling on shared command/use-case paths.

### P1

1. Add compact conditional multi-agent cues when strongly grounded.
2. Add compact conditional operator-load cues when strongly grounded.
3. Add explicit named alternate modes such as `dense` or `attention` if and only if their
   semantics remain fixed and documented.

## File-by-file implementation plan

This plan is the intended tranche shape, not a hard module naming mandate.

### Application/query layer

Introduce a dedicated fleet workbench query/projection path:

- new fleet workbench DTOs and projection output in the application layer
- dedicated normalization from `AgendaSnapshot` / `AgendaItem` into:
  - header summary
  - normalized rows
  - selected-operation fleet brief

Likely touch points:

- [operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_projections.py)
- new query module adjacent to [operation_dashboard_queries.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_dashboard_queries.py)
- [agenda.py](/Users/thunderbird/Projects/operator/src/agent_operator/runtime/agenda.py) only where upstream summary enrichment is truly necessary

### CLI driving adapter

Update fleet CLI entrypoints to consume the new projection:

- [main.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/main.py)
- fleet `--once`
- fleet `--json`
- zero-argument `operator` when it resolves to fleet behavior

### TUI driving adapter

Update fleet TUI rendering to consume normalized rows and normalized fleet brief:

- [tui.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui.py)

Expected changes:

- replace the current fleet row DTO with a contract-aligned row model
- replace the old list-table/dashboard-style detail rendering
- preserve existing command dispatch callbacks
- preserve deeper operation/session drill-down behavior

### Tests

Add or update tests in three layers:

- projection tests for fleet normalization
- CLI tests for fleet snapshot / `--json`
- TUI tests for fleet rendering/controller behavior against the new payload shape

Likely touch points:

- [test_operation_projections.py](/Users/thunderbird/Projects/operator/tests/test_operation_projections.py)
- [test_tui.py](/Users/thunderbird/Projects/operator/tests/test_tui.py)
- [test_cli.py](/Users/thunderbird/Projects/operator/tests/test_cli.py)

## Implementation checklist

The intended execution order for this ADR is:

1. **Introduce the fleet workbench projection API**
   - add a dedicated fleet workbench query/projection path
   - keep it separate from the broader operation dashboard payload

2. **Normalize fleet rows**
   - add projection fields for:
     - `display_name`
     - `attention_badge`
     - `state_label`
     - `agent_cue`
     - `recency_brief`
     - `row_hint`
     - `sort_bucket`

3. **Normalize the selected-operation fleet brief**
   - add explicit fleet brief fields for:
     - `goal`
     - `now`
     - `wait`
     - `progress.done`
     - `progress.doing`
     - `progress.next`
     - `attention`
     - `recent`

4. **Add projection-level tests first**
   - verify row normalization
   - verify row sorting
   - verify fleet brief assembly

5. **Switch CLI fleet snapshot to the new projection**
   - update `operator fleet --once`
   - update `operator fleet --json`
   - keep non-TTY fleet output aligned with the same shared projection

6. **Switch TUI fleet rendering to the new projection**
   - replace the old fleet row DTO/render assumptions
   - render the agreed 3-line row semantics
   - render the agreed fleet brief sections
   - preserve existing shared command callbacks

7. **Update adapter-level tests**
   - update TUI tests to use the new fleet payload shape
   - add CLI tests for textual snapshot and JSON snapshot parity

8. **Polish only after parity is established**
   - truncation behavior
   - narrow-terminal fallback
   - optional compact multi-agent cues if strongly grounded

### Explicitly deferred from this tranche

- full operator-load modeling
- arbitrary configurable layouts
- full multi-agent fleet grammar
- redesign of deeper `Operation View` / `Session View` contracts

## Follow-on implementation note: Operation View

The `Operation View` tranche is narrower than the fleet tranche.

Unlike `Fleet`, the repository already has most of the required application/query substrate for the
new `Operation View` contract:

- task-board data
- selected-task detail data
- decision memo data
- recent event data
- memory data
- session linkage data
- shared command paths for `answer`, `pause`, `unpause`, `interrupt`, and `cancel`

The main gap is therefore not action parity and not the existence of deeper query substrate.
The main gap is:

- lack of a normalized compact operation-brief contract inside the one-operation query payload
- and lack of TUI rendering that matches the new split right-pane contract

### Operation View implementation checklist

1. **Add a normalized operation-brief section to the one-operation query/projection path**
   - extend the existing one-operation dashboard/query payload with a dedicated compact
     `operation_brief` section
   - preferred fields:
     - `now`
     - `wait`
     - `progress.done`
     - `progress.doing`
     - `progress.next`
     - `attention`
     - `recent`

2. **Keep the broader operation dashboard payload for deeper data**
   - do not build a separate second truth for decisions, events, memory, sessions, or transcript
   - continue to use the shared one-operation query path as the source for deeper drill-down

3. **Switch TUI `Operation View` rendering to the new contract**
   - keep the left pane as a task-first board
   - split the right pane into:
     - compact operation brief
     - selected-task panel
   - keep selected-task modes:
     - `detail`
     - `decisions`
     - `events`
     - `memory`

4. **Preserve shared command semantics**
   - `answer`, `pause`, `unpause`, `interrupt`, and `cancel` must continue to flow through shared
     command/use-case paths with CLI-equivalent semantics

5. **Update tests**
   - projection tests for the new compact `operation_brief`
   - TUI tests for:
     - task-board rendering assumptions
     - split right-pane assumptions
     - task selection continuity across pane switches
     - drill-down continuity into `Session View`

### Operation View file-by-file plan

Likely touch points:

- [operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_projections.py)
  - add normalized `operation_brief` output alongside existing dashboard fields
- [operation_dashboard_queries.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_dashboard_queries.py)
  - keep as the shared one-operation query entrypoint
- [tui.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui.py)
  - update `Operation View` rendering to the new split right-pane contract
- [test_operation_dashboard_queries.py](/Users/thunderbird/Projects/operator/tests/test_operation_dashboard_queries.py)
  - assert normalized `operation_brief` content
- [test_tui.py](/Users/thunderbird/Projects/operator/tests/test_tui.py)
  - assert the new operation-view layout assumptions

### Operation View tranche classification

- `implemented`: shared one-operation query substrate and action parity
- `implemented`: operation-level brief normalization (`operation_brief` in dashboard payload)
- `implemented`: final rendering contract in TUI for `Task Board + Operation Brief`

### Operation View verification status

- `OperationProjectionService.build_dashboard_payload` now includes `operation_brief` with the
  normalized fields (`goal`, `now`, `wait`, `progress`, `attention`, `recent`).
- `tui_rendering.py` now renders the operation right pane as:
  - compact operation brief
  - selected task detail when in detail mode
- Coverage:
  - `tests/test_operation_dashboard_queries.py`
  - `tests/test_tui.py`

## Alternatives considered

### Option A: Keep reusing `AgendaSnapshot` + old fleet payload as the final fleet contract

Rejected.

That preserves an implementation-oriented shape rather than the agreed UX contract and keeps fleet
semantics split between runtime summaries and delivery-specific interpretation.

### Option B: Reuse the full operation dashboard payload for fleet rows and fleet brief

Rejected.

That encourages fleet sprawl into an `Operation View` substitute and keeps the fleet surface coupled
to deeper one-operation inspection concerns.

### Option C: Build a dedicated TUI-only fleet model

Rejected.

That violates the CLI/TUI parity direction and creates a second truth for the same product surface.

### Option D: Introduce a dedicated fleet workbench projection shared by CLI and TUI

Accepted.

This is the narrowest route that satisfies the existing ADR chain and the current fleet UX contract.

## Consequences

- Fleet becomes a first-class shared product surface rather than an agenda dump plus TUI rendering.
- CLI and TUI fleet behavior become easier to keep aligned.
- Future `dense` or `attention` modes can vary rendering emphasis without changing the underlying
  shared fleet semantics.
- Operator-load and multi-agent cues remain intentionally conditional instead of being overclaimed in
  the first tranche.

## Verification

The tranche is complete only when all of the following are true:

1. Fleet TUI rendering consumes the dedicated fleet workbench projection rather than the old
   dashboard-like list shape.
2. CLI fleet snapshot and `--json` consume the same projection truth.
3. Fleet rows expose the normalized 3-line semantics through projection fields rather than delivery
   heuristics alone.
4. The selected-operation fleet brief is available without depending on a broad operation dashboard
   contract.
5. Fleet actions in TUI still route through shared command/use-case paths with CLI-equivalent
   semantics.

### Verification artifacts

- 2026-04-09: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` → `391 passed, 11 skipped`.
- Added regression coverage for:
  - `test_build_fleet_workbench_payload_normalizes_rows_and_header`
  - `test_fleet_view_uses_selected_fleet_brief_sections`

## Dependencies

- `ADR 0109` for CLI authority and TUI workbench role split
- `ADR 0112` for action parity and safety
- `ADR 0113` for projection-over-substrate rules
- `ADR 0114` for CLI/TUI shared delivery substrate extraction
