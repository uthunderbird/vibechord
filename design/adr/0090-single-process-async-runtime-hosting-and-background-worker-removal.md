# ADR 0090: Single-process async runtime hosting and background-worker removal

## Status

Accepted

## Context

The repository currently carries a separate background-worker execution model built around:

- `AgentAdapter`
- `poll` / `collect`
- file-backed background run artifacts
- worker-process lifecycle distinct from the main async runtime

For the closure wave, this hosting model would preserve a second protocol family and a second
source of execution semantics even if the main runtime becomes event-sourced.

### Current truth

Background execution is now hosted through one in-process async runtime model shared by attached
and background work.

### Implementation notes

The canonical composition root uses `InProcessAgentRunSupervisor` for live runtime hosting.
Persisted `background/runs` and `background/results` remain as derived observability artifacts for
CLI inspection.

The old worker-process path has been removed:

- `background_worker.py` is gone
- `FileAgentRunSupervisor` is gone
- `build_supervisor()` / `build_inspection_supervisor()` are gone
- CLI inspection now uses a read-only background-run inspection store instead of an execution
  supervisor

## Decision

The target runtime host is a single-process async runtime.

### Hosting rule

Attached and background execution become scheduling modes inside one async runtime host, not
separate protocol families or worker-process architectures.

### Removal rule

The target architecture must remove:

- separate background-worker process ownership
- file-backed poll/collect worker lifecycle as canonical execution behavior
- any requirement that recovery semantics depend on background worker artifacts being present

### Persistence rule

Durable observability and recovery surfaces may remain file-backed, but they must reflect the
single-process runtime as derived artifacts rather than define a second execution protocol.

## Consequences

- The runtime architecture becomes consistent with `RFC 0010` instead of split between attached and
  worker-hosted modes.
- Cancellation, wakeups, and recovery can be reasoned about through one async ownership model.
- The repository can retire background-worker-specific protocol glue together with `AgentAdapter`.
- Persisted background artifacts remain available for CLI observability even though the worker
  process is no longer the canonical host.

## Verification

- `tests/test_bootstrap.py`
- `tests/test_runtime.py`
- `tests/test_cli.py`
- full suite: `320 passed, 11 skipped`

## This ADR does not decide

- the exact task/supervisor implementation used inside the single process
- whether a daemonized outer process still exists for CLI or TUI supervision
- the canonical business event catalog

## Alternatives Considered

### Keep the background worker and only rewrite it around new runtime contracts

Rejected. That preserves an unnecessary second hosting model during RFC closure.

### Keep both single-process and worker-process hosting as long-lived options

Rejected. The repository follows zero-fallback policy and does not need dual hosting complexity in
pre-release.
