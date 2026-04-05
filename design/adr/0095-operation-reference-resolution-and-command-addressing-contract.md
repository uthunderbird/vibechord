# ADR 0095: Operation reference resolution and command addressing contract

## Status

Accepted

## Extends

- [Vision](../VISION.md)
- [CLI UX Vision](../CLI-UX-VISION.md)

## Context

Most CLI workflows depend on how users refer to operations, attentions, and task-scoped turns. If
that addressing model is left implicit, each command risks inventing its own resolution rules.

The current UX direction already assumes:

- full operation IDs are not the only acceptable reference
- `last` is a first-class shortcut
- answer and interrupt flows may omit some subordinate IDs when defaults are safe

These rules need one shared CLI decision instead of per-command improvisation.

### Current truth

Today:

- the CLI now has a shared operation-reference resolver for:
  - full IDs
  - unambiguous short prefixes
  - `last`
- `answer OP [ATT]` now supports omitted attention IDs by selecting the oldest blocking open
  attention
- `interrupt OP [--task TASK]` is now the public user-facing stop-turn surface
- ambiguity now fails explicitly instead of silently selecting one candidate
- not every remaining operation-facing command has been migrated onto the shared resolver yet

## Decision

All operation-facing CLI commands must share one common reference-resolution contract.

### Accepted operation references

Commands that accept an operation reference must accept:

- the full operation ID
- an unambiguous short prefix
- `last`
- an unambiguous profile-scoped reference where explicitly supported by the command

### `last`

`last` resolves to the most recently started operation in the current project scope.

Its persisted source of truth is project-local runtime state, not shell history or process memory.

### Ambiguity behavior

Reference resolution must fail fast when a shorthand is ambiguous.

The error must:

- explain that the reference matched more than one operation
- print the candidate operations
- ask the user to supply a longer reference

No command may silently pick one arbitrary candidate.

### `answer`

`operator answer OP [ATT]` is the canonical answer flow.

If `ATT` is omitted:

- resolve the oldest blocking attention for the operation
- fail if none exist

### `interrupt`

`operator interrupt OP [--task TASK]` is operation-first.

Without `--task`, it targets the current active agent turn for the operation.

With `--task`, the task reference must accept:

- full task ID
- unambiguous short task prefix

## Consequences

- CLI implementation can centralize reference resolution instead of duplicating it in each command.
- `last` gains one durable scope rule instead of ad hoc behavior.
- Answer and interrupt flows become predictable and scriptable.
- Ambiguity becomes explicit user-facing behavior instead of hidden command-specific drift.

## Implementation notes

The current repository has implemented:

- shared resolution of operation references by full ID, short prefix, and `last`
- `answer OP [ATT]`
- oldest-blocking-attention default when `ATT` is omitted
- `interrupt OP [--task TASK]` as the public command

## Verification

- `tests/test_cli.py`

## This ADR does not decide

- the exact on-disk format used to persist `last`
- whether future fleet-wide commands accept cross-project symbolic names
- shell-completion behavior
- how task references are displayed in TUI surfaces

## Alternatives Considered

### Require full IDs for all commands

Rejected. It is mechanically simple but materially worse for everyday CLI use.

### Let each command define its own shorthand rules

Rejected. That would create avoidable UX drift and inconsistent failure behavior.

### Resolve omitted `ATT` by newest attention instead of oldest blocking attention

Rejected. The workflow vision is explicitly about clearing the oldest blocking attention first.
