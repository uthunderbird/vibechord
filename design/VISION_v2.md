# Vision v2

## Status

Forward-looking product vision.

This document is not yet the accepted architectural source of truth.
It describes the intended next-stage shape of `operator` after the current v1 foundations.

## Project

`operator` should evolve from a transparent operator loop into a true harness for long-lived,
goal-directed agent work.

It should remain:

- a minimalist Python library and CLI,
- LLM-first in orchestration,
- deterministic where control semantics must be trustworthy,
- protocol-oriented at integration boundaries,
- and transparent by default.

But the user experience should become much stronger:

- one live control surface,
- many long-running agent actions over time,
- explicit human intervention points,
- and clear real-time visibility into what is happening now.

## Core Thesis

The center of the system is still the operator loop.

But in v2 that loop should no longer be modeled as only:

- decide,
- call an agent,
- inspect the result,
- repeat.

It should instead become a long-lived control process that arbitrates among several kinds of
inbound signals:

1. agent events and results,
2. human commands and answers,
3. deterministic runtime wakeups and timers,
4. explicit attention requirements,
5. and durable project policy.

The operator should feel like a live harness, not just a resumable run launcher.

## Product Goal

The product goal is a system where a user can:

- start a long-lived operator run,
- watch it work in real time,
- interrupt or redirect it at any time,
- let it continue autonomously when appropriate,
- and inspect exactly why it chose each step.

The operator should be able to manage long-lived objectives across:

- many tasks,
- many sessions,
- many agent turns,
- and potentially multiple agent types,

while keeping a single authoritative persisted control plane.

## Why This Exists

Most agent tools still optimize for one agent in one surface:

- one terminal session,
- one hosted API worker,
- one chat surface,
- or one predetermined workflow.

`operator` targets a different problem:

- long-lived orchestration across heterogeneous agents,
- transparent supervision of that work,
- and explicit human control without collapsing back into manual micromanagement.

The real problem is not merely "run an agent."
It is "supervise evolving agent work toward a durable objective under explicit policy."

## What Changes In v2

The strongest new capabilities in this vision are:

### 1. True harness control

The operator itself becomes a live controllable process.

The user can:

- pause the operator,
- resume it,
- stop the whole operation,
- stop one active agent turn,
- answer a question,
- patch the objective or harness,
- change constraints,
- and send a message to the operator while it is running.

### 2. Human attention as a first-class concept

The operator should not ask for help only through prose in logs.

It should create typed attention requests such as:

- question
- approval request
- policy gap
- blocked external dependency
- novel strategic fork

These should be visible, addressable, and resolvable.

### 3. Adjustable autonomy

The operator should support explicit user involvement levels.

Examples:

- unattended
- auto
- collaborative
- approval-heavy

The point is not only how often the operator asks questions.
The point is how it behaves when the user is unavailable:

- which branches it can continue,
- which branches it should defer,
- which situations count as hard stops,
- and which resolved decisions become reusable project policy.

### 4. Project-local policy learning

The operator should be able to remember approved project decisions as policy.

Examples:

- testing expectations
- repo bootstrap conventions
- when to run red team
- how to treat manual-testing debt
- how to handle external canonical-doc sync

This policy should be explicit and inspectable.
It must not silently mutate from every interaction.

### 5. Project profiles

Large repeated launch commands should give way to lightweight project profiles.

A profile should capture stable project defaults such as:

- `cwd`
- relevant paths
- default adapters
- default harness instructions
- success criteria defaults
- involvement mode
- monitoring preferences

Profiles should remain declarative and human-readable.
They are defaults, not live runtime state.

### 6. Real-time CLI/TUI monitoring

The operator should expose a live monitoring and intervention surface comparable in feel to a
good terminal-native agent interface.

That means:

- fleet overview,
- focused operation view,
- active sessions,
- current focus,
- attention queue,
- and intervention commands.

But this TUI must remain a projection of the control plane, not a second hidden runtime.

## Design Principles

### 1. LLM-first orchestration, not LLM-first control truth

The operator brain should still do:

- planning,
- synthesis,
- evaluation,
- route selection,
- and strategic adaptation.

But control-plane truths should remain deterministic where ambiguity would damage trust.

Examples:

- command acceptance
- command targeting
- pause / resume / stop semantics
- attention request lifecycle
- policy promotion provenance

### 2. Persisted control plane remains authoritative

The system should keep one authoritative persisted view of:

- objective state
- task state
- session state
- command history
- attention requests
- outcomes
- and traceability artifacts

Attached live runtime is the preferred user story.
Persisted state is the authoritative recovery story.

### 3. TUI follows runtime truth

The TUI must not invent business logic.

It should render:

- state snapshots,
- attention alerts,
- command acknowledgements,
- and condensed trace projections

that already exist in the runtime truth.

### 4. Sessions are execution resources, not the product center

The center of the system is:

- objective
- tasks
- branches
- policy
- attention
- and control state

Sessions matter, but they should not become the main mental model.

### 5. Minimal explicit abstractions

The project should continue preferring:

- small typed domain models,
- `typing.Protocol` contracts,
- deterministic reducers where needed,
- and file-backed transparency

over hidden frameworks or giant orchestration stacks.

## Runtime Model

The preferred runtime surface is a live attached harness.

That harness should:

- keep running until completion, failure, or explicit stop,
- supervise long-running agent work,
- accept commands while work is active,
- and surface attention and progress in real time.

Underneath that, the control plane should remain:

- persisted,
- resumable,
- inspectable,
- and recoverable after interruption.

This implies a hybrid runtime model:

- attached live control for normal use,
- resumable persisted recovery underneath.

## Live Control Plane

The next real substrate for v2 is a typed command and attention model.

### Operation command inbox

The operator should receive durable commands such as:

- pause operator
- resume operator
- stop operation
- patch objective
- patch harness
- patch constraints
- set involvement level
- answer attention request
- inject operator message

These should be stored and acknowledged as explicit runtime events.

### Deterministic vs brain-mediated boundary

Some commands should be handled deterministically:

- pause
- resume
- stop
- answer attention request
- set involvement level

Some should be accepted deterministically but require replanning:

- patch objective
- patch constraints
- inject operator message

The brain may replan after accepted commands.
It must not decide whether a valid command exists or whether it took effect.

### Scheduler state

The operator likely needs a scheduler-facing state distinct from coarse operation status.

Examples:

- active
- pause_requested
- paused
- draining

This is especially important during attached active turns.

### Pause semantics

In the first honest version:

- pause during idle scheduler state can become immediate `paused`
- pause during an active attached turn should become `pause_requested`
- once the current turn yields, the operator transitions to `paused`

If the user wants to interrupt the active agent immediately, that should be a separate command,
not hidden behind pause.

## Attention Model

The operator should create typed attention requests when human involvement is needed.

Those requests should include:

- type
- scope
- blocking vs non-blocking
- question or requested decision
- status
- and resolution provenance

Human answers should route back to a concrete attention item, not only to the operation in
general.

This makes future dashboards and involvement-level behavior much cleaner.

## Autonomy Model

The operator should adapt its involvement behavior to context.

### Unattended

The operator should continue where policy allows, defer blocked branches, and avoid waking the
user except for hard-stop conditions.

### Auto

This should likely be the default.

The operator should ask the user when it encounters a conceptually novel situation that it
cannot resolve confidently from:

- current objective and harness
- existing project policy
- prior accepted decisions
- or deterministic runtime rules

### Collaborative and approval-heavy

The operator should ask more readily before major strategic or risky decisions.

This model should be explicit and inspectable, not hidden in prompt wording.

## Delivery Surfaces

### CLI remains core

The CLI should stay a primary product surface, not a fallback.

It should support:

- live runs,
- command submission,
- inspection,
- tracing,
- session views,
- attention views,
- and profile-driven launches.

### TUI becomes a serious product surface

The future TUI should provide:

- fleet dashboard
- focused operation detail
- attention queue
- active session view
- live command palette
- and fast drill-down into condensed agent logs

Its job is operational monitoring and intervention, not raw-log dumping.

### Forensic surfaces stay separate

The project should preserve a split between:

- live operational surfaces
- and forensic/debug surfaces

Examples:

- report
- trace
- raw agent logs
- condensed Codex log view

## Project Model

Project profiles should become the main ergonomic entrypoint for repeated work.

A profile should define stable defaults for a project, but not hide runtime truth.

Likely future commands:

- `operator project list`
- `operator project inspect <name>`
- `operator run --project <name> "objective..."`

Every run should still record:

- which profile it used,
- which values were overridden,
- and the fully resolved runtime configuration.

## Non-Goals

Even in v2, `operator` should not become:

- a generic visual workflow builder,
- a hidden autonomous daemon with opaque behavior,
- a replacement for every agent SDK,
- a full distributed scheduler,
- or a giant framework-heavy orchestration platform.

The goal remains narrower:

- one transparent control plane for real agent work
- with explicit human steering
- over long-lived objectives

## Early v2 Success Criteria

The first meaningful v2 tranche should demonstrate:

1. a live command inbox for running operations
2. explicit pause / resume / stop semantics
3. typed attention requests and answer routing
4. an inspectable involvement-level model
5. one lightweight project profile system
6. one honest live monitoring surface built on runtime truth

## Directional Bias

If future choices conflict, the bias should be toward preserving:

- the operator loop as the center,
- LLM-first orchestration with deterministic control truth,
- protocol-oriented adapters,
- file-backed transparency,
- and delivery surfaces that reflect the real runtime rather than invent it.
