# ADR 0134: One-operation live follow surface

- Date: 2026-04-10

## Status

Accepted

## Implementation Status

Partial

## Commands Covered

- `operator watch`

## Not Covered Here

- one-operation shell summary via `status`
- session-scoped live follow
- TUI fleet or operation workbench layout

## Context

The CLI vision retains `watch`, but no longer treats it as:

- the default operation summary
- an operation dashboard substitute
- or a projection dump

RFC 0014 now gives `watch` a narrower and healthier role:

- one-operation textual live follow
- compact, redraw-friendly
- useful when TUI is unnecessary or unavailable

That role deserves a dedicated ADR rather than being left as residual behavior from older
dashboard-era assumptions.

Current repository truth on 2026-04-10:

- `implemented`: `operator watch` already exists as a public one-operation live-follow command
- `partial`: the shipped surface is still being tightened toward the compact redraw-oriented
  contract defined here

## Decision

`watch` should remain a first-class but deliberately narrow textual live-follow command for one
operation.

Its job is to answer, within one screen:

- what the operation is doing now
- whether it is waiting or blocked
- whether attention requires intervention
- what the current work focus is

It is not the canonical shell summary and it is not a transcript tail.

## Live Follow Contract

`watch` should:

- redraw idempotently as a compact live surface
- stay bounded in visible density
- prioritize current focus over retrospective summary
- avoid turning into a rolling event ledger
- remain human-readable by default

The command may reuse shared supervisory summary fields, but its layout should remain distinct from
`status`.

## Explicit Rejections

This ADR rejects three failure modes:

1. replacing `status` as the primary shell summary
2. becoming a mini-dashboard or detail command
3. becoming a transcript-like append stream

## Consequences

Positive:

- `watch` keeps a clear reason to exist next to both `status` and TUI
- RFC 0014 live-follow family gets a narrow owner

Tradeoffs:

- the CLI must preserve a meaningful distinction between summary and live follow
- implementers must resist packing too much detail into the live surface

## Verification

The repository should continue moving toward and preserve these conditions:

- `watch` remains compact and redraw-oriented
- `watch` does not become the default status grammar with polling
- `watch` does not become transcript output

## Related

- [ADR 0096](./0096-one-operation-control-and-summary-surface.md)
- [ADR 0116](./0116-cli-parity-gaps-for-fleet-operation-and-session-surfaces.md)
- [RFC 0014](../rfc/0014-cli-output-contract-and-example-corpus.md)
