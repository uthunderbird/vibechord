# True Harness Control Plane Consolidation Brainstorm Ideas

## Status

Brainstorm only. Not architecture truth.

## Scope Of This Consolidation

This note consolidates four narrower brainstorm tracks:

- [operation-command-inbox-and-live-human-command-model-brainstorm-ideas.md](/Users/thunderbird/Projects/operator/design/brainstorm/operation-command-inbox-and-live-human-command-model-brainstorm-ideas.md)
- [deterministic-vs-brain-mediated-live-command-handling-brainstorm-ideas.md](/Users/thunderbird/Projects/operator/design/brainstorm/deterministic-vs-brain-mediated-live-command-handling-brainstorm-ideas.md)
- [pause-semantics-during-active-attached-turns-brainstorm-ideas.md](/Users/thunderbird/Projects/operator/design/brainstorm/pause-semantics-during-active-attached-turns-brainstorm-ideas.md)
- [attention-request-model-and-answer-routing-brainstorm-ideas.md](/Users/thunderbird/Projects/operator/design/brainstorm/attention-request-model-and-answer-routing-brainstorm-ideas.md)

The goal is to clarify the next coherent architectural tranche for making `operator` a true
harness.

## Starting Point

The current runtime already has useful foundations:

- attached long-lived `run`
- resumable recovery machinery
- task/session/objective state
- wakeup reconciliation
- traceability surfaces
- and scoped cancellation entrypoints

But it still lacks a first-class live control model.

That is the key missing substrate between:

- today's operator loop
- and the desired future where the operator is a transparent, steerable harness

## Consolidated Thesis

The next major control-plane milestone should be:

- a live `OperationCommandInbox`
- plus a small `AttentionRequest` model
- plus explicit scheduler-state semantics for attached runs

This is the minimal honest substrate for:

- human intervention during live runs
- pause/resume/stop semantics
- human answers to operator questions
- involvement-level behavior
- and a future TUI that is a projection of real runtime truth

## What The System Needs First

### 1. Typed command inbox

The operator must accept durable human commands while running.

These commands should be explicit control-plane records, not:

- ad hoc prompt edits
- CLI restarts
- or freeform text smeared into logs

### 2. Deterministic command handling boundary

The runtime must distinguish:

- command validation and acceptance
- from brain-mediated replanning after accepted commands

Without this split, the harness will not be trustworthy.

### 3. Scheduler-state model for attached runs

The operator needs a scheduler-facing state separate from coarse `OperationStatus`.

This is required to represent:

- `active`
- `pause_requested`
- `paused`
- `draining`

without abusing `BLOCKED`.

### 4. Typed attention queue

The operator must be able to say:

- what human attention is needed
- whether it is blocking
- what answer is being requested

and then accept an answer routed to that exact attention item.

## Strongest Architectural Rules

### Rule 1: TUI comes after control semantics

The next TUI should be built on top of:

- persisted command truth
- scheduler state
- attention items
- and explicit command outcomes

Not the other way around.

### Rule 2: The brain does not own command acceptance

The brain may replan after a command is accepted.

It should not decide:

- whether a command exists
- whether it targets the right thing
- whether pause took effect
- or whether an explicit human answer resolved a specific attention request

### Rule 3: Pause is not cancel

`pause_operator` should not be overloaded to mean:

- stop operation
- cancel current session
- interrupt current turn

Those are separate actions with separate semantics.

### Rule 4: Attention is not just blocked prose

`BLOCKED` may remain a top-level operation status, but it should be explainable through explicit
open attention items rather than only freeform summaries.

## Recommended V1 Semantics

### Command families worth doing first

- `pause_operator`
- `resume_operator`
- `stop_operation`
- `set_involvement_level`
- `patch_harness`
- `patch_objective`
- `patch_constraints`
- `inject_operator_message`
- `answer_attention_request`

### Command handling split

Strictly deterministic in v1:

- `pause_operator`
- `resume_operator`
- `stop_operation`
- `set_involvement_level`
- `patch_harness`
- `answer_attention_request`

Deterministic accept plus brain-mediated consequence:

- `patch_objective`
- `patch_constraints`
- `inject_operator_message`

Explicitly out of scope for v1:

- arbitrary branch surgery
- general `inject_agent_message`
- multi-session live reprioritization

## Recommended V1 Pause Model

The first honest attached-run pause should be:

- no active turn => immediate `paused`
- active attached turn => `pause_requested`
- once current turn yields => `paused`

If the user wants to interrupt the active turn directly, that should be a separate command:

- `stop_agent_turn`

This is a better contract than pretending we support transport-level suspension across all
adapters.

## Recommended V1 Attention Model

First attention taxonomy:

- `question`
- `approval_request`
- `policy_gap`
- `blocked_external_dependency`
- `novel_strategic_fork`

Each attention item should have:

- `attention_id`
- type
- severity
- blocking flag
- question
- target scope
- status

And the human answer path should be:

- `answer_attention_request(attention_id=...)`

## How This Fits In The Existing Runtime

The new layer should sit beside current runtime truths:

- `OperationState`
- `FocusState`
- `pending_wakeups`
- `SessionRecord`
- `TaskState`

Likely additions:

- `scheduler_state`
- `open_attention_requests`
- `resolved_attention_requests`
- `pending_commands`
- `applied_commands`

The attached run loop should:

1. drain command inbox
2. apply deterministic command effects
3. drain or observe agent progress
4. surface attention requirements
5. replan only when needed

The critical attached-mode change is:

- command draining must happen during the active wait loop between `poll()` calls

Otherwise live intervention remains fake.

## Recommended ADR Tranche

This brainstorm points to one coherent ADR tranche rather than a random list:

1. `operation command inbox and command envelope`
2. `deterministic command reducer vs brain-mediated replanning boundary`
3. `scheduler state model and pause semantics for attached runs`
4. `attention request taxonomy and answer routing`

These four ADRs together would define the first real control plane for true harness behavior.

## Recommended Implementation Order

### Phase 1

Introduce:

- `OperationCommand`
- `OperationCommandInbox`
- command submission and inspection surfaces

No TUI yet.

### Phase 2

Add:

- scheduler state
- `pause_requested`
- `paused`
- command draining during attached wait

### Phase 3

Add:

- `AttentionRequest`
- answer routing
- blocked-by-attention semantics

### Phase 4

Add:

- involvement-level behavior on top of typed attention and commands

### Phase 5

Only then build:

- a serious live TUI/dashboard

Because by then the UI will have a real substrate to project.

## What This Deliberately Does Not Solve Yet

This tranche should not try to solve:

- full branch-aware scheduler semantics
- rich project policy storage
- multi-operation TUI layout
- full project-profile schema
- transport-level pause/resume across all adapters

Those can come later.

## Working Conclusion

The true-harness control plane should begin with:

- typed live commands
- deterministic command handling
- explicit attached-run pause semantics
- and typed attention requests

That is the smallest coherent package that moves `operator` from:

- "a good long-lived operator loop"

toward:

- "a transparent, steerable harness for long-running agent work"
