# ADR 0042: Attached Turn Timeouts And Recovery Replanning

## Status

Implemented

## Context

`operator` currently treats an attached agent turn as the preferred live runtime path.

That path already has:

- attached execution as the default `run` mode,
- an explicit `stop_agent_turn` control seam,
- rich persisted operation state,
- and adapter-specific logs and artifacts for inspection.

But it still has an important failure mode:

- an attached agent turn starts,
- the agent produces partial work, partial tool results, or local repository changes,
- the turn then hangs or silently disappears before yielding a final completed result,
- and `operator` remains in `Waiting on an attached agent turn.`

This is operationally bad for long-lived runs.

Real examples show several variants of the same problem:

- a worker reaches a late tool call such as `lake build` or `pytest` and never yields a final
  turn result,
- a worker lands a real diff and tests pass, but the attached session never returns the final
  wrap-up message,
- or a worker drifts into stale theorem-shaped scaffolding and the control plane keeps waiting
  indefinitely instead of recovering from the latest meaningful state.

The current runtime has explicit stale-recovery logic for background runs, but no symmetric
timeout-and-recovery path for attached turns.

## Decision

`operator` will introduce explicit timeout-based recovery semantics for attached agent turns.

The model is:

1. each attached turn gets a configurable wall-clock timeout budget,
2. when that budget expires without a completed turn result, the operation enters recovery rather
   than waiting indefinitely,
3. recovery inspects persisted truth from the operation state, session state, adapter logs,
   completed tool results, repository changes, and any final completed agent message already
   available,
4. the runtime derives a recovery summary from that evidence,
5. and the operator replans from the recovered state instead of remaining stuck on the incomplete
   turn.

The accepted first slice is intentionally narrow:

- timeout detection only for attached turns,
- recovery uses existing persisted truth and adapter log evidence,
- latest meaningful completed evidence becomes canonical operator input for the next brain cycle,
- and the operation surfaces an explicit runtime alert that recovery happened.

The runtime should not blindly treat the last streamed text chunk as canonical.

Recovery should prefer, in order:

- the latest completed full agent message if one exists,
- otherwise the latest completed tool-backed state plus repo-truth summary,
- otherwise the last persisted agent result already recorded by the operation.

## Alternatives Considered

### Option A: Keep indefinite waiting and rely on manual cancel/restart

Rejected.

This preserves a simple runtime model, but it leaves the preferred attached mode too fragile and
too dependent on human babysitting.

### Option B: Hard-kill timed-out attached turns and mark the operation failed

Rejected.

This is too destructive for long-running work where the repository may already contain useful
partial progress.

### Option C: Add attached-turn timeout plus recovery inspection and replan from recovered state

Accepted.

This keeps attached mode live and resilient while staying faithful to persisted runtime truth.

## Consequences

- Positive: attached runs stop hanging indefinitely on incomplete turns.
- Positive: useful partial work can be recovered and turned into the next planning state.
- Positive: the control plane becomes more symmetric with existing stale-background-run recovery.
- Positive: runtime alerts can truthfully distinguish normal waiting from suspect/hung turns.
- Negative: recovery adds more runtime state and more edge cases around partial completion.
- Negative: adapter log inspection becomes a first-class part of recovery semantics.
- Negative: poor recovery heuristics could over-trust incomplete agent output if not kept narrow.
- Follow-up: add attached-turn timeout configuration and timeout timestamps to session state.
- Follow-up: add recovery-summary generation and recovery runtime alerts.
- Follow-up: add deterministic replanning semantics after attached-turn recovery.

## Implementation outcome

This direction is now repository truth.

Implemented evidence includes:

- configured attached-turn timeout handling in the application/runtime layer
- attached-turn timeout reconciliation and recovered synthetic results
- recovery summaries stored on session state
- runtime-alert projection for timeout recovery
- regression tests covering timeout recovery and log-tail-assisted recovery

The remaining work is refinement of heuristics and observability, not adoption of the model.
