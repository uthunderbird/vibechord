# Deterministic Vs Brain-Mediated Live Command Handling Brainstorm Ideas

## Status

Brainstorm only. Not architecture truth.

## Why This Boundary Matters

If the future command inbox lets the brain decide too much, the operator will become unreliable:

- user commands may be accepted inconsistently
- pause and stop semantics may drift
- message routing may become ambiguous
- and the live TUI will look interactive without being trustworthy

If the runtime makes everything deterministic, the operator becomes rigid and loses the point of
having an orchestration brain.

So the boundary needs to be explicit.

## Core Thesis

The command system should split into two layers:

### 1. Deterministic control layer

Responsible for:

- command validation
- targeting
- acceptance / rejection / idempotency
- direct runtime state transitions
- provenance
- and auditable command lifecycle

This behaves like a reducer or command handler, not like a planning model.

### 2. Brain-mediated orchestration layer

Responsible for:

- interpreting open-text guidance
- replanning after accepted changes
- deciding how to satisfy updated objective/harness/constraints
- deciding whether to message agents or switch routes

This is where operator intelligence still lives.

## Strong Rule

The brain may decide what work should happen next after a command is accepted.

It must not decide:

- whether a valid command exists
- whether a command targets the requested entity
- whether a pause or stop takes effect
- or whether an explicit user answer resolved the matching attention request

Those are control-plane truths.

## Commands That Should Stay Deterministic

These should be handled entirely by runtime rules, with no brain discretion needed for
acceptance or immediate effect.

### Administrative control

- `pause_operator`
- `resume_operator`
- `stop_operation`
- `stop_agent_turn`
- `stop_session`
- `set_involvement_level`

Why:
- they are direct user authority over the harness
- they correspond to concrete state transitions
- ambiguous LLM interpretation here would be unacceptable

### Structured state patching

- `patch_objective`
- `patch_harness`
- `patch_success_criteria`
- `patch_constraints`
- `answer_attention_request`

Why:
- the patch envelope and target should be validated deterministically
- applying the patch should mutate persisted truth directly
- replanning afterward can be brain-mediated

### Provenance and policy commands

- `record_policy_decision`
- `revoke_policy_decision`
- `approve_route`
- `reject_route`

Why:
- these are explicit human judgments
- the system should not infer or reinterpret them as if they were freeform chat

## Commands That Can Be Brain-Mediated After Acceptance

These commands should still have deterministic envelopes, but their operational consequence
requires interpretation or synthesis by the operator brain.

### Open-text operator guidance

- `inject_operator_message`
- `add_note`
- `attach_context`

Why:
- the runtime can store the message deterministically
- but the implications for planning are contextual

### Tactical route influence

- `force_next_step`
- `reprioritize_task`
- `defer_task_branch`

Why:
- the request itself is explicit
- but the scheduler may need the brain to evaluate how that change should affect current plans

### User-to-agent forwarding

- `inject_agent_message`

Why:
- acceptance and targeting should be deterministic
- but the operator may need to decide whether:
  - to send immediately
  - to defer until the active step finishes
  - to wrap it with control context
  - or to reject it due to constraints

This command is especially sensitive and may deserve its own ADR.

## Commands That Should Probably Be Rejected In V1

The first implementation should avoid pretending to support commands whose semantics are not yet
clean.

Strong candidates for explicit `not supported yet`:

- `pause_session_branch`
- `cancel_task_branch`
- `force_next_step` across many active branches
- arbitrary live rerouting of multiple active sessions

Why:
- current runtime is not yet branch-rich enough to make these safe
- pretending support here would create false confidence

## Suggested Runtime Flow

1. user submits command
2. command reducer validates shape and target
3. reducer applies direct state mutation if command is deterministic
4. command status becomes:
   - `applied`
   - `rejected`
   - or `accepted_pending_replan`
5. operator loop sees that control context changed
6. brain replans if needed
7. trace and brief surfaces explain both:
   - deterministic command effect
   - downstream planning consequence

## Command Outcome Classes

This likely needs explicit statuses richer than just `applied/rejected`.

Candidate statuses:

- `pending`
- `applied`
- `rejected`
- `accepted_pending_replan`
- `superseded`
- `expired`

Important distinction:
- a command may be valid and accepted
- but still require later planning work to become behaviorally visible

## Relation To Existing Runtime

Current code already hints at the right boundary:

- `cancel(...)` is deterministic
- `OperationStatus` transitions are explicit
- `FocusState` is explicit
- wakeup reconciliation is deterministic

The next step should preserve that style.

That suggests:
- command handling belongs beside wakeup reconciliation
- not inside `brain.decide_next_action(...)`

## The Hardest Edge Cases

### 1. Pause during an active attached turn

Deterministic part:
- mark scheduler paused
- stop launching new work

Brain-mediated part:
- none immediately

Open question:
- do we also attempt to cancel the active turn, or only pause after it yields?

### 2. Objective patch during active work

Deterministic part:
- update objective
- mark relevant planning state stale
- record command provenance

Brain-mediated part:
- decide whether to stop the active agent
- decide whether existing task graph still stands
- replan

### 3. Human answer to an attention request

Deterministic part:
- link answer to the addressed attention item
- mark that request resolved

Brain-mediated part:
- decide how the resolved answer changes next actions

### 4. Direct message to agent

Deterministic part:
- validate target session or active turn
- record exact message and provenance

Brain-mediated part:
- decide whether forwarding it bypasses harness constraints
- possibly wrap, defer, or reject on policy grounds

## Strong Bias For V1

V1 should err on the side of:

- fewer command types
- more deterministic envelopes
- explicit rejection for unsupported scopes
- and visible status transitions

The first version does not need to support every imaginable live intervention.

It only needs to establish a trustworthy pattern.

## Recommended V1 Split

### Deterministic in v1

- `pause_operator`
- `resume_operator`
- `stop_operation`
- `set_involvement_level`
- `patch_harness`
- `answer_attention_request`

### Deterministic accept + brain-mediated consequence in v1

- `patch_objective`
- `patch_constraints`
- `inject_operator_message`

### Explicitly defer in v1

- `inject_agent_message`
- branch-level live surgery
- multi-session reprioritization commands

## Recommended ADR Topics

1. `deterministic command reducer vs brain-mediated replanning boundary`
2. `command outcome lifecycle and status model`
3. `objective patch semantics during active work`
4. `pause semantics during active attached turns`
5. `user-to-agent message forwarding policy`

## Working Conclusion

The command inbox should not be modeled as "more text for the brain."

It should be modeled as:

- deterministic command acceptance and state mutation
- followed by brain-mediated replanning only where interpretation is actually needed

That is the cleanest way to preserve both:

- LLM-first orchestration
- and reliable human control over the harness
