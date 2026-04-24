# ADR 0209: Legacy Removal and Migration Gate

- Date: 2026-04-23

## Decision Status

Proposed

## Implementation Status

Planned

## Context

The repository is pre-release and already has a full-rewrite v2 strategy. However, legacy snapshot
paths remain in code and tests. Removing them without gates risks losing migration evidence,
breaking forensic workflows, or replacing explicit debt with hidden compatibility behavior.

## Decision

Legacy removal requires an explicit gate.

For each legacy path, choose exactly one:

- delete with no migration because it is not authoritative
- keep as read-only migration input until a named removal date
- convert with one bounded migration/import script

No new compatibility fallback may be added without naming its retirement condition.

## Required Properties

- `.operator/runs` is not required for new v2 operations.
- `FileOperationStore` is not injected into v2 control/query paths except where explicitly marked
  legacy or migration-only.
- docs stop advertising legacy behavior as current behavior.
- tests distinguish legacy fixtures from v2 canonical fixtures.

## Verification Plan

- static tests prevent new v2 business writes through `save_operation()`.
- v2 e2e passes after deleting `.operator/runs` for the tested operation.
- migration/import script, if any, has before/after fixture tests.
- docs search shows no stale claim that `.operator/runs` is operation authority.

## Related

- ADR 0077
- ADR 0086
- ADR 0108
- ADR 0194
- ADR 0203
