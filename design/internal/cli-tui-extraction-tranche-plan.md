# CLI/TUI Extraction Tranche Plan

Internal implementation plan. Not architectural authority by itself.

## Purpose

This note turns `ADR 0114` into an implementation-oriented tranche plan.

Current implementation snapshot:

- [cli-tui-extraction-tranche-outcome-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/cli-tui-extraction-tranche-outcome-2026-04-09.md)

It exists to answer a narrow question:

- what should move out of `src/agent_operator/cli/main.py` before substantial TUI work begins,
- in what order,
- and along which architectural boundaries.

This document does not change the authority chain:

- `ARCHITECTURE.md` remains the structural overview,
- `ADR 0109`, `ADR 0112`, `ADR 0113`, and `ADR 0114` remain the design authority for the CLI/TUI
  boundary,
- and this note is only a concrete implementation plan.

The linked outcome note records repository truth after the first extraction waves; this plan
remains the forward-looking tranche map.

## Governing Rule

Build explicit command/query contracts before TUI delivery work.

In practice, that means:

- application-facing command/use-case ports before TUI action wiring,
- application-facing query/projection services before TUI panels,
- CLI-only rendering separation before any TUI reuse attempt,
- and thin delivery adapters rather than a new middle-layer mini-framework.

## Architectural Reading

In hexagonal terms:

- CLI and future TUI are peer driving adapters.
- Shared state-changing paths belong to application-facing command/use-case ports.
- Shared supervisory and inspection read models belong to application-facing query/projection
  services.
- Rich and future TUI rendering remain adapter-local.

This tranche should therefore avoid two bad outcomes:

1. a direct TUI dependency on CLI-specific Rich helpers
2. a new ambiguous "delivery substrate" layer that becomes a second application layer in practice

## Scope

This tranche is limited to reusable delivery-facing extraction from:

- `src/agent_operator/cli/main.py`

The goal is not total CLI decomposition.

The goal is to make these reusable without CLI rendering or Typer wiring:

- supervisory read models,
- inspection read models,
- lifecycle/intervention action paths.

## Non-Goals

This tranche does not require:

- moving every CLI command into its own file,
- redesigning public command names or flags,
- reworking debug/smoke surfaces unless they block the extraction,
- introducing a TUI framework,
- or minimizing `cli/main.py` to an ideal endpoint before other progress continues.

## Recommended Implementation Order

### Phase 1: query/projection extraction

Extract shared application-facing query/projection services first.

Why first:

- TUI supervision depends on read models before it depends on rendering,
- CLI/TUI drift is most likely if projections stay trapped in the CLI module,
- and this extraction is lower-risk than moving action semantics first.

### Target outcomes

- supervisory and inspection payload construction is callable without importing Rich rendering code
- the resulting models are UI-agnostic and suitable for both CLI and TUI adapters
- projection ownership is explicit rather than hidden inside command handlers

### Initial candidate groups from `cli/main.py`

- fleet and agenda projections
- project dashboard projections
- operation dashboard/status/context projections
- durable truth projections for inspect/report/tasks/memory/artifacts
- live snapshot and operation summary payloads where they are reusable without Rich-specific
  presentation assumptions

### Candidate extraction targets

Possible destination shapes:

- `src/agent_operator/application/projections.py`
- or `src/agent_operator/application/projections/`

Representative projection families:

- `fleet`
- `agenda`
- `dashboard`
- `context`
- `inspect`
- `report`
- `tasks`
- `memory`
- `artifacts`

## Phase 2: command/use-case extraction

Extract shared application-facing command/use-case ports for lifecycle and intervention actions.

Why second:

- action parity matters for TUI,
- but action extraction is safer after the query side has already clarified which behaviors are
  read-only vs state-changing,
- and this keeps the command/query split explicit.

### Target outcomes

- CLI commands become thinner adapters over reusable command/use-case entrypoints
- future TUI actions can route through the same semantics
- state mutation paths stop living inside Typer-oriented glue

### Initial candidate groups from `cli/main.py`

- `status`
- `pause`
- `unpause`
- `interrupt`
- `answer`
- `cancel`
- command enqueue paths

### Candidate extraction targets

Possible destination shapes:

- `src/agent_operator/application/delivery_commands.py`
- `src/agent_operator/application/operator_controls.py`
- or a narrow package of command-side adapter-facing entrypoints

## Phase 3: CLI rendering separation

Move CLI-specific Rich rendering behind explicit rendering boundaries.

Why third:

- once query/projection services exist, rendering separation becomes straightforward,
- and this ensures CLI remains a strong adapter without becoming a reuse source for TUI.

### Target outcomes

- Rich panels, tables, and live layouts no longer own payload assembly
- CLI rendering consumes shared projections rather than rebuilding them
- future TUI work has no reason to import Rich helpers

### Candidate extraction targets

Possible destination shapes:

- `src/agent_operator/cli/rendering.py`
- or `src/agent_operator/cli/rendering/`

Representative rendering families:

- fleet rendering
- project dashboard rendering
- operation dashboard rendering
- live watch formatting

## Phase 4: CLI adapter thinning

After projection and command extraction, reduce `cli/main.py` to adapter responsibilities.

### Desired end state

`src/agent_operator/cli/main.py` should primarily own:

- Typer command registration
- command-line option parsing and normalization
- invocation of application-facing command/query contracts
- routing into CLI-local rendering
- CLI-only help and hidden-command behavior

It should not remain the primary home for:

- shared read-model assembly
- shared state-changing action semantics
- or Rich rendering internals

## Suggested Ownership Split

### Delivery adapter ownership

CLI and future TUI should own:

- input parsing
- keybinding interpretation
- navigation rules
- rendering and presentation
- surface-specific empty-state behavior

### Application ownership

Application-facing command/query contracts should own:

- state-changing control semantics
- supervisory and inspection projection assembly
- reusable read/write orchestration exposed to delivery surfaces

### Integration ownership

Integration-layer components should continue to own:

- stores
- event sinks
- ACP adapters
- clocks and process services
- other external-system mechanics

## Practical File Strategy

The first tranche should prefer extraction by architectural role, not by command count.

Prefer:

- one projection-oriented module or package,
- one command/use-case-oriented module or package,
- one CLI rendering-oriented module or package,
- then a thinner `cli/main.py`

Do not begin with:

- one-file-per-command decomposition,
- or a large generic `cli/substrate.py` dumping ground.

## Exit Criteria

This tranche is complete when all of the following are true:

1. TUI implementation can consume supervisory and inspection data without importing CLI Rich
   helpers.
2. TUI-triggered actions can route through the same application-facing command/use-case paths as
   public CLI commands.
3. `src/agent_operator/cli/main.py` is no longer the primary location of:
   - shared projection assembly,
   - shared state-changing action semantics,
   - and Rich rendering internals.
4. Public CLI command names, arguments, and user-facing semantics remain unchanged.

## Deferral Rules

The following may remain deferred after this tranche if they do not block the exit criteria:

- broader CLI modularization
- debug and smoke surface cleanup
- ideal final package layout refinement
- TUI framework choice and concrete pane implementation

## Working Conclusion

The right pre-TUI move is not "split the CLI everywhere."

The right move is:

1. extract application-facing query/projection services
2. extract application-facing command/use-case ports
3. isolate CLI-local rendering
4. leave CLI and future TUI as thin driving adapters over those contracts
