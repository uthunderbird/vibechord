# Operation Command Inbox And Live Human Command Model Brainstorm Ideas

## Status

Brainstorm only. Not architecture truth.

## Why This Topic Comes First

The current runtime already has meaningful control-plane pieces:

- attached long-lived `run`
- resumable recovery
- `OperationState`
- `FocusState`
- wakeups
- session and task records
- scoped cancellation entrypoints

But it still lacks the most important ingredient for a true harness:

- a first-class way for the human to intervene while the operator is running

Without that, future TUI work would mostly be a nicer viewer over the same limited runtime.

## Core Thesis

The next real step toward a true harness is a typed `OperationCommandInbox`.

The operator should not treat a human interruption as:

- a restarted CLI invocation,
- an edited prompt,
- or a special-case imperative escape hatch.

It should treat it as a durable control-plane event addressed to a running operation.

## Main Design Goal

Introduce a first-class human-to-operator command model that is:

- durable
- inspectable
- restart-safe
- scope-aware
- and deterministic at the envelope level

The operator brain may interpret the semantic implications of some commands, but it should not
be responsible for deciding whether the command exists, whether it was accepted, or what entity
it targets.

## Strongest Design Principle

Separate:

- `command envelope`
  - what the user asked
  - what entity it targets
  - whether it was accepted, rejected, queued, or applied
- from `brain interpretation`
  - how the operator replans after accepting that command

This is the same control-plane split that already exists between:

- deterministic runtime guardrails
- and LLM-driven orchestration

## Candidate Command Families

### 1. Operation-level control

- `pause_operator`
- `resume_operator`
- `stop_operation`
- `drain_and_stop_operation`
- `set_involvement_level`

These affect the harness as a whole.

### 2. Objective and policy updates

- `patch_objective`
- `patch_harness`
- `patch_success_criteria`
- `patch_constraints`
- `record_policy_decision`
- `revoke_policy_decision`

These change the control context under which the operator works.

### 3. Human answers and context

- `answer_attention_request`
- `add_note`
- `attach_context`
- `approve_route`
- `reject_route`

These resolve open questions without pretending they are ordinary goal edits.

### 4. Agent and session control

- `stop_agent_turn`
- `stop_session`
- `pause_session_branch`
- `inject_agent_message`
- `request_agent_status_refresh`

These are narrower than operation-wide pause/stop.

### 5. Task and branch control

- `defer_task_branch`
- `cancel_task_branch`
- `reprioritize_task`
- `force_next_step`

These operate at the planner/scheduler layer rather than the agent transport layer.

## Candidate Command Envelope

The runtime likely needs an explicit model like:

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

Important point:
- the envelope is deterministic
- `payload` should stay small and typed per command family

## Delivery Semantics

The command inbox should be:

- durable
- append-only or append-plus-status
- visible in CLI inspection surfaces
- and consumable by the attached long-lived operator loop

That suggests:

- one file-backed inbox per operation at first
- later maybe a unified command bus

The first implementation should bias toward file-backed transparency, not hidden sockets or
opaque daemon RPC.

## Expected Command Lifecycle

1. user submits command
2. runtime validates target scope and shape
3. command is recorded as `pending`
4. operator loop consumes it
5. runtime applies deterministic state transition if needed
6. operator replans if the command changes control context
7. command becomes `applied`, `rejected`, or `superseded`

## Minimum Acceptance Rules

Some rules should stay deterministic:

- invalid target => reject
- operation already terminal => reject most control commands
- duplicate command id => idempotent no-op
- `resume_operator` on non-paused run => reject or no-op explicitly
- `stop_agent_turn` with no active turn => reject explicitly
- `patch_objective` should mark relevant planning state stale

This is not brain work.

## Relationship To Existing Runtime Concepts

This topic should layer onto, not replace:

- `OperationState`
- `FocusState`
- `SessionRecord`
- `TaskState`
- `pending_wakeups`
- background wakeup reconciliation

Likely additions:

- `pending_commands`
- `applied_commands`
- `operator_scheduler_state`
- `attention_requests`

The command inbox should sit beside:

- wakeup inbox
- event sink
- trace store

Not inside the brain prompt as ad hoc prose.

## Command Scope Model

At minimum, the system should distinguish:

- `operation`
- `task`
- `branch`
- `session`
- `agent_turn`
- `attention_request`

If this scope model is not explicit, pause/stop/inject semantics will become muddy fast.

## User Message Model

Not every human intervention should be a "chat message."

There are at least three kinds:

### Administrative commands

- pause
- stop
- resume
- set involvement

These should bypass the brain except for downstream replanning.

### Structured context updates

- patch objective
- patch harness
- patch constraints
- answer a specific open question

These should update persisted control truth and then trigger replanning.

### Open-text operator messages

- note
- strategic guidance
- freeform clarification

These may need brain interpretation, but should still arrive through the same inbox.

## The Hardest Boundary

The most dangerous ambiguity is between:

- `message to operator`
- and `message to agent`

These must remain distinct.

The human should be able to say:

- "Operator, change your strategy."
- or
- "Tell the current agent to do X next."

Those are different commands with different provenance and safety implications.

## Attention Model Link

This inbox is tightly coupled to human-attention semantics.

The operator should ask for attention via typed objects, not only prose:

- `question`
- `approval_request`
- `policy_gap`
- `conflicting_evidence`
- `blocked_external_dependency`
- `novel_strategic_fork`

Then the human answer can target one explicit attention request.

That gives future TUI work a stable substrate:

- attention queue
- answer form
- resolution state

## Risks And Tradeoffs

### Positive

- makes the operator feel live and steerable
- keeps human intervention auditable
- creates a real substrate for pause/stop/message UI
- preserves restart-safe control semantics

### Risks

- overbuilding into a generic workflow/event framework
- duplicating semantics between wakeups and commands
- inventing too many command types too early
- allowing freeform text to bypass deterministic validation

### Design warning

The first slice should not try to solve every future interactive feature.

It only needs to make one thing real:

- a running operator can receive durable typed commands and respond coherently

## Recommended First Slice

The smallest strong milestone looks like:

1. file-backed `OperationCommandInbox`
2. command types:
   - `pause_operator`
   - `resume_operator`
   - `stop_operation`
   - `patch_harness`
   - `answer_attention_request`
   - `inject_operator_message`
3. command status model:
   - `pending`
   - `applied`
   - `rejected`
4. attached run loop drains commands between scheduling steps and during waits
5. CLI commands:
   - `operator command <operation-id> ...`
   - `operator pause <operation-id>`
   - `operator resume-live <operation-id>`
   - `operator message <operation-id> --to operator ...`
6. `inspect` and `trace` show pending/applied commands

That is enough to make future pause/attention/TUI work honest.

## Recommended ADR Topics

1. `operation command inbox and envelope`
2. `live command scope and target semantics`
3. `operator scheduler state and pause semantics`
4. `attention request model and human answer routing`
5. `user-to-operator vs user-to-agent message boundary`

## Recommended Questions For The Next Narrow Swarm

1. Which commands must be deterministic vs brain-mediated?
2. Should command application mutate `OperationState` directly or flow through a dedicated reducer?
3. How should attached mode drain commands while blocked on one active agent turn?
4. What is the smallest honest command set for v1?
5. How should command provenance appear in briefs, reports, and traceability?
