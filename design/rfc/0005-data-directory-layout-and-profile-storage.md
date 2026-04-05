# RFC 0005: Data Directory Layout and Profile Storage

## Status

Proposed

## Context

`operator` currently has two overlapping mechanisms for project profile configuration and no
documented principle governing what lives where inside the data directory.

### Two profile mechanisms

**Local profile file** — `operator-profile.yaml` placed in the working directory (or any ancestor).
Auto-discovered by walking up from `cwd`. Applied automatically when `operator run` is invoked
without `--project`.

**Named profiles** — YAML files under `{data_dir}/projects/{name}.yaml`. Created by
`operator project init`. Selected explicitly via `operator run --project name`.

Both mechanisms supply the same class of information (default objective, agents, harness
instructions, involvement level, adapter settings) but through different paths, with different
discovery rules, and different write locations. The naming of the `projects/` subdirectory implies
per-project storage but the files are actually reusable presets with no binding to a specific
project.

### Unsegmented data directory

The data directory currently mixes configuration artefacts (named profile YAML files) with runtime
state (operation JSON, trace JSONL, wakeup records, command records, policy entries). There is no
documented principle distinguishing the two.

### Shared event log

All operations write to a single `events/events.jsonl` file. Events are filtered by `operation_id`
in memory at read time. This creates an O(n_total_events) read cost for any per-operation query
and a shared-writer hazard when multiple operations run concurrently.

## Decision

### 1. Three-category file model

All files managed by `operator` fall into exactly one of three categories:

| Category | Location | Author | May be committed to VCS |
|---|---|---|---|
| Project config | `{project-root}/operator-profile.yaml` | User (hand-authored) | Yes, optionally |
| Named presets | `{data_dir}/profiles/{name}.yaml` | `operator project init` | No |
| Runtime state | `{data_dir}/{runs,events,wakeups,commands,policies,background}/` | System | No |

Configuration artefacts that a user intentionally authors and may want to version-control belong at
the project root, not inside the data directory. Named presets are system-managed and workspace-
scoped; they belong inside the data directory but are not runtime state.

### 2. Rename `projects/` to `profiles/`

The subdirectory `{data_dir}/projects/` is renamed to `{data_dir}/profiles/`.

Rationale: "projects" implies a one-to-one binding between a directory entry and a source project.
The files are reusable configuration presets with no inherent project binding. "profiles" is the
correct term (already used in the domain model and CLI surface).

### 3. Data directory layout

The canonical layout after this RFC:

```
{project-root}/
  operator-profile.yaml             # project config; discovery anchor; may be committed

  .operator/                        # workspace data dir; gitignored
    profiles/
      {name}.yaml                   # named presets (was: projects/)

    runs/
      {op-id}.operation.json        # OperationState
      {op-id}.outcome.json          # OperationOutcome
      {op-id}.brief.json            # TraceBriefBundle
      {op-id}.timeline.jsonl        # forensic trace (TraceRecord)
      {op-id}.report.md             # human-readable report
      {op-id}/
        agents/
          {session-id}-{iter}.summary.json
        reasoning/
          {iter}.json               # DecisionMemo

    events/
      {op-id}.jsonl                 # per-operation RunEvent log (was: events/events.jsonl)

    wakeups/
      {wakeup-id}.json

    commands/
      {cmd-id}.json

    policies/
      {policy-id}.json
      {project-scope}/
        {policy-id}.json

    background/
      ...
```

### 4. Per-operation event files

`JsonlEventSink` is instantiated with `data_dir/events/{operation_id}.jsonl` instead of the shared
`data_dir/events/events.jsonl`.

Invariant: each operation has exactly one writer for its event file. No cross-operation locking is
needed because files do not overlap.

Lookup cost becomes O(events_for_operation) instead of O(all_events).

The existing `read_events(operation_id=...)` filtering path in `JsonlEventSink` is replaced by
direct file open: the operation_id is the file stem.

### 5. Discovery order

**Data directory resolution** (in priority order):

1. `OPERATOR_DATA_DIR` environment variable — used as an absolute path if set.
2. `data_dir` setting in config, if explicitly set or differs from the default — resolved relative
   to `cwd`.
3. Walk up from `cwd`; use the first `.operator/` directory found.
4. Walk up from `cwd`; use `{git-root}/.operator/` at the first `.git` found.
5. Fallback: `{cwd}/.operator/`.

This order is unchanged from the current implementation. It is documented here as the canonical
reference.

**Project profile resolution** (when `operator run` is invoked):

1. `--project name` explicit flag → search `{data_dir}/profiles/{name}.yaml`, then
   `~/.config/operator/profiles/{name}.yaml` (user-level layer, optional).
2. No `--project` flag → walk up from `cwd` looking for `operator-profile.yaml`; apply if found.
3. Neither found → freeform mode; no profile defaults applied.

### 6. Semantics of the two profile mechanisms

Both mechanisms remain. They are not redundant — they serve different purposes:

**`operator-profile.yaml`** is a *project declaration*. Its presence in a directory signals that
this project is intended to be run with `operator`. It contains project-specific defaults (objective
template, harness instructions, agent selection, involvement level). It may be committed to version
control so that project collaborators or CI systems get the same defaults without extra setup.

**`{data_dir}/profiles/{name}.yaml`** is a *named preset*. It is a reusable configuration bundle
that can be applied to any operation via `--project name`. It is workspace-scoped and system-
managed. It is not committed.

When both are present in one invocation (local profile auto-discovered and `--project` explicitly
provided): the named preset wins for all fields it specifies. The local profile supplies `cwd` and
any fields the named preset leaves unset.

## Consequences

### Immediate changes required

- Rename the `profile_dir()` function return value from `data_dir / "projects"` to
  `data_dir / "profiles"`.
- Update all call sites that construct paths under `data_dir / "projects"`.
- Change `JsonlEventSink` instantiation in `bootstrap.py` from the shared path to the per-
  operation path. The sink must receive `operation_id` at construction time or via a factory.
- Update `read_events` and `iter_events` in `JsonlEventSink` to open the per-operation file
  directly rather than filtering a shared file.

### No migration needed

There are no existing users. Files under `.operator/projects/` can be treated as stale and ignored
or deleted. The shared `events/events.jsonl` file carries no operational dependency.

### Deferred

- Splitting `.operator/` into explicit `config/` and `state/` subdirectories — logically sound
  but adds nesting without immediate benefit; revisit when the data directory grows further.
- User-level preset layer at `~/.config/operator/profiles/` — the discovery order reserves slot 1
  for this but it is not required for initial implementation.
- Formal config file format decision (YAML vs TOML for `operator-profile.yaml`) — out of scope
  for this RFC.
