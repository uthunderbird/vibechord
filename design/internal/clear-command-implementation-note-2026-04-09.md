# `operator clear` Implementation Note

## Purpose

Bridge [ADR 0122](/Users/thunderbird/Projects/operator/design/adr/0122-project-operator-state-clear-command.md)
into an implementation tranche with:

- exact deletion targets
- clear preservation rules
- a safe execution order
- concrete CLI and runtime touch points
- focused regression tests

## Command shape

Canonical first tranche:

```text
operator clear [--yes]
```

Behavior:

- destructive project-local operator reset
- preserves profiles
- removes runtime, trace, history, and learned operator state
- refuses when active or recoverable operations still exist

Deferred:

- `--force`
- interactive confirmation without `--yes`
- selective clear modes

## Runtime truth to use

Use the same workspace and data-dir discovery path as the normal CLI:

- [resolve_operator_data_dir()](/Users/thunderbird/Projects/operator/src/agent_operator/runtime/profiles.py)
- [discover_workspace_root()](/Users/thunderbird/Projects/operator/src/agent_operator/runtime/profiles.py)

Do not invent a second path-resolution rule for clear.

## Exact deletion set

Delete these data-dir children when present:

- `runs/`
- `events/`
- `commands/`
- `control_intents/`
- `wakeups/`
- `operation_events/`
- `operation_checkpoints/`
- `background/`
- `project_memory/`
- `policies/`
- `acp/`
- `claude/`
- `monitor/`
- `projects/`
- `last`

Delete this workspace-root file when present:

- `operator-history.jsonl`

### Preserve set

Always preserve:

- `operator-profile.yaml`
- `operator-profiles/`
- `.operator/profiles/`

Preserve for now:

- `.operator/uv-cache/`

Rationale:

- profiles are explicit project configuration, not runtime residue
- `uv-cache` is tooling cache, not operator mission truth

## Active/recoverable refusal rule

Before deletion, load all known operations from the current store and refuse if any operation is:

- actively running
- waiting on resumable/background work
- paused but still resumable
- otherwise still materially recoverable under the current runtime model

Conservative rule for tranche 1:

- refuse unless every persisted operation is terminal and non-recoverable

This is intentionally stricter than necessary.

It is better to block a wipe that the user can re-run later than to erase live work.

## Suggested implementation split

### 1. Runtime-facing helper

Add a small helper module under `runtime/` or `cli/helpers_*.py` that:

- resolves the data dir and workspace root
- enumerates delete targets
- enumerates preserve targets
- performs refusal checks
- returns a structured summary of what would be or was deleted

Suggested shape:

- `OperatorClearPlan`
- `OperatorClearResult`
- `build_operator_clear_plan(settings) -> OperatorClearPlan`
- `execute_operator_clear(plan) -> OperatorClearResult`

Avoid pushing this into a generic filesystem helper. It is product semantics, not just file I/O.

### 2. CLI wiring

Best initial home:

- [commands_project.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/commands_project.py)

or

- a new small module such as `commands_workspace.py`

Recommendation:

- add it as a top-level command, not under `project`

Reason:

- this is a primary workspace-level operator lifecycle action
- it belongs closer to `init` and `run` semantics than to named-profile management

### 3. File deletion strategy

Use `shutil.rmtree()` for directories and `Path.unlink()` for files.

Deletion order:

1. build plan
2. validate refusal condition
3. delete files first
4. delete directories except `.operator/profiles`
5. opportunistically remove now-empty `.operator/` children
6. never delete the data dir root if preserved content remains

Do not shell out to `rm`.

## Human-readable output

Default human output should be concise and explicit.

Suggested shape:

```text
Cleared operator state for /path/to/workspace

Deleted:
- .operator/runs
- .operator/events
- .operator/background
- operator-history.jsonl

Preserved:
- operator-profile.yaml
- operator-profiles/
- .operator/profiles/
- .operator/uv-cache/
```

If refusal triggers:

```text
Refusing to clear operator state because active or recoverable operations still exist.
Use status/list/inspect to resolve or terminate them first.
```

## Likely file touch set

Primary:

- [commands_project.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/commands_project.py) or a new top-level command module
- [app.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/app.py) only if a new command module is introduced
- [profiles.py](/Users/thunderbird/Projects/operator/src/agent_operator/runtime/profiles.py)

Likely new support module:

- `src/agent_operator/runtime/clear.py`
  or
- `src/agent_operator/cli/helpers_clear.py`

Tests:

- [test_cli.py](/Users/thunderbird/Projects/operator/tests/test_cli.py)
- [test_runtime.py](/Users/thunderbird/Projects/operator/tests/test_runtime.py) if a runtime helper module is added

## Test targets

### CLI behavior

1. `operator clear --yes` removes runtime state and history.
2. `operator clear --yes` preserves:
   - `operator-profile.yaml`
   - `operator-profiles/`
   - `.operator/profiles/`
3. `operator clear --yes` preserves `.operator/uv-cache/`.
4. `operator clear --yes` prints a deleted/preserved summary.

### Safety behavior

5. command refuses when persisted operations are active or recoverable
6. refusal leaves all files untouched

### Edge cases

7. works when some targets do not exist
8. works when only profile files exist
9. works when `.operator/` contains legacy directories like `claude/` or `monitor/`
10. removes `operator-history.jsonl` only for the current discovered workspace root

## Deliberate deferrals

Not in tranche 1:

- force wipe over active operations
- dry-run mode
- operation-selective cleanup
- cache cleanup beyond operator mission state
- cleaning global logs outside the resolved workspace data dir
