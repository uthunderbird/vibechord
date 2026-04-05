# ADR 0093: CLI command taxonomy, visibility tiers, and default `operator` entry behavior

## Status

Accepted

## Extends

- [ADR 0038](./0038-cli-authority-and-tui-supervisory-workbench.md)
- [Vision](../VISION.md)
- [CLI UX Vision](../CLI-UX-VISION.md)

## Context

The repository now has a coherent CLI UX direction in `VISION.md` and `CLI-UX-VISION.md`, but it
does not yet have narrow execution-facing decisions for:

- what `operator` does with no arguments
- which commands are primary vs secondary vs hidden debug
- which internal/runtime surfaces must move under `operator debug`
- whether user-facing command taxonomy follows user intent or implementation history

Without an ADR, every CLI implementation slice would have to reopen the same structural debates.

### Current truth

Today:

- `operator` with no arguments now behaves fleet-first:
  - TTY opens the live fleet view
  - non-TTY renders one fleet snapshot when persisted operations exist
  - non-TTY falls back to help when no operations exist
- internal/runtime commands now have a canonical hidden `operator debug` home
- legacy top-level runtime commands remain callable but are hidden from default help
- `--help --all` now reveals the hidden debug surface explicitly
- the repository now implements the intended disclosure contract even where some later ADRs still
  govern command-specific naming and placement

## Decision

The CLI must adopt one explicit command taxonomy with three visibility tiers and a fleet-first
default entry.

### Default `operator` behavior

`operator` with no arguments is the default fleet entry surface.

The behavior is:

1. when a TTY is attached, open the fleet view
2. when no TTY is attached, print one fleet snapshot
3. when no operations exist and no TTY is attached, fall back to help

This makes the default entry about supervision rather than command discovery.

### Visibility tiers

The CLI must expose three command tiers:

1. primary commands shown in default `--help`
2. secondary commands shown in default `--help` after the primary set
3. hidden debug commands shown only via `--help --all`

The default `--help` must optimize for user workflows, not for full command enumeration.

### Primary tier

The primary tier is:

- `run`
- `fleet`
- `status`
- `answer`
- `cancel`
- `pause`
- `unpause`
- `interrupt`
- `message`
- `history`
- `init`
- `project`

### Secondary tier

The secondary tier is:

- `log`
- `tasks`
- `memory`
- `artifacts`
- `attention`
- `report`
- `policy`
- `list`

### Hidden debug tier

Internal/runtime commands move under `operator debug`.

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

### Taxonomy rules

- The top level stays flat for operation-facing commands.
- `project` and `policy` remain real subgroups.
- No `op` subgroup is introduced.
- No vendor-named top-level transcript commands are retained.

## Consequences

- CLI implementation can reorganize help and command placement without reopening naming debates.
- Default entry behavior becomes fleet-first rather than help-first.
- Debug/runtime plumbing stops competing with user-facing supervision commands.
- Existing top-level internal commands must move, gain aliases, or be retired deliberately.
- Future CLI ADRs can assume one stable taxonomy and visibility model.

## Verification

Verified by:

- CLI tests covering fleet-first no-arg behavior
- CLI tests covering hidden default-help treatment
- CLI tests covering `operator debug`
- CLI tests covering `operator --help --all` disclosure of hidden commands

This ADR is accepted because its own contract is now implemented and verified. Later CLI ADRs
still narrow command-specific surfaces, but they no longer block the taxonomy and disclosure
decision captured here.

## This ADR does not decide

- the exact alias/deprecation schedule for moved commands
- detailed help text wording
- TUI rendering details for fleet view
- project-profile precedence or `run` argument resolution
- the exact `log` filtering contract

## Alternatives Considered

### Keep the current broad top-level CLI surface

Rejected. It leaks implementation history into the user-facing command map and weakens progressive
disclosure.

### Add a new `op` subgroup for operation commands

Rejected. The CLI UX direction is intentionally flat for operation-facing commands.

### Keep help as the default no-argument behavior

Rejected. The intended product entry is live supervision, not command memorization.
