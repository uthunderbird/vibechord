# ADR 0224: Resume And Tick Signal Existing Runtime Owner

- Date: 2026-05-04

## Decision Status

Accepted

## Implementation Status

Implemented

## Context

A live operator-on-operator run exposed a resumable wakeup failure after an answered Codex ACP
permission request:

1. `operator answer` recorded the human approval.
2. `operator tick` / `operator resume` reconciled the answer and selected `CONTINUE_AGENT`.
3. The operation started a background run in `RESUMABLE_WAKEUP` mode.
4. The run almost immediately became `cancelled`, with no useful output and no background log file.
5. The operation status stayed `running` with pending wakeups, so each later `resume` repeated the
   pattern.

Observed evidence from the failing runs:

- background run files had `pid: null`;
- `.operator/background/logs/` contained no log file for the advertised `background_log_path`;
- result files contained synthetic `background_run_cancelled` errors;
- the run completed within roughly one second;
- the ACP transcript showed an approved tool call being aborted when the host follow-up turn was
  interrupted.

The code path explains the symptom:

- `operator resume` and `operator tick` use `BackgroundRuntimeMode.RESUMABLE_WAKEUP`;
- the current runtime still backs that mode with `InProcessAgentRunSupervisor`;
- `InProcessAgentRunSupervisor.start_background_turn()` starts an `asyncio.create_task(...)` in the
  current CLI process;
- once the drive loop reaches "waiting on background agent turn", the CLI command returns;
- exiting the CLI `anyio.run(...)` event loop cancels pending in-process tasks;
- `_run_turn()` catches `asyncio.CancelledError` and persists `background_run_cancelled`.

That means `resume`/`tick` are currently replacing the runtime owner with a short-lived CLI process
that cannot own resumable background work. This violates the intended resumable wakeup model.

## Decision

`resume` and `tick` are control-plane signals to an existing runtime owner. They must not become the
runtime owner themselves.

The canonical contract is:

1. A long-lived runtime owner owns live agent sessions, background turns, and wakeup delivery.
2. `operator resume` and `operator tick` may enqueue commands, reconcile durable facts, and poke the
   runtime owner to continue work.
3. `operator resume` and `operator tick` must not start in-process background turns that are expected
   to outlive the CLI process.
4. If no compatible runtime owner is available, resumable commands must fail loudly or run in an
   explicitly inline/attached mode whose lifetime is bounded by the command.
5. Event-loop shutdown cancellation must not be recorded as a user or operator cancellation.

## Non-Goals

This ADR does not redesign the complete background runtime. It narrows one contract:
short-lived delivery commands are not a substitute for a durable runtime owner.

This ADR does not remove attached operation runs. Attached mode may continue to host live work for
the duration of the foreground command.

This ADR does not weaken cancellation semantics. Explicit user cancellation must still produce
`background_run.cancelled` and a terminal cancelled result.

## Required Implementation

### 1. Separate signal delivery from runtime ownership

`operator resume` and `operator tick` should deliver durable control-plane intent to the existing
operation runtime owner instead of dispatching a new in-process background task.

Acceptable mechanisms include:

- a durable command / wakeup queue consumed by a daemon or foreground owner;
- an IPC poke to an existing owner process;
- a bounded inline mode selected explicitly for commands that should not outlive the CLI.

The default resumable command path must not depend on `asyncio.create_task(...)` surviving after the
CLI command exits.

### 2. Add runtime-owner availability checks

Before dispatching work in `RESUMABLE_WAKEUP`, the command path must prove that a compatible runtime
owner exists.

If no owner exists, the operator should return a clear failure such as:

```text
resumable_runtime_unavailable: resume/tick can only signal an existing runtime owner; start or
attach an operator runtime before continuing.
```

It must not silently start a fake background turn that will be cancelled by event-loop shutdown.

### 3. Preserve explicit cancellation but distinguish host shutdown

`InProcessAgentRunSupervisor` may keep explicit cancellation behavior, but it must distinguish:

- explicit operator/user cancellation;
- adapter-reported cancellation;
- host event-loop shutdown or task disposal.

Only explicit cancellation should persist `background_run_cancelled`. Host shutdown should be
reported as lost/disconnected/stale, or should be prevented by the runtime-owner availability guard.

### 4. Fix stale status feedback

Status surfaces should not advertise a background run as still running when the supervisor has
already persisted a terminal result.

When a terminal background result exists but the operation projection has not reconciled it, status
must make that gap explicit and should guide the user toward the correct reconciliation command
without implying that a live agent is still doing work.

### 5. Add regressions for CLI lifecycle semantics

Tests must cover:

- `resume`/`tick` do not start a long-lived in-process background task when no durable owner exists;
- event-loop shutdown does not produce `background_run_cancelled`;
- explicit cancellation still produces cancelled run/result records;
- status reports terminal-but-unreconciled background runs accurately;
- a resumable command can signal an existing runtime owner without replacing it.

## Consequences

### Positive

- Resumable wakeup semantics become honest: a resumable CLI command signals durable runtime state
  instead of pretending to host background work after exit.
- Cancel-loop failures stop being recorded as user cancellations.
- Status output becomes more trustworthy during partial reconciliation.
- The runtime owner boundary becomes explicit enough to support daemon, MCP, or foreground owner
  implementations.

### Negative

- `operator resume` / `operator tick` may fail where they previously appeared to continue work.
- A durable owner or explicit inline fallback must be implemented before some unattended workflows
  can run end-to-end.
- Tests that assume in-process background tasks can outlive the CLI command will need to be
  rewritten.

## Relationship To Existing ADRs

- ADR 0200 introduced the in-process agent run supervisor. This ADR constrains where that
  supervisor is valid: it can host work only while its owning event loop remains alive.
- ADR 0201 covers crash recovery and orphan detection. This ADR prevents routine CLI command exit
  from masquerading as orphan recovery or explicit cancellation.
- ADR 0205 defines the event-sourced command/control plane. This ADR requires `resume` and `tick`
  to act as control-plane signals rather than runtime substitutes.
- ADR 0218 defines continuation and parked wake semantics. This ADR clarifies that parked wake
  continuation must target an existing runtime owner.
- ADR 0220 covers synchronizable operation state and runtime fact reconciliation. This ADR adds the
  runtime-owner boundary needed for those facts to be meaningful.

## Verification Plan

Implementation should not be marked `Implemented` until focused tests prove that `resume` and
`tick` no longer create in-process background work that is cancelled by CLI event-loop shutdown.

Implementation should not be marked `Verified` until:

- focused lifecycle tests cover absent-owner, existing-owner, explicit-cancel, and host-shutdown
  paths;
- status/read-model tests cover terminal-but-unreconciled background runs;
- a live or integration smoke proves `operator answer` followed by `resume` does not produce a
  synthetic `background_run_cancelled` loop;
- the full repository test suite passes.

## Implementation Notes

Implemented in the 2026-05-04 ADR 0224 wave:

- `RESUMABLE_WAKEUP` execution now requires an explicit compatible runtime owner before
  dispatching `START_AGENT` or `CONTINUE_AGENT`.
- The production bootstrap does not treat the short-lived CLI `InProcessAgentRunSupervisor` as a
  durable resumable runtime owner.
- Test service wiring may still opt into owner availability when a fake supervisor intentionally
  models a durable owner.
- `InProcessAgentRunSupervisor` now distinguishes explicit cancellation from host event-loop task
  cancellation. Explicit cancel still records `background_run_cancelled`; host task shutdown records
  a disconnected `background_run_host_cancelled` result.
- Existing status surfaces already expose terminal-but-unreconciled background runs via
  `runtime_alert` instead of implying live progress.

Focused verification run:

- `uv run pytest -q tests/test_operation_drive_service.py tests/test_runtime.py -k 'resumable_wakeup_without_runtime_owner or resumable_run_mode_uses_enqueue_delivery_for_background_turns or resumable_background_wait_skips_brain_on_heartbeat_tick or inprocess_supervisor_task_cancel or inprocess_supervisor_explicit_cancel'`
- `uv run pytest -q tests/test_operation_status_queries.py -k 'runtime_alert or live_snapshot_omits_stale_waiting_reason'`
- `uv run pytest -q tests/test_cli.py -k 'unreconciled_background_completion'`
- `uv run ruff check src/agent_operator/application/decision_execution.py src/agent_operator/application/drive/operation_drive_decision.py src/agent_operator/bootstrap.py src/agent_operator/testing/operator_service_support.py src/agent_operator/runtime/supervisor.py tests/test_operation_drive_service.py tests/test_runtime.py`

Not yet `Verified`: the full repository test suite and a live `answer` + `resume` smoke have not
been run for this wave.
