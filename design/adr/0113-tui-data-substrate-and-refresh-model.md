# ADR 0113: TUI Data Substrate and Refresh Model

## Status

Implemented

## Context

TUI reliability depends on the same state model used by CLI and persisted runtime artifacts.
The operator already has several stable read surfaces:

- canonical shell-native summary via `status`,
- lightweight textual live following via `watch`,
- supervisory snapshots via `fleet` and related workbench queries,
- operation inspection via `tasks`, `memory`, `artifacts`, and `report`,
- and debug/forensic inspection via `operator debug ...` surfaces such as `context` and `trace`.

Without explicit substrate rules, TUI is at risk of introducing a second state system and creating
stale or inconsistent displays.

## Decision

TUI must operate as a projection layer over existing application-facing query/projection services
and persisted runtime truth, not as a separate runtime authority or a CLI-local read path.

### Canonical truth

- source-of-truth for live supervision: persisted operation/task/session state files and the
  application-facing query/projection services derived from them;
- action execution: application-facing command/use-case ports that preserve the same semantics as
  public CLI commands;
- display transforms: TUI-only rendering only, no state ownership.

In hexagonal terms:

- CLI and TUI are peer driving adapters;
- TUI does not read through CLI-local rendering helpers;
- TUI consumes the same shared query/projection contracts and command/use-case contracts exposed to
  delivery surfaces.

### Refresh model

1. **Default mode:** polling-based view refresh is acceptable and consistent with current live behavior.
2. Poll interval default is `0.5s`; CLI flag `--poll-interval` is the TUI-side override source.
3. TUI refresh reads through the same query/projection paths that back `fleet`, `status`, `watch`,
   and related supervisory snapshots for consistency.
4. Refresh must remain bounded for N active operations and degrade gracefully when file reads fail.
5. Event-driven wakeup refresh is preferred when wakeup/event APIs provide a stable public path in the
   future; this transition is tracked explicitly and cannot regress polling fallback.

### Output consistency

- status glyphs and terminal states follow the existing status model (`RUNNING`, `NEEDS_HUMAN`, `FAILED`,
  `CANCELLED`, `COMPLETED`, etc.).
- no TUI-only status enum should be added.
- raw transcript rendering uses existing `log` command contract.

### Roadmap gating in substrate decisions

- `operator_acp` hierarchy is allowed in layout only if underlying operation hierarchy runtime contracts are
  implemented.
- `ambient observations` (e.g. `[~N]`) must have a dedicated upstream runtime model before TUI propagation is
  treated as stable.

## Alternatives Considered

### Option A: Add a dedicated TUI state cache/database and bypass CLI read models

Rejected.

This creates a second truth source and increases divergence risk between automation and supervision.

### Option B: Polling-only forever without future event-driven path

Rejected.

Poll-only is simpler initially but misses an explicit optimization path and can drift against future
runtime contracts.

### Option C: Projection-only model with bounded polling and explicit event-driven upgrade path

Accepted.

This is consistent with current architecture, keeps behavior auditable, and enables phased optimization.

## Consequences

- TUI implementation work can proceed without introducing extra persistence or hidden synchronization logic.
- Non-trivial behavior changes must be implemented in application command/query contracts first,
  then adopted by CLI and TUI adapters.
- Operational bugs in state projection become diagnosable by validating against existing CLI outputs.
- Staleness budgets and refresh behavior become design-reviewed and measurable.

## Verification

- `tests/test_tui.py::test_fleet_refresh_failure_is_reported_and_non_fatal`
- `tests/test_tui.py::test_fleet_operation_payload_refresh_failure_is_non_fatal`

`FleetWorkbenchController.refresh` now catches read path failures for both fleet-list and per-operation
payloads, preserves prior UI state where possible, and emits concise error text without interrupting
interactive execution.
