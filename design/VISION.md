# Vision

## Project

`vibechord` is a minimalist Python library and CLI for supervising agent work
through a central operation loop.

It is a successor to `operator`, not a compatibility layer for it. The goal is
to preserve the strongest product and architecture ideas while restarting from a
smaller, clearer core.

Normative language:

- **must** is a binding requirement.
- **should** is a strong recommendation.
- **may** is permitted.
- Present-tense implementation claims must match repository evidence.

## Current Status

- `implemented`: documentation/policy skeleton, six-part runtime core, JSONL
  event store, replay/projections, CLI first slice, REST first slice, pure TUI
  view/reducer slice, line-oriented terminal TUI runtime, full-screen curses TUI
  runtime, public local Python SDK, MCP stdio and HTTP POST
  tools/resources/prompts/progress surface, fake adapters, local process-agent
  adapter, local process-brain adapter, OpenAI Responses brain adapter, and fake
  harness.
- `verified`: local `uv run vibechord verify full` passes.
- `planned`: none currently documented for the verified local release gate.

## Why This Exists

Agent work needs a supervisory control plane that can:

- pursue a goal over multiple iterations;
- call external agents with different invocation models;
- evaluate progress from evidence;
- surface human decisions when needed;
- keep live state visible without hiding canonical truth;
- let the operator talk back to the running system.

`operator` demonstrated that this shape is useful. It also showed that hidden
authority splits, delivery-surface drift, and late event-model repair are
expensive. `vibechord` starts by making those concerns explicit.

## Core Thesis

The center of the system is an operation loop.

The loop is responsible for:

1. accepting a goal and constraints;
2. maintaining operation state;
3. deciding whether to reason internally, invoke an agent, wait for human input,
   or stop;
4. applying deterministic guardrails;
5. recording events for every observable state transition;
6. updating shared read projections;
7. repeating until a stop policy fires.

LLM-assisted decisions may plan, decompose, evaluate, and choose next steps.
Deterministic control-plane rules must enforce stop conditions, budgets,
concurrency limits, event recording, command application, and state authority.

## Minimalism

Minimalism means fewer authority boundaries, not weaker behavior.

`vibechord` should have:

- a small set of central abstractions;
- explicit state and event authority;
- thin delivery adapters;
- vendor behavior isolated in adapters;
- no compatibility shims without a real migration reason;
- no abstraction without a concrete capability or coupling reduction.

Minimalism does not mean omitting fleet supervision, live chat, durable traces,
or safety guardrails. Those are product requirements.

## Product Goals

Planned parity target:

- operation run lifecycle;
- resumable work;
- multiple external agent adapters;
- deterministic stop policies;
- structured attention and human input;
- free-form live operator chat;
- fleet-level view of operations and agents;
- TUI workbench;
- CLI, TUI, and REST API surfaces over shared contracts;
- SDK and future MCP surfaces over the same contracts when needed;
- event-backed status and forensic traceability.

First implementation target:

1. prove the operation loop with fake brain and fake agent dependencies;
2. persist canonical events in a replayable local store;
3. expose the same operation and fleet state through CLI, TUI, and REST;
4. support attention answers and live operator messages through shared commands;
5. produce E2E fake harness artifacts that verify replay, projection, and
   delivery parity claims.

## Design Principles

### 1. Operation-loop first

Every major feature should either feed the loop, execute its decisions, expose
its state, or guard its behavior.

### 2. Deterministic guardrails

The runtime must enforce stop policies, budget limits, cancellation, command
application, concurrency limits, and event recording. These are not left to LLM
judgment.

### 3. Protocol-oriented integration

External agents, LLM providers, clocks, stores, consoles, and process managers
should be accessed through explicit contracts.

### 4. Shared delivery authority

CLI, TUI, REST, SDK, and future MCP surfaces should use shared command/query
contracts. Surface-specific rendering is allowed; surface-specific business
authority is not.

### 5. Event-backed transparency

Every observable state transition should produce an event. Live surfaces may
derive projections, but canonical truth must remain replayable.

### 6. Truth labels over confidence theater

Documentation and UI surfaces should say whether data is canonical, derived,
stale, partial, planned, or unverified.

## Non-Goals

- Reimplement every agent capability locally.
- Preserve `operator` compatibility for its own sake.
- Start with a complex plugin framework before the core loop exists.
- Treat TUI state as canonical business truth.
- Let public docs claim runtime behavior before code and tests exist.
- Expose REST beyond localhost before authentication, authorization, and audit
  behavior are implemented.
