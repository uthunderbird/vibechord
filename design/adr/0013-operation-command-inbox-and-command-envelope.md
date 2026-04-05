# ADR 0013: Operation Command Inbox And Command Envelope

## Status

Accepted

## Context

`operator` is moving toward a true harness model where a running operation is not only:

- a loop that decides the next action,
- invokes an agent,
- evaluates the result,
- and repeats.

It is also becoming a live control surface that the human should be able to steer while it is
running.

The current runtime already has several control-plane foundations:

- attached long-lived `run`
- resumable recovery
- persistent `OperationState`
- `FocusState`
- wakeup handling
- session and task records
- and scoped cancellation entrypoints

But it still lacks a first-class model for live human intervention.

Today, a user intervention tends to collapse into one of a few weak shapes:

- rerunning a CLI command,
- editing prompt-like inputs out of band,
- or relying on coarse stop or blocked behavior.

That is not sufficient for a true harness.

The operator needs a durable, inspectable, restart-safe way to receive live human commands such
as:

- pause the operator
- resume it
- stop the operation
- patch the harness
- patch the objective
- answer an open question
- or send a message to the operator itself

Without a first-class command surface:

- future TUI work will be mostly cosmetic,
- pause and intervention semantics will drift,
- and human control will remain less reliable than the rest of the persisted control plane.

## Decision

`operator` will introduce a first-class `OperationCommandInbox` and an explicit typed command
envelope for live human-to-operator intervention.

The core decision is:

- live user interventions should be modeled as durable control-plane records addressed to one
  operation
- not as ad hoc prompt edits, transient CLI behavior, or raw freeform text injected into the
  planning context

The initial model should include:

```python
class OperationCommand(BaseModel):
    command_id: str
    operation_id: str
    command_type: OperationCommandType
    target_scope: CommandTargetScope
    target_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    submitted_by: str = "user"
    submitted_at: datetime
    status: CommandStatus = CommandStatus.PENDING
    rejection_reason: str | None = None
    applied_at: datetime | None = None
```

Important semantic rules:

- the command envelope is deterministic
- targeting, validation, idempotency, and lifecycle state are runtime concerns
- the operator brain may interpret the consequences of some accepted commands, but it does not
  own command existence, targeting, or acceptance

The command inbox should be:

- durable
- restart-safe
- inspectable from CLI surfaces
- and consumable by the attached live runtime

The initial implementation should bias toward file-backed transparency rather than hidden daemon
RPC or opaque transport channels.

The command system should sit beside existing runtime substrates such as:

- wakeup inbox
- event sink
- trace store
- persisted operation state

It should not be represented merely as more text in the brain prompt.

## Non-Goals

This ADR does not by itself define:

- the full deterministic vs brain-mediated handling boundary for every command type
- final pause semantics during active attached turns
- the final attention-request taxonomy
- the final involvement-level model
- or the final TUI delivery shape

Those are follow-up decisions and should be captured in later ADRs.

This ADR also does not guarantee that v1 will support every imaginable live command.

In particular, it does not by itself promise support for:

- arbitrary branch surgery
- general user-to-agent direct message forwarding
- transport-level suspension of in-flight external agent turns

## Minimum Requirements

The stronger guarantee of this ADR depends on several minimum rules:

- every command must target one operation
- command shape and target scope must be validated deterministically
- invalid target or invalid command shape must be rejected explicitly
- duplicate command ids must be idempotent
- command lifecycle state must be inspectable
- attached live runs must be able to consume pending commands without requiring a fresh process
  start
- command provenance must be visible in inspection and trace surfaces

## Initial Scope Model

The runtime should be able to distinguish at least these target scopes:

- `operation`
- `task`
- `branch`
- `session`
- `agent_turn`
- `attention_request`

The initial implementation does not need to support rich behavior for every scope.
But the scope model should be explicit from the start so that future commands are not forced into
one overloaded target shape.

## Initial Command Families

The long-term command family likely includes:

### Operation-level control

- `pause_operator`
- `resume_operator`
- `stop_operation`
- `drain_and_stop_operation`
- `set_involvement_level`

### Objective and policy updates

- `patch_objective`
- `patch_harness`
- `patch_success_criteria`
- `patch_constraints`
- `record_policy_decision`
- `revoke_policy_decision`

### Human answers and context

- `answer_attention_request`
- `add_note`
- `attach_context`
- `approve_route`
- `reject_route`

### Agent and session control

- `stop_agent_turn`
- `stop_session`
- `pause_session_branch`
- `inject_agent_message`
- `request_agent_status_refresh`

### Task and branch control

- `defer_task_branch`
- `cancel_task_branch`
- `reprioritize_task`
- `force_next_step`

The first implementation may support only a strict subset of these, but it should do so within
this explicit command-envelope model.

## Command Lifecycle

The expected command flow is:

1. user submits command
2. runtime validates the command envelope and target
3. command is recorded durably
4. runtime or operator loop consumes the command
5. deterministic command effects are applied where appropriate
6. replanning happens if the accepted command changes control context
7. command becomes `applied`, `rejected`, `superseded`, or another explicit terminal lifecycle
   state

This means the runtime must distinguish:

- receipt of a command
- acceptance or rejection
- and downstream behavioral consequences

Those are related, but they are not the same event.

## Alternatives Considered

### Option A: Keep live intervention as ad hoc CLI behavior

Rejected because:

- it is not restart-safe,
- it weakens provenance,
- it makes TUI or live monitoring semantics fragile,
- and it leaves the control plane less explicit than the rest of the runtime.

### Option B: Represent user interventions as freeform operator messages only

Rejected because:

- it blurs administrative control with open-text guidance,
- it forces deterministic control semantics into prompt interpretation,
- and it makes targeting and acknowledgement too ambiguous.

### Option C: Introduce a typed command inbox with explicit envelope and lifecycle

Accepted because:

- it matches the true-harness direction,
- it keeps control-plane truth durable and inspectable,
- it provides a clean substrate for future pause, attention, and TUI work,
- and it preserves the architectural split between deterministic runtime control and LLM-driven
  orchestration.

## Consequences

### Positive

- Live human intervention becomes a first-class runtime capability.
- The control plane remains inspectable and restart-safe.
- Future TUI work can reuse real runtime truth instead of inventing hidden semantics.
- Command provenance and acknowledgement become explicit.
- The operator can evolve toward a true harness without abandoning persisted transparency.

### Negative

- The domain model and runtime state grow more complex.
- A new inbox and command lifecycle must be persisted and surfaced consistently.
- The project will need follow-up ADRs to define pause, attention, and command-handling
  semantics in detail.
- There is a risk of overbuilding if too many command types are supported too early.

### Follow-Up Implications

- The runtime will likely need an `OperationCommandType`, `CommandTargetScope`, and
  `CommandStatus` model.
- Attached live runs must be able to drain command inbox entries while the operator is already
  active.
- `inspect`, `trace`, and future live monitoring surfaces should display pending and applied
  commands.
- Follow-up ADRs should define:
  - deterministic command reducer vs brain-mediated replanning boundary
  - scheduler-state and pause semantics
  - attention-request taxonomy and answer routing
  - involvement-level behavior
