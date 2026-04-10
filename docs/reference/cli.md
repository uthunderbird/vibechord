# CLI Reference

`operator` exposes a fleet-first CLI organized around a few primary entry surfaces plus deeper
inspection and forensic commands.

Implementation families for this delivery surface live under
`agent_operator.cli.commands`, `agent_operator.cli.rendering`, `agent_operator.cli.tui`,
`agent_operator.cli.workflows`, and `agent_operator.cli.helpers`.

Primary workflow surfaces:

- `operator` — fleet view in a TTY, fleet snapshot otherwise
- `run` — start an operation toward a goal
- `fleet` — supervise active operations across projects
- `status` — canonical shell-native one-operation summary
- `answer` — answer a blocking attention request
- `message` — inject durable operator context
- `pause` / `unpause` — control operation execution
- `interrupt` — stop the current agent turn without cancelling the whole operation
- `cancel` — cancel an operation
- `history` — show committed project history
- `init` — set up operator in the current project
- `clear` — wipe project-local operator runtime state while preserving profiles
- `project ...` — manage project profiles
- `policy ...` — inspect and mutate project-local policy memory

Situational and forensic surfaces:

- `watch` — lightweight textual live view for one operation
- `dashboard` — richer one-operation live dashboard
- `session` — task-addressed session snapshot surface (`--task`, `--once`, `--follow`, `--json`)
- `tasks` — task board for an operation
- `memory` — distilled memory entries
- `artifacts` — durable outputs
- `attention` — attention request details
- `report` — human-readable operation report
- `log` — condensed transcript events
- `list` — persisted operation inventory
- `agenda` — cross-operation agenda view
- `involvement` — update the autonomy level for a running operation

## Entry surface

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator
```

In the current product model:

- `status` is the canonical shell-native one-operation summary surface
- the TUI workbench launched from `operator` / `fleet` is the preferred interactive live supervision surface
- `watch` remains a lighter textual live follower rather than the flagship interactive surface

## Common examples

Initialize a project:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator init
```

Clear project-local operator state:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator clear --yes
```

Run an operation:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator run "Inspect the repository and summarize the main boundaries."
```

Inspect the latest operation:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator status last
UV_CACHE_DIR=/tmp/uv-cache uv run operator report last
```

Inspect the session bound to a task:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator session last --task task-1 --once
```

Inspect project defaults and effective resolved run settings:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator project list
UV_CACHE_DIR=/tmp/uv-cache uv run operator project inspect femtobot
UV_CACHE_DIR=/tmp/uv-cache uv run operator project resolve femtobot
```

`project list` is an inventory surface. By default it prints just profile names under a `Projects`
header; use `--json` for machine-readable inventory metadata.

Inspect policy inventory, a stored policy entry, or current policy coverage:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator policy list --project femtobot
UV_CACHE_DIR=/tmp/uv-cache uv run operator policy projects
UV_CACHE_DIR=/tmp/uv-cache uv run operator policy inspect policy-1
UV_CACHE_DIR=/tmp/uv-cache uv run operator policy explain last
```

`policy list` is the entry inventory surface. By default it prints active entries for the selected
project scope under a `Policy entries:` section; use `--all` to include inactive entries and
`--json` for machine-readable entry payloads.

`policy projects` is a project index surface. By default it prints project names under a
`Projects With Policies` header; use `--json` for counts, raw scopes, and categories.

`policy explain` is the deterministic explainability surface. It evaluates one operation against
the scoped policy set and separates matched entries from skipped entries; use `--all` to include
inactive entries in that explanation.

For deeper command-shape rationale, see `design/CLI-UX-VISION.md` and
`design/adr/0093-cli-command-taxonomy-visibility-tiers-and-default-operator-entry-behavior.md`
in the repository.
