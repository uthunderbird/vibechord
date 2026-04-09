# ADR 0114: CLI Delivery Substrate Extraction Before TUI

## Status

Implemented

## Context

`ADR 0038` and `ADR 0109` establish the product boundary:

- CLI is the authoritative control surface.
- TUI is a supervisory workbench layered over the same persisted truth.
- TUI must not invent separate control semantics.

`ADR 0112` and `ADR 0113` tighten that boundary further:

- state-changing TUI actions must map to existing CLI command semantics,
- and TUI must operate as a projection over existing persisted truth and read models.

This ADR records the extraction rule that made the current TUI direction viable and remains the
constraint for further delivery work.

The implementation shape that prompted this ADR created a delivery-layer obstacle to that direction.

`src/agent_operator/cli/main.py` is not only Typer command wiring. It currently combines:

- public command registration and CLI entry behavior,
- async control/execution paths for lifecycle and intervention commands,
- read-model and payload construction for surfaces such as `fleet`, `dashboard`, `context`,
  `inspect`, and related summaries,
- and Rich-specific terminal rendering for live supervision views.

That structure is workable for a CLI-first product, but it is a poor substrate for TUI delivery.
If TUI implementation starts directly on top of the current module shape, the likely outcomes are:

- direct reuse of CLI-specific Rich rendering helpers inside TUI code,
- duplication of read-model assembly and action-dispatch logic,
- or gradual creation of a second implicit UI authority path.

That would violate the delivery and authority boundaries established by the existing ADR chain.

## Decision

`operator` must extract and preserve explicit application-facing ports and projection services out of
the CLI entry module so CLI and TUI act as thin driving adapters over the same underlying contracts.

This extraction is not a cosmetic refactor. It is the architectural prerequisite that the existing
and future TUI work must continue to respect.

The term **shared delivery substrate** in this ADR is a migration term for the extraction tranche.
It is not a new top-level enduring architectural layer parallel to the existing application layer.
In hexagonal terms:

- CLI and TUI are the driving adapters,
- shared action entrypoints belong to application-facing command/use-case ports,
- shared supervisory read models belong to application-facing query/projection services,
- and UI-specific rendering remains local to each adapter.

### Required extraction boundaries

The following boundaries must exist before TUI is implemented against them:

1. **Application-facing query/projection services**
   - Data assembly for supervisory surfaces such as `fleet`, `status`, `watch`, workbench queries,
     `tasks`, `memory`, `artifacts`, `report`, and related operation summaries
     must be callable without importing CLI-specific Rich rendering code.
   - These projections are shared application-facing read models for delivery surfaces; they are
     not CLI-local helpers and not TUI-owned state.
   - Debug and forensic inspection surfaces such as `operator debug context`, `operator debug trace`,
     and `inspect` may consume the same underlying projection services, but they are not the primary
     supervisory contract that drives the TUI workbench taxonomy.

2. **Application-facing command/use-case ports**
   - Existing lifecycle and intervention flows used by CLI commands such as `status`, `pause`,
     `unpause`, `interrupt`, `answer`, `cancel`, and command enqueue paths must be reachable
     through shared application-facing helpers rather than being trapped inside Typer command
     functions or terminal-oriented command glue.
   - These paths express application control semantics; they are not delivery-owned business
     logic and should not be framed as a second orchestration layer.

3. **CLI-only rendering separation**
   - Rich layout/rendering and terminal presentation helpers remain in the CLI delivery layer and
     must not become the reuse boundary for TUI.

4. **Driving adapter thinness**
   - CLI and future TUI should each translate surface-specific inputs into calls on the shared
     command/query contracts.
   - Input parsing, keybinding handling, navigation behavior, and presentation remain adapter-local.

5. **CLI command wiring remains authoritative**
   - Typer command registration, help behavior, hidden-command policy, and shell-facing argument
     handling remain in the CLI surface and are not the substrate TUI reuses.

### Non-goals

This ADR does not require:

- moving every CLI command into its own module,
- fully minimizing `src/agent_operator/cli/main.py` before any other work proceeds,
- changing public CLI semantics,
- introducing a TUI-only abstraction layer,
- introducing a new permanent architectural layer between delivery and application,
- or replacing the existing CLI control surface as the canonical user path.

## Decision Consequences

- TUI implementation can consume shared query/projection services and shared command/use-case
  ports without importing CLI terminal rendering code.
- CLI remains the authoritative public surface, but it stops being the only place where
  delivery-facing read-model assembly and action glue live.
- `status` remains the canonical shell-native one-operation summary surface.
- `watch` remains a lightweight textual live follower rather than the preferred interactive
  supervision surface.
- TUI remains the preferred interactive live supervision surface over the shared substrate.
- Future delivery work is partitioned by authority:
  - application-facing command/use-case ports,
  - application-facing query/projection services,
  - CLI-specific shell and rendering layer,
  - TUI-specific rendering and navigation layer.
- Refactor scope is constrained: only the reusable substrate is prerequisite work; broader CLI
  modularization stays optional.

## Alternatives Considered

### Option A: Implement TUI directly against the current `cli/main.py` structure

Rejected.

That encourages either reuse of CLI-specific rendering code or duplication of shared logic, and it
raises the risk of hidden divergence between CLI and TUI behavior.

### Option B: Fully decompose the entire CLI before any TUI work

Rejected.

That is broader than necessary. The architectural requirement is extraction of the shared
data/action substrate, not total CLI reorganization.

### Option C: Extract only the shared substrate needed by both delivery surfaces

Accepted.

This gives TUI a clean architectural footing while preserving momentum and avoiding a cosmetic
refactor wave.

## Hexagonal Interpretation

The canonical hexagonal reading of this ADR is:

- **Driving adapters:** CLI and future TUI.
- **Inbound application contracts:** command/use-case ports for state-changing and control actions.
- **Application query/projection contracts:** shared supervisory and inspection read models.
- **Driven adapters / infrastructure:** existing stores, event sinks, clocks, ACP adapters, and
  other integration-layer components already described by the architecture docs.

This ADR therefore does not create a new architectural "substrate layer" between delivery and
application. It requires the existing delivery code to stop hiding application-facing command and
query contracts inside a CLI-specific module.

## Verification

Implementation is materially complete and verified by tests plus static shape checks:

- `tests/test_operation_projections.py`
- `tests/test_operation_delivery_commands.py`
- `tests/test_operation_agenda_queries.py`
- `tests/test_operation_project_dashboard_queries.py`
- `tests/test_operation_dashboard_queries.py`
- `tests/test_tui.py`
- `tests/test_cli.py`

Observed outcomes:

- `src/agent_operator/cli/main.py` is now a thin shell adapter (exports command app, service factory and
  thin workflow entrypoints only).
- CLI/TUI surfaces consume shared `OperationDeliveryCommandService`, `OperationAgendaQueryService`,
  `OperationDashboardQueryService`, and `OperationProjectDashboardQueryService` instead of inlining shared
  projection logic.
- CLI-only rendering paths remain in `src/agent_operator/cli/rendering*.py` and `helpers_rendering.py` while data
  construction and control ports stay in application-facing services.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_operation_projections.py tests/test_operation_delivery_commands.py tests/test_operation_agenda_queries.py tests/test_operation_project_dashboard_queries.py tests/test_operation_dashboard_queries.py tests/test_tui.py tests/test_cli.py -q`
  reports `141 passed`.

## Dependencies

- `ADR 0038` for CLI authority and TUI workbench boundary.
- `ADR 0109` for the refined CLI-authority contract for the TUI series.
- `ADR 0112` for action parity and safety mapping.
- `ADR 0113` for TUI projection-over-substrate rules.
