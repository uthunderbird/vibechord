# ADR 0136: Transcript, retrospective, and ledger surfaces

- Date: 2026-04-10

## Status

Accepted

## Implementation Status

Implemented

Skim-safe current truth on 2026-04-10:

- `implemented`: `operator log`, `operator history`, and `operator report` already exist as the
  transcript, ledger, and retrospective family
- `implemented`: `log` remains transcript-first and supports condensed human-readable output plus
  `--json` machine-readable output for supported transcript sources
- `implemented`: `history` remains the committed ledger surface for durable operation history
- `implemented`: `report` remains the retrospective summary surface and supports both
  human-readable and `--json` output
- `implemented`: current CLI docs now describe the family distinction in `docs/reference/cli.md`
- `verified`: focused CLI coverage for `history`, `report`, and `log` exists in
  `tests/test_cli.py`
- `partial`: RFC 0014 remains draft, so broader family-example closure beyond this landed slice is
  still incomplete

## Commands Covered

- `operator log`
- `operator history`
- `operator report`

## Not Covered Here

- hidden forensic/debug inspection commands
- one-operation summary/detail surfaces
- cross-operation inventory listing

## Context

The CLI now has three adjacent but importantly different surfaces:

- transcript access
- durable history ledger access
- operator-facing retrospective reporting

Older ADRs settled `log` and `history`, but the corpus still lacks one current family ADR that
makes the distinctions explicit and gives `report` a stable owner.

Without this, these commands can drift toward one another:

- `history` toward inventory
- `report` toward status recap
- `log` toward generic inspection

## Decision

The CLI should treat transcript, retrospective, and ledger commands as one related but explicitly
differentiated family.

### `log`

`log` remains the canonical transcript-first surface.

It owns raw or near-raw session output and transcript-oriented escalation.

### `history`

`history` remains the canonical durable ledger surface.

It owns committed or durable historical record, not live supervision and not transcript playback.

### `report`

`report` remains the retained retrospective summary surface.

It should provide an operator-facing synthesized summary of one operation rather than duplicate
either `status` or `history`.

## Distinction Rule

These commands must remain separable by job:

- `log`: "show me what the agent said or emitted"
- `history`: "show me the durable record of runs and terminal history"
- `report`: "summarize what happened in this operation"

That distinction should stay visible in:

- help/discoverability
- default human-readable output
- and machine-readable semantics where applicable

## Consequences

Positive:

- transcript, ledger, and retrospective surfaces become easier to teach and maintain
- RFC 0014 gets one ADR owner for these otherwise easy-to-confuse commands

Tradeoffs:

- `report` must remain intentionally different from both `status` and `history`

## Verification

Current evidence for the landed slice:

- `verified`: `history` reads committed durable history and supports operation-reference selection
- `verified`: `report` returns the synthesized retrospective body and machine-readable payload
- `verified`: `log` remains transcript-oriented for Codex, Claude, and OpenCode transcript sources

The repository should preserve these conditions:

- `log` remains transcript-first
- `history` remains ledger-first
- `report` remains retrospective rather than transcript or live summary

## Related

- [ADR 0097](./0097-forensic-log-unification-and-debug-surface-relocation.md)
- [ADR 0098](./0098-history-ledger-and-history-command-contract.md)
- [RFC 0014](../rfc/0014-cli-output-contract-and-example-corpus.md)
