# CLI/TUI Extraction Tranche Outcome

Internal implementation note. Not architectural authority by itself.

Date: 2026-04-09

This note records the current repository state after the first extraction waves driven by
`ADR 0114` and [cli-tui-extraction-tranche-plan.md](/Users/thunderbird/Projects/operator/design/internal/cli-tui-extraction-tranche-plan.md).

## Scope of this outcome

This is not a claim that the full extraction is complete.

It is a narrower claim:

- the repository now has explicit application-side command/query seams for the main supervisory
  surfaces,
- `src/agent_operator/cli/main.py` is materially thinner than before,
- the main CLI rendering paths have been separated into dedicated CLI-local modules,
- and the remaining work is now clearer and more bounded.

## Implemented extraction seams

### Application-facing projection service

Implemented in:

- [operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_projections.py)

Current role:

- durable truth payloads
- operation context payloads
- fleet payloads
- project dashboard payloads
- operation dashboard payloads
- brief summary / inspect summary / live snapshot payloads
- shared `ProjectionAction` output for adapter-local control hint rendering

Status:

- `implemented`

### Application-facing command/use-case service

Implemented in:

- [operation_delivery_commands.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_delivery_commands.py)

Current role:

- status payload / status rendering support
- resume / tick / recover / daemon sweep
- cancel
- generic command enqueue
- stop-turn enqueue
- answer-attention flow
- command payload validation
- policy-decision payload validation
- shared live snapshot builder

Status:

- `implemented`

### Application-facing agenda/fleet query service

Implemented in:

- [operation_agenda_queries.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_agenda_queries.py)

Current role:

- agenda snapshot loading
- project filtering
- agenda item assembly over shared status-core loading

Status:

- `implemented`

### Application-facing project dashboard query service

Implemented in:

- [operation_project_dashboard_queries.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_project_dashboard_queries.py)

Current role:

- active policy loading for a profile scope
- fleet snapshot loading via agenda query service
- project dashboard payload assembly via projection service

Status:

- `implemented`

### Application-facing one-operation dashboard query service

Implemented in:

- [operation_dashboard_queries.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_dashboard_queries.py)

Current role:

- one-operation dashboard query orchestration
- command/event enrichment
- projection payload assembly
- adapter-supplied upstream transcript callback

Status:

- `implemented`

## CLI main.py effect

`src/agent_operator/cli/main.py` still exists as the main Typer surface, but it no longer owns as
much shared logic as before.

### What is now mostly out of `main.py`

- command payload rules
- policy promotion payload rules
- lifecycle resume/tick/recover/daemon orchestration
- shared status-core loading for:
  - `status`
  - `watch`
  - `dashboard`
  - `inspect`
  - `report`
  - `context`
  - agenda/fleet-derived surfaces
- agenda/fleet query orchestration
- project dashboard query orchestration
- one-operation dashboard query orchestration
- major Rich dashboard rendering
- major text rendering for status/context/watch/inspect-style surfaces

### What intentionally remains in `main.py`

- Typer command registration
- shell-facing option parsing and normalization
- thin adapter-local rendering wrappers
- transcript/log selection and formatting
- some forensic/trace assembly
- run entry wiring and project/profile selection glue

## CLI rendering separation

The main CLI rendering paths are no longer implemented directly inside
`src/agent_operator/cli/main.py`.

Implemented in:

- [rendering.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/rendering.py)
- [rendering_text.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/rendering_text.py)

Current role:

- fleet Rich rendering
- project dashboard Rich rendering
- one-operation dashboard Rich rendering
- operation list line formatting
- live snapshot formatting
- status brief formatting
- context line emission
- inspect summary rendering
- live event formatting

Status:

- `implemented`

`main.py` still contains thin wrappers over some of these rendering functions where preserving
stable call sites and shortening policy remains useful.

## Shared status-core adoption

The main supervisory surfaces now converge on the same status-core loading path via
`OperationDeliveryCommandService.build_status_payload(...)`.

Surfaces already moved to this path:

- `status`
- `watch`
- `dashboard`
- `inspect`
- `report`
- `context`
- `agenda` / `fleet` / `project dashboard`
- part of `trace`

Status:

- `implemented`

## Adapter-local compatibility shaping

The repository still preserves CLI-facing `control_hints` while shared projections expose
structured `actions`.

Current adapter-local shaping remains in:

- [main.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/main.py)

Current helper:

- `_cli_projection_payload(...)`

Status:

- `implemented`
- `intentional`

This is still acceptable because it is explicitly adapter-local compatibility shaping rather than
shared projection logic.

## Tests added

Focused tests were added for the extracted services:

- [test_operation_projections.py](/Users/thunderbird/Projects/operator/tests/test_operation_projections.py)
- [test_operation_delivery_commands.py](/Users/thunderbird/Projects/operator/tests/test_operation_delivery_commands.py)
- [test_operation_agenda_queries.py](/Users/thunderbird/Projects/operator/tests/test_operation_agenda_queries.py)
- [test_operation_project_dashboard_queries.py](/Users/thunderbird/Projects/operator/tests/test_operation_project_dashboard_queries.py)
- [test_operation_dashboard_queries.py](/Users/thunderbird/Projects/operator/tests/test_operation_dashboard_queries.py)

Status:

- `implemented`
- `verified by focused tests`

Verification snapshot for the current extraction state:

- `uv run pytest tests/test_operation_projections.py tests/test_operation_delivery_commands.py tests/test_operation_agenda_queries.py tests/test_operation_project_dashboard_queries.py tests/test_operation_dashboard_queries.py`
  - `15 passed`
- `uv run pytest tests/test_cli.py`
  - `103 passed`

## Remaining work

The extraction is materially advanced but not complete.

### Still reasonable next extraction targets

- explicit query service for forensic `trace` payload assembly if it needs TUI reuse
- continued thinning of `main.py` around transcript/log/drill-down helpers
- possible dedicated CLI-local module for transcript/log formatting if that surface keeps growing
- possible consolidation of project/profile query glue if TUI will consume that surface directly

### Things that do not need to happen before initial TUI work

- moving every command into its own module
- total decomposition of `main.py`
- moving all CLI-only formatting out immediately

## Practical interpretation

The repository is now in a better state for TUI implementation than it was when `ADR 0114` was
written.

More precisely:

- the core command/query contracts are no longer trapped in one CLI module,
- the main supervisory surfaces now share reusable application-side loading and projection paths,
- the main CLI rendering paths now live outside `main.py`,
- and the remaining CLI code is increasingly adapter-local rather than mixed authority logic.

## Current assessment

- `ADR 0114 prerequisite`: `mostly satisfied, with major command/query/rendering seams implemented`
- `TUI footing`: `improved and now credible for an initial implementation tranche`
- `CLI main.py thinness`: `partial, materially improved`
- `need for further extraction before substantial TUI work`: `reduced; remaining work is now mostly optional or surface-specific`
