# ADR 0004: Testing Rails As Architecture

- Date: 2026-05-23

## Decision Status

Accepted

## Implementation Status

Partial

Scope: local fast/focused/full gates, fake harness summaries, and release
documentation gate verified; broader protocol conformance suites remain
planned.

## Context

The project goal requires development to stay correct and directionally aligned.
Tests must cover local behavior and architectural drift.

## Decision

`design/TESTING-RAILS.md` is part of the architecture contract. New runtime
features must identify the relevant unit, contract, replay, delivery, TUI, and
E2E fake-harness coverage.

## Required Properties

- Fakeable dependencies for major runtime boundaries.
- Reusable protocol conformance suites.
- Event/replay tests for state-changing behavior.
- Delivery parity tests for user-facing surfaces.
- Architecture fitness functions for dependency direction and authority rules.
- E2E fake harness with machine-readable summaries.

## Consequences

### Positive

- Implementation choices remain testable by local tools.
- Directional drift can fail tests before it becomes design debt.

### Negative

- Initial implementation work must include test harness infrastructure.

## Verification Plan

- Scenario coverage: VS-001 through VS-013 in
  [VERIFICATION-SCENARIOS.md](../VERIFICATION-SCENARIOS.md).
- Add fast/focused/full verification commands once package layout exists.
- Build the E2E fake harness in the first implementation tranche.
- Require design/implementation plans to reference relevant rails.
