# ADR 0172: Derived Live Status Over Stored Session Summary

## Decision Status

Accepted

## Implementation Status

Verified

Implementation grounding on 2026-04-14:

- `implemented`: `OperationStatusQueryService` already distinguishes durable truth from live
  runtime alerting by reading background inspection and pending wakeups during status queries
- `implemented`: `overlay_live_background_progress()` updates timestamps from live background
  inspection without overwriting `SessionRecord.waiting_reason`
- `implemented`: `OperationStatusQueryService.build_live_snapshot()` suppresses stale
  `waiting_reason` output when `runtime_alert` is present
- `implemented`: dashboard/TUI status surfaces already prefer `runtime_alert` over stale
  `waiting_reason` text
- `verified`: targeted status/query, projection, and TUI regression coverage exists for the
  derived-status behavior at current repository truth

## Context

The operator repeatedly shows stale or contradictory short status snapshots such as:

- `session_status: running`
- `waiting_reason: "Agent session completed."`

even while `inspect`, timeline, and background inspection already show that the operation has
either advanced to a new iteration or is carrying unreconciled wakeups that require a resume.

The repository now has enough concrete evidence that this is not a one-off rendering bug. It is
an architectural problem: multiple overlapping status surfaces are being treated as if they were
one source of truth.

Current repository truth mixes at least three distinct layers:

1. durable reconciled operation truth from the checkpoint/store
2. live runtime inspection truth from background run files and wakeup inboxes
3. human-facing session summary fields such as `SessionRecord.waiting_reason`

The main problematic write path is `overlay_live_background_progress()`, which takes runtime
inspection output and writes `run.progress.message` into a copied `SessionRecord.waiting_reason`.
That means a read-time status query mutates a read model into a hybrid object that looks like
canonical session truth even though it is only a transient overlay.

This creates a false-state surface:

- durable session state says one thing,
- runtime inspection says another,
- and the short status view renders the mixed copy as if it were current truth.

## Decision

Treat live status as a derived query product, not a stored or overlaid session-summary field.

Specifically:

- `SessionRecord.waiting_reason` remains reconciled session truth only
- read-time background inspection must not overwrite `SessionRecord.waiting_reason`
- live runtime conditions such as pending wakeups, terminal-but-unreconciled background runs, or
  in-flight background progress must be rendered from dedicated derived fields
- status surfaces must distinguish:
  - reconciled truth
  - live runtime overlay
  rather than collapsing them into one mutable session summary field

The rule is:

> status must be derived, not stored

and:

> runtime overlays may annotate a status response, but must not masquerade as canonical
> `SessionRecord` truth

## Consequences

### Positive

- `status` becomes less misleading during reconciliation lag
- pending wakeups and background-run inspection take precedence over stale session summary text
- the system moves toward one canonical truth path for short status surfaces
- future status bugs become easier to localize because the query layer no longer rewrites session
  summary fields on read

### Negative

- some live status outputs may become less chatty until dedicated derived live-progress fields are
  added everywhere
- callers that implicitly relied on overlaid `waiting_reason` text may need updates

### Neutral / Follow-on

- this ADR does not eliminate `waiting_reason` entirely
- this ADR does not yet remove all summary-like fields from operation/session models
- a later tranche may introduce explicit split payload sections such as:
  - `reconciled_status`
  - `live_runtime_status`

## Alternatives Considered

### 1. Keep storing and overlaying summary strings, but patch contradictory cases one by one

Rejected.

That leaves the root design intact and guarantees repeated stale-status regressions.

### 2. Hide `waiting_reason` only when `runtime_alert` is present

Rejected as the full solution, accepted only as a possible migration aid.

This is a presentation patch, not the architectural correction. It may still be useful as a
bounded implementation slice while removing read-time mutation of session truth.

### 3. Make runtime inspection the only source of status truth

Rejected for now.

Runtime inspection is not durable truth and should not replace canonical reconciled operation
state. The right model is explicit separation, not inversion of authority.

## Closure Evidence Matrix

| ADR line / closure claim | Repository evidence | Verification |
| --- | --- | --- |
| Stop `overlay_live_background_progress()` from copying runtime progress text into `SessionRecord.waiting_reason` | `src/agent_operator/cli/helpers/rendering.py:overlay_live_background_progress` only updates `updated_at` and `last_event_at` on the copied session record | `tests/test_operation_status_queries.py::test_overlay_live_background_progress_keeps_waiting_reason_as_durable_truth` |
| Prefer `runtime_alert` over stale session wait text in status snapshots | `src/agent_operator/application/queries/operation_status_queries.py:build_live_snapshot` only includes `waiting_reason` when `runtime_alert` is absent | `tests/test_operation_status_queries.py::test_build_live_snapshot_omits_stale_waiting_reason_when_runtime_alert_present` |
| Status summaries and dashboards treat runtime alerting as the live source of truth | `src/agent_operator/application/queries/operation_projections.py:build_operation_brief_payload`; `src/agent_operator/cli/rendering/operation.py:render_dashboard`; `src/agent_operator/cli/tui/models.py:session_brief` | `tests/test_operation_projections.py::test_render_dashboard_prefers_runtime_alert_over_waiting_reason`; `tests/test_tui.py::test_tui_session_views_prefer_runtime_alert_over_stale_waiting_reason` |
| Final repository truth is verified against current code and regression tests | changed implementation under `src/agent_operator/...`; this ADR document | `pytest -q tests/test_operation_status_queries.py tests/test_operation_projections.py -q`; `pytest -q tests/test_tui.py -k 'runtime_alert_over_stale_waiting_reason'` |

## Follow-on (Not Blocking Acceptance)

- add explicit derived live-progress payload fields where richer live runtime detail is useful
- split reconciled-status and live-status sections more explicitly in query DTOs if status payloads
  keep growing
- continue reducing summary-like stored strings on operation/session models under the broader
  immutability/query-boundary work in [ADR 0173](./0173-immutable-truth-and-query-boundaries.md)
