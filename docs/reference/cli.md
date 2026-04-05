# CLI Reference

`operator` exposes a fleet-first CLI with the following primary commands:

- `run` — run the operator against a goal
- `init` — set up operator in the current project
- `status` — show the default one-operation summary
- `cancel` — cancel an operation or one of its background runs
- `involvement` — update the involvement level for a running operation
- `pause` / `unpause` — control attached operation execution
- `interrupt` — stop the current attached turn without cancelling the whole operation
- `message` — send a durable operator-level message
- `attention` — show attention requests
- `tasks` — show the task board
- `memory` — show distilled memory entries
- `artifacts` — show durable artifacts
- `answer` — answer an open attention request
- `list` — list persisted operations
- `history` — show committed project history
- `agenda` — show the cross-operation agenda
- `fleet` — show a live cross-operation dashboard
- `report` — print the human-readable report for an operation
- `dashboard` — show a live one-operation dashboard
- `watch` — watch an operation via persisted events and state
- `log` — show condensed human-readable transcript events

## Entry surface

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator
```

## Common examples

Initialize a project:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator init
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

For deeper command-shape rationale, see `design/CLI-UX-VISION.md` and
`design/adr/0093-cli-command-taxonomy-visibility-tiers-and-default-operator-entry-behavior.md`
in the repository.
