# True Harness Runtime Brainstorm Ideas

## Status

Brainstorm only. Not architecture truth.

## Context

`operator` already has:

- an attached long-lived `run` as the preferred runtime surface,
- resumable recovery machinery,
- agent/session/task/objective state,
- and CLI inspection surfaces.

The next large step is a true harness runtime where the operator is not just a loop that calls one agent, but a long-lived control process that can:

- manage several agent threads over time,
- accept human interventions while running,
- pause or redirect work,
- and keep making progress under an explicit autonomy policy.

## Core Thesis

The true harness should be modeled as a long-lived control plane with three kinds of inbound signals:

1. agent events,
2. human control messages,
3. deterministic timers and guardrail wakeups.

The operator loop should no longer treat the next agent turn as its only input. It should instead arbitrate among these inbound signals while preserving a single authoritative operation state.

## Main Design Axes

### 1. Scheduler vs command surface

Separate:

- the scheduling brain that decides what work should happen next,
- from the command/control surface that can pause, stop, redirect, or inject new instructions.

This prevents user interventions from being treated like ordinary agent results.

### 2. Operation state vs live runtime state

Keep persisted `OperationState` authoritative, but introduce an explicit live runtime layer for:

- active event subscriptions,
- in-flight control intents,
- pause mode,
- and pending user messages.

Persist only what is needed for recovery and truth, not every transport detail.

### 3. Session control vs operator control

Distinguish:

- stop one agent turn,
- stop or cancel one session,
- pause the operator scheduler,
- stop the whole operation.

These are different actions and should not share one overloaded "cancel" path.

### 4. Human message injection

User messages to the running operator should be first-class control events, not hacks through edited prompts or restarts.

Examples:

- adjust objective,
- add or remove constraints,
- answer a question,
- issue a tactical instruction to one agent,
- or approve a policy.

### 5. Attention management

The operator should have an explicit notion of when it may continue autonomously and when it must surface a blocker.

That should be a control-plane concern, not left to incidental prompt wording.

## Likely Architecture Direction

### Preferred shape

Add a dedicated control bus or inbox beside the existing event/wakeup path.

Suggested event families:

- `agent_event`
- `user_message`
- `control_command`
- `policy_decision`
- `attention_alert`
- `timer_wakeup`

Suggested control commands:

- `pause_operator`
- `resume_operator`
- `stop_operation`
- `stop_agent_turn`
- `stop_session`
- `inject_operator_message`
- `inject_agent_message`
- `update_constraints`
- `update_objective`

### Runtime consequences

The long-lived operator process should become an event-driven loop:

1. drain inbound control and wakeup sources,
2. reconcile state,
3. decide whether to schedule new work,
4. observe active work,
5. emit live summaries and attention alerts,
6. persist checkpoints.

### State consequences

The runtime needs first-class notions of:

- operator run mode,
- scheduler state: active, paused, draining, blocked, stopped,
- pending user messages,
- pending control commands,
- active attention requirement,
- and target entity for a control action.

## Risks And Tradeoffs

### Positive

- matches the real product mental model better than `resume`-driven control,
- supports long-running work without awkward restarts,
- creates a clean place for pause/stop/message semantics,
- and makes human intervention explicit and auditable.

### Risks

- easy to overbuild into a workflow engine,
- possible duplication between wakeup inbox and new control bus,
- higher concurrency complexity if multiple active agent turns arrive too early,
- and more chances for state drift if control commands are not idempotent.

### Design warning

Do not make the operator itself a hidden opaque daemon first.
The control plane should stay inspectable and CLI-visible from day one.

## Recommended ADR Topics

1. `operator command and control event model`
2. `pause, stop, and cancel semantics across operator/session/turn scopes`
3. `user message injection as a first-class runtime surface`
4. `live scheduler state model for long-lived operator runs`
5. `attention and escalation policy contract`
