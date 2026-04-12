# CLI Reference

`operator` exposes a fleet-first CLI organized around a few primary entry surfaces plus deeper
inspection and forensic commands.

The workspace shell and lifecycle family is:

- `operator` / `fleet` — enter supervision for the current workspace
- `init` — prepare first-run workspace configuration
- `run` — start a new operation in the current workspace
- `clear` — reset project-local operator runtime state when the workspace needs a clean slate

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
- `agent ...` — inspect configured agent descriptors and adapter settings
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
- `status` should make the current attention state explicit, including showing when there is no open
  attention
- the TUI workbench launched from `operator` / `fleet` is the preferred interactive live supervision surface
- `watch` remains a lighter textual live follower rather than the flagship interactive surface
- `watch` should stay compact and explicitly tell you whether attention is present, plus the next
  response command when intervention is required
- in a real TTY, `watch` now redraws the current live snapshot in place instead of appending an
  ever-growing event stream; `--json` continues to stream structured events/snapshots/outcomes

## Workspace lifecycle

The shell is intended to read as one workspace lifecycle rather than a bag of unrelated commands:

1. Run `operator init` once to prepare the workspace profile and local ignore rules.
2. Start work with `operator run ...`.
3. Return through `operator` or `operator fleet` to supervise current work.
4. Use `operator clear` only when you need to reset project-local runtime state.

`clear` is a destructive workspace reset command. It is not a generic cache cleaner and does not
replace profile management under `operator project ...`.

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
UV_CACHE_DIR=/tmp/uv-cache uv run operator dashboard last --once
UV_CACHE_DIR=/tmp/uv-cache uv run operator watch last
```

Inspect transcript, ledger, and retrospective surfaces:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator log last --limit 20
UV_CACHE_DIR=/tmp/uv-cache uv run operator history last
UV_CACHE_DIR=/tmp/uv-cache uv run operator report last --json
```

Inspect the session bound to a task:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator session last --task task-1 --once
UV_CACHE_DIR=/tmp/uv-cache uv run operator session last --task task-1 --follow --once
```

`session` remains task-addressed rather than session-id-addressed. Default/`--once` output is the
bounded investigation snapshot; `--follow` is the more compact live variant and keeps transcript
escalation explicit via `operator log` rather than inlining transcript body. In a real TTY,
`session --follow` redraws the current Level 2 snapshot in place instead of appending duplicate
snapshots. Snapshot mode keeps `Now`, one decisive `Wait` or `Attention` line, `Latest`, a bounded
recent slice, and optional event detail; `--follow` trims that further while keeping the transcript
escalation hint explicit.

Inspect project defaults and effective resolved run settings:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator project list
UV_CACHE_DIR=/tmp/uv-cache uv run operator project create femtobot --agent codex_acp
UV_CACHE_DIR=/tmp/uv-cache uv run operator project dashboard femtobot --once
UV_CACHE_DIR=/tmp/uv-cache uv run operator project inspect femtobot
UV_CACHE_DIR=/tmp/uv-cache uv run operator project resolve femtobot
```

`project list` is an inventory surface. By default it prints just profile names under a `Projects`
header; use `--json` for machine-readable inventory metadata.

`project create` is the explicit project-profile authoring/update surface. It writes profile
defaults and confirms the written profile path; use `--json` for machine-readable mutation output.

`project dashboard` is the project-scoped supervision surface. Use `--once` for a single snapshot
or `--json` for a machine-readable dashboard payload.

Inspect the configured agent roster and one agent's current configuration:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator agent list
UV_CACHE_DIR=/tmp/uv-cache uv run operator agent show codex_acp
```

`agent list` is an inventory surface for the built-in agent registry. By default it prints stable
agent keys with display names under an `Agents` header; use `--json` for machine-readable
capability inventory payloads.

`agent show` is the inspection surface for one configured agent. By default it prints descriptor
capabilities plus the current resolved adapter settings; use `--json` for a machine-readable detail
payload.

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

`policy record` remains the explicit durable policy-mutation path, including attention-linked
promotion via `--attention`. `policy revoke` remains a destructive explicit mutation and therefore
asks for confirmation by default; use `--yes` to skip the prompt.

`log`, `history`, and `report` are adjacent but intentionally different:

- `log` is transcript-first. It shows condensed agent transcript events and supports follow mode for
  session-oriented inspection.
- `history` is ledger-first. It shows committed durable run history for the current project and can
  resolve operation references like `last`.
- `report` is retrospective-first. It shows the synthesized operation report and, under `--json`,
  includes the report text plus brief/outcome and durable-truth payloads.

Operation-scoped surfaces that take an operation argument accept the normal operation reference
forms: full id, unique short prefix, and `last`.

For deeper command-shape rationale, see `design/CLI-UX-VISION.md` and
`design/adr/0093-cli-command-taxonomy-visibility-tiers-and-default-operator-entry-behavior.md`
in the repository.

For the stable machine-readable contract covered by ADR 0145, see
`docs/reference/cli-json-schemas.md`.
