# SDLC

## Purpose

This document defines how `vibechord` work should move from idea to accepted
design to implementation.

The process is intentionally lightweight, but it is not informal. The project
uses explicit status labels, red-team review for substantial artifacts, and ADRs
for durable architecture decisions.

## Work Stages

### 1. Explore

Use `design/brainstorm/` for option generation, tradeoff exploration, and
swarm-mode outputs.

Exploration artifacts may contain uncertainty, but they must label it.

### 2. Propose

Move stable direction into design authority:

- `design/VISION.md` for product and behavioral intent;
- `design/TESTING-RAILS.md` for verification architecture and testability
  gates;
- `design/VERIFICATION-SCENARIOS.md` for concrete scenario coverage;
- `design/MOVING-PARTS.md` for minimum core moving parts and extension rules;
- `design/ARCHITECTURE.md` for implementation architecture;
- delivery surface visions for CLI, TUI, and REST API;
- ADRs for specific decisions affecting contracts, persistence, events,
  lifecycle, adapters, or delivery surfaces.

### 3. Red-Team

Substantial new artifacts should receive a red-team pass before they are treated
as stable.

The red-team pass should check:

- overclaims;
- missing status labels;
- authority confusion;
- hidden fallback paths;
- unverified behavior claims;
- delivery-surface drift risks;
- event/replay/staleness gaps;
- fleet and live-chat omissions.

Critique artifacts belong in `design/internal/` unless they are small enough to
fold directly into the revised document.

### 4. Implement

Implementation starts only after the relevant architecture direction is clear
enough to avoid accidental authority splits.

New code should have:

- explicit types;
- focused tests;
- deterministic failure behavior;
- event/trace visibility for state transitions;
- no vendor-specific behavior in core modules.

### 5. Verify

Verification should match the claim:

- unit tests for local behavior;
- contract tests for protocols;
- integration tests for delivery surfaces;
- persisted artifact inspection for event and replay claims;
- live/manual verification for TUI behavior when automation is insufficient.

See [TESTING-RAILS.md](TESTING-RAILS.md) for the planned full-stack test mesh,
architecture fitness functions, and agent-executable gates.
See [VERIFICATION-SCENARIOS.md](VERIFICATION-SCENARIOS.md) for the concrete
scenario catalog that implementation plans should reference.

### 6. Record

When implementation changes architecture truth:

- update docs in the same work wave;
- update ADR implementation status;
- record follow-up work in `design/BACKLOG.md`;
- keep public docs aligned with implemented and verified behavior.

## ADR Rules

Use ADRs for decisions that affect:

- public interfaces;
- protocol contracts;
- runtime behavior;
- persistence format;
- event schemas;
- adapter lifecycle;
- dependency direction;
- delivery-surface authority.

Each ADR must include:

- `Decision Status`;
- `Implementation Status`;
- context;
- decision;
- consequences;
- verification plan.

## Definition of Done

A design artifact is done when:

- it is placed in the right directory;
- it labels planned vs implemented truth;
- it has been red-teamed if substantial;
- it has no known unresolved contradiction with the rest of the design corpus;
- follow-up work is in `design/BACKLOG.md`.

Runtime implementation is done only when:

- tests or another concrete verification path cover the claim;
- docs match behavior;
- failure modes are explicit;
- user-visible state has event/trace evidence where relevant.
- the relevant rails in [TESTING-RAILS.md](TESTING-RAILS.md) are either covered
  or explicitly marked out of scope for that feature.
