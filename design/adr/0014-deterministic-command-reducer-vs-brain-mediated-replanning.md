# ADR 0014: Deterministic Command Reducer Vs Brain-Mediated Replanning

## Status

Accepted

## Context

[ADR 0013](/Users/thunderbird/Projects/operator/design/adr/0013-operation-command-inbox-and-command-envelope.md)
introduces a first-class `OperationCommandInbox` and a typed command envelope for live
human-to-operator intervention.

That decision creates a second architectural question:

- which parts of command handling belong to deterministic runtime control
- and which parts belong to the operator brain

Without an explicit boundary, the future harness will become unreliable in one of two ways:

### Failure mode 1: the brain owns too much

If the operator brain decides too much about command handling, then:

- pause and stop semantics may drift,
- valid commands may be accepted inconsistently,
- explicit human answers may be reinterpreted ambiguously,
- and the live UI may appear interactive without actually being trustworthy.

### Failure mode 2: the runtime owns too much

If all command consequences are forced into deterministic logic, then:

- the harness becomes rigid,
- strategic human guidance becomes hard to integrate,
- and the operator brain loses the ability to adapt plans after live intervention.

The project therefore needs a hard split between:

- deterministic command control
- and brain-mediated orchestration after accepted commands

This boundary should align with the project's broader architectural bias:

- deterministic control-plane truths remain explicit
- while LLM-first orchestration remains responsible for planning and adaptation

## Decision

`operator` will handle live commands through a two-layer model:

1. a deterministic command reducer
2. brain-mediated replanning after accepted command effects

The deterministic command reducer is responsible for:

- command validation
- target resolution
- idempotency
- command acceptance or rejection
- direct state mutation for deterministic command effects
- command lifecycle transitions
- and provenance recording

The operator brain is responsible for:

- interpreting open-text guidance
- deciding how accepted changes affect plans
- replanning tasks, sessions, or priorities
- deciding what work should happen next after a valid command changed control context

The operator brain must not decide:

- whether a command exists
- whether a command targets the requested entity
- whether a pause or stop took effect
- whether an explicit human answer resolved a particular attention request
- or whether a deterministic command was accepted, rejected, superseded, or expired

Those are control-plane truths and belong to the reducer.

## Command Outcome Model

The command lifecycle should distinguish at least:

- `pending`
- `applied`
- `rejected`
- `accepted_pending_replan`
- `superseded`
- `expired`

Important semantic rule:

- a command may be valid and accepted before its full behavioral consequence has been realized

This is why `accepted_pending_replan` is a useful explicit state:

- the runtime has accepted the command
- but the operator has not yet replanned around it

## Initial Deterministic Command Set

The following command classes should remain deterministic in acceptance and immediate effect.

### Administrative control

- `pause_operator`
- `resume_operator`
- `stop_operation`
- `stop_agent_turn`
- `stop_session`
- `set_involvement_level`

These represent direct user authority over the harness and should not depend on LLM judgment.

### Structured state patching

- `patch_objective`
- `patch_harness`
- `patch_success_criteria`
- `patch_constraints`
- `answer_attention_request`

The patch envelope, target validation, and persisted mutation should be deterministic.

Replanning after the mutation may still be brain-mediated.

### Provenance and policy commands

- `record_policy_decision`
- `revoke_policy_decision`
- `approve_route`
- `reject_route`

These are explicit human judgments and should not be reinterpreted as freeform chat.

## Brain-Mediated Consequence After Acceptance

Some commands still require brain-mediated interpretation after the reducer has accepted them.

### Open-text operator guidance

- `inject_operator_message`
- `add_note`
- `attach_context`

The runtime can store these deterministically, but their planning implications are contextual.

### Tactical route influence

- `force_next_step`
- `reprioritize_task`
- `defer_task_branch`

These should still have deterministic envelopes, but the operator brain may need to interpret
how the accepted change affects the next plan.

### Objective and constraint changes

Even when the reducer applies:

- `patch_objective`
- `patch_constraints`

the brain may need to decide:

- whether the current plan is still valid
- whether the active task graph should be revised
- whether live work should be stopped or allowed to yield first

So the mutation is deterministic, but the downstream plan adaptation is not.

## Unsupported Or Deferred V1 Commands

The first implementation should reject clearly unsupported command classes instead of pretending
to support them vaguely.

Likely deferred or explicitly unsupported in v1:

- `pause_session_branch`
- `cancel_task_branch`
- broad multi-branch live surgery
- arbitrary multi-session reprioritization
- general `inject_agent_message`

The current runtime is not yet branch-rich enough to make these trustworthy.

## Runtime Placement

The deterministic reducer should live beside existing runtime control logic such as:

- wakeup reconciliation
- operation status transitions
- focus reconciliation
- background-run reconciliation
- and cancellation flows

It should not be embedded inside:

- `brain.decide_next_action(...)`
- or hidden in prompt interpretation

This preserves the same architectural direction already visible in current code, where:

- `cancel(...)` is deterministic
- `OperationStatus` transitions are explicit
- and wakeup handling is not delegated to the brain

## Non-Goals

This ADR does not define:

- the final scheduler-state model for pause semantics
- the full attention-request taxonomy
- the final policy-memory model
- or the final set of supported command types

Those remain follow-up decisions.

This ADR also does not require every command consequence to be deterministic.

It only requires that:

- command acceptance and direct control truth remain deterministic

## Alternatives Considered

### Option A: Let the brain interpret and apply all commands

Rejected because:

- it weakens trust in live control,
- risks inconsistent command handling,
- and blurs direct user authority with orchestration judgment.

### Option B: Handle all commands and all consequences deterministically

Rejected because:

- it undercuts the LLM-first orchestration model,
- makes open-text guidance awkward,
- and forces too much planning intelligence into rigid control logic.

### Option C: Deterministic reducer for command truth, brain-mediated replanning for plan adaptation

Accepted because:

- it preserves reliable control semantics,
- keeps user authority explicit,
- and still lets the operator brain adapt plans intelligently after accepted commands.

## Consequences

### Positive

- Live control semantics become more trustworthy.
- The operator brain keeps its orchestration role without owning control-plane truth.
- The future TUI can show command acknowledgement and command effect honestly.
- Attention answers and objective patches gain clearer provenance.
- Unsupported commands can be rejected explicitly instead of failing ambiguously.

### Negative

- The runtime grows a clearer reducer-like layer.
- Some command flows will require two phases:
  - accepted deterministically
  - then integrated through replanning
- The project will need careful wording in UI surfaces so users understand the difference
  between:
  - accepted
  - applied
  - and accepted but pending replan

### Follow-Up Implications

- The runtime will likely need an explicit command reducer or equivalent reducer-shaped logic.
- `inspect`, `trace`, and future live monitoring should surface command lifecycle states.
- A follow-up ADR should define pause semantics during active attached turns.
- A follow-up ADR should define attention-request and answer-routing semantics.
- The implementation should reject unsupported v1 command classes explicitly rather than routing
  them into vague brain behavior.
