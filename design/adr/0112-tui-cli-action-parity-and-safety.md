# ADR 0112: TUI Action Parity and Safety Contract

## Status

Accepted

## Context

A future TUI can be fast and useful only if every state-changing action maps to an existing CLI
control surface. It also fails safely only if destructive flows reuse the same safeguards as CLI.

Current TUI documents already imply action keys, but without an explicit contract there is risk of:

- key-to-command drift,
- inconsistent destructive confirmation policy,
- and stale naming (`stop_turn` semantics) in interactive surfaces.

## Decision

Meaningful TUI actions are command-aligned and safety-aligned with CLI:

In hexagonal terms:

- CLI and TUI are peer driving adapters,
- public CLI commands remain the authoritative user-facing contract,
- and both surfaces must drive the same application-facing command/use-case ports rather than
  maintaining separate control logic.

1. **`a` = answer blocking attention**
   - TUI-level action for selected scope (operation or task context).
   - Maps to `operator answer OP [ATT]`.
   - Defaults to oldest blocking attention if ATT omitted, matching CLI behavior.

2. **`p` / `u` = pause / unpause**
   - Maps to `operator pause OP` and `operator unpause OP`.
   - `p` and `u` are always level-gated by selected operation.

3. **`s` = interrupt**
   - Maps to `operator interrupt OP` (and optional task scoping where supported by UI scope).
   - Replaces any legacy `stop_turn` naming in TUI-facing docs and action docs.

4. **`c` = cancel**
   - Maps to `operator cancel OP`.
   - Must require explicit confirmation step in TUI before execution.

5. **View actions**
   - `d`, `t`, `m`, `r` are non-destructive view actions and may switch right pane/detail mode or open
     raw transcript where applicable.

### Destructive safety policy

- `cancel` initiated from TUI always requires confirmation `[y/N]` (or equivalent inline bar).
- `Esc` or any non-affirmative input aborts cancellation.
- A destructive action that is non-configured with explicit confirmation is rejected by this contract.

## Action-Command Mapping Snapshot

- `Fleet -> Enter` = zoom only, no state mutation.
- `Fleet -> a` = `answer` for selected operation blocking attention.
- `Fleet -> p/u` = `pause` / `unpause` operation.
- `Fleet -> c` = `cancel` with confirmation.
- `Operation -> Enter` = zoom to session scope.
- `Operation -> a` = `answer` for selected task attentions.
- `Operation -> s` = `interrupt`.
- `Session -> Enter` = expand selected event.
- `Session -> r` = open raw transcript.

## Alternatives Considered

### Option A: Let TUI define alternate destructive semantics for richer UX

Rejected.

That would create behavior that cannot be guaranteed through shell automation and CLI equivalence.

### Option B: Use local TUI-only confirmations but preserve CLI rules for direct command use

Rejected.

Inconsistent safety semantics between interfaces are a source of real runtime risk.

### Option C: Full command/action parity with shared destructive policy

Accepted.

This gives fast supervision while retaining CLI reliability and auditability.

## Consequences

- TUI implementation is constrained to deterministic command equivalence.
- TUI action handling must route through the same command/use-case semantics that back public CLI
  commands; it must not add a separate state-mutation path.
- Existing naming conflicts are removed from user-facing docs in favor of `interrupt`.
- Operational safety policy becomes uniform: destructive actions are always confirmed unless explicitly
  bypassed with CLI equivalent flags (`--yes`) where applicable.

## Verification

- `a`, `p`, `u`, `s`, `c` action paths are covered by CLI command tests and UI action tests.
- TUI-triggered `a` is implemented with a modal text input and dispatches through the same
  `answer_attention` application command path used by CLI `operator answer`.
- TUI-triggered actions remain explainable by the same underlying application-facing command/use-case
  paths as the corresponding public CLI commands.
- Any new TUI key requiring state mutation must have one explicit mapping in this ADR or a
  successor ADR before implementation.
- Destructive paths are explicitly confirmed in docs and user-visible behavior.

## Implementation Notes (2026-04-09)

- `a` now starts an in-TUI answer mode in fleet/operation scopes, preselecting oldest blocking attention:
  operation scope uses oldest blocking attention across the selected operation; operation view uses oldest
  blocking attention for the currently selected task.
- Answer dispatch includes non-empty input validation and explicit abort on `Esc` / `Ctrl+C`.
