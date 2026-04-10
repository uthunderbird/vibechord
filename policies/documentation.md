# Documentation Policy

## Public Documentation

- Public docs must be self-contained enough that a new user can understand the current truth
  without reconstructing chat history.
- Do not rely on internal intent as justification in docs.
- If something is not implemented or not established, label it as assumption, planned direction, or
  open question.
- When docs describe a feature as complete, the repository should contain matching evidence in
  code, tests, or runtime artifacts.

## Claim Discipline

- Do not overclaim.
- Distinguish clearly between implemented behavior, intended behavior, tested behavior, and future
  direction.
- Distinguish clearly between decision authority and implementation completeness.
- Prefer evidence from code, persisted state, tests, and logs over prompt wording or design intent.
- If a route fails, record the failure honestly and preserve the lesson.
- Make skim-safe truth explicit: a reader should not need to read the full body of a long ADR or
  RFC to discover that implementation is only partial.

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

For RFCs and other design documents, use an explicit implementation-status section whenever the
document could otherwise read as "accepted or drafted therefore complete".

If an ADR has `Decision Status: Accepted` and `Implementation Status: Partial`, it must include an
early skim-safe summary of:

- what has landed
- what has not landed
- where the remaining work is tracked canonically

Do not rely on scattered body prose to communicate partiality.

## Documentation Placement

- End-user and integrator docs go in [`../docs/`](../docs/).
- Design authority and design history go in [`../design/`](../design/).
- Repository-operational policies go in this directory.
- ADRs go in [`../design/adr/`](../design/adr/).
- RFCs go in [`../design/rfc/`](../design/rfc/).
- Brainstorms and critiques go in [`../design/brainstorm/`](../design/brainstorm/) or
  [`../design/internal/`](../design/internal/).

Do not mix public quickstarts and how-to guides with design critiques, brainstorms, or
implementation plans.
