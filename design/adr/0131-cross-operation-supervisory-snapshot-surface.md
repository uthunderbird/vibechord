# ADR 0131: Cross-operation supervisory snapshot surface

- Date: 2026-04-10

## Status

Accepted

## Implementation Status

Implemented

Skim-safe current truth on 2026-04-12:

- `implemented`: no-arg `operator` in non-TTY renders the cross-operation supervisory snapshot
  (Fleet Dashboard with needs_attention, status_mix, operation rows); falls back to help when no
  operations exist
- `implemented`: `operator fleet --once` renders the same cross-operation snapshot grammar,
  sharing supervisory summary fields with no-arg `operator`
- `implemented`: `operator list` remains inventory-shaped — plain id/status rows without
  dashboard header, needs_attention counts, or supervisory narrative
- `implemented`: TTY `operator` enters TUI workbench rather than re-entering textual snapshot
- `verified`: `test_fleet_once_renders_cross_operation_dashboard` and
  `test_no_args_non_tty_renders_fleet_snapshot_when_operations_exist` confirm shared snapshot
  grammar in `tests/test_cli.py`
- `verified`: `test_list_default_is_human_readable_brief` confirms inventory shape
- `verified`: `test_list_is_inventory_shaped_not_supervisory_snapshot` explicitly asserts the
  fleet/list distinction

## Commands Covered

- `operator`
- `operator fleet`
- `operator list`

## Not Covered Here

- workspace lifecycle commands such as `run`, `init`, and `clear`
- one-operation summary/control commands such as `status` and `answer`
- one-operation live follow (`watch`)

## Context

The CLI already has accepted decisions for:

- fleet-first default entry behavior
- visible vs hidden command taxonomy
- shared fleet/operation/session supervisory scopes
- fleet/query substrate work that improved parity with the TUI

What it still lacks is one current ADR that governs the textual cross-operation shell contract for:

- no-arg `operator` in non-TTY mode
- `operator fleet`
- persisted operation inventory via `operator list`

RFC 0014 now defines a clearer family model:

- cross-operation supervisory snapshot is a distinct output class
- it is not the same as one-operation shell summary
- it is not the same as live TUI workbench behavior
- it is not the same as raw persisted inventory listing

Without a dedicated ADR here, those three related commands will continue to drift between:

- fleet supervision
- persisted inventory
- and "selected operation" detail rendering

## Decision

The CLI should treat cross-operation supervision as one explicit public command family with a
distinct snapshot contract.

### `operator`

`operator` remains the shell entry surface.

Its non-TTY or `--once` behavior should render the cross-operation supervisory snapshot rather than
help, raw inventory, or a one-operation summary.

Interactive TTY behavior remains governed by the fleet/TUI authority chain and is not redefined by
this ADR.

### `operator fleet`

`fleet` remains the explicit named cross-operation supervisory command.

Its textual output should share the same cross-operation snapshot grammar as non-interactive
no-arg `operator`, while still allowing the command to remain the canonical explicit fleet entry.

### `operator list`

`list` remains a retained secondary command, but it is not another name for the fleet snapshot.

It owns persisted operation inventory rather than supervisory summarization.

Its output should therefore optimize for:

- inventory and identification
- durable/local runtime presence
- lightweight listing semantics

not for selected-operation supervision narrative.

## Cross-Operation Snapshot Contract

The shared human-readable snapshot for `operator` and `fleet --once` should:

- start with one clear cross-operation headline
- show a compact list of current operations suitable for scanability
- optionally include a bounded selected-operation brief
- keep transcript and forensic detail out of the default view
- compress toward row scanability rather than toward prose completeness

The command family should reuse the normalized supervisory summary contract beneath the CLI/TUI
stack rather than inventing command-local summary semantics.

## Relationship To Inventory Listing

`list` should remain adjacent to this family but not identical to it.

Accepted distinction:

- `operator` / `fleet --once` answer "what requires supervisory attention now?"
- `list` answers "which persisted operations are present?"

This distinction must remain visible both in help/discoverability and in output shape.

## Consequences

Positive:

- no-arg `operator`, `fleet`, and `list` get a stable separation of concerns
- cross-operation textual supervision stops drifting toward raw inventory or mini-dashboard output
- RFC 0014 examples for this family gain an ADR owner

Tradeoffs:

- rendering code will need a deliberate split between supervisory snapshot and inventory list modes
- `list` remains useful but intentionally lower-status than `fleet`

## Verification

When implemented, the repository should preserve these conditions:

- no-arg non-TTY `operator` and textual `fleet` use the same cross-operation snapshot grammar
- `list` remains inventory-shaped rather than supervisory-summary-shaped
- TTY `operator` does not re-enter textual snapshot logic when it should open the TUI

## Related

- [ADR 0093](./0093-cli-command-taxonomy-visibility-tiers-and-default-operator-entry-behavior.md)
- [ADR 0115](./0115-fleet-workbench-projection-and-cli-tui-parity.md)
- [ADR 0116](./0116-cli-parity-gaps-for-fleet-operation-and-session-surfaces.md)
- [ADR 0126](./0126-supervisory-activity-summary-contract.md)
- [RFC 0014](../rfc/0014-cli-output-contract-and-example-corpus.md)
