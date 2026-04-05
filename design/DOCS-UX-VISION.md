# Docs UX Vision

## Purpose

This document records the design direction for `operator`'s documentation information
architecture.

The repository now distinguishes four committed surfaces:

- root `README.md` for evaluators and package consumers
- `docs/` for public product documentation
- `design/` for design authority and design history
- `policies/` for canonical repository-operational instructions for agents and contributors

## Design Principles

**D1 — Evaluator-first, user-second, contributor-third.**
The root `README.md` answers "should I try this?" Public docs answer "how do I use it?" Design
docs answer "why is it like this?" Policy docs answer "how should work be done in this repo?"

**D2 — Namespace honesty matters.**
`docs/` should mean end-user and integrator documentation. Design history should not occupy that
namespace.

**D3 — Public docs should stay small.**
The initial public surface should cover quickstart, task-oriented how-to guides, stable reference,
and integration entrypoints. It should not duplicate the full design corpus.

**D4 — Design history stays committed.**
ADRs, RFCs, critiques, brainstorms, and implementation plans remain public project history under
`design/`. They are not local scratch and must not be gitignored.

**D5 — Agent instructions need their own home.**
Repository-operational instructions should live in `policies/`, with `AGENTS.md` acting as the
entrypoint and router.

## Current Documentation Model

### Root surface

- `README.md` is the evaluator-facing front door.
- `CONTRIBUTING.md` is the contributor-facing entrypoint.
- `STACK.md` stays at the repository root.
- `AGENTS.md` stays at the repository root as the short agent entrypoint.

### Public docs

Public docs live in `docs/` and should contain:

- `docs/README.md`
- `docs/quickstart.md`
- `docs/how-to/*`
- `docs/reference/*`
- `docs/integrations.md`

These documents should be task-oriented and contract-oriented, not rationale-heavy.

### Design corpus

The design corpus lives in `design/` and contains:

- `VISION.md`
- `ARCHITECTURE.md`
- `*-UX-VISION.md`
- `adr/`
- `rfc/`
- `brainstorm/`
- `internal/`
- critiques
- implementation plans
- roadmaps and backlog artifacts

### Policies

Canonical repository-operational instructions live in `policies/`:

- `engineering.md`
- `documentation.md`
- `architecture.md`
- `verification.md`

## MkDocs Direction

Public docs should be rendered through MkDocs.

The site should:

- use `docs/` as the source directory
- render a curated public documentation tree
- generate technical API reference from selected public docstrings
- avoid publishing internal application modules as public API by default

Generated API docs should focus on stable technical surfaces such as:

- package root
- protocols
- domain models
- selected runtime utilities
- ACP and adapter-facing surfaces

They should not automatically expose internal application orchestration modules.

## Consequences

- The repository now has a normal public-docs front door without losing its design history.
- Contributors still get a rich design corpus, but it no longer occupies the public `docs/`
  namespace.
- Public docs, design docs, and repo policies can evolve independently without collapsing into one
  mixed tree.
