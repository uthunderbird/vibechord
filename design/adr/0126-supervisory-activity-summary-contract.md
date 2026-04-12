# ADR 0126: Supervisory activity summary contract

- Date: 2026-04-10

## Status

Accepted

## Implementation Status

Implemented

Skim-safe current truth on 2026-04-12:

- `implemented`: the repository now has one shared supervisory activity summary contract in
  `OperationProjectionService` rather than separate ad hoc fleet/operation/session brief dict
  shapes
- `implemented`: fleet workbench rows, one-operation dashboard payloads, and session views now all
  emit the same normalized summary fields: `goal`, `now`, `wait`, `progress`, `attention`,
  `recent`, plus optional `agent_activity` and `operator_state`
- `implemented`: TUI fleet, operation, and session detail panes now consume those same shared
  summary fields instead of inventing separate labels for agent/operator cues
- `verified`: focused projection, dashboard-query, and TUI coverage exists in
  `tests/test_operation_projections.py`, `tests/test_operation_dashboard_queries.py`, and
  `tests/test_tui.py`
- `implemented`: `agent_activity` and `operator_state` are now populated across fleet, operation,
  and session projections with real runtime signals (e.g. `"codex_acp active session"`,
  `"observing"`, `"draining"`, `"pause requested"`)
- `verified`: `agent_activity` and `operator_state` assertions in `tests/test_operation_projections.py`
  and `tests/test_tui.py`

## Context

The current supervisory CLI/TUI stack already has:

- a shared fleet and operation projection path
- a stable zoom hierarchy from `fleet` to `operation` to `session` to `forensic`
- richer recent implementation slices for filtering, help, and non-blocking attention

What it did not yet have was a single explicit contract for richer live summaries of active work.

Recent product exploration identified a recurring next-wave need:

- a normalized short summary of what a running operation is doing now
- a stable distinction between waiting, blocked, paused, and active work
- a compact indication of whether one or more agents are active
- a small operator-state cue when the signal is strong enough
- the ability for both CLI and TUI to render the same live summary truth

Without an ADR here, richer live summaries would drift into delivery-local invention:

- TUI rows would improvise "now" hints
- CLI might expose a different explanation surface
- operator-load cues could appear with inconsistent semantics

This is not merely a rendering preference. It is a shared product and query contract question.

## Decision

The repository should define one shared supervisory activity summary contract beneath both CLI and
TUI.

This contract should become the canonical source for compact live-status explanations such as:

- `now: ...`
- `waiting: ...`
- `paused: ...`
- `failed: ...`

and related compact cues such as:

- single-agent vs plural-agent presence
- blocking vs non-blocking activity summary
- optional operator busy/idle/following state when the runtime truth is strong enough

The summary contract belongs to the shared delivery/query/projection surface, not to TUI-only
presentation code.

## Contract Scope

The shared contract should define:

1. a normalized short-running-summary field suitable for fleet rows and compact briefs
2. a normalized waiting/blocked summary field
3. a compact agent-activity cue
4. an optional operator-state cue, gated by strong truth
5. recency and recent-progress summary semantics suitable for live supervision
6. a stable distinction between blocking and non-blocking attention in compact summary form

The contract should not require:

- transcript-derived prose summaries
- speculative "cognitive load" metrics
- exact per-agent resource accounting
- arbitrary summary text generation in the delivery layer

## Authority Rule

CLI and TUI should consume the same summary truth.

Delivery layers may choose different layouts, but they should not invent divergent semantics for:

- what the operation is doing now
- whether it is waiting
- whether multiple agents are active
- whether the operator is actively intervening or simply observing

If the underlying truth is weak, the field should be omitted rather than rendered with false
precision.

## Data-Strength Rule

The contract should distinguish:

- strong facts that can always be rendered compactly
- conditional facts that may render only when reliable
- unsupported facts that should not be surfaced as stable product signals

In particular:

- operator-state rendering is conditional
- multi-agent plurality cues are conditional on stable runtime evidence
- exact operator workload metrics are out of scope unless later ADR work makes them real

## Consequences

Positive:

- richer live summaries get one shared truth source
- future fleet and operation layouts can become more informative without becoming ad hoc
- CLI/TUI parity improves because both read from the same explanatory contract

Tradeoffs:

- projection/query code will need explicit summary normalization
- some summary desires will be rejected until the runtime truth is strong enough
- implementation will require careful evidence discipline to avoid overclaiming

## Verification

Current evidence for the landed slice:

- `verified`: fleet workbench payloads emit the shared summary contract, including optional
  `agent_activity` / `operator_state` cues when repository truth is strong enough
- `verified`: operation dashboard payloads and session views emit the same contract fields instead
  of separate delivery-local summary shapes
- `verified`: TUI fleet, operation, and session panes render the shared cues when present
- `not yet verified`: broader CLI/TUI parity for every future supervisory surface that may consume
  the contract

The repository should preserve these conditions:

- CLI and TUI consume the same supervisory activity summary fields
- compact running/waiting/paused summaries are normalized rather than freeform
- weak signals are omitted rather than rendered as precise product claims
- summary logic does not live only inside TUI rendering code

## Related

- [ADR 0109](./0109-cli-authority-and-tui-workbench-v2.md)
- [ADR 0110](./0110-tui-view-hierarchy-and-zoom-contract.md)
- [ADR 0113](./0113-tui-data-substrate-and-refresh-model.md)
- [ADR 0115](./0115-fleet-workbench-projection-and-cli-tui-parity.md)
- [ADR 0118](./0118-supervisory-surface-implementation-tranche.md)
