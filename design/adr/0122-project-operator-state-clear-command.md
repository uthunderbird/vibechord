# ADR 0122: Project Operator State Clear Command

## Status

Accepted

## Context

The repository now persists a substantial amount of project-local operator state under the resolved
data dir, usually `.operator/`.

That state includes:

- live and terminal operation state in `.operator/runs/`
- trace and report artifacts in `.operator/runs/<op>/...`
- event streams in `.operator/events/`
- event-sourced artifacts in `.operator/operation_events/` and `.operator/operation_checkpoints/`
- durable control ingress in `.operator/commands/` and `.operator/control_intents/`
- wakeup files in `.operator/wakeups/`
- background-run inspection artifacts in `.operator/background/`
- learned project memory in `.operator/project_memory/`
- persisted policy state in `.operator/policies/`
- adapter/vendor logs such as `.operator/acp/` and `.operator/claude/`
- operation-reference conveniences such as `.operator/last`
- legacy or incidental runtime leftovers such as `.operator/monitor/` and `.operator/projects/`

The repository also retains project configuration surfaces that must not be treated as disposable
runtime state:

- committed default profile: `operator-profile.yaml`
- committed named profiles: `operator-profiles/*.yaml`
- local named profiles: `.operator/profiles/*.yaml`

There is currently no canonical command for "make this project feel as if operator had never been
run here before" while preserving profile configuration.

Without such a command, users must manually discover and delete a mixed set of directories and
files. That is error-prone and creates at least four failures:

1. users leave stale state behind and then misread new runs through old artifacts
2. users accidentally delete profile configuration together with runtime state
3. users forget committed history and see a false "fresh" state while `operator history` still
   reports prior runs
4. cleanup behavior remains tribal knowledge rather than a public, testable contract

## Decision

The CLI will add a canonical destructive project-state reset command:

```text
operator clear [--yes]
```

This command deletes project-local operator runtime and derived state for the resolved operator
data dir and project workspace, while preserving project profile configuration.

It is intentionally destructive and must require explicit confirmation.

## Command semantics

`operator clear` means:

- remove operator runtime state
- remove operator logs and trace artifacts
- remove operation history for this project
- preserve profile configuration
- leave the project in the same operator-visible state as if no operation had previously been run
  for this workspace

This is a project/workspace reset command, not a generic cache-cleaning command.

### Required confirmation

The command must not execute destructive deletion unless one of the following is true:

- the user passes `--yes`
- or an interactive confirmation flow explicitly confirms the wipe

The first implementation tranche may use `--yes` as the only non-interactive bypass.

### Required safety check

The command must refuse by default if the repository still has active or recoverable operations in
the resolved data dir.

The repository should not silently erase potentially live background or resumable work.

An escape hatch such as `--force` may be added later, but it is not required by this ADR.

## Scope of deletion

The command should remove all operator-owned project-local state except profiles.

### Delete

Under the resolved operator data dir:

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

It should also remove the committed project history ledger:

- `operator-history.jsonl`

if that ledger belongs to the current discovered workspace root.

### Preserve

The command must preserve:

- `operator-profile.yaml`
- `operator-profiles/`
- `.operator/profiles/`

It should also preserve non-semantic caches unless the repository later introduces a separate cache
policy:

- `.operator/uv-cache/`

### Cleanup behavior for empty directories

After removing deletable state, the command may:

- leave `.operator/` present if needed for `.operator/profiles/`
- remove empty deleted subdirectories

It must not delete `.operator/` itself when that would also delete `.operator/profiles/`.

## Why `clear`

`clear` is chosen over `prune`.

`prune` implies selective retention of runtime data. That is not the goal here. The desired
behavior is stronger and simpler:

- wipe all operator-owned project state
- preserve only profile configuration

`clear` better communicates that contract.

## Consequences

### 1. The repository gets an explicit "fresh mission" reset surface

Users no longer need to understand the internal `.operator/` layout to return a workspace to
pre-run state.

### 2. Profile configuration becomes the only retained local operator contract

This reinforces the separation between:

- project configuration
- operator-generated state

### 3. History is treated consistently with fresh-start semantics

This ADR explicitly includes `operator-history.jsonl` in the clear scope.

If the command left history behind, the repository could not honestly claim that the workspace now
looks as though operator had never been run here before.

### 4. Learned policy and project memory are treated as operator state

This ADR intentionally clears `.operator/policies/` and `.operator/project_memory/`.

That is correct for the command's contract:

- it is not "preserve durable project governance"
- it is "return to never-run-before state except for profiles"

If the repository later wants a narrower runtime-only reset, that should be a separate command or
flag, not a weaker interpretation of `clear`.

## Explicit non-goals

This ADR does not require:

- deleting `policies/` in the repository root
- deleting design or documentation artifacts
- deleting unrelated tool caches outside the operator data dir
- deleting `.gitignore`
- deleting profile files
- deleting arbitrary user-authored workspace files
- providing operation-selective cleanup in the first tranche

## Rejected alternatives

### Option A: Manual deletion remains the workflow

Rejected.

The current layout is too rich and too easy to mis-delete manually. A public destructive surface is
safer than undocumented shell knowledge.

### Option B: `prune` deletes only logs and terminal artifacts

Rejected.

That would leave history, memory, policies, or checkpoints behind and would not satisfy the "never
run before" contract.

### Option C: Preserve policy and project memory by default

Rejected.

That would make `clear` semantically weaker than the user-facing promise. If those artifacts remain,
the workspace is not truly reset.

### Option D: Delete profile configuration too

Rejected.

Profiles are the explicit retained project contract and must survive a fresh-start reset.

## First implementation tranche

### P0

1. Add `operator clear --yes`.
2. Resolve the current workspace root and operator data dir using the same discovery path as normal
   CLI execution.
3. Refuse if active or recoverable operations still exist.
4. Delete all runtime and derived state listed in this ADR.
5. Preserve all profile locations listed in this ADR.
6. Print a human-readable summary of what was deleted and what was preserved.

### P1

1. Add interactive confirmation when `--yes` is absent.
2. Add a narrower or broader mode only if a real user need appears:
   - e.g. runtime-only clear
   - e.g. forced clear with active runs present

## Likely implementation touch points

The first tranche will likely concentrate in:

- [main.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/main.py) or its command-module replacement
- [profiles.py](/Users/thunderbird/Projects/operator/src/agent_operator/runtime/profiles.py)
- [store.py](/Users/thunderbird/Projects/operator/src/agent_operator/runtime/store.py)
- [background_inspection.py](/Users/thunderbird/Projects/operator/src/agent_operator/runtime/background_inspection.py)
- [history.py](/Users/thunderbird/Projects/operator/src/agent_operator/runtime/history.py)

and the corresponding CLI/runtime tests.

## Verification criteria

This ADR is materially satisfied when:

- `operator clear --yes` exists
- it preserves:
  - `operator-profile.yaml`
  - `operator-profiles/`
  - `.operator/profiles/`
- it removes runtime and derived artifacts from the current workspace
- it removes `operator-history.jsonl`
- after clear, normal CLI surfaces behave like a never-run workspace:
  - no live operations listed
  - no history entries
  - no stale wakeups, commands, or background artifacts
  - no trace/report/event residue

## Implementation Notes (2026-04-10)

Current repository truth now includes a first implementation tranche:

- `operator clear` exists as a top-level CLI command.
- destructive execution requires explicit confirmation; `--yes` is the non-interactive bypass.
- the command clears the current workspace `operator-history.jsonl`.
- the command preserves:
  - `operator-profile.yaml`
  - `operator-profiles/`
  - `.operator/profiles/`
  - `.operator/uv-cache/`
- the command refuses when persisted non-terminal operations or live background-run records still
  exist for the resolved workspace data dir.

This satisfies the ADR's P0 contract. The broader forced-clear follow-on was later added under
[ADR 0168](./0168-operator-clear-force-mode.md).

## Implementation Status

Implemented

Skim-safe current truth on 2026-04-14:

- `implemented`: `operator clear` exists, is confirmation-gated (`--yes`), and refuses when active
  or recoverable operations are present
- `implemented`: `operator clear --force` exists and discards live or recoverable operator state
  while preserving the same operator-owned deletion boundary
- `implemented`: clears runtime state while preserving committed profiles
- `verified`: `test_clear_yes_removes_runtime_state_and_preserves_profiles`,
  `test_clear_refuses_when_running_operation_exists`,
  `test_clear_force_yes_discards_blockers_and_preserves_profiles`, and
  `test_clear_without_yes_prompts_and_can_cancel` in `tests/test_cli.py`
