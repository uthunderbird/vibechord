# ADR 0143: Attached-live continuation and wakeup reconciliation contract

- Date: 2026-04-10

## Decision Status

Accepted

## Implementation Status

Verified

Skim-safe current truth on 2026-04-26:

- `implemented`: attached runtime reconciliation now re-checks already-terminal background runs
  during supervisor polling instead of leaving them in a stale active state
- `implemented`: attached waiting predicates and CLI runtime alerts now stop treating
  terminal/disconnected runs as still-live background waits
- `implemented`: `run` persists an operation-scoped snapshot of effective adapter settings and
  `resume`/`recover` restore that snapshot before rebuilding runtimes
- `implemented`: runtime metadata now keeps the operation's continuity-mode identity distinct from
  the current `run` / `resume` / `recover` invocation mode, so attached-live continuity is not
  silently rewritten during recovery entrypoints
- `verified`: targeted regression coverage landed in `tests/test_cli.py` and
  `tests/test_operation_traceability_service.py`
- `verified`: focused entrypoint/projection coverage for continuity-vs-invocation runtime metadata
  now exists in `tests/test_operation_entrypoints.py` and `tests/test_operation_projections.py`
- `verified`: status/runtime-alert coverage now explicitly guards the no-`resume`-while-live rule
  through `tests/test_operation_status_queries.py::test_build_runtime_alert_ignores_terminal_background_run_when_live_run_exists`
- `verified`: full end-to-end attached-live progression across repeated background turns without
  manual recovery covered in `tests/test_operation_drive_service.py::test_attached_live_progresses_across_repeated_background_turns_without_resume`
- `verified`: focused attached-live regression coverage passed on 2026-04-26 with
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_operation_status_queries.py -q`
  (`9 passed`)
- `verified`: full repository verification passed on 2026-04-26 with
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`
  (`1034 passed, 11 skipped`)

## Commands Covered

- `operator run --mode attached`
- attached `operator`
- attached `operator fleet`
- attached `operator status`
- attached `operator watch`
- `operator resume` as the recovery fallback

## Not Covered Here

- resumable background operation lifecycle beyond the `attached_live` vs `resumable_wakeup`
  boundary
- TUI pane/layout behavior
- transcript rendering and forensic inspection formatting

## Context

The repository already has:

- a persisted wakeup mechanism for terminal background runs
- reconciliation services that can consume wakeups and assimilate terminal background results
- an `attached_live` runtime mode and a distinct `resumable_wakeup` mode
- CLI/status rendering that can diagnose pending wakeups and recommend `operator resume`
- project-profile and runtime adapter settings that determine how `codex_acp` and other ACP-backed
  agents are actually launched

Current runtime evidence shows a problematic gap in attached mode:

- background agent turns complete and persist terminal wakeups correctly
- the attached operation may remain in a blocking "waiting on background agent turn" state
- status/inspect can then report pending reconciliation and recommend `resume`
- the operation only advances once another scheduler cycle is explicitly driven
- when the operator re-delegates a subsequent background turn, the effective adapter launch
  configuration may be lost and the turn may fall back to the adapter default command instead of the
  configured runtime command
- that can make a relaunch fail immediately even though the original attached operation was started
  with a valid command override and project profile

That behavior is too weak for the intended meaning of attached live supervision.

It treats `resume` as a normal per-turn continuation tool instead of as a recovery tool.
It also breaks attached-turn continuity by letting later launches drift away from the run's
effective adapter configuration.

## Decision

`attached_live` must preserve continuity across turn boundaries.

That means:

- terminal background wakeups are reconciled automatically without routine manual `operator resume`
- subsequent background launches and relaunches inherit the run's effective adapter runtime
  configuration instead of falling back to unrelated global defaults

## Runtime Contract

### 1. Attached live waiting is self-healing

When an attached run enters blocking wait on a background agent turn:

- waiting is allowed while that turn is actually pending or running
- once the background turn becomes terminal, the attached loop should automatically consume the
  persisted wakeup/result and leave the stale waiting state

### 2. Automatic post-turn progression

After terminal wakeup reconciliation in attached mode, the operation should automatically do one of
the following:

- continue into the next planning or execution step
- transition into a truthful blocked / needs-human state
- transition into a truthful terminal state

Manual continuation is not the normal attached-mode contract.

### 3. Subsequent attached launches inherit effective adapter runtime configuration

When an attached operation starts with an effective adapter configuration, that effective
configuration becomes part of the run's continuation contract.

For later background launches or relaunches in the same attached operation:

- the operator must reuse the run's effective adapter command/runtime settings
- project-profile adapter settings that were resolved at launch must remain authoritative unless a
  later explicit operator/user action changes them
- a later launch must not silently fall back from a resolved command such as
  `npx @zed-industries/codex-acp --` to the adapter default `codex-acp`

This applies equally to:

- the first turn after `resume`
- re-delegation after a failed or stale attached session
- later bounded slices in the same attached run

### 4. Transient lag is allowed, durable stuck waiting is not

The contract does not require zero-latency reconciliation.

A short transient delay between:

- terminal background completion
- and visible attached-state reconciliation

is acceptable.

What is not acceptable is steady-state behavior where:

- terminal wakeups accumulate in a healthy attached run
- the operation remains indefinitely blocked on a background wait
- or the user must manually run `resume` after ordinary turn completion

### 5. `resume` is a recovery path, not the normal turn boundary

`operator resume` remains valid for:

- resumable/offline continuation
- recovering after client/process interruption
- forcing reconciliation when the live attached path failed

It should not be required for routine attached progression after each completed agent turn.

## Mode Boundary

The product boundary between runtime modes is:

- `attached_live`:
  - live supervision
  - automatic wakeup/result reconciliation
  - automatic progression when possible

- `resumable_wakeup`:
  - durable wakeup persistence for later continuation
  - explicit re-entry / resume semantics are acceptable and expected

This distinction must remain visible in runtime behavior and in user-facing guidance.

## User-Facing Consequences

For attached CLI/TUI supervision:

- `status` and `watch` may truthfully show that the operation is waiting on an active agent turn
- once that turn is complete, those surfaces should converge automatically to the next truthful
  state
- if the operator re-delegates a new attached turn, that turn should start under the same effective
  adapter command/runtime contract as the current run unless explicitly changed
- runtime alerts about pending wakeups should be exceptional fallback diagnostics, not normal
  steady-state attached UX

If attached live reconciliation fails, the repository may surface:

- a runtime alert
- a `resume` hint
- or a richer recovery/debug recommendation

but those are failure-path affordances, not the normal contract.

## Consequences

Positive:

- attached mode regains its intended "stay with the operation and keep driving it" semantics
- `resume` regains a clean recovery/continuation role instead of becoming a per-turn ritual
- wakeup persistence and live supervision get a clear division of responsibilities
- subsequent attached launches become predictable and do not silently drift to a different adapter
  command source

Tradeoffs:

- attached runtime needs a reliable bridge from persisted wakeups to live scheduler progression
- attached runtime must persist and propagate effective adapter launch settings as part of run
  continuity state
- transient lag must be distinguished from true reconciliation failure

## Verification

Current evidence for the landed slice:

- `verified`: targeted regression coverage for adapter-setting continuity and stale-wait/runtime-alert
  truth in `tests/test_cli.py` and `tests/test_operation_traceability_service.py`
- `verified`: `tests/test_operation_status_queries.py::test_build_runtime_alert_ignores_terminal_background_run_when_live_run_exists`
  now catches the regression where `status`/`watch` style runtime alerts would suggest
  `operator resume` even though another background run is still actively advancing
- `verified`: full end-to-end attached-live progression across repeated background turns without
  manual recovery in `tests/test_operation_drive_service.py`
- `verified`: local verification completed on 2026-04-26 with
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_operation_status_queries.py -q`
  (`9 passed`) and `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`
  (`1034 passed, 11 skipped`)

When the full ADR is implemented, the repository should preserve these conditions:

- a completed background agent turn in `attached_live` is reconciled without manual `resume`
- attached waiting state does not remain stuck after ordinary terminal turn completion
- re-delegated or resumed attached turns launch with the same effective adapter command/runtime
  settings that were resolved for the run, unless an explicit change was made
- an attached run started with profile-provided ACP command overrides does not later regress to the
  adapter default executable
- `status` and `watch` only recommend `resume` in attached mode when live reconciliation has
  actually failed or the run is no longer actively advancing
- repeated attached turns do not accumulate pending wakeups as a normal steady-state pattern
- `resumable_wakeup` continues to permit explicit resume-driven continuation without changing this
  attached-live contract

## Related

- [ADR 0122](./0122-project-operator-state-clear-command.md)
- [ADR 0132](./0132-workspace-shell-and-lifecycle-commands.md)
- [ADR 0133](./0133-one-operation-summary-and-control-surface.md)
- [ADR 0134](./0134-one-operation-live-follow-surface.md)
- [ADR 0142](./0142-hidden-debug-recovery-and-forensic-inspection-surfaces.md)
- [ADR 0143 implementation plan](../internal/0143-attached-live-continuity-implementation-plan.md)
