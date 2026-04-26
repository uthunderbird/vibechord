# CLI JSON Schemas

This document is the stability reference for CLI payloads emitted through `--json`.

The ADR 0145 agent-facing stability contract is the narrow subset required for subprocess/agent
integration. ADR 0210 extends this page into the repository-wide reference for the rest of the
current JSON-capable CLI surface, including project, policy, inventory, and debug/repair payloads.

## Stability Rules

- Published field names are stable.
- Adding new optional fields is non-breaking.
- Removing a field, renaming a field, or changing a field's type is breaking and requires a
  deprecation cycle.
- The deprecation cycle is: ship the new field alongside the old field in one release, then remove
  the old field in the next release with a changelog note.

## Covered Commands

### `operator run --json`

Without `--wait`, `run --json` emits JSON objects over stdout as a JSONL stream:

- `{"type":"operation","operation_id":"..."}`
- `{"type":"event","event":{...}}`
- `{"type":"snapshot","snapshot":{...}}` when live follow surfaces emit snapshots
- `{"type":"outcome","outcome":{...}}`

With `--wait`, the command emits one final JSON object:

- `operation_id`: string
- `status`: `completed|failed|needs_human|cancelled`
- `summary`: string
- `metadata`: object

### `operator status --json`

- `operation_id`: string
- `status`: string
- `summary`: object
- `action_hint`: string or null
- `durable_truth`: object

### `operator ask --json`

- `question`: string
- `answer`: string

### `operator fleet --once --json`

Fleet snapshot object as emitted by `cli_projection_payload(...)`.

### `operator list --json`

One JSON object per line. Each object is the operation brief payload for one operation, optionally
with `runtime_alert`.

### `operator tasks --json`

- `operation_id`: string
- `tasks`: array

### `operator attention --json`

- `operation_id`: string
- `attention_requests`: array

### `operator answer --json`

- `operation_id`: string
- `answer_command`: object
- `policy_command`: object or null
- `outcome`: object or null

### `operator ask --json`

- `operation_id`: string
- `question`: string
- `answer`: string

### `operator cancel --json`

- `operation_id`: string
- `status`: `running|cancelled|failed|needs_human|completed`
- `summary`: string
- `metadata`: object

`status` can be `running` for a scoped cancellation request (`--session`/`--run`) that has
been queued but not yet terminal at the operation level; in that case the process exited with
code `0`.

### `operator watch --once --json`

Single snapshot object as emitted by `build_live_snapshot(...)`.

## Additional Stable JSON Surfaces

### `operator history --json`

- `operation_id`: string
- `entries`: array of committed ledger entries

### `operator agenda --json`

Agenda payload object as emitted by the agenda workflow, including grouped actionable and recent
operation summaries.

### `operator inspect --json`

- `operation_id`: string
- `summary`: object
- `durable_truth`: object
- optional forensic arrays when `--full` is used

### `operator report --json`

- `operation_id`: string
- `status`: string
- `report`: string
- `summary`: object
- `outcome`: object or null
- `durable_truth`: object

### `operator dashboard --json`

Dashboard snapshot object as emitted by `build_dashboard_payload(...)`.

### `operator memory --json`

- `operation_id`: string
- `entries`: array

### `operator artifacts --json`

- `operation_id`: string
- `artifacts`: array

### `operator log --json`

- `operation_id`: string
- `agent`: string
- `entries`: array

### `operator session --json`

- `operation_id`: string
- `task`: object
- `session`: object
- `latest_event`: object or null
- `attention`: object or null

### `operator agent list --json`

- `agents`: array of agent inventory objects

Each inventory object contains:

- `key`: string
- `display_name`: string
- `supports_follow_up`: boolean
- `supports_cancellation`: boolean
- `capability_names`: array of strings

### `operator agent show --json`

- `key`: string
- `display_name`: string
- `supports_follow_up`: boolean
- `supports_cancellation`: boolean
- `capabilities`: array
- `configured_settings`: object

### `operator config show --json`

Redacted global configuration payload as emitted by `redacted_global_config_payload(...)`.

### `operator config set-root --json`

- `config_path`: string
- `added`: boolean
- `project_root`: string
- `project_roots`: array of strings

### `operator project list --json`

- `project_profiles`: array

Each project profile inventory item contains:

- `name`: string
- `path`: string
- `scope`: `local|committed`
- `cwd`: string or null
- `default_agents`: array of strings
- `default_objective`: string or null
- `default_involvement_level`: string or null

### `operator project create --json`

- `profile_path`: string
- `profile_scope`: `local|committed`
- `profile`: object

### `operator project inspect --json`

Declared `ProjectProfile` payload as emitted by `ProjectProfile.model_dump(mode="json")`.

### `operator project resolve --json`

- `profile`: object
- `resolved`: object
- `data_dir`: string
- `data_dir_source`: string
- `profile_path`: string or null
- `profile_source`: string

### `operator project dashboard --json`

Project-scoped dashboard snapshot object as emitted by `project_dashboard_async(...)`.

### `operator policy projects --json`

- `policy_projects`: array

Each project bucket contains:

- `project`: string
- `project_scope`: string
- `policy_count`: integer
- `active_policy_count`: integer
- `categories`: array of strings

### `operator policy list --json`

- `project_scope`: string or null
- `policy_entries`: array

### `operator policy inspect --json`

Single policy-entry payload as emitted by `policy_payload(...)`.

### `operator policy explain --json`

- `operation_id`: string
- `project_scope`: string or null
- `matched_policy_entries`: array
- `skipped_policy_entries`: array
- `has_policy_scope`: boolean

## Transitional And Debug JSON Surfaces

Top-level transitional aliases (`resume`, `recover`, `daemon`, `wakeups`, `sessions`, `inspect`,
`context`, `trace`) reuse the same payloads as their canonical `operator debug ...` homes.

### `operator debug daemon --json`

Daemon sweep/resume payload as emitted by `daemon_async(...)`.

### `operator debug recover --json`

Recovery payload as emitted by `recover_async(...)`.

### `operator debug resume --json`

Resume payload as emitted by `resume_async(...)`.

### `operator debug wakeups --json`

- `operation_id`: string
- `wakeups`: array

### `operator debug sessions --json`

- `operation_id`: string
- `sessions`: array
- `background_runs`: array

### `operator debug inspect --json`

Forensic inspection payload for one operation; `--full` includes stored state, trace, events,
wakeups, and background runs.

### `operator debug context --json`

Effective control-plane context payload for one operation.

### `operator debug trace --json`

Forensic trace payload for one operation.

### `operator debug event append --json`

Repair preview/apply payload for allowlisted event appends, including dry-run output when `--yes`
is not supplied.
