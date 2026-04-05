# ADR 0054: Recoverable ACP Disconnects and Session Reattach

## Status

Accepted

## Context

The operator previously treated ACP subprocess and transport failures as fatal agent failure. That was too strong for `claude_acp`.

In the incident that drove this ADR:

- the ACP subprocess failed,
- Claude itself could still be alive,
- Claude-spawned work such as `lean` and `lake build` also remained alive,
- and the operator responded by starting a fresh session and a fresh execution.

That behavior was wrong in two ways:

- it overstated what the ACP failure actually proved,
- and it created duplicate heavy work on the same project target.

The repository already moved to a canonical `Operation / Session / Execution` model with the application service as the single writer of lifecycle truth. The missing piece was a way to represent “lost ACP contact, but same session may still be recoverable” without collapsing it into `FAILED`.

## Decision

Introduce an additive recoverable-disconnect path for ACP-backed agents, starting with `claude_acp`.

The chosen semantics are:

- `AgentResultStatus.DISCONNECTED` means ACP contact was lost during an active turn and the underlying session may still be recoverable.
- `claude_acp` classifies only a narrow, explicit set of transport failures as `DISCONNECTED`.
- `ExecutionObservedState.LOST` is the canonical execution-state representation of a disconnected background turn.
- `SessionState` remains logically active and moves to waiting with a recovery-specific waiting reason.
- on the next operator cycle, the service prefers continuing the same logical session over starting a fresh one.

The service also interprets a brain `START_AGENT` decision as a continuation when a recoverable disconnected session already exists for that adapter. This keeps recovery operator-owned and deterministic instead of relying on prompt wording.

## Alternatives Considered

- Continue treating all ACP subprocess failures as fatal
- Recover only at the human CLI layer via manual `recover`
- Add a generic ACP recovery path for all adapters immediately
- Solve only the duplicate-build symptom with command dedup and leave disconnect semantics unchanged

## Consequences

- Positive consequence: the operator no longer overclaims fatal failure from ACP transport loss alone.
- Positive consequence: surviving Claude sessions can be reattached instead of spawning a fresh parallel session.
- Positive consequence: duplicate heavy work such as repeated `lake build` becomes much less likely even before command-level dedup.
- Negative consequence: runtime state now has one more additive status (`disconnected`) that projections and reconciliation paths must understand.
- Negative consequence: v1 is intentionally Claude-first; broader ACP generalization remains follow-up work.
- Follow-up implication: command-level duplicate-heavy-work guards should build on top of this recovery path, not replace it.
