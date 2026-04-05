# ADR 0073: Command bus and planning trigger semantics

## Status

Accepted

## Context

[`RFC 0009`](../rfc/0009-operation-event-sourced-state-model-and-runtime-architecture.md)
and the follow-up ADRs define:

- canonical domain events and derived checkpoints
- non-canonical fact translation
- pure projector and reducer slices
- process managers restricted to control-plane reactions and planning triggers

The remaining unresolved boundary is how these planning triggers move through the system.

The current design already has a durable command inbox and explicit command lifecycle, but the new
event-sourced architecture adds a sharper distinction between:

- deterministic control-plane commands
- planning triggers that tell the operator brain "a new deliberation cycle is now required"
- substantive next-step choices that remain the brain's responsibility

Without an ADR here, the implementation can drift into one of three bad shapes:

1. planning triggers become ad hoc booleans or in-memory flags
2. planning triggers are treated as substantive commands and begin to carry hidden strategy
3. process-manager outputs bypass the durable command path, making control-plane causality harder to
   inspect and replay

## Decision

### One command bus for user and internal control-plane intents

There is one command bus per operation.

It carries:

- user-issued commands
- process-manager-issued control-plane commands
- process-manager-issued planning triggers

This preserves one durable, inspectable path for operator control intent.

This ADR does **not** require that all command classes share one exact Python type at the leaf
level. It requires one logical bus with one durable lifecycle and one inspectable control-plane
surface.

### Planning trigger is a distinct control-plane intent

A planning trigger is not a substantive work instruction.

It means only:

> "given the current canonical state, the operator should run a new planning cycle."

It does **not** mean:

> "here is the substantive next step the operator should take."

Examples of valid planning triggers:

- attention resolved
- execution lost
- cooldown expired
- operator message received
- policy applicability changed
- accepted command changed planning context

### Planning trigger payload

A planning trigger may include only control-plane-safe metadata such as:

- `reason`
- `source_event_id`
- `source_event_type`
- optional target references such as `task_id`, `session_id`, or `execution_id`
- `dedupe_key`

It must not include:

- authored work instructions
- substantive route choices
- prioritized candidate plans
- preferred agent choice for business work

### Brain is the only substantive planner

When a planning trigger is drained:

1. it is applied as control-plane truth
2. it makes the operation eligible for a new planning cycle
3. the brain receives the updated checkpoint, harness, policies, and active context
4. the brain chooses the substantive next step

The planning trigger itself never contains that next step.

### Command bus lifecycle

All commands on the bus share the same lifecycle model:

- accepted
- rejected
- pending follow-up if relevant
- terminalized when their deterministic effect is complete

For planning triggers specifically:

- `accepted` means the trigger was valid and recorded
- `applied` means it made the operation eligible for planning
- terminalization occurs when the corresponding planning cycle has been entered or intentionally
  superseded

This ADR does not force existing command status enum names to change immediately. It fixes the
semantic model for the event-sourced architecture.

### Coalescing and deduplication

Planning triggers may be coalesced.

Reason:

- multiple domain events may all imply "planning is needed"
- the system should not enqueue N equivalent brain cycles when one will do

Required rule:

- triggers with the same `dedupe_key` or same coalescing class may collapse into one pending
  planning obligation

Examples:

- several recovery-related events for the same session may collapse into one planning trigger
- `OperatorMessageReceived` followed by `PolicyEvaluated` may or may not collapse depending on
  dedupe class; implementation choice is allowed if inspectability is preserved

### Process-manager interaction

`ProcessManager` may emit:

- deterministic control-plane commands
- planning triggers

It may not emit substantive work-selection commands.

This ADR therefore operationalizes ADR 0072 rather than revisiting it.

## Implementation Note

Current repository truth implements this ADR as a bridge slice over the current snapshot-based
runtime:

- one durable `FileControlIntentBus`
- `FileOperationCommandInbox` as a user-command facade over that bus
- `PlanningTrigger` as an internal durable control-plane intent
- coalescing by `dedupe_key`

The implementation does **not** yet claim that the full runtime is event-sourced. It only claims
that planning-trigger causality is now durable, inspectable, and no longer represented by
`accepted_pending_replan` or `pending_replan_command_ids`.

### Command bus vs domain events

Commands and planning triggers are not domain events.

They are control-plane intents that may, when accepted and applied, lead to domain events or to a
brain planning cycle.

This distinction is important:

- command bus expresses requested control intent
- domain event stream expresses business state transition truth

### Durability and inspectability

Planning triggers must be durably inspectable.

The user should be able to answer:

- why did the operator run another planning cycle?
- which event or command caused it?
- was the trigger deduplicated or superseded?

Therefore planning triggers may not exist only as in-memory flags.

## Consequences

- process-manager outputs remain visible and auditable
- planning cycles are causally attributable to domain events and control-plane intents
- harness authority is preserved because triggers carry no substantive next-step content
- command-bus semantics stay unified instead of splitting into visible user commands and invisible
  internal triggers

## Alternatives Considered

### Treat planning trigger as just another substantive command

Rejected. This would make it too easy to smuggle strategy into what should remain a control-plane
intent.

### Keep planning-needed state as an in-memory flag only

Rejected. This would make replanning causality opaque and brittle under resume/recovery.

### Let process managers invoke the brain directly

Rejected. That would bypass the durable control-plane path and make planning-entry causality harder
to inspect and reason about.

### Do not coalesce planning triggers

Rejected. It would create unnecessary repeated planning cycles from equivalent causes.
