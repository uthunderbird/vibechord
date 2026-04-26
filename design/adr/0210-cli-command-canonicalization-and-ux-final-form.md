# ADR 0210: CLI Command Canonicalization and UX Final Form

- Date: 2026-04-23

## Decision Status

Accepted

## Implementation Status

Verified

Implementation grounding on 2026-04-26:

- `implemented`: the repository now has one canonical command inventory at
  `docs/reference/cli-command-inventory.md` that classifies every registered CLI path as
  `stable`, `transitional`, or `debug-only` instead of leaving that distinction implicit.
- `implemented`: the command inventory is mirrored in a small checked-in metadata table at
  `src/agent_operator/cli/command_inventory.py`, so ADR 0210 command-shape assertions are bound to
  one explicit artifact rather than spread across prose and help output.
- `verified`: a new regression proves the inventory covers the actual Typer tree and that hidden
  debug aliases such as `resume` / `tick` / `recover` stay transitional while their canonical
  homes remain `debug`-only. Evidence:
  `tests/test_cli_command_inventory.py::test_cli_command_inventory_covers_registered_typer_tree`,
  `tests/test_cli_command_inventory.py::test_cli_command_inventory_keeps_debug_aliases_out_of_stable_set`.
- `implemented`: the main CLI reference now links to the canonical inventory instead of forcing
  readers to infer command status from scattered sections. Evidence: `docs/reference/cli.md`.
- `implemented`: the repository now has a command-by-command contract matrix at
  `docs/reference/cli-command-contracts.md` that names stability, JSON-reference coverage, and the
  currently published semantic exit-code/error contract for every registered CLI path.
- `implemented`: `docs/reference/cli-json-schemas.md` now covers the full current `--json` command
  surface rather than only the narrow ADR 0145 agent-facing subset. The added sections now include
  agenda/history/inspect/report/dashboard/log/session, project/profile surfaces, policy surfaces,
  admin surfaces, and the current debug/repair JSON payloads.
- `verified`: dedicated doc-guard regressions bind ADR 0210's reference docs to the live command
  inventory and the current JSON-capable surface. Evidence:
  `tests/test_cli_contract_docs.py::test_cli_command_contract_matrix_covers_inventory_paths`,
  `tests/test_cli_contract_docs.py::test_cli_json_schema_reference_lists_current_json_surfaces`.
- `verified`: existing CLI help tests already prove the progressive-disclosure contract required by
  ADR 0093 and relied on here: default help hides debug/runtime commands, `operator debug` lists
  them, and `--help --all` reveals the hidden surface. Evidence:
  `tests/test_cli.py::test_default_help_hides_debug_commands`,
  `tests/test_cli.py::test_debug_help_lists_hidden_runtime_commands`,
  `tests/test_cli.py::test_help_all_reveals_hidden_debug_commands`.
- `verified`: existing CLI tests already cover important parts of the final-form behavior ADR 0210
  calls out, including ambiguous references, missing operations, semantic cancel exit codes,
  run-wait exit codes, canonical `--json` surfaces, and TTY/non-TTY live supervision behavior.
  Representative evidence:
  `tests/test_cli.py::test_resolution_ambiguous_prefix_reports_stable_cli_error`,
  `tests/test_cli.py::test_cancel_json_returns_cancelled_exit_code`,
  `tests/test_cli.py::test_run_wait_uses_needs_human_exit_code`,
  `tests/test_cli.py::test_watch_once_json_emits_live_snapshot`,
  `tests/test_cli.py::test_default_help_hides_debug_commands`.
- `verified`: focused ADR 0210 verification passed on 2026-04-26:
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_cli_contract_docs.py tests/test_cli_command_inventory.py -q`
  (`5 passed`) and
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_cli.py -k "json or help or ambiguous or wait or cancel or project or policy or agent or session or watch or status or ask or answer or report or history or list or attention or tasks or memory or artifacts or dashboard or agenda" -q`
  (`146 passed, 66 deselected`).
- `verified`: full repository verification passed on 2026-04-26:
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest` (`1011 passed, 11 skipped`).

## Context

The CLI is currently both primary user interface and a collection of transitional debug/legacy
entrypoints. Some commands are hidden aliases; some use legacy services; some know v2 replay; some
render directly from snapshots. CLI cleanup should happen after storage, identity, command, and
query authority are canonical.

## Decision

Define the final v2 CLI taxonomy, names, hidden/debug boundaries, output schemas, exit codes, and
behavior.

The final CLI has these categories:

- lifecycle: `run`, `resume`, `recover`, `tick`, `cancel`, `clear`
- control: `answer`, `pause`, `unpause`, `interrupt`, `message`, `patch-*`
- read: `status`, `inspect`, `watch`, `dashboard`, `report`, `session`, `log`, `tasks`,
  `attention`, `memory`, `artifacts`
- fleet/project/policy surfaces
- debug/repair surfaces

Debug surfaces must be clearly separated from stable user-facing commands.

The repository accepts this direction now. Acceptance records the command taxonomy and command
status model as the intended authority. It does not claim that every remaining schema, help text,
and error-shape detail has already reached final-form closure.

## Required Properties

- every command declares whether it is stable, transitional, or debug-only.
- `--json` schemas are documented and contract-tested.
- TTY and non-TTY behavior is deterministic.
- errors use consistent exit codes and messages.
- terminal/cancelled/missing/ambiguous operation behavior is covered.

## Verification Plan

- command-by-command golden/contract tests.
- `--json` schema tests for machine-facing commands.
- TTY/non-TTY tests for watch/dashboard/session.
- ambiguous ref and terminal operation tests.
- hidden debug command inventory test.

## Related

- ADR 0093
- ADR 0145
- ADR 0204
- ADR 0205
- ADR 0206
- ADR 0207
