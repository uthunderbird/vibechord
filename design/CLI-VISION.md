# CLI Vision

Status: `verified`

The CLI is the scriptable, shell-native control surface for `vibechord`.

## Role

The CLI should be:

- the fastest way to start and inspect work;
- stable enough for scripts;
- explicit about canonical truth versus live overlays;
- aligned with the same command/query contracts used by TUI and REST.

The CLI is not the owner of business logic.

## Command Families

Initial command families:

- `vibechord init` — initialize workspace-local configuration and storage.
- `vibechord run "goal"` — start an operation.
- `vibechord status OP` — one-operation canonical summary.
- `vibechord fleet` — fleet snapshot in non-TTY, TUI workbench in TTY.
- `vibechord watch OP` — textual live feed for one operation.
- `vibechord answer OP ATTENTION_ID "text"` — answer attention.
- `vibechord message OP "text"` — post live operator message.
- `vibechord pause OP` / `vibechord resume OP` — control execution.
- `vibechord interrupt OP` — stop current agent turn without cancelling the
  whole operation.
- `vibechord cancel OP` — cancel operation.
- `vibechord show ...` — details, trace, events, sessions, report.
- `vibechord agent ...` — inspect configured agents.
- `vibechord project ...` — inspect project configuration.
- `vibechord serve` — start REST API server.

## Output Contract

Every user-facing command should have:

- human-readable default output;
- `--json` for machine-readable output when useful;
- stable error codes for scriptable failures;
- clear operation id resolution behavior.

Human output may be concise. JSON output should expose status, provenance, and
staleness fields where relevant.

Initial exit-code contract:

- `0` success;
- `1` command rejected by application rules;
- `2` invalid CLI usage or invalid local configuration;
- `3` operation id not found or ambiguous;
- `4` event store or replay failure;
- `5` adapter/runtime failure surfaced by the operation loop.

JSON error output should include `code`, `message`, `operation_id` when known,
and `retryable` when the application can classify it.

## Interaction Rules

- Destructive commands require confirmation unless `--yes` is passed.
- Long-running live commands should have `--once` where a snapshot is useful.
- Commands that mutate operation state use the shared command application path.
- Read commands use `ProjectionService` through shared delivery contracts.
- CLI should not bypass REST/TUI parity contracts by assembling its own state.

## First Implementation Slice

The first CLI slice should cover:

1. `init`;
2. `run` with fake brain/fake adapter support;
3. `status`;
4. `fleet --once`;
5. `message`;
6. `answer`;
7. `watch --once` or equivalent event dump.

This is enough to prove the operation loop, commands, event store, read models,
and delivery parity foundation.

Acceptance gates:

- `run` returns a resolvable operation id.
- `status --json` and REST operation detail share the same status DTO shape for
  covered fields.
- `fleet --once --json` and REST fleet share the same row DTO shape.
- `message` and `answer` produce command responses with stable accepted or
  rejected codes.
- `watch --once --json` exposes canonical event sequence and live-feed envelope
  provenance without reading private store internals.
