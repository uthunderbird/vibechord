# ADR 0015: Scheduler State And Pause Semantics For Attached Runs

## Status

Accepted

## Context

[ADR 0013](/Users/thunderbird/Projects/operator/design/adr/0013-operation-command-inbox-and-command-envelope.md)
introduces a first-class command inbox for live human intervention.

[ADR 0014](/Users/thunderbird/Projects/operator/design/adr/0014-deterministic-command-reducer-vs-brain-mediated-replanning.md)
separates deterministic command control from brain-mediated replanning.

Those two decisions create a more specific runtime question:

- what should `pause` mean while an attached live run is already inside an active agent turn?

This matters because the current attached runtime is built around a direct wait loop:

- start or continue one agent turn
- enter `_collect_attached_turn(...)`
- repeatedly `poll()`
- persist progress
- sleep
- continue until the turn yields a terminal or waiting-input result

This model is deliberately simple and works well for attached runs.

But it creates a control-plane seam:

- there is currently no first-class pause model for the scheduler
- and attached waiting does not yet drain live user commands while the poll loop is active

Without an explicit decision here, future live control risks becoming misleading in one of two
ways:

### Failure mode 1: pause is overclaimed

If `pause_operator` is described as immediate pause of live work, users may infer transport-level
suspension of the current external agent turn even though adapters do not provide a symmetric,
reliable mid-turn pause primitive.

### Failure mode 2: pause is vague

If `pause` is treated as a loose synonym for cancel or stop, then:

- pause becomes operationally blunt,
- live control semantics become harder to trust,
- and users cannot distinguish:
  - pause after current turn
  - interrupt current turn
  - or stop the operation entirely

The runtime therefore needs:

- an explicit scheduler-state model
- and a narrow, honest first definition of pause semantics for attached runs

## Decision

`operator` will introduce an explicit scheduler-state model for attached live runs and define the
first attached pause semantics as a soft scheduler pause, not as implicit interruption of the
current agent turn.

### Core semantic rule

In v1 attached mode:

- `pause_operator` means "pause the scheduler"
- not "suspend the transport of the active external agent turn"

This implies:

- if there is no active attached turn, `pause_operator` can become effective immediately
- if there is an active attached turn, `pause_operator` becomes `pause_requested`
- once the current turn yields, the scheduler transitions to `paused`
- no new work is launched until `resume_operator`

If the user wants to interrupt the currently running agent turn directly, that is a separate
command:

- `stop_agent_turn`

Pause is therefore not a synonym for cancel.

## Scheduler State Model

The runtime should maintain a scheduler-facing state distinct from coarse `OperationStatus`.

The initial state set should include at least:

- `active`
- `pause_requested`
- `paused`
- `draining`

Additional values may appear later, but the first implementation should avoid overloading
`OperationStatus.BLOCKED` to represent a user-requested pause.

Important distinction:

- `OperationStatus` describes coarse operation truth
- scheduler state describes what the harness is currently allowed to do next

## Attached Pause Semantics

### Case 1: pause with no active turn

The reducer should:

- accept `pause_operator`
- transition scheduler state to `paused`
- prevent new work from being launched
- surface the paused condition in inspection and live monitoring surfaces

### Case 2: pause during active attached turn

The reducer should:

- accept `pause_operator`
- transition scheduler state to `pause_requested`
- record command provenance
- surface that the operator heard the pause but is waiting for the current turn to yield

When the current turn yields:

- the scheduler must not launch further work
- the scheduler transitions to `paused`
- the latest yielded result remains preserved

### Case 3: resume from paused

The reducer should:

- accept `resume_operator`
- transition scheduler state from `paused` or `pause_requested` to `active`
- allow the scheduling loop to continue normally

## Required Runtime Consequence

To make this pause model real, attached waiting must gain a live control seam.

Specifically:

- the attached wait loop must be able to drain pending control commands between `poll()` calls

That does not mean full replanning inside the wait loop.

It means the runtime must at least be able to notice and apply deterministic control commands
such as:

- `pause_operator`
- `resume_operator`
- `stop_operation`
- `stop_agent_turn`

without requiring the current active turn to finish first in all cases.

## Non-Goals

This ADR does not promise:

- true transport-level suspension of an in-flight external agent turn
- symmetric pause and resume support across all adapters
- final semantics for `stop_agent_turn`
- final scheduler-state semantics for every future branch-aware runtime case

Those remain separate decisions.

This ADR also does not define how pause should interact with rich multi-branch scheduling in the
future.

It is intentionally about the first honest attached-run control semantics.

## Minimum User-Facing Requirements

Live surfaces should distinguish clearly among:

- `paused`
- `pause requested`
- `waiting for current turn to yield`
- `stopping active turn`

Without this, users cannot tell whether the operator:

- accepted the pause
- ignored it
- or is still waiting on an active turn

The semantics must be visible rather than implied.

## Alternatives Considered

### Option A: Treat pause as immediate interruption of the active turn

Rejected because:

- current adapters do not provide a strong cross-adapter mid-turn pause primitive
- it would overclaim transport capabilities the runtime does not yet have
- and it would make top-level pause semantics adapter-sensitive too early

### Option B: Treat pause as equivalent to cancel or stop

Rejected because:

- it collapses distinct user intentions into one blunt action
- and makes live control less trustworthy

### Option C: Use an explicit scheduler state and soft pause semantics for attached runs

Accepted because:

- it is honest about current runtime capabilities
- preserves a clean distinction between pause and interruption
- and provides a real substrate for future TUI and command-inbox work

## Consequences

### Positive

- Attached live runs gain a clear and honest first pause model.
- The control plane remains adapter-agnostic in its top-level pause semantics.
- Future TUI and CLI surfaces can display pause state truthfully.
- The operator can become interruptible without overpromising unsupported transport semantics.

### Negative

- Users may expect pause to be more immediate than it really is.
- Long-running turns that do not yield promptly will still need a stronger escape hatch.
- The runtime must add scheduler-state plumbing and command-drain points inside the attached
  wait loop.

### Follow-Up Implications

- A follow-up ADR should define `stop_agent_turn` semantics in attached mode.
- The runtime will likely need a scheduler-state type on persisted operation truth.
- `inspect`, `list`, and future live monitoring surfaces should display scheduler state
  separately from operation status where useful.
- The implementation should expose `pause_requested` explicitly rather than silently describing
  it as already paused.
