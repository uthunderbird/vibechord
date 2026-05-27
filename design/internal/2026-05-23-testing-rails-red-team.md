# Testing Rails Red-Team Pass

Date: 2026-05-23

Target artifacts:

- `design/TESTING-RAILS.md`
- `design/SDLC.md`
- `design/ARCHITECTURE-DRAFT.md`
- `policies/verification.md`

## Result

The testing rails are directionally strong: they define a test mesh rather than
a generic pyramid, cover unit/contract/replay/delivery/TUI/E2E layers, and name
architecture fitness functions.

The initial version still had several mechanism gaps. Fixes were applied in
`design/TESTING-RAILS.md`.

## Findings

### P0: Contract suite mechanics were underspecified

Result type: verified issue.

The document named protocol contract tests but did not say how implementations
would share the same behavioral suite.

Fix applied: added a reusable conformance-suite rule using implementation
factories/fixtures.

### P0: Top-level harness evidence was too vague

Result type: verified issue.

The document said output artifacts should be inspectable, but did not require
machine-readable summaries or stable failure messages.

Fix applied: added evidence requirements for stdout/stderr, persisted tempdir
artifacts, machine-readable summary files, and stable rail-specific failures.

### P1: Gate tiers were missing

Result type: bounded concern.

Without fast/focused/full tiers, developers could skip slow rails or only run
feedback late.

Fix applied: added gate tiers and completion guidance.

### P1: Product goals needed layer mapping

Result type: bounded concern.

The rails listed layers but did not show that operation loop, human attention,
live chat, fleet, adapters, and TUI each need multi-layer coverage.

Fix applied: added a product coverage matrix.

## Remaining Open Work

- Exact async test framework choice.
- Exact event store format.
- Exact TUI golden/snapshot strategy.

Later resolution: planned verify command families and the E2E fake harness
summary shape are specified in `design/VERIFICATION-SCENARIOS.md`.
