# AGENTS

## Purpose

This repository builds `vibechord`: a minimalist successor to `operator` for
supervising agent work through a small, inspectable operation loop.

`vibechord` should preserve the strongest parts of `operator`:

- an explicit operator loop,
- deterministic guardrails around LLM-driven decisions,
- protocol-oriented agent integration,
- event-backed transparency,
- shared command/query contracts across delivery surfaces,
- careful documentation status discipline.

It should avoid inheriting accidental complexity, compatibility shims, and
authority splits that made later `operator` work harder.

## Start Here

Agents working in this repository should start with:

1. [README.md](/Users/thunderbird/Projects/vibechord/README.md)
2. [policies/README.md](/Users/thunderbird/Projects/vibechord/policies/README.md)
3. [design/VISION.md](/Users/thunderbird/Projects/vibechord/design/VISION.md)
4. [design/SDLC.md](/Users/thunderbird/Projects/vibechord/design/SDLC.md)
5. [design/TESTING-RAILS.md](/Users/thunderbird/Projects/vibechord/design/TESTING-RAILS.md)
6. [design/VERIFICATION-SCENARIOS.md](/Users/thunderbird/Projects/vibechord/design/VERIFICATION-SCENARIOS.md)
7. [design/MOVING-PARTS.md](/Users/thunderbird/Projects/vibechord/design/MOVING-PARTS.md)
8. [design/ARCHITECTURE.md](/Users/thunderbird/Projects/vibechord/design/ARCHITECTURE.md)
9. [design/CLI-VISION.md](/Users/thunderbird/Projects/vibechord/design/CLI-VISION.md)
10. [design/TUI-VISION.md](/Users/thunderbird/Projects/vibechord/design/TUI-VISION.md)
11. [design/REST-API-VISION.md](/Users/thunderbird/Projects/vibechord/design/REST-API-VISION.md)

## Non-Negotiables

- Keep the operation loop central.
- Prefer small explicit abstractions over framework-heavy designs.
- Keep vendor-specific behavior inside adapters.
- Use `typing.Protocol` for core contracts when implementation begins.
- Prefer deterministic guardrails around LLM-driven decisions.
- Treat fleet supervision and live operator chat as first-class product goals.
- Keep canonical truth, live overlays, and forensic logs distinct.
- Do not overclaim; distinguish `implemented`, `verified`, `partial`, `planned`,
  and `blocked`.
- Keep public docs self-contained and aligned with repository truth.
- Red-team new substantial design artifacts before treating them as stable.

## Before Code Changes

Before implementation work starts, read [policies/engineering.md](policies/engineering.md).

For design or documentation work, also read:

- [policies/documentation.md](policies/documentation.md)
- [policies/architecture.md](policies/architecture.md)
- [policies/verification.md](policies/verification.md)

## Placement Rules

- End-user and integrator docs live in [docs/](docs).
- Design authority and design history live in [design/](design).
- Repository-operational rules live in [policies/](policies).
- Architectural decisions live in [design/adr/](design/adr).
- Brainstorms and critique artifacts live in [design/brainstorm/](design/brainstorm)
  or [design/internal/](design/internal).

## Backlog Rule

If you notice a real issue while working nearby and it cannot be fixed quickly,
document it in [design/BACKLOG.md](design/BACKLOG.md).
