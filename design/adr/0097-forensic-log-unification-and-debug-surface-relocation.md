# ADR 0097: Forensic log unification and debug-surface relocation

## Status

Accepted

## Extends

- [ADR 0165](./0165-condensed-claude-session-log-view.md)
- [Vision](../VISION.md)
- [CLI UX Vision](../CLI-UX-VISION.md)

## Context

The current and historical CLI surfaces still carry two kinds of drift:

- vendor-named forensic log commands
- visible internal/runtime commands that compete with the user-facing supervision surface

The refreshed product vision already prefers:

- one unified `log` command
- one `debug` namespace for internal/runtime surfaces

The repository needs one ADR that fixes those relocations explicitly, including the current tension
around whether `trace` and `inspect` remain visible.

### Current truth

Today:

- `operator log OP [--agent ...]` is now the canonical transcript/log surface
- `trace` and `inspect` are now hidden top-level commands with canonical access under
  `operator debug`
- runtime/internal surfaces now have an explicit hidden `debug` namespace

## Decision

The CLI must unify forensic transcript access under `log` and move internal/runtime plumbing under
`operator debug`.

### Unified log command

`operator log OP [--agent ...]` is the canonical transcript/log surface.

It replaces vendor-named top-level commands such as:

- `claude-log`
- `codex-log`

Vendor specificity remains available through selection flags and underlying artifacts, but not
through separate top-level command names.

### `debug` namespace

Internal/runtime-oriented commands move under `operator debug`.

This includes:

- `daemon`
- `tick`
- `recover`
- `resume`
- `wakeups`
- `sessions`
- `command`
- `context`
- `trace`
- `inspect`

### Visible vs hidden decision

`trace` and `inspect` move under `operator debug` and leave the default visible CLI surface.

They remain supported, but they are no longer primary or secondary user-facing commands.

The visible forensic surface is:

- `log`
- `tasks`
- `memory`
- `artifacts`
- `attention`
- `report`

## Consequences

- The top-level command map becomes organized by user intent rather than vendor or runtime plumbing.
- The CLI keeps forensic power without making debug internals the default experience.
- Existing vendor-named commands must migrate through aliases, deprecation, or removal.
- `trace` and `inspect` remain available for deep investigation but stop crowding the main CLI
  taxonomy.

## Implementation notes

## Verification

- `tests/test_cli.py`
- adapter-package tests

## Implementation notes

The current repository has implemented:

- unified `log`
- hidden `trace` and `inspect` at the top level
- canonical `debug` access to runtime/internal surfaces

## This ADR does not decide

- the exact deprecation window for legacy command aliases
- the internal transcript storage format
- the final `log --agent` value taxonomy
- whether future TUI surfaces expose `trace` or `inspect` affordances directly

## Alternatives Considered

### Keep vendor-named transcript commands

Rejected. They leak implementation details into the top-level UX and fragment one user intent into
multiple commands.

### Keep `trace` and `inspect` visible as ordinary secondary commands

Rejected. The CLI UX direction is to keep those deep forensic and runtime surfaces behind the debug
namespace.

### Hide all forensic surfaces, including `log`

Rejected. Transcript access is still a real user-facing supervision need, not only an internal
debug tool.
