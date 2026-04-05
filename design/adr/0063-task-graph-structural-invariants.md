# ADR 0063: Task graph structural invariants

## Status

Accepted

## Context

`TaskState` carries a `dependencies: list[str]` field that the brain populates when proposing task
decomposition. A dependency edge `A → B` means "task A cannot start until task B is complete." The
brain may add new dependency edges later via `TaskPatch.add_dependencies`.

Without explicit invariant enforcement, the dependency graph is vulnerable to:

1. **Cycles** — a set of edges forming A → B → C → A would deadlock the operation: none of the
   tasks could ever become ready.
2. **Self-dependencies** — a task that depends on itself is a degenerate cycle.
3. **Silent dependency removal** — the brain removing a dependency it set earlier, without an audit
   trail, defeats the purpose of encoding the constraint in the first place.

These are not hypothetical: an LLM that proposes tasks in multiple iterations can create
cross-iteration cycles without noticing. Cycle detection needs to be a runtime invariant, not a
convention.

## Decision

### Invariant 1 — Acyclicity

The dependency graph must be a DAG at all times. When the brain proposes a new dependency edge
(either at task creation via `TaskDraft.dependencies` or at patch time via
`TaskPatch.add_dependencies`), cycle detection fires before the edge is committed:

- If adding the edge would create a cycle, the edge is **rejected** — not silently dropped, but
  rejected with a `task.dependency_cycle_detected` domain event that records the task ID, the
  rejected dependency ID, and the reason.
- The task is still created (if at creation time), but without the offending dependencies.
- The operation continues; the brain receives the event and may replan.

Detection algorithm: DFS from the dependent task through the combined existing + proposed edges.
If the DFS reaches the dependent task again, a cycle exists.

### Invariant 2 — No self-dependency

A task cannot list itself as a dependency. Self-dependency is a degenerate cycle and is rejected
by the same mechanism as Invariant 1 (`task.dependency_cycle_detected` with
`reason: "self_dependency"`).

### Invariant 3 — Dependency removal requires reason

`TaskPatch.remove_dependencies` is permitted — the brain may determine that a previously-set
dependency is no longer valid. However, removal requires a non-empty
`dependency_removal_reason` string. The enforcement is via the `task.dependency.removed` event,
which records both the removed dependency and the reason. If no reason is provided, the removal
still proceeds but the event records `"no reason provided"`.

**Rationale for soft enforcement:** Making removal require a non-None reason at the type level
would cause all patches that do not remove dependencies to require an empty string. The friction
is instead in the event record — every removal is visible in the trace, creating an audit trail
without blocking the brain.

### Why no hard-blocking on silent removal

The alternative — rejecting `remove_dependencies` with no reason — was considered and rejected.
The brain's reasoning about why a dependency is no longer valid may be embedded in its `rationale`
field rather than the patch. Blocking on the patch level would require duplicating context.
The audit trail in the event record achieves the traceability goal at lower friction.

## Consequences

- `TaskPatch.add_dependencies: list[str]` — new field; cycle detection fires for each entry
- `TaskPatch.remove_dependencies: list[str]` — new field; requires `dependency_removal_reason`
  for audit trail
- `TaskPatch.dependency_removal_reason: str | None` — the reason string
- `OperatorService._has_cycle()` — static DFS-based cycle detector; checks combined existing +
  proposed adjacency
- Cycle rejection emits `task.dependency_cycle_detected` (domain event) with `reason` field
  (`"would_create_cycle"` or `"self_dependency"`)
- Accepted dependency adds emit `task.dependency.added` (domain event)
- Removed dependencies emit `task.dependency.removed` (domain event) with reason
- `TaskDraft.dependencies` is still accepted at creation time; cycle detection fires there too;
  tasks are created without offending dependencies if a cycle is detected
