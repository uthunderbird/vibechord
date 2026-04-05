# ADR 0055: Background ACP progress snapshots and SDK notification logging

## Status

Accepted

## Context

The operator had a visibility gap for ACP-backed background runs.

In the incident that drove this ADR:

- Claude activity continued in `~/.claude`,
- the SDK-backed ACP path did receive or could have received session updates,
- but the operator-visible ACP log stopped at `session/prompt`,
- and resumable/background runtime surfaces only showed heartbeat plus “background turn started”.

Two design gaps caused that behavior:

- `AcpSdkConnection` queued incoming `session/update` notifications in memory but did not log them to
  the ACP jsonl file,
- and the background worker treated ACP turns as `start/send -> collect()` instead of polling live
  progress while the turn was still running.

That made attached runs look much richer than background runs even when the underlying agent work was
equally alive.

## Decision

Introduce a shared background-progress path for ACP-backed runs and log inbound SDK notifications.

The chosen behavior is:

- SDK-backed ACP notifications such as `session/update` are now logged as inbound `jsonrpc.stdout`
  events, matching the subprocess-backed ACP forensic shape closely.
- Background workers poll ACP adapters while a background turn is active instead of waiting silently in
  `collect()`.
- Background run files now carry an additive live `progress` snapshot with:
  - state
  - message
  - partial output preview
  - updated timestamp
  - last ACP event timestamp when available
- Supervisor and CLI reads use those snapshots as runtime evidence for active background sessions.

This is an observability and runtime-evidence decision, not a lifecycle-ownership change. The
application service remains the single writer of canonical session and execution truth.

## Alternatives Considered

- Keep background ACP runs as terminal-result-only and rely on `~/.claude` for forensic detail
- Log only SDK notifications and leave background runtime surfaces unchanged
- Emit a new high-frequency progress event stream instead of storing snapshots in background run files
- Add adapter-specific Claude-only progress logic instead of a shared ACP/runtime slice

## Consequences

- Positive consequence: background ACP runs now expose live progress before terminal result delivery.
- Positive consequence: SDK-backed ACP logs are now useful for comparing operator-visible evidence with
  upstream Claude activity.
- Positive consequence: `inspect` and `sessions` can show richer live background state without waiting
  for a resume or terminal wakeup.
- Negative consequence: background runtime files now carry one more additive field that projections must
  understand.
- Negative consequence: the worker now polls adapters continuously during background runs instead of
  waiting only on `collect()`.
- Follow-up implication: if progress snapshots later become too noisy or too expensive, throttling or a
  separate progress event stream can be added above this baseline.
