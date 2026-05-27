# ADR 0005: Fleet And Live Chat Are First-Class Product Surfaces

- Date: 2026-05-23

## Decision Status

Accepted

## Implementation Status

Verified

Scope: shared command/projection first slice.

## Context

The successor project should include not only current `operator` behavior but
also planned fleet and live operator chat capabilities. These cannot be TUI-only
features without creating hidden state authority.

## Decision

Fleet and live operator chat are first-class application concepts.

Fleet is a shared read model. Live chat is a command/event-backed operation
input channel. CLI, TUI, and REST consume or submit them through shared
contracts.

## Required Properties

- Fleet rows are derived from canonical events, projections, and runtime
  overlays with provenance.
- Fleet labels stale or partial data.
- Operator messages are distinct from typed commands and attention answers.
- Operator messages enter brain context through explicit retention rules.
- Operator message expiry is evented.

## Consequences

### Positive

- Fleet can be tested and exposed outside the TUI.
- Live chat can work through CLI, TUI, and REST consistently.

### Negative

- Chat retention and fleet projection schemas must be specified before TUI
  implementation.

## Verification Plan

- Scenario coverage: VS-004, VS-005, and VS-010 in
  [VERIFICATION-SCENARIOS.md](../VERIFICATION-SCENARIOS.md).
- Fleet read-model tests.
- Live chat command/replay tests.
- Cross-surface message parity tests.
- E2E fake harness with multi-operation fleet and chat-affects-next-plan flow.
