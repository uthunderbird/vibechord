# ADR 0130: Attention and intervention UX for blocking and non-blocking work

- Date: 2026-04-10

## Status

Accepted

## Implementation Status

Partial

Skim-safe current truth on 2026-04-10:

- `implemented`: TUI workbench surfaces blocking and non-blocking attention as distinct selectable
  intervention classes
- `implemented`: `n` answers the oldest non-blocking attention in the current scope
- `implemented`: `A` opens a compact current-scope attention picker across blocking and
  non-blocking items
- `implemented`: shared supervisory summaries now expose blocking attention separately from
  non-blocking review cues, and those cues are rendered in TUI detail panes plus the
  human-readable `operator session` snapshot
- `verified`: focused projection, TUI, and session-CLI coverage now checks the review cue path
- `partial`: broader fleet/status/list family closure for the distinction remains distributed
  across the newer CLI/TUI ADR wave rather than fully closed here

## Context

Earlier TUI ADRs established:

- attention propagation across supervisory levels
- action parity and safety
- the main blocking-attention path as a first-class supervisory concern

Implementation has since gone further and already introduced non-blocking attention flow as a real
product behavior.

That creates a new design question:

- blocking attention is urgent and gate-like
- non-blocking attention is informative but may still deserve intervention

Without an ADR, the product can drift into one of two bad shapes:

1. non-blocking items become invisible ambient noise even when they matter
2. non-blocking items are rendered with the same urgency semantics as blocking work and overwhelm
   triage

## Decision

The supervisory UX should treat blocking and non-blocking attention as distinct classes with
different intervention semantics.

Blocking attention remains the primary interruption class.

Non-blocking attention is a real supervisory signal, but it should surface as triage-capable,
secondary intervention material rather than as an equivalent gate.

## UX Rules

### 1. Blocking attention

Blocking attention should:

- sort to the front of triage surfaces
- be visible in compact badges and summaries
- support direct answer/intervention flows
- clearly explain when work is waiting on the operator

### 2. Non-blocking attention

Non-blocking attention should:

- remain visible in supervision surfaces
- be eligible for explicit review and intervention
- not override the visual urgency semantics of blocking work by default

It may surface as:

- a compact summary count
- a secondary attention section
- a review queue or follow-up cue

It should not masquerade as a hard block.

### 3. Distinct escalation semantics

The product should preserve a stable distinction between:

- "must answer now to unblock progress"
- "should review because it may improve or redirect work"

The UI should not force the operator to infer that distinction from prose alone.

### 4. Shared truth beneath delivery

The blocking vs non-blocking distinction should come from shared delivery/query truth, not only
from TUI-local rendering heuristics.

CLI and TUI may present the distinction differently, but they should not disagree about whether an
item is blocking.

## Intervention Rule

The default supervisory flow should prioritize:

1. blocking attention
2. active failures or pauses
3. meaningful non-blocking review items

This preserves intervention discipline without erasing the utility of softer supervisory cues.

## Consequences

Positive:

- the product can surface richer operator workflows without collapsing into noise
- non-blocking attention gets a durable place in the UX
- review and implementation can distinguish true gates from advisory interventions

Tradeoffs:

- more explicit attention taxonomy must appear in summaries and actions
- some UI space must be reserved for secondary intervention cues
- implementation must resist treating every attention item as equally urgent

## Verification

When implemented, the repository should preserve these conditions:

- blocking vs non-blocking attention remain distinct in shared truth and rendered UX
- blocking attention drives primary triage ordering
- non-blocking attention remains visible but secondary
- tests cover both summary and interaction behavior for the two classes

Current focused evidence:

- [tests/test_tui.py](/Users/thunderbird/Projects/operator/tests/test_tui.py)
- [tests/test_cli.py](/Users/thunderbird/Projects/operator/tests/test_cli.py)
- [tests/test_operation_projections.py](/Users/thunderbird/Projects/operator/tests/test_operation_projections.py)
- [src/agent_operator/cli/tui/controller.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui/controller.py)
- [src/agent_operator/cli/tui/rendering.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui/rendering.py)
- [src/agent_operator/application/queries/operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/queries/operation_projections.py)

## Related

- [ADR 0111](./0111-tui-signal-and-attention-propagation-contract.md)
- [ADR 0112](./0112-tui-cli-action-parity-and-safety.md)
- [ADR 0118](./0118-supervisory-surface-implementation-tranche.md)
- [ADR 0126](./0126-supervisory-activity-summary-contract.md)
