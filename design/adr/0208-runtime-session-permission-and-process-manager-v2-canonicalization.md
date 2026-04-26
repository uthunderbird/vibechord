# ADR 0208: Runtime, Session, Permission, and Process-Manager v2 Canonicalization

- Date: 2026-04-23

## Decision Status

Accepted

## Implementation Status

Verified

Implementation grounding on 2026-04-26:

- `implemented`: ACP permission handling accepts both integer and string JSON-RPC request ids,
  normalizes them into shared permission requests, and preserves that id through the connection
  response path so Codex/runtime permission flows are not dropped on UUID-shaped ids. Evidence:
  `src/agent_operator/acp/permissions.py`,
  `src/agent_operator/acp/client.py`,
  `src/agent_operator/acp/adapter_runtime.py`,
  `src/agent_operator/domain/adapter_runtime.py`,
  `tests/test_acp_permissions.py::test_normalize_permission_request_accepts_string_jsonrpc_id`,
  `tests/test_agent_session_runtime.py::test_acp_agent_session_runtime_routes_string_id_permission_request`.
- `implemented`: shared ACP permission handling emits canonical
  `permission.request.observed|decided|escalated|followup_required` facts, records pending-input
  state for escalation/user-input waits, and forces known-but-unhandled permission server requests
  into explicit `session.failed(error_code=\"agent_server_request_unrecognized\")` facts instead of
  silently ignoring them. Evidence:
  `src/agent_operator/acp/runtime_permissions.py`,
  `src/agent_operator/acp/session_runtime.py`,
  `tests/test_acp_permissions.py::test_shared_permission_helper_records_escalation_payload`,
  `tests/test_acp_permissions.py::test_shared_permission_helper_reject_sets_last_error_and_closes`,
  `tests/test_acp_permissions.py::test_shared_permission_helper_records_user_input_wait`,
  `tests/test_agent_session_runtime.py::test_acp_agent_session_runtime_known_permission_request_never_silently_noops`.
- `implemented`: v2 drive execution materializes runtime permission facts into canonical domain
  events, links escalations to blocking attentions, carries follow-up-required evidence into the
  next brain call, and records terminal session facts before adapter close completion is allowed to
  lag behind. Evidence:
  `src/agent_operator/application/drive/policy_executor.py`,
  `tests/test_drive_service_v2.py::test_policy_executor_records_terminal_success_before_close_returns`,
  `tests/test_drive_service_v2.py::test_drive_service_materializes_permission_escalation_as_attention_request`,
  `tests/test_drive_service_v2.py::test_drive_service_materializes_approved_permission_decision_events`,
  `tests/test_drive_service_v2.py::test_drive_service_materializes_rejected_codex_permission_followup_events`,
  `tests/test_drive_service_v2.py::test_drive_service_exposes_codex_permission_followup_to_next_brain_call`,
  `tests/test_drive_service_v2.py::test_drive_service_exposes_checkpoint_permission_followup_to_brain`.
- `implemented`: restart/crash recovery and runtime/supervisor coordination remain event-driven in
  v2. Orphaned sessions become canonical `session.crashed` events, while the v2 supervisor is
  treated as an orphan-tracking authority rather than a legacy polling API. Evidence:
  `src/agent_operator/application/drive/runtime_reconciler.py`,
  `tests/test_runtime_reconciler.py::test_detect_orphaned_v2_no_running_sessions_returns_empty`,
  `tests/test_runtime_reconciler.py::test_detect_orphaned_v2_known_session_not_orphaned`,
  `tests/test_runtime_reconciler.py::test_detect_orphaned_v2_unknown_session_generates_crashed_event`,
  `tests/test_runtime_reconciler.py::test_detect_orphaned_v2_runs_once_per_drive_call`,
  `tests/test_runtime_reconciler.py::test_drain_wakeups_releases_v2_supervisor_events_without_polling_api`,
  `tests/test_runtime_reconciler.py::test_poll_background_runs_returns_empty_for_v2_supervisor`.
- `implemented`: replay, projections, and user-facing consumers surface canonical permission and
  session facts from durable truth rather than requiring adapter-local state, including legacy
  compatibility normalization for older session/attention payload shapes. Evidence:
  `src/agent_operator/projectors/operation.py`,
  `tests/test_operation_projector.py::test_operation_projector_projects_permission_events_for_replay_visibility`,
  `tests/test_operation_projector.py::test_operation_projector_normalizes_legacy_interrupted_terminal_state`,
  `tests/test_operation_projector.py::test_operation_projector_accepts_legacy_attention_request_id_shape`,
  `tests/test_tui.py::test_tui_session_timeline_includes_replayed_permission_events`,
  `tests/test_tui.py::test_tui_session_timeline_reads_permission_events_from_durable_truth`.
- `implemented`: canonical operation loading is used for policy explainability on v2-only
  operations, which keeps a read-path consumer on replay-derived truth instead of `.operator/runs`
  snapshots. Evidence:
  `src/agent_operator/cli/commands/policy.py`,
  `tests/test_policy_cli.py::test_policy_explain_reads_event_sourced_operation_without_snapshot`.
- `verified`: focused regression suite passed on 2026-04-26:
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_operation_projector.py tests/test_acp_permissions.py tests/test_agent_session_runtime.py tests/test_drive_service_v2.py tests/test_policy_cli.py tests/test_runtime_reconciler.py -q`
  (`72 passed`).
- `verified`: full repository suite passed on 2026-04-26:
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`.

## Context

The runtime layer produces session facts, permission requests, process signals, wakeups, supervisor
state, and crash recovery observations. v2 correctness depends on these facts reaching canonical
events and read models quickly enough for CLI/TUI/MCP/SDK consumers and the brain.

## Decision

Runtime coordination facts that affect operation behavior become event/projector-backed v2
contracts.

Covered facts:

- session created/started/waiting/terminal
- execution registered/linked/observed state
- permission observed/decided/escalated/followup-required
- supervisor background task state
- wakeups and orphan recovery
- process signals and cancellation requests

## Required Properties

- Brain decisions see relevant runtime facts through replay-derived state.
- TUI/live surfaces receive session and permission events promptly.
- Restart/crash recovery is event-driven where behavior depends on the fact.
- Codex rejection or escalation wakes replacement-instruction flow when required.
- Runtime caches remain ephemeral unless explicitly materialized as domain events.

## Verification Plan

- restart/crash recovery tests with v2-only fixtures.
- permission approve/reject/escalate/needs_human tests.
- Codex post-denial follow-up regression.
- TUI session timeline receives permission/session events.
- orphan detection produces replayable state transitions.

## Related

- ADR 0082
- ADR 0084
- ADR 0196
- ADR 0200
- ADR 0201
- ADR 0202
