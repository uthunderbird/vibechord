# Operator Runtime And True Harness Brainstorm Ideas

## Status

Brainstorm only. Not a source-of-truth architecture document.

## Grounding

The current vision already treats `operator` as a control plane rather than another agent shell.
The next large step is to make that control plane feel like a real harness:

- the operator stays alive for long-lived work,
- manages multiple attached agent resources,
- can be interrupted and steered by the user in real time,
- and remains recoverable through persisted state.

## Core Thesis

The right target is not "a daemon first" and not "resume-first recovery UX".
It is:

- a true long-lived harness as the default runtime experience,
- on top of a persisted, resumable control plane.

That means:

- attached execution is the primary user story,
- persisted state remains authoritative,
- resumable mode remains recovery and automation substrate,
- and the operator becomes a live supervisor for many agent threads, not just a loop that occasionally calls one agent.

## Main Design Axes

### 1. Operation control vs agent control

The operator needs distinct control surfaces for:

- the whole operation,
- the scheduler,
- each task,
- each session,
- each currently running agent turn.

Those are not the same.

Examples:

- pause the operator scheduler but let a currently running agent finish
- stop a single agent turn without cancelling the whole objective
- pause all outbound agent work but continue allowing user messages and inspection
- hard-stop the whole operation immediately

### 2. Attached control loop vs background execution

The operator should have one canonical control loop, but multiple execution modes underneath:

- attached foreground turns for normal interactive work
- background-supervised turns for long blocking work or detached recovery

The harness should choose these explicitly rather than leaking mode complexity into user-facing semantics.

### 3. User messages as first-class runtime events

Messages from the user should not be treated as ad hoc CLI overrides.
They should be first-class control-plane events that can:

- change objective text,
- update harness instructions,
- modify constraints,
- answer a pending operator question,
- provide a one-off directive,
- or pause/cancel specific execution paths.

### 4. Scheduler authority

The operator brain may still propose what matters next, but the deterministic runtime must own:

- pause state,
- stop state,
- branch deferral,
- concurrency ceilings,
- interrupt routing,
- and whether a user intervention applies globally or locally.

## Proposed Runtime Direction

### Control primitives

The harness likely needs an explicit control model like:

- `OperationState`
- `SchedulerState`
- `TaskState`
- `SessionRecord`
- `RunControlState`
- `UserIntervention`

Where `RunControlState` can hold:

- `mode`: attached | resumable
- `pause_state`: running | paused | draining | stopping
- `attention_state`: normal | needs_user | degraded
- `intervention_queue`

### User intervention model

User input should enter through a typed queue, not direct mutation calls.
Candidate event kinds:

- `user.message`
- `user.answer`
- `user.pause_requested`
- `user.resume_requested`
- `user.stop_requested`
- `user.stop_agent_requested`
- `user.constraint_patch`
- `user.goal_patch`
- `user.harness_patch`

The operator loop then consumes these events, records them, and replans.

### Pause semantics

The harness needs at least two pause modes:

- `scheduler_pause`
  - stop issuing new decisions and new agent work
  - allow in-flight turns to finish or be cancelled deliberately
- `full_pause`
  - no new scheduling
  - no agent continuation
  - only inspection and explicit control actions

### Stop semantics

There should be separate actions for:

- stop one agent turn
- stop one session
- cancel one task branch
- stop all agent execution
- cancel the whole operation

Without this split, the harness will stay too coarse for real long-lived work.

## Risks And Tradeoffs

### Risk: building a workflow engine by accident

If task, control, attention, and intervention entities multiply without discipline, the operator can drift into a generic orchestration platform.

Guardrail:

- keep the operator loop central
- keep the protocol surface small
- add entities only when they change runtime authority

### Risk: mixing live UX with runtime authority

The TUI should not become the source of truth.
The control plane must remain independent from any one renderer.

### Risk: pause semantics become vague

"Pause" often means different things:

- stop scheduling
- stop polling
- stop sending messages
- cancel running tools

These must be explicit in the model.

### Risk: intervention flood

If every user message triggers a full replan, the system can thrash.
The runtime needs batching/debouncing rules and clear "takes effect now vs next cycle" semantics.

## Candidate ADR Topics

1. Operator control-state model for pause, stop, and intervention handling
2. User-intervention event schema and runtime consumption rules
3. Scheduler authority boundaries for whole-operation vs per-agent control
4. Attached vs supervised execution-mode selection inside the true harness
5. Operation attention-state model for human-required vs self-resolvable situations

## Open Questions

- When should the operator automatically defer one blocked branch and continue another?
- Should pause apply immediately to running agent turns or only to new scheduling?
- Do user one-off directives become durable policy by default, or only after explicit approval?
- How much of this belongs to one operation vs one project?
