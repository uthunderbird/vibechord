# Pause Semantics During Active Attached Turns Brainstorm Ideas

## Status

Brainstorm only. Not architecture truth.

## Why This Topic Matters

If the operator is supposed to feel like a true harness, the user must be able to pause it
honestly while an attached run is in progress.

Right now attached mode directly awaits one active agent turn.
That is good for simplicity, but it creates a hard question:

- what does `pause` mean while the operator is already inside the active turn wait loop?

This is the first real interaction boundary for a live harness.

## Grounding In Current Runtime

The current attached path in [service.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/service.py):

- starts or continues one agent turn
- records the turn as started
- enters `_collect_attached_turn(...)`
- loops:
  - `adapter.poll(session)`
  - persist progress
  - `sleep(1)`
  - continue until terminal

Important current fact:

- attached waiting does not drain any human command inbox while it is polling

So today there is no real place where:

- `pause_operator`
- `stop_agent_turn`
- or `inject_operator_message`

could be consumed coherently during the active wait.

That is the core seam.

## Core Thesis

`pause_operator` during an active attached turn should not mean one vague thing.

There are at least three distinct pause semantics:

1. `scheduler_pause`
   - stop starting new work after the current turn yields
2. `interrupting_pause`
   - actively stop or cancel the current agent turn and then enter paused state
3. `soft_pause_request`
   - record intent to pause, surface it immediately, and apply it at the next safe checkpoint

The first implementation should not pretend these are the same.

## Recommended V1 Meaning

For v1, the cleanest definition is:

- `pause_operator` during an active attached turn becomes `soft_pause_request`
- the operator acknowledges the pause immediately
- the scheduler stops launching new work as soon as the current attached turn yields
- the runtime does not guarantee interruption of the active turn in v1

Why this is the safest first step:

- current adapters do not all have symmetrical mid-turn pause semantics
- attached mode is currently built around one direct wait loop
- forcing immediate interruption semantics too early will create adapter-specific drift

## Strong Distinction

`pause_operator` is not the same as:

- `stop_agent_turn`
- `stop_session`
- `stop_operation`

Those should remain separate commands.

If pause is overloaded to mean "interrupt whatever is running right now", it will quickly become
an unreliable euphemism for cancel.

## Candidate State Model

The runtime likely needs an explicit scheduler state separate from `OperationStatus`.

Candidate values:

- `active`
- `pause_requested`
- `paused`
- `draining`
- `blocked`
- `stopped`

Why:

- `OperationStatus` is about coarse operation truth
- scheduler state is about what the harness is currently allowed to do next

This avoids abusing `BLOCKED` for a user-requested pause.

## Candidate V1 Behavior

### Case 1: pause with no active turn

Deterministic:

- transition scheduler state to `paused`
- accept no new work until `resume_operator`
- surface that state in `inspect`, `list`, and future TUI

### Case 2: pause during active attached turn

Deterministic:

- transition scheduler state to `pause_requested`
- record command provenance
- surface `"pause requested; waiting for current attached turn to yield"`

When the turn yields:

- do not schedule another task or turn
- transition scheduler state to `paused`
- preserve latest result

### Case 3: resume from paused

Deterministic:

- transition scheduler state back to `active`
- continue normal scheduling loop

## Why Not Immediate Interrupt In V1

Immediate interrupt sounds attractive but carries real complexity:

- some adapters support cancel better than others
- some turns may be inside external RPC/ACP states
- the operator may receive partial output or ambiguous terminal state
- "pause" would become transport-sensitive instead of harness-level

That is a poor first meaning for a top-level human control command.

## When Interrupt Belongs

Immediate interruption should likely be a different command:

- `stop_agent_turn`

That command can:

- call adapter `cancel(...)`
- reconcile partial output if any
- mark the active turn as cancelled or incomplete
- and then leave the scheduler paused, active, or blocked according to policy

This keeps pause semantics cleaner.

## Required Runtime Changes

To make even soft pause real, attached mode probably needs one structural change:

- `_collect_attached_turn(...)` must periodically drain control commands between polls

Not to replan fully inside that loop, but at least to notice:

- pause request
- stop operation
- stop active turn

That suggests a pattern like:

1. poll agent
2. persist progress
3. drain control inbox
4. apply deterministic command transitions
5. decide whether:
   - continue polling
   - cancel active turn
   - or stop scheduling after yield

This is the minimal live-control seam.

## Human-Facing Behavior

The CLI/TUI should distinguish visibly:

- `paused`
- `pause requested`
- `stopping active turn`
- `waiting for current turn to yield`

Without this, users will hit pause and have no idea whether:

- the operator heard them
- the agent is still running
- or the system ignored the command

## Traceability Requirements

The runtime should emit distinct trace records for:

- pause requested
- pause applied
- resume applied
- stop-agent-turn requested
- stop-agent-turn completed

The brief layer should also reflect:

- whether the operator is paused because the human asked
- or blocked because of some operational issue

Those are not the same thing.

## Risks And Tradeoffs

### Positive

- gives live harness behavior a clear and honest first semantics
- avoids overclaiming true mid-turn suspension
- preserves adapter independence for v1

### Risks

- users may expect pause to be immediate
- soft pause may feel weak if turns are long-running
- attached turns that never yield still need a stronger escape hatch

## Design Warning

Do not call the first version "pause" if the system actually means "pause after current turn."

Either:

- name it clearly in UI copy
- or show explicit state like `pause requested`

The semantics must be discoverable.

## Recommended V1 Contract

### Deterministic

- `pause_operator`
  - no active turn => `paused`
  - active attached turn => `pause_requested`
- `resume_operator`
  - `paused` or `pause_requested` => `active`
- `stop_operation`
  - terminal stop request
- `stop_agent_turn`
  - explicit interrupt command, separate from pause

### Not promised in v1

- true transport-level pause of an active external agent
- arbitrary suspension and resume of in-flight ACP prompts

## Recommended ADR Topics

1. `scheduler state model for live attached runs`
2. `pause request vs pause applied semantics`
3. `stop_agent_turn contract in attached mode`
4. `control-inbox draining during active attached wait loops`
5. `user-visible state copy for pause and stop transitions`

## Working Conclusion

The first honest pause model for attached runs is:

- soft pause by default
- explicit interrupt through a separate command
- and an attached wait loop that can drain control commands between polls

That is strong enough to make the harness feel live without promising impossible mid-turn
suspension semantics too early.
