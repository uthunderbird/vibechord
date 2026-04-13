# ADR 0170: Agent Session Manager Live-Session Ownership Boundary

## Status

- Decision Status: Accepted
- Implementation Status: Verified

## Context

The operator currently mixes two different kinds of session responsibility:

1. durable operator truth about sessions as coordination objects
2. live runtime ownership of ACP-backed agent sessions

This mix shows up in several places:

- `TaskState.linked_session_id` and `SessionState` are part of operator coordination truth
- `active_session` exists as a separate shortcut over canonical session state
- attached/background execution owns transport lifecycle through operator-side registry and runtime layers
- runtime disposal currently collapses into semantic cancellation, producing false `context_exit` churn

The current shape creates avoidable bugs:

- normal runtime disposal is interpreted as session cancellation
- live session reuse and continuation semantics are spread across operator, registry, supervisor, and adapter runtime
- stale or pre-link background execution records accumulate around session lifecycle edges

At the same time, the operator cannot simply delete session truth entirely. Session identity is still used semantically for:

- task-to-session linkage
- attention targeting
- cooldown and recovery targeting
- cancellation targeting
- execution lineage and replay-backed reconciliation

Therefore the correct boundary is not "no sessions in operator." The correct boundary is "no operator-owned live session micromanagement."

## Decision

Introduce an explicit `AgentSessionManager` boundary as the single owner of live session lifecycle.

This boundary should likely be implemented by evolving the current attached-session registry into a real manager, rather than adding a parallel subsystem.

The `AgentSessionManager` owns live-session concerns such as:

- ensuring that a usable live session exists for one logical session identity
- reattach/load/reuse rules
- quiet runtime disposal versus semantic cancellation
- follow-up and continuation transport behavior
- fork behavior when an adapter supports it
- guaranteeing at most one live runtime instance per logical session identity

The operator keeps only durable session truth, including:

- `linked_session_id`
- canonical session records and statuses
- execution linkage and reconciliation metadata
- attention, cooldown, and cancellation addressability

The operator should ask for semantic actions such as:

- continue this session
- fork this session
- cancel this session or execution
- report whether this session is waiting, running, terminal, or recoverable

The operator should not directly own transport lifecycle details such as:

- when ACP session context is opened or disposed
- whether a live connection should be kept warm
- whether a follow-up requires reattach/load
- whether closing a runtime context should emit a semantic cancel

## Consequences

### Positive

- session lifecycle invariants have one clear owner
- live transport disposal can be cleanly separated from semantic cancellation
- adapter/runtime-specific session behavior stays below the operator domain layer
- future features like fork, warm reuse, and stronger session recovery have one natural home
- `active_session` can be retired as separate dual-write state over time

### Negative

- this is a meaningful refactor, not a local bug fix
- the current registry, supervisor, and attached-turn paths will need rebinding to the new ownership model
- a poor `AgentSessionManager` API could become an extra indirection layer without removing old responsibilities

### Neutral / Follow-on

- session truth remains in operator, so this does not by itself eliminate all session-related domain state
- follow-on ADR or tranche planning should define:
  - the minimal operator-visible session model
  - the exact `AgentSessionManager` protocol
  - fork semantics and adapter capability gates
  - migration away from `active_session`

## Alternatives Considered

### 1. Remove session context from operator entirely

Rejected for now.

Session identity is currently part of real operator coordination semantics, not just transport metadata. Removing it completely would require a broader redesign of task linkage, attention routing, cancellation, and replay semantics than is justified by the immediate bug class.

### 2. Add only a SessionFactory

Rejected.

Creation is not the main problem. The real problem is lifecycle ownership across reuse, reattach, close, cancel, and fork.

### 3. Keep the current design and patch individual lifecycle bugs

Rejected as the primary route.

This would reduce symptoms but preserve the underlying ownership confusion between operator, registry, supervisor, and adapter runtime.

## Implementation Notes

The first implementation tranche is now implemented and verified at repository truth:

- `active_session` has been removed from `OperationState`, `OperationCheckpoint`, canonical birth,
  and projector flow
- replay, command handling, attached-turn orchestration, and result folding no longer persist or
  consult `active_session` as a separate source of truth
- read surfaces still expose an `active_session` payload, but only as a derived convenience view
  from canonical session truth
- verification passed at current repository truth: `610 passed, 11 skipped`

The second implementation tranche is now also implemented and verified at repository truth:

- explicit `AgentSessionManager` protocol now exists as the application-facing live-session boundary
- the current attached-session registry is wrapped behind a registry-backed manager adapter
- foreground services and the in-process supervisor now share one app-scoped manager instance
- `AdapterRuntime` and `AgentSessionRuntime` now distinguish quiet `close()` from semantic `cancel()`
- runtime disposal no longer maps `__aexit__()` to semantic `context_exit` cancellation
- targeted verification passed at current repository truth, and full verification passed:
  `610 passed, 11 skipped`

ADR 0170 is now fully implemented and verified at repository truth:

- the concrete attached-session implementation now lives as `AttachedSessionManager`, so the
  application-facing manager contract owns the live-session implementation directly rather than
  routing through a registry-backed wrapper
- runtime reconstruction and technical-fact application for attached sessions now sit behind
  manager-owned helpers instead of leaking inline through the public manager surface
- ACP fork support now remains capability-gated at runtime-binding truth and reuses loaded-session
  configuration before exposing a forked session as live
- runtime-native test bindings now advertise fork support only when the fake adapter actually
  implements fork behavior, so helper-layer capability claims match executable truth
- targeted verification passed for the manager/runtime/binding slice, and full verification passed:
  `622 passed, 11 skipped`
