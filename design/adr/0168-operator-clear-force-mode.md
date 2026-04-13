# ADR 0168: operator clear force mode

- Date: 2026-04-13

## Decision Status

Accepted

## Implementation Status

Verified

Implementation grounding on 2026-04-14:

- `implemented`: `operator clear` now accepts `--force` on the canonical CLI surface in
  `src/agent_operator/cli/commands/run.py`
- `implemented`: `clear_async()` threads the force flag through confirmation and output handling in
  `src/agent_operator/cli/workflows/workspace.py`
- `implemented`: `clear_project_operator_state(..., force=True)` bypasses blocker refusal while
  preserving the existing operator-owned deletion set in
  `src/agent_operator/runtime/project_clear.py`
- `verified`: refusal, forced deletion, preserved-surface behavior, and forced confirmation/output
  text are covered in `tests/test_cli.py`
- `verified`: targeted verification passed for the updated clear-command slice, and full
  `uv run pytest` passed at current repository truth

## Context

`operator clear` is the canonical workspace-local cleanup command for runtime state:

- runs
- events
- background artifacts
- wakeups
- checkpoints
- ACP session logs
- operator history

Today the command refuses to run while any active or recoverable operations still exist. The
blocking logic lives in:

- `src/agent_operator/runtime/project_clear.py`
- `src/agent_operator/cli/workflows/workspace.py`

The current refusal is reasonable as a safety default, but it leaves one practical gap: when a
workspace accumulates stale or abandoned recoverable operations, the operator-native cleanup path
is blocked and the user is pushed toward manual deletion of `.operator/` or broad git/file-system
cleanup.

That is the wrong boundary.

When the user explicitly wants to discard operator runtime state, `operator` should provide a
first-class escape hatch inside the operator surface itself rather than requiring ad hoc shell
deletion.

## Decision

Add `--force` to `operator clear`.

`operator clear --force` means:

- skip the active/recoverable-operation blocker check,
- delete the same operator-managed runtime surfaces that `operator clear` already deletes,
- preserve the same committed profile surfaces that ordinary clear preserves,
- and make the destructive scope explicit in the confirmation text or direct CLI output.

This is an operator-runtime cleanup mode only. It is not a repository cleanup mode and must not:

- run `git clean`,
- restore tracked files,
- delete non-operator workspace content,
- or infer that user-created files near the workspace are disposable.

## Command contract

### Default behavior remains unchanged

`operator clear` without `--force` keeps the current safe behavior:

- refuse cleanup when active or recoverable operations still exist,
- print the blocking operation ids,
- and require the user to cancel/recover them first.

### Forced behavior

`operator clear --force`:

- bypasses the blocker refusal,
- deletes operator-managed runtime state even if operations are still marked running or
  recoverable,
- and prints that forced cleanup discarded live/recoverable operator state.

`--force` should also imply non-interactive semantic sufficiency for the blocker check itself, but
it should not silently suppress the normal human confirmation prompt unless `--yes` is also given.

Expected examples:

```sh
uv run operator clear --force
uv run operator clear --force --yes
```

## Scope boundary

The force mode deletes only operator-owned runtime state under the workspace-local operator data
directory plus the existing operator history file.

It does not delete:

- `operator-profile.yaml`
- committed profiles directories
- `docs/`, `design/`, `solution/`, `work/`, or other project content
- git-tracked or untracked non-operator files

If a repository has committed `.operator` artifacts, force-clear still follows the operator-owned
path boundary rather than expanding into git semantics. Any tracked-file consequences remain visible
to git and are outside the responsibility of the clear command itself.

## Implementation notes

The minimal implementation shape is:

1. add `force: bool = typer.Option(False, "--force", ...)` to the CLI surface;
2. thread `force` through `clear_async`;
3. update `clear_project_operator_state()` to bypass `find_project_clear_blockers()` when
   `force=True`;
4. make the confirmation/output text explicitly say that live or recoverable operations will be
   discarded;
5. add tests for both refusal and forced deletion behavior.

## Verification requirements

Before this ADR can move to `Implemented`, the repository should have direct evidence for:

1. `operator clear` still refusing when blockers exist and `--force` is absent;
2. `operator clear --force --yes` deleting runtime state in the same scenario;
3. preserved surfaces still being preserved;
4. no expansion of deletion scope beyond the operator-owned cleanup set.

## Consequences

- Users get a clean operator-native recovery path for abandoned workspaces.
- Cleanup semantics become explicit instead of relying on manual shell deletion.
- The default path remains conservative.
- The CLI gains one more destructive flag, so messaging must stay precise.

## Related

- `src/agent_operator/cli/commands/run.py`
- `src/agent_operator/cli/workflows/workspace.py`
- `src/agent_operator/runtime/project_clear.py`
