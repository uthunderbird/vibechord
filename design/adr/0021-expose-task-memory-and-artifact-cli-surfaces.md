# ADR 0021: Expose Task, Memory, And Artifact CLI Surfaces

## Status

Accepted

## Context

The runtime already treats tasks, distilled memory, and durable artifacts as first-class
operation truth.

That truth exists in:

- persisted `OperationState`
- operator-brain prompts
- and traceability updates during execution

But the CLI still exposed those layers mostly through raw JSON or indirect forensic views.

This created a product gap:

- the architecture says long-lived work should be portable across sessions through tasks,
  memory, and artifacts
- but the normal CLI inspection surface still centered timelines and events more than the
  durable work product itself

After shipping the live attached transparency slice, the next leverage point is not a richer
live UI. It is making the durable operation knowledge visible and inspectable as a first-class
CLI surface.

## Decision

`operator` will expose first-class CLI surfaces for durable operation knowledge:

- `operator tasks <operation-id>`
- `operator memory <operation-id>`
- `operator artifacts <operation-id>`

The human-readable `report` output will also include concise sections for:

- tasks
- current memory
- and artifacts

These surfaces are projections over existing persisted runtime truth.
They do not introduce a new store, a new event model, or a separate dashboard-only state path.

## Alternatives Considered

- Option A: defer these surfaces and build a TUI/dashboard next
- Option B: keep relying on `inspect --full` JSON and forensic traces
- Option C: expose dedicated task, memory, and artifact surfaces now

Option A was rejected because it would add delivery complexity before the durable knowledge
model is properly surfaced.

Option B was rejected because it keeps essential product truth hidden behind debugging-oriented
views.

Option C was accepted because it strengthens the current architecture with a small, shippable,
end-to-end slice.

## Consequences

- Durable operation knowledge becomes directly inspectable from the CLI.
- `report` becomes a better default handoff and post-run summary surface.
- Future TUI or dashboard work can build on the same surfaced truth instead of inventing a new
  intermediate layer.
- The CLI surface area grows slightly, but without changing core runtime semantics.
