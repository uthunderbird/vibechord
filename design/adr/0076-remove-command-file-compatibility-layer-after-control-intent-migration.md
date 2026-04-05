# ADR 0076: Remove command-file compatibility layer after control-intent migration

## Status

Accepted

## Context

[`ADR 0074`](./0074-bridge-slice-cleanup-after-process-manager-and-planning-trigger-integration.md)
closed the bridge cleanup around process managers and planning triggers. During that cleanup, the
runtime was intentionally left with one temporary compatibility seam:

- canonical command processing now goes through the durable control-intent model
- command files under `commands/` still expose legacy flat top-level fields such as
  `command_type`, `command_id`, `target_scope`, `target_id`, and `payload`

That compatibility output exists only to avoid breaking current CLI and file-based readers during
the migration window.

This repository is pre-release and follows zero-fallback policy. Transitional compatibility is
acceptable only when it is explicitly temporary and tracked to removal. If this shim remains in
place after readers migrate to the control-intent substrate, it will become architectural drift.

## Decision

The flat command-file compatibility layer is temporary and must be removed after all in-repository
consumers that still rely on `commands/*.json` top-level legacy fields are migrated to the
control-intent model.

### Required end state

- `StoredControlIntent` remains the only canonical persisted shape for command/control processing
- `commands/*.json` must no longer duplicate legacy flat command fields solely for compatibility
- command readers inside this repository must consume the canonical model, not the legacy flat shim
- bootstrap and runtime wiring must not preserve compatibility serialization once migration is
  complete

### Scope of removal

This cleanup ADR specifically targets temporary bridge code added for migration safety, including:

- compatibility-only flattening in `FileOperationCommandInbox`
- any bootstrap flags or wiring that exist only to enable that flattening
- tests that assert the legacy flat file shape instead of the canonical control-intent contract

### Non-goal

This ADR does not change the accepted decisions from:

- [`ADR 0072`](./0072-process-manager-policy-boundary-and-builder-assembly.md)
- [`ADR 0073`](./0073-command-bus-and-planning-trigger-semantics.md)
- [`ADR 0074`](./0074-bridge-slice-cleanup-after-process-manager-and-planning-trigger-integration.md)

It only records the obligation to remove a temporary migration shim once it is no longer needed.

## Consequences

- The repository has an explicit cleanup record for the compatibility compromise introduced during
  the bridge cleanup.
- Future work can migrate readers intentionally instead of letting the shim silently fossilize.
- `ADR 0074` stays closed without pretending that the compatibility layer is part of the desired
  long-term architecture.

## Closure Notes

- CLI and in-repository tests now read canonical `StoredControlIntent` records instead of relying
  on legacy flat top-level command fields in `commands/*.json`.
- `FileOperationCommandInbox` no longer emits compatibility-only flattened command payloads.
- Bootstrap wiring no longer enables compatibility serialization for command files.
- `commands/*.json` now persist the canonical control-intent shape only.
- Verification:
  - targeted command/CLI/runtime tests pass
  - full repository test suite passes (`274 passed, 11 skipped`)

## Alternatives Considered

### Keep the compatibility layer indefinitely

Rejected. That would preserve duplicate persistence semantics and violate the repository's stated
pre-release and zero-fallback discipline.

### Treat the shim as the new stable contract

Rejected. The flat command-file shape is a migration aid, not the intended architectural truth.
