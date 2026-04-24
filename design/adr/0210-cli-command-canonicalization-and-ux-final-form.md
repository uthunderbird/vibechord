# ADR 0210: CLI Command Canonicalization and UX Final Form

- Date: 2026-04-23

## Decision Status

Proposed

## Implementation Status

Planned

## Context

The CLI is currently both primary user interface and a collection of transitional debug/legacy
entrypoints. Some commands are hidden aliases; some use legacy services; some know v2 replay; some
render directly from snapshots. CLI cleanup should happen after storage, identity, command, and
query authority are canonical.

## Decision

Define the final v2 CLI taxonomy, names, hidden/debug boundaries, output schemas, exit codes, and
behavior.

The final CLI has these categories:

- lifecycle: `run`, `resume`, `recover`, `tick`, `cancel`, `clear`
- control: `answer`, `pause`, `unpause`, `interrupt`, `message`, `patch-*`
- read: `status`, `inspect`, `watch`, `dashboard`, `report`, `session`, `log`, `tasks`,
  `attention`, `memory`, `artifacts`
- fleet/project/policy surfaces
- debug/repair surfaces

Debug surfaces must be clearly separated from stable user-facing commands.

## Required Properties

- every command declares whether it is stable, transitional, or debug-only.
- `--json` schemas are documented and contract-tested.
- TTY and non-TTY behavior is deterministic.
- errors use consistent exit codes and messages.
- terminal/cancelled/missing/ambiguous operation behavior is covered.

## Verification Plan

- command-by-command golden/contract tests.
- `--json` schema tests for machine-facing commands.
- TTY/non-TTY tests for watch/dashboard/session.
- ambiguous ref and terminal operation tests.
- hidden debug command inventory test.

## Related

- ADR 0093
- ADR 0145
- ADR 0204
- ADR 0205
- ADR 0206
- ADR 0207
