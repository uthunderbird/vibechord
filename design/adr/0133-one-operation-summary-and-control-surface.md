# ADR 0133: One-operation summary and control surface

- Date: 2026-04-10

## Status

Accepted

## Implementation Status

Implemented

Skim-safe current truth on 2026-04-12:

- `implemented`: `status` remains the canonical one-operation shell summary surface and still ends
  with an explicit action line when blocking attention is open
- `implemented`: `status` attention guidance now uses the public positional `operator answer OP ATT
  --text '...'` syntax consistently in both the action line and the open-attention section
- `implemented`: `answer`, `message`, `pause`, `unpause`, `interrupt`, and `cancel` remain the
  user-facing operation control family rather than exposing raw command-envelope internals
- `implemented`: `status` output follows RFC 0014 shell-summary grammar — operation anchor, Now/Wait,
  Attention, Progress, Action blocks
- `implemented`: `cancel` is confirmation-gated; `answer` stays separate from policy mutation
  commands while still supporting `--promote` as an explicit opt-in
- `verified`: focused CLI coverage checks status action line, open-attention guidance syntax,
  cancel confirmation gate, answer/policy-promotion separation, pause/unpause/interrupt/message
  in `tests/test_cli.py`

## Commands Covered

- `operator status`
- `operator answer`
- `operator cancel`
- `operator pause`
- `operator unpause`
- `operator interrupt`
- `operator message`

## Not Covered Here

- one-operation textual live follow (`watch`)
- session-scoped surfaces
- transcript and forensic surfaces

## Context

The repository already has an accepted one-operation control and summary ADR, but the CLI has since
evolved further:

- RFC 0014 defines a refined one-operation shell-summary family
- blocking attention and action-hint output have become more explicit
- the answer/policy boundary is clearer than before
- interruption can be task-scoped without changing the operation-first mental model

The current design corpus needs one up-to-date ADR that owns this whole operation-scoped summary
and control family together.

## Decision

The CLI should treat `status` plus the operation-scoped control commands as one coherent shell
family.

### `status`

`status` remains the canonical one-operation shell summary surface.

Its default output should:

- prioritize decisive current-state explanation
- surface blocking attention clearly
- end with an action line when the operation is blocked
- remain distinct from transcript, session, and deep detail surfaces

`status --brief` remains the compact scriptable summary form.

### `answer`

`answer` remains the public response path for blocking attention.

It should stay focused on immediate attention handling rather than absorb the whole policy workflow.

### `pause`, `unpause`, `interrupt`, `cancel`

These remain the public control family for one operation.

They should preserve:

- explicit operation-first framing
- clear destructive vs non-destructive distinction
- confirmation for destructive controls where required
- task scoping only where already product-valid

### `message`

`message` remains the durable operator-to-operation context-injection command.

It should remain user-facing and not be reframed as internal typed-command injection.

## Output And Interaction Rules

This family should follow the one-operation shell-summary grammar from RFC 0014:

- one clear operation anchor
- explicit `Now` / `Wait`
- explicit attention line or explicit absence of attention
- compact recent/progress context only as support for actionability

The control commands in this family should produce:

- explicit success/failure confirmation
- concise next-state explanation
- no raw internal command-envelope output

## Boundary Rule

This ADR intentionally keeps one-operation summary/control separate from:

- `watch`, which is the lean textual live follower
- `session`, which is task-addressed level-2 supervision
- `log`, which is transcript-first
- `debug`, which is hidden forensic/recovery work

## Consequences

Positive:

- the most common one-operation commands gain one current ADR owner
- summary and control semantics stay aligned instead of drifting independently
- RFC 0014 command examples for this core family become traceable to one design record

Tradeoffs:

- this ADR partially supersedes older narrower wording while still depending on it historically

## Verification

When implemented, the repository should preserve these conditions:

- `status` remains the canonical shell summary for one operation
- blocked output yields explicit action guidance
- `answer` stays separate from policy mutation commands even when they reference the same attention
- `cancel` remains confirmation-gated

## Related

- [ADR 0095](./0095-operation-reference-resolution-and-command-addressing-contract.md)
- [ADR 0096](./0096-one-operation-control-and-summary-surface.md)
- [ADR 0028](./0028-explicit-answer-time-policy-promotion.md)
- [RFC 0014](../rfc/0014-cli-output-contract-and-example-corpus.md)
