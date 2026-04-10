# ADR 0141: Policy mutation and attention-promotion workflow

- Date: 2026-04-10

## Status

Accepted

## Implementation Status

Implemented

Skim-safe current truth on 2026-04-10:

- `implemented`: `operator policy record` enqueues explicit durable policy mutation rather than
  folding policy creation into `answer`
- `implemented`: `operator policy record --attention ...` supports explicit attention-linked
  promotion without requiring separate title/text overrides
- `implemented`: `operator policy revoke` remains an explicit revocation command and is now
  confirmation-gated by default, with `--yes` as the explicit bypass
- `verified`: focused CLI coverage for mutation, attention-linked promotion, and revoke
  confirmation behavior now exists in `tests/test_cli.py`
- `partial`: RFC 0014 remains draft, so broader example-corpus closure beyond this landed slice is
  still incomplete

## Commands Covered

- `operator policy record`
- `operator policy revoke`

## Not Covered Here

- policy read-side commands
- `operator answer` as the immediate attention-response command

## Context

The current CLI vision wants policy mutation to remain explicit while still fitting naturally into
live operator workflows.

The repository already has accepted authority for:

- explicit policy promotion
- answer-time policy promotion
- explicit policy revocation

But RFC 0014 now needs one current ADR that owns the mutation family itself and its relationship to
attention handling.

## Decision

The CLI should treat `policy record` and `policy revoke` as the explicit public policy-mutation
family.

### `policy record`

`policy record` remains the canonical mutation path for creating durable policy entries.

It may reference attentions and workflow context, but it remains a distinct mutation command rather
than disappearing into `answer`.

### `policy revoke`

`policy revoke` remains the explicit revocation command.

It should continue to be confirmation-gated because revocation is a destructive policy change.

## Relationship To `answer`

The accepted model is:

- `answer` handles the immediate blocking attention
- `policy record` handles durable policy mutation

The workflow may be tightly linked, but the command responsibilities remain distinct.

## Consequences

Positive:

- policy mutation becomes easier to teach as a visible CLI workflow
- RFC 0014 policy-mutation examples gain an ADR owner

Tradeoffs:

- the CLI must preserve explicitness rather than hiding policy mutation inside response handling

## Verification

Current evidence for the landed slice:

- `verified`: `policy record` remains an explicit mutation surface
- `verified`: `policy revoke` is confirmation-gated by default and bypassable with `--yes`
- `verified`: attention-time policy promotion still preserves the distinction between `answer` and
  durable policy mutation

The repository should preserve these conditions:

- `policy record` remains an explicit mutation surface
- `policy revoke` remains confirmation-gated
- attention-time policy promotion does not erase the distinction between response and mutation

## Related

- [ADR 0019](./0019-policy-memory-and-promotion-workflow.md)
- [ADR 0028](./0028-explicit-answer-time-policy-promotion.md)
- [ADR 0096](./0096-one-operation-control-and-summary-surface.md)
- [RFC 0014](../rfc/0014-cli-output-contract-and-example-corpus.md)
