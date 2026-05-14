# ADR 0220: Synchronizable Operation State And Runtime Fact Reconciliation

- Date: 2026-05-02

## Decision Status

Accepted

## Implementation Status

Verified

Implementation grounding on 2026-05-02:

- `implemented`: status and inspect surfaces expose sync-health fields for canonical, fact,
  translated-fact, checkpoint, and current checkpoint-backed projection cursors. Evidence:
  `src/agent_operator/application/queries/operation_status_queries.py`,
  `tests/test_operation_status_queries.py`.
- `implemented`: technical fact storage now has durable translated cursors and preserves
  unsupported technical facts as untranslated lag instead of silently advancing the cursor.
  Evidence: `src/agent_operator/runtime/facts.py`,
  `src/agent_operator/application/event_sourcing/event_sourced_operation_loop.py`,
  `tests/test_fact_store.py`, `tests/test_event_sourced_operation_loop.py`.
- `implemented`: v2 drive persists technical facts for session start, terminal, disconnected,
  waiting-input, and permission outcomes; canonical events are linked by `causation_id`, and the
  translated cursor advances after canonical append. Evidence:
  `src/agent_operator/application/drive/drive_service.py`,
  `src/agent_operator/application/drive/policy_executor.py`,
  `tests/test_drive_service_v2.py`.
- `implemented`: trace brief absence no longer hides canonical latest-turn truth, cancelled
  attached turns materialize cancelled canonical events, and runtime drain materializes a parked
  state instead of silent `running`. Evidence: `tests/test_operation_status_queries.py`,
  `tests/test_drive_service_v2.py`, `tests/test_attached_session_registry.py`.
- `implemented`: future standalone persisted read-model-store projection lag is split into
  ADR 0221. Current status projections are checkpoint-backed and explicitly report
  `projection_lag` using the checkpoint sequence basis.
- `verified`: local focused and full repository suites passed during implementation tranches,
  ending with `uv run pytest`: `1058 passed, 11 skipped`.

## Context

The v2 event-sourced operation path has made canonical operation truth explicit, but recent live
runs exposed a second-order problem: several state families can still move independently without a
single synchronization contract.

The recurring failures are not one adapter bug:

- a completed attached turn could be present in canonical events while status summaries remained
  blank because the trace brief sidecar was missing;
- an ACP session could return `stopReason = cancelled` in its transport log while the canonical
  operation stream remained stuck at `session.created`;
- attached execution could drain after a turn without durable operation-level evidence explaining
  why the run stopped progressing;
- resumed or reused sessions could carry stale execution-profile metadata unless the reuse path
  explicitly merged the current desired profile.

These failures all have the same shape:

1. a non-canonical state family changed;
2. the change was not translated into canonical domain truth, or not projected from canonical truth;
3. user-facing surfaces continued to report an apparently valid state such as `running`.

The relevant state families today include:

- canonical operation domain events under `.operator/operation_events/`;
- derived checkpoints used for replay acceleration;
- runtime and adapter technical facts;
- ACP transport logs under `.operator/acp/`;
- wakeups and background runtime overlays;
- trace brief sidecars under `.operator/runs/`;
- query/read-model projections used by CLI, TUI, MCP, and SDK surfaces.

The repository already has the right direction in pieces:

- `OperationEventStore` is the canonical domain event persistence contract;
- `FactStore` is explicitly non-canonical;
- `OperationCheckpointStore` is documented as derived replay acceleration;
- public delivery surfaces should read from shared application authority rather than invent their
  own truth.

What is missing is the synchronization contract that connects these pieces.

## Decision

The operator will adopt an explicit synchronizable-state model:

1. **canonical operation events remain the only business source of truth**
2. **runtime observations become durable technical facts before they affect business state**
3. **a deterministic fact-to-domain translation boundary converts technical facts into domain
   events**
4. **derived checkpoints, read models, and trace briefs are rebuildable projections or enrichments**
5. **each synchronization boundary exposes cursor and lag information**
6. **user-facing status surfaces report sync health instead of silently presenting stale state as
   active progress**

This ADR does not replace ADR 0218. ADR 0218 defines when execution may continue. This ADR defines
how state changes observed outside canonical operation events become synchronized with canonical
truth and projections.

## Canonical Business Truth

The only authoritative business state for an event-sourced operation is the operation domain event
stream:

- `.operator/operation_events/<operation_id>.jsonl`
- the `OperationEventStore` protocol
- replay through the canonical projector

Business claims include:

- operation lifecycle status;
- scheduler state;
- task state;
- attention and permission state once materialized into domain events;
- session observed state;
- agent turn outcomes;
- parked execution state;
- final summaries and terminal reasons.

No derived file, runtime overlay, ACP log, trace brief, checkpoint, dashboard row, or CLI payload may
act as a competing authority for these claims.

## Runtime Facts As Durable Inputs

Runtime and adapter observations are inputs to canonical truth, not canonical truth themselves.

Examples include:

- `session.started`
- `session.completed`
- `session.cancelled`
- `session.failed`
- `session.disconnected`
- `session.output_chunk_observed`
- `session.waiting_input_observed`
- `permission.request.observed`
- `permission.request.decided`
- `permission.request.escalated`
- `runtime.drained`
- `runtime.reconnected`

These observations should be persisted as technical facts with stable identifiers and sequence
positions before they are translated into business events.

Adapter logs may remain useful for raw forensics, but the operator must not require manual log
tailing to know that a runtime terminal condition occurred.

## Fact-To-Domain Translation Boundary

The fact-to-domain boundary is responsible for converting durable technical facts into canonical
operation events.

The translator must be deterministic and idempotent:

- the same technical fact set and checkpoint context must produce the same domain event drafts;
- already translated facts must not generate duplicate domain events;
- translation failures must be visible as sync health, not hidden behind stale projections.

Illustrative translations:

- `session.completed` ->
  - `agent.turn.completed(status=completed)`
  - `session.observed_state.changed(observed_state=completed)`
- `session.cancelled` ->
  - `agent.turn.completed(status=cancelled)`
  - `session.observed_state.changed(observed_state=cancelled)`
- `session.failed` ->
  - `agent.turn.completed(status=failed)`
  - `session.observed_state.changed(observed_state=failed)`
- rejected permission request ->
  - `permission.request.observed`
  - `permission.request.decided`
  - either an attention event, an interrupted turn, or a failed turn depending on policy
- `runtime.drained` while an operation remains non-terminal ->
  - a durable runtime-drained or parked/waiting domain event with a re-entry hint

Transport-level terminal outcomes must never remain only in ACP logs.

## Synchronization Cursors

Every operation should expose enough synchronization cursors to answer:

> "Which state family is behind canonical truth, and by how much?"

Minimum cursor families:

- last adapter fact sequence observed
- last technical fact sequence persisted
- last technical fact sequence translated
- last canonical domain event sequence appended
- last checkpoint sequence materialized
- last projection sequence materialized

The exact storage shape may evolve, but the user-facing sync report must be able to distinguish:

- runtime has new facts that are not translated;
- canonical events advanced but checkpoints are stale;
- checkpoints advanced but trace briefs are absent;
- projections are stale relative to canonical events;
- no active runtime exists for an operation that is still rendered as running.

## Derived State Rules

Derived state stores are allowed, but their role must remain explicit.

### Checkpoints

Checkpoints are replay acceleration.

They must be rebuildable from canonical events and must not be accepted as fresher business truth
than the event stream.

### Read Models And Query Payloads

Read models and query payloads are projections.

They should prefer canonical domain events and replayed state. If they use runtime overlays or trace
briefs, those values must be treated as enrichment or clearly labeled runtime overlay.

### Trace Briefs

Trace briefs are useful for richer summaries and forensics.

They are not required for lifecycle truth. If a trace brief is absent but canonical
`agent.turn.completed` exists, status surfaces must still show a truthful latest-turn summary.

### ACP Logs

ACP logs are raw transport evidence.

They must not be the only place where terminal session outcomes or permission decisions are
observable.

## Terminal-Fold Invariant

The system must enforce this invariant:

> Every observed runtime terminal outcome for an operation-bound session must eventually become a
> canonical domain event or an explicit sync failure.

Examples of runtime terminal outcomes:

- completed
- cancelled
- failed
- disconnected
- drained with no active continuation

If the translator cannot map the outcome, the operation must surface a sync alert rather than remain
as ordinary `running`.

## No False Running

`running` must not mean "the last known canonical state was not terminal."

For user-facing surfaces, a running operation should be distinguishable from:

- running with an active runtime;
- running but parked on a material wake predicate;
- running but runtime-drained and awaiting re-entry;
- running with untranslated runtime facts;
- running with stale projections.

If the system lacks enough information to prove active progress is possible, status should expose
that uncertainty.

## Sync Health Surface

JSON and debug-oriented status surfaces should include a synchronization-health section.

Illustrative fields:

- `canonical_sequence`
- `checkpoint_sequence`
- `projection_sequence`
- `last_runtime_observation`
- `last_runtime_observed_at`
- `unsynced_fact_count`
- `untranslated_fact_count`
- `active_runtime_present`
- `sync_alert`

Default human text may remain compact, but it must not hide material sync failures.

## Implementation Order

The implementation should proceed in small tranches:

1. **ACP terminal fold**
   - ensure ACP `session.cancelled`, `session.failed`, and `session.completed` are folded into
     canonical `agent.turn.completed` and `session.observed_state.changed` events.

2. **Runtime drain materialization**
   - when an attached drive call drains before terminalizing an operation, persist a durable
     domain event or parked/waiting state explaining the stop.

3. **Status sync health**
   - expose minimal sequence and runtime-observation health in `status --json`.

4. **Durable technical fact cursor**
   - persist and translate runtime facts with an idempotent cursor so ACP logs are not the recovery
     authority.

5. **Projection lag checks**
   - make read models and trace-derived enrichments report their canonical sequence basis.

## Consequences

### Positive

- Operation truth remains single-sourced.
- Runtime outcomes cannot silently disappear in adapter logs.
- Status surfaces can explain stale or unsynchronized state.
- Derived state can remain useful without becoming a hidden authority.
- The same model covers ACP terminal folds, attached drain, trace-brief absence, and projection lag.

### Negative

- The runtime path gains another explicit boundary and cursor to maintain.
- Some status payloads become more complex.
- Tests must cover synchronization lag and translation idempotency, not only final projections.

### Migration

This should be implemented without a second canonical store.

During migration:

- missing trace briefs may continue to exist;
- old raw ACP logs may remain forensic-only;
- newly observed runtime terminal facts should be translated into canonical events wherever possible;
- any unsupported runtime fact should create a sync alert rather than silently disappearing.

## Rejected Alternatives

### Treat ACP logs as a second authority

Rejected.

ACP logs are adapter transport evidence. Letting user-facing lifecycle truth depend on manually
reading them would preserve split-brain state.

### Rebuild trace sidecars as the main fix

Rejected as the primary strategy.

Trace sidecars may enrich summaries, but they cannot be required for lifecycle truth.

### Patch every observed drift independently

Rejected as a complete strategy.

Local fixes are still necessary, but the repeated failure pattern shows that the underlying issue is
missing synchronization semantics across state families.

## Verification Plan

Minimum regressions:

- ACP `stopReason = cancelled` produces canonical cancelled turn/session events.
- ACP `session.failed` produces canonical failed turn/session events.
- A drained attached drive call leaves a durable runtime-drained or parked state, not silent
  `running`.
- `status --json` reports completed-turn truth from canonical events even when trace briefs are
  absent.
- status/debug payloads expose sync lag when runtime facts are newer than canonical events.
- replay from canonical events rebuilds the same business state without trace sidecars or ACP logs.

## Current Status

This ADR is accepted and implemented for the current checkpoint-backed v2 runtime.

The repository already has partial ingredients:

- canonical operation events;
- derived checkpoints;
- non-canonical fact-store protocol;
- ACP technical facts;
- trace brief enrichment;
- canonical fallback for latest-turn status summaries.

Implemented slices:

- canonical fallback for latest-turn status summaries when trace briefs are absent;
- attached cancelled turn results materialize as `agent.turn.completed(status=cancelled)` and
  `session.observed_state.changed(status=cancelled)`;
- attached drive drain materializes a durable `operation.parked.updated` record with
  `kind=runtime_drained` instead of silently exiting as ordinary `running`.
- `status --json` exposes an initial `runtime_overlay.sync_health` payload with canonical,
  checkpoint, projection, active-runtime, and sync-alert fields.
- `status --json` reads the durable fact-store cursor and exposes `fact_sequence` in
  `runtime_overlay.sync_health`.
- technical fact ingestion now advances a durable translated-fact cursor only after successful
  fact translation, canonical event append, and checkpoint materialization.
- translated-fact cursor advancement is causation-based: a technical fact is counted as translated
  only when a persisted canonical event references that fact as its `causation_id`; unsupported
  facts remain visible as untranslated sync lag.
- `status --json` reads the translated-fact cursor and reports `translated_fact_sequence`,
  `untranslated_fact_count`, and `technical_facts_pending_translation` sync alerts.
- `status --json` reports explicit `checkpoint_lag` and `projection_lag`; current status
  projections are checkpoint-backed, so their sequence basis is the replay checkpoint sequence.
- v2 `DriveService` now persists technical facts for materialized agent terminal outcomes and
  permission outcomes, links the resulting canonical events by `causation_id`, and advances the
  translated-fact cursor after canonical append.
- v2 `DriveService` now persists `session.started` facts before collection, links them to
  `session.created`, and advances the translated cursor through the session start boundary.
- ACP session collection now preserves accumulated permission event payloads in `AgentResult.raw`,
  so v2 drive materialization and fact persistence see permission outcomes from both success and
  terminal collection paths.
- v2 drive materialization preserves disconnected ACP outcomes as `agent.turn.completed(status=
  disconnected)`, `session.observed_state.changed(status=disconnected)`, and
  `session.discontinuity_observed` facts instead of folding them into generic failed outcomes.
- v2 drive fact persistence covers waiting-input turns and permission follow-up outcomes:
  `session.waiting_input_observed`, `permission.request.observed`,
  `permission.request.escalated`, and `permission.request.followup_required` are durably stored,
  causally linked to canonical events, and included in translated cursor advancement.

Future work:

- persisted projection lag for future standalone read-model stores is tracked separately in
  ADR 0221.
