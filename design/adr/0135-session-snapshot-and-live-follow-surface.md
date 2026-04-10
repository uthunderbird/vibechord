# ADR 0135: Session snapshot and live follow surface

- Date: 2026-04-10

## Decision Status

Accepted

## Implementation Status

Partial

Skim-safe current truth on 2026-04-10:

- `implemented`: the public `operator session OP --task TASK` surface already exists and is
  task-addressed rather than session-id-addressed
- `implemented`: the current CLI/test corpus already covers human-readable snapshot output,
  machine-readable payload output, selected-event detail, and `--follow --once` live rendering
- `implemented`: current session payloads and output keep transcript escalation explicit rather than
  collapsing the default surface into transcript body
- `implemented`: human-readable `session --follow` now stays narrower than snapshot mode by keeping
  the transcript hint while dropping selected-event detail and trimming the recent-event slice
- `implemented`: human-readable `session --follow` now points transcript escalation at the live
  `operator log ... --follow` path instead of reusing the snapshot hint verbatim
- `verified`: focused CLI coverage now checks that `session --follow --once` stays compact and keeps
  transcript escalation explicit
- `partial`: this ADR's full RFC 0014 alignment remains incomplete; the command family exists, but
  the broader command-family output-contract closure is still tracked in
  [RFC 0014](../rfc/0014-cli-output-contract-and-example-corpus.md)

## Commands Covered

- `operator session OP --task TASK`
- `operator session OP --task TASK --follow`

## Not Covered Here

- operation-scoped summary via `status`
- operation-scoped live follow via `watch`
- transcript escalation via `log`

## Context

The repository already accepted the existence of a public session-scoped CLI surface, addressed by:

- operation reference
- task reference

RFC 0014 refines that further by distinguishing:

- session investigation snapshot
- session live follow

and by tightening the relationship between session supervision and transcript escalation.

The design corpus now needs one current ADR that owns the whole session-scope family in its RFC
0014 form.

## Decision

The CLI should treat `session` as the bounded level-2 supervisory family beneath one operation.

### Snapshot mode

Default `session OP --task TASK` should provide one human-readable session investigation snapshot.

It should surface:

- session identity/state
- `Now`
- `Wait` or `Attention`
- latest meaningful output
- a short recent event/timeline slice
- a transcript escalation hint

### Live mode

`session ... --follow` should provide a session-scoped live textual follower.

It should keep slightly more local context than `watch`, but it should remain bounded and avoid
sliding into transcript or forensic dump behavior.

## Addressing Rule

The public CLI continues to address session supervision through:

- operation reference
- task reference

It must not require the user to discover or type session UUIDs.

## Boundary Rule

This ADR keeps the session family distinct from:

- `watch`, which remains operation-scoped
- `log`, which remains transcript-first
- `debug trace` / `debug inspect`, which remain forensic

## Consequences

Positive:

- session supervision becomes a stable public CLI family rather than a parity afterthought
- RFC 0014 session examples gain a dedicated ADR owner

Tradeoffs:

- the CLI must keep session detail bounded instead of turning it into another dashboard
- transcript escalation needs to stay explicit because the default session view must not absorb it

## Verification

Current evidence for the landed slice:

- `verified`: session command snapshot, JSON payload, `--follow --once`, selected-event detail, and
  task-addressed behavior are covered in `tests/test_cli.py`
- `not yet verified`: full RFC 0014 closure for the session command family

When the full ADR is implemented, the repository should preserve these conditions:

- session supervision is task-addressed, not session-id-addressed
- snapshot and `--follow` remain distinct but coherent
- default session output includes transcript escalation rather than transcript body

## Related

- [ADR 0117](./0117-public-session-scope-cli-surface.md)
- [RFC 0014](../rfc/0014-cli-output-contract-and-example-corpus.md)
