# ADR 0170: Agent Session Manager Live-Session Ownership Boundary

## Status

- Decision Status: Proposed
- Implementation Status: Planned

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

The first implementation tranche should prefer boundary clarification over feature expansion:

1. separate quiet close/dispose from semantic cancel
2. concentrate live session ownership in one manager layer
3. route operator calls through semantic session operations instead of transport-level assumptions
4. stop persisting or consulting `active_session` as a separate source of truth where canonical session records already suffice

Fork support should be introduced only where the target adapter can support it honestly.
