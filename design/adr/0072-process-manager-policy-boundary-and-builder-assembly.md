# ADR 0072: Process manager policy boundary and builder assembly

## Status

Accepted

## Context

[`RFC 0009`](../rfc/0009-operation-event-sourced-state-model-and-runtime-architecture.md)
keeps `operator` intentionally LLM-first. The operator brain remains the component that makes
substantive orchestration decisions under the current objective, harness instructions, success
criteria, and project policy context.

At the same time, the RFC and follow-up ADRs introduce explicit event-sourced boundaries:

- canonical domain event stream
- projector and reducer slices
- fact translation layer

The remaining question is what kind of behavior is allowed in `ProcessManager`.

This is a high-stakes boundary. If `ProcessManager` is allowed to choose substantive next actions,
the system stops being an LLM-first operator and quietly becomes a deterministic workflow engine
with an LLM bolted on for narration.

That would contradict the project's core thesis in VISION.md.

## Decision

### `ProcessManager` is a control-plane reactor, not a strategy engine

`ProcessManager` reacts to domain events and updated canonical checkpoint state.

Its responsibility is limited to:

- deterministic control-plane hygiene
- state-machine progression
- attention routing
- deliberate triggering of a new planning cycle

It is **not** responsible for substantive work selection.

### Allowed outputs

A `ProcessManager` may emit only commands whose payload is fully determined by:

- the observed domain event
- the updated canonical checkpoint
- static or configured policy

Allowed examples:

- request a planning cycle because attention was resolved
- request a recovery evaluation because an execution was marked lost
- request reconciliation because new technical facts are pending
- request policy refresh because applicability prerequisites changed
- request cooldown expiry handling after a timer or state transition

These are control-plane obligations or planning triggers, not substantive route choices.

### Forbidden outputs

A `ProcessManager` must not emit commands that choose substantive work.

Forbidden examples:

- choose which task should run next among multiple plausible candidates
- choose which agent should be assigned for substantive work
- author a new agent instruction for business work
- choose one proof or implementation route over another
- collapse an uncertainty that the harness intends the brain to reason through
- continue an agent turn with newly authored substantive instructions

### Explicit anti-pattern

The anti-pattern this ADR forbids is:

> **Hidden deterministic orchestration**: a `ProcessManager` that appears to be a control-plane
> component but in fact chooses the next substantive business step, thereby shrinking or bypassing
> harness-governed LLM deliberation.

### Current implementation shape

Current repository truth implements this boundary as a bridge slice over the snapshot-based
`OperatorService`:

- code-defined `ProcessManagerPolicy` units
- code-assembled managers via `CodeProcessManagerBuilder`
- internal bridge signals via `ProcessManagerSignal`
- outputs restricted to `PlanningTrigger`

The current implementation does **not** allow process managers to emit substantive business
instructions, task-selection decisions, or authored agent prompts.

This anti-pattern is unacceptable even if it improves short-term efficiency.

If a proposed `ProcessManager` rule can be rephrased as "decide what substantive work should happen
next," that rule belongs to the brain, not to a process manager.

### Harness authority

Harness remains authoritative for any open-ended next-step choice.

The rule is:

- if the next step can be fully determined from current event + checkpoint + static policy, a
  process manager may emit it
- if the next step requires prioritization, synthesis, route comparison, task selection, or
  authored work instructions, the process manager must emit a planning trigger instead

This preserves the LLM-first thesis while still allowing deterministic control-plane progression.

### `ProcessManager` is assembled from policy through a builder

There is no single monolithic hand-written `ProcessManager` with embedded if/else orchestration
logic.

Instead, process-manager behavior is assembled from a bounded set of `Policy` objects through a
`ProcessManagerBuilder`.

The builder's job is to:

- gather the applicable process-manager policies
- compose them into concrete process-manager instances
- order or group them by concern
- ensure only allowed control-plane behavior is assembled

### Role of policy

In this ADR, `Policy` means deterministic rules governing control-plane reaction, not substantive
planning strategy.

Examples of allowed process-manager policy:

- when `AttentionRequestResolved` occurs, schedule a planning trigger
- when `ExecutionObservedStateChanged(... -> lost)` occurs, schedule recovery evaluation
- when policy applicability changes, schedule planning trigger or permission refresh
- when a scheduler pause is cleared, make the operation eligible for planning again

Examples of disallowed process-manager policy:

- if theorem proving task exists, always continue the proof agent
- if repo looks frontend-heavy, prefer codex over claude for the next slice
- after proof gap event, choose route B rather than route A

Those are harness-governed planning rules, not control-plane policy.

### Builder contract

`ProcessManagerBuilder` is responsible for constructing process managers from policy and static
dependencies.

Its inputs include:

- static runtime dependencies
- configured process-manager policy set
- operation profile or mode if relevant

Its outputs are:

- one or more concrete `ProcessManager` instances
- already constrained to control-plane-safe behavior

The builder does not read live facts or mutate checkpoint state. It is assembly-time only.

### Architectural split

After this ADR:

- reducers answer: "what is now true?"
- process managers answer: "what control-plane reaction or planning trigger is now required?"
- brain answers: "given the objective, harness, and current state, what substantive work should be
  chosen next?"

This split is intentional and normative.

## Consequences

- `ProcessManager` stays compatible with the LLM-first thesis
- harness retains authority over substantive orchestration choices
- deterministic control-plane logic is still extracted from `OperatorService`
- process-manager behavior becomes composable and reviewable through policy objects
- future changes to process-manager behavior can be made by adding or adjusting policies rather than
  growing one implicit reactor

## Alternatives Considered

### Let `ProcessManager` choose substantive next actions

Rejected. This is the hidden deterministic orchestration anti-pattern and would reduce harness to a
post-hoc refinement layer.

### Keep all follow-up behavior inside `OperatorService`

Rejected. This preserves the current god-object failure mode.

### Build one monolithic `ProcessManager` with hard-coded rules

Rejected. It would make policy boundaries implicit, reduce inspectability, and make anti-pattern
drift harder to detect.

### Put all control-plane follow-up through the brain

Rejected. This would preserve thesis purity at the cost of re-LLM-ifying deterministic hygiene and
state-machine progression that should remain algorithmic.
