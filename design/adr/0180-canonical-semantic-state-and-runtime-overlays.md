# ADR 0180: Canonical semantic state and runtime overlays

- Date: 2026-04-15

## Decision Status

Accepted

## Implementation Status

Verified

Skim-safe status on 2026-04-15:

- `implemented`: the status/query path already derives runtime overlays from wakeup/background-run
  inspection while keeping durable session truth separate
- `implemented`: the runtime reconciliation path already retires redundant wakeup debt after
  equivalent terminal truth is folded
- `verified`: targeted regression coverage exists for both the representative query-side and
  reconciliation-side failure modes this ADR scoped
- `verified`: the full `uv run pytest` suite is green at current repository truth

Implementation grounding on 2026-04-15:

- `implemented`: `OperationStatusQueryService.build_status_payload()` derives runtime alert inputs
  from explicit background-run payloads instead of mutating durable operation/session truth
- `implemented`: `OperationStatusQueryService.build_live_snapshot()` suppresses stale
  `waiting_reason` output when a runtime overlay is present, so runtime diagnostics do not
  masquerade as canonical session truth
- `implemented`: `OperationRuntimeReconciliationService.reconcile_background_wakeups()` clears
  claimed wakeup debt once wakeups are acknowledged or released
- `implemented`: `OperationRuntimeReconciliationService.reconcile_terminal_background_run_from_supervisor()`
  folds terminal agent truth and emits explicit reconciliation evidence rather than leaving
  terminal background-run debt as a competing authority
- `verified`: query-side regression coverage exists in
  `tests/test_operation_status_queries.py` and
  `tests/test_operation_status_query_immutability.py`
- `verified`: reconciliation-side regression coverage exists in
  `tests/test_operation_runtime_reconciliation_service.py`
- `verified`: CLI/status inspection coverage for the previously divergent unreconciled-terminal
  incident exists in `tests/test_cli.py`

## Context

`operator` currently exposes operation truth through surfaces that mix:

- durable semantic state
- live runtime inspection
- reconciliation debt
- mutable convenience summaries

Repository truth now shows that this produces long-lived contradictions rather than only short-lived
eventual-consistency lag. Observed symptoms include:

- stale `focus` pointing at sessions that are already terminal or cancelled
- `session_status` and task/session summaries that disagree with durable terminal results
- `pending wakeups` that remain visible after equivalent terminal truth has already been folded
- `runtime_alert` and status payloads that combine inspection-store facts and persisted operation
  fields as if they had the same semantic authority

Some domain/runtime skew is unavoidable. Live runtime can know facts that durable state does not
yet reflect:

- whether a subprocess is still alive at this instant
- whether a chunk is currently streaming
- whether a turn is in flight but not terminal
- whether a transient transport or adapter interruption has just occurred

That kind of short-lived temporal skew is normal in an attached/background runtime system.

What is not acceptable is long-lived semantic split-brain where multiple layers can each author
canonical-looking truth about the same operation.

Current repository code still stores mixed runtime-summary fields inside durable operation state,
including session/execution observed-state summaries, waiting reasons, mutable focus, and
reconciliation-debt metadata. Query/status surfaces then merge those fields with runtime inspection
stores directly.

This makes it too easy for the system to present runtime guesses or stale summaries as if they were
canonical semantic facts.

## Decision

`operator` will treat canonical semantic state and runtime liveness state as distinct authorities.

The target model is:

1. **Canonical semantic state** is domain-owned and durably replayable.
2. **Runtime overlays** are live, derived, and explicitly non-canonical.
3. Query/status surfaces may merge both, but must preserve the distinction between them.
4. Terminal events must converge quickly so runtime overlays stop contradicting canonical truth
   after bounded reconciliation.

Under this ADR:

1. Domain state should own semantic facts such as:
   - decisions issued
   - commands issued
   - attention lifecycle
   - durable blocker semantics
   - terminal agent results
   - durable task/session outcomes
2. Runtime layers may own ephemeral facts such as:
   - live liveness
   - heartbeat freshness
   - in-flight execution progress
   - transient busy/waiting transport facts
   - unresolved reconciliation debt before fold
3. Mixed summary fields that currently behave like canonical truth should be progressively reduced
   in authority:
   - they may remain as migration scaffolding
   - but query surfaces must prefer canonical semantic truth plus explicit runtime overlays
   - not raw mutable stored summaries
4. A contradiction between durable terminal truth and a runtime-derived summary must resolve in
   favor of durable semantic truth.

In short:

> runtime can be fresher than domain state for a short time, but it must not become a competing
> semantic authority

and:

> `operator` should publish one semantic truth plus explicit runtime overlays, not one blended
> mutable truth

## Rationale

This repository already has evidence that pure “better hygiene” inside the current blended model is
not sufficient on its own. Wakeup debt, stale focus, and status/session contradictions all trace
back to the same architectural issue:

- semantic-looking state is being authored in more than one place
- runtime summaries are persisted and then surfaced as if they were canonical
- reconciliation paths can advance some truths while leaving other canonical-looking summaries
  behind

The right target is not full elimination of temporal skew. That is unrealistic and would either
require synchronous runtime coupling or would hide useful live diagnostics.

The right target is:

- one canonical semantic authority
- explicit runtime overlays
- bounded convergence after terminal events

That model preserves operational visibility without allowing long-lived split-brain.

## Consequences

### Positive

- query/status surfaces become easier to reason about
- terminal truth can override stale runtime summaries consistently
- long-lived contradictions between operation state and runtime state should decrease
- reconciliation work can focus on converging overlays instead of repairing semantic ambiguity
- later ADRs about wakeups, attention, and attached-session lifecycle fit into a clearer authority
  model

### Negative

- some current persisted fields will need to lose authority or move toward derived-only use
- query and projection code becomes more explicit about freshness, source, and merge semantics
- incremental migration will temporarily keep mixed structures alive while they are being
  de-authorized

### Neutral / Follow-on

- this ADR does not require removing all runtime inspection surfaces
- this ADR does not require a big-bang rewrite
- this ADR sets a target architecture; implementation can proceed tranche by tranche

## Migration Shape

The expected migration path is incremental:

1. stop introducing new canonical-looking fields that are really runtime summaries
2. prefer query-time derivation from canonical truth plus runtime overlay data
3. reduce authority of mutable stored summaries such as stale focus or session live-status
   surrogates
4. add bounded-convergence rules where terminal truth already exists but runtime debt remains
5. remove or de-emphasize mixed fields once dependent query surfaces no longer rely on them

The first implementation tranches should prioritize places where divergence creates operational
harm:

1. wakeup debt that survives terminal reconciliation
2. stale focus/session/task status that blocks or misleads operators
3. status payloads that prefer stored mutable summaries over derived terminal truth

## Closure Criteria

This ADR can move to `Implemented` when:

1. at least one major query/status surface prefers canonical semantic truth over stored mutable
   runtime-summary fields
2. at least one reconciliation path explicitly collapses redundant runtime debt after equivalent
   terminal truth is already folded
3. new implementation work avoids adding fresh mixed-authority summary fields

This ADR can move to `Verified` when:

1. regression coverage proves durable terminal truth wins over stale runtime-summary state on a
   representative query surface
2. regression coverage proves redundant runtime debt can be drained after equivalent semantic truth
   is already folded
3. the full `pytest` suite is green
4. status/inspect behavior is checked against at least one previously divergent real incident

## Verification Plan

Representative first verification targets:

- query-level regression proving a stale stored session/focus summary no longer overrides durable
  terminal truth
- reconciliation-level regression proving redundant wakeup debt is retired once equivalent terminal
  truth has already been folded

Expected implementation sites will likely include:

- `src/agent_operator/application/queries/operation_status_queries.py`
- `src/agent_operator/application/runtime/operation_runtime_reconciliation.py`
- `src/agent_operator/domain/operation.py`

## Closure Evidence Matrix

| ADR line / closure claim | Repository evidence | Verification |
| --- | --- | --- |
| Query/status surfaces prefer canonical semantic truth plus explicit runtime overlays over stored mutable runtime-summary fields | `src/agent_operator/application/queries/operation_status_queries.py:build_status_payload`; `src/agent_operator/application/queries/operation_status_queries.py:build_live_snapshot` | `tests/test_operation_status_queries.py::test_build_live_snapshot_omits_stale_waiting_reason_when_runtime_alert_present`; `tests/test_operation_status_query_immutability.py::test_build_status_payload_keeps_stored_session_truth_unmodified`; `tests/test_operation_status_query_immutability.py::test_build_status_payload_uses_derived_background_run_payloads_without_model_dump` |
| At least one reconciliation path collapses redundant runtime debt after equivalent terminal truth is already folded | `src/agent_operator/application/runtime/operation_runtime_reconciliation.py:reconcile_background_wakeups`; `src/agent_operator/application/runtime/operation_runtime_reconciliation.py:reconcile_terminal_background_run_from_supervisor` | `tests/test_operation_runtime_reconciliation_service.py::test_duplicate_terminal_wakeups_do_not_refold_same_background_run`; `tests/test_operation_runtime_reconciliation_service.py::test_resume_reconciles_completed_background_run_without_wakeup`; `tests/test_operation_runtime_reconciliation_service.py::test_resume_releases_unhandled_wakeup_for_retry` |
| Durable terminal truth wins over stale runtime-summary state on a representative query surface | `src/agent_operator/application/queries/operation_status_queries.py:build_live_snapshot` only emits `waiting_reason` when `runtime_alert` is absent | `tests/test_operation_status_queries.py::test_build_live_snapshot_omits_stale_waiting_reason_when_runtime_alert_present` |
| Status/inspect behavior is checked against a previously divergent real incident | CLI inspect/list surfaces now render unreconciled terminal background completion as a runtime overlay instead of blended truth | `tests/test_cli.py::test_inspect_surfaces_runtime_alert_for_unreconciled_background_completion`; `tests/test_cli.py::test_list_surfaces_runtime_alert_for_unreconciled_background_completion`; `tests/test_cli.py::test_list_and_agenda_json_derive_runtime_alert_inputs_without_serializing_execution_models` |
| Final repository truth is verified against current code and tests | changed ADR plus existing implementation/tests under `src/agent_operator/...` and `tests/...` | `uv run pytest` |

## Related

- [ADR 0172](./0172-derived-live-status-over-stored-session-summary.md)
- [ADR 0173](./0173-immutable-truth-and-query-boundaries.md)
- [src/agent_operator/application/queries/operation_status_queries.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/queries/operation_status_queries.py)
- [src/agent_operator/application/runtime/operation_runtime_reconciliation.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/runtime/operation_runtime_reconciliation.py)
- [src/agent_operator/domain/operation.py](/Users/thunderbird/Projects/operator/src/agent_operator/domain/operation.py)
