# Documentation Policy

## Public Documentation

- Public docs must be self-contained enough that a new user can understand the
  current truth without reconstructing chat history.
- Do not rely on internal intent as justification in docs.
- If something is not implemented or not established, label it as planned,
  partial, blocked, open, or assumption.
- When docs describe a feature as complete, the repository should contain
  matching evidence in code, tests, or runtime artifacts.

## Claim Discipline

- Do not overclaim.
- Distinguish implemented behavior, intended behavior, tested behavior, and
  future direction.
- Distinguish decision authority from implementation completeness.
- Prefer evidence from code, persisted state, tests, and logs over design intent.
- If a route fails, record the failure honestly and preserve the lesson.

## Status Labels

Use these labels where helpful:

- `implemented`
- `verified`
- `partial`
- `planned`
- `blocked`

For ADRs, always expose both:

- `Decision Status`
- `Implementation Status`

An accepted ADR records decision authority, not automatic delivery closure.

## Documentation Placement

- End-user and integrator docs go in [`../docs/`](../docs).
- Design authority and design history go in [`../design/`](../design).
- Repository-operational policies go in this directory.
- ADRs go in [`../design/adr/`](../design/adr).
- Brainstorms and critiques go in [`../design/brainstorm/`](../design/brainstorm)
  or [`../design/internal/`](../design/internal).

Do not mix public quickstarts and how-to guides with design critiques,
brainstorms, or implementation plans.
