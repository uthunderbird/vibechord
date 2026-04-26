# ADR 0209: Legacy Removal and Migration Gate

- Date: 2026-04-23

## Decision Status

Accepted

## Implementation Status

Partial

Implementation grounding on 2026-04-26:

- `implemented`: v2 mutation-path structure already has static guardrails that fail if core v2
  business writes reintroduce direct `save_operation()` snapshot authority. Evidence:
  `tests/test_application_structure.py::test_adr_0203_v2_mutation_paths_do_not_save_legacy_snapshots`,
  `tests/test_application_structure.py::test_drive_loop_save_operation_only_via_advance_checkpoint`.
- `implemented`: canonical entrypoint loading now isolates snapshot reads behind an explicit named
  fallback helper, so canonical state loading and resume preparation do not silently depend on
  `.operator/runs` semantics. Evidence:
  `src/agent_operator/application/operation_entrypoints.py`,
  `tests/test_operation_entrypoints.py::test_operation_entrypoint_service_loads_canonical_state_without_snapshot`,
  `tests/test_operation_entrypoints.py::test_operation_entrypoint_service_isolates_snapshot_reads_to_named_fallback`.
- `implemented`: covered CLI control and forensic paths now read canonical event-sourced operation
  state even when no legacy snapshot exists, including `answer`, `patch-objective`, `debug wakeups`,
  and `debug sessions`. Evidence:
  `src/agent_operator/cli/workflows/control.py`,
  `src/agent_operator/cli/workflows/forensics.py`,
  `src/agent_operator/cli/helpers/services.py`,
  `tests/test_cli.py::test_answer_uses_canonical_operation_state_without_snapshot`,
  `tests/test_cli.py::test_patch_objective_command_wait_for_ack_uses_canonical_operation_state`,
  `tests/test_cli.py::test_debug_wakeups_reads_event_sourced_operation_without_runs_dir`,
  `tests/test_cli.py::test_debug_sessions_reads_event_sourced_operation_without_runs_dir`.
- `implemented`: delivery-command loading now keeps direct snapshot reads behind an explicit
  `_load_snapshot_fallback()` helper, so canonical-first delivery behavior and legacy fallback are
  separated in the same way as entrypoint loading. Evidence:
  `src/agent_operator/application/commands/operation_delivery_commands.py`,
  `tests/test_operation_delivery_commands.py::test_answer_attention_prefers_canonical_state_loader_over_snapshot_store`,
  `tests/test_operation_delivery_commands.py::test_answer_attention_uses_snapshot_fallback_when_canonical_state_missing`,
  `tests/test_operation_delivery_commands.py::test_operation_delivery_command_service_isolates_snapshot_reads_to_named_fallback`.
- `partial`: snapshot fallback still exists in shared resolution/query and delivery-command loader
  code for mixed-mode and migration cases. The repository truth is therefore "legacy constrained and
  explicitly bounded," not "legacy removed." Evidence:
  `src/agent_operator/application/queries/operation_resolution.py`,
  `src/agent_operator/application/queries/operation_status_queries.py`,
  `src/agent_operator/application/commands/operation_delivery_commands.py`.
- `blocked`: this ADR's stronger removal gate is not yet closed because the repository still keeps
  `.operator/runs` as legacy or migration input and still contains many legacy-fixture tests.

## Context

The repository is pre-release and already has a full-rewrite v2 strategy. However, legacy snapshot
paths remain in code and tests. Removing them without gates risks losing migration evidence,
breaking forensic workflows, or replacing explicit debt with hidden compatibility behavior.

The repository now has enough concrete static and behavioral guardrails to anchor the decision
itself in git, even though removal is still incomplete. Acceptance here records that legacy
retention must stay explicit, bounded, and test-guarded; it does not claim that `.operator/runs`
has been fully removed.

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
