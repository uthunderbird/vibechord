# ADR 0100: Pluggable operator policy boundary above loaded-operation runtime

## Status

Accepted

## Context

The repository already distinguishes:

- durable operation state (`OperationState` and related domain models),
- operation-scoped runtime coordination (`OperationRuntime`),
- and an LLM-shaped operator dependency (`OperatorBrain`).

That is enough for the current LLM-first operator, but it is not yet a clean architectural story
for multiple operator implementations.

`ADR 0083` already established that `OperationRuntime` is the operation-scoped coordination
boundary beneath `OperatorService` and above session/runtime transport layers. `ADR 0099`
simultaneously pushed `OperatorService` toward a thinner shell by extracting workflow authorities.

After those moves, a new design question becomes explicit:

- if multiple operator implementations exist,
- where does that variation live without forking the runtime loop itself?

The discriminator is a plausible alternative such as `BrainlessGoOnOperator`:

- the first agent message is synthesized from fixed configuration,
- the follow-up policy is essentially "continue",
- evaluation and stopping semantics are simpler than the current LLM-first operator,
- but the deterministic runtime machinery should remain the same.

That alternative does not obviously require:

- a different persistence model,
- a different wakeup/reconciliation model,
- a different background-runtime model,
- or a different per-operation coordination substrate.

It does, however, require a different answer to:

- what next action should be taken,
- how returned results should be interpreted,
- when the operator should stop,
- and how much of that behavior depends on an LLM.

At the same time, the current `OperatorBrain` protocol is not the right top-level seam for this
variation. It is already provider- and LLM-shaped:

- `decide_next_action`
- `evaluate_result`
- `summarize_agent_turn`
- `normalize_artifact`
- `distill_memory`
- `summarize_progress`

and [ProviderBackedBrain](../../src/agent_operator/providers/brain.py) is explicitly an adapter
from `StructuredOutputProvider` into that contract.

That means `OperatorBrain` already behaves like a dependency of one operator family, not like the
canonical architecture seam for all operator implementations.

The repository also already distinguishes external control-plane commands from internal operator
intent:

- `OperationCommand` is a persisted external command envelope with IDs, status, and application
  lifecycle,
- `BrainDecision` is an internal orchestration intent carrying rationale, assumptions, task
  mutations, and blocking-focus metadata.

So the current design pressure is not "make everything a command" and not "make every operator
variant a separate top-level shell". The missing decision is the boundary between:

- a stable loaded-operation runtime/coordinator,
- and a pluggable operator behavior layer.

This ADR therefore decides where operator variation belongs without reopening:

- `OperationRuntime` as the per-operation coordination substrate,
- `OperatorService` as the top-level shell/composition root,
- or the current external control-plane command model.

## Decision

`operator` should use a stable loaded-operation runtime together with a pluggable
operator-policy/controller layer.

### Stable layer

The stable layer is the loaded-operation runtime/coordinator for one loaded operation instance.

It owns:

- deterministic runtime mechanics,
- per-operation coordination,
- task/session/background bookkeeping,
- persistence and wakeup interplay,
- reconciliation,
- command application,
- and runtime guardrails.

This layer remains shared across operator implementations.

`OperatorService` remains the system-level shell that:

- accepts public entrypoints,
- creates or loads one operation instance,
- constructs the loaded-operation runtime/coordinator,
- wires infrastructure dependencies,
- and delegates execution.

The loaded-operation runtime/coordinator is the operation-scoped owner beneath that shell.

### Pluggable layer

Operator implementations vary through a pluggable operator-policy/controller boundary.

That boundary owns:

- choosing the next internal operator intent,
- interpreting returned agent results for continuation/termination,
- deciding when clarification or human escalation is required,
- and deciding what operator-visible progress summaries or derived interpretation steps are needed.

The current LLM-first operator is one implementation of that policy/controller family.

A `BrainlessGoOnOperator`-style implementation is another.

The policy/controller boundary decides *what should happen next*.

It does not own:

- persistence,
- wakeup or reconciliation mechanics,
- background-run bookkeeping,
- command inbox draining,
- deterministic stop/timeout/concurrency guardrails,
- or operation-runtime lifecycle ownership.

Those remain in the loaded-operation runtime/coordinator and surrounding application services.

### Relationship to `OperatorBrain`

`OperatorBrain` is not the top-level seam for alternative operator implementations.

Instead:

- `OperatorBrain` becomes a dependency used by one family of operator policies/controllers,
- especially the current LLM-first policy family,
- but non-LLM or low-LLM operator variants do not need to implement `OperatorBrain` directly.

This means the repository should gradually treat `OperatorBrain` as:

- an LLM-facing decision/evaluation helper contract,
- not the architectural synonym for "operator implementation".

### Relationship to Command pattern

The repository should not adopt "everything is an `OperationCommand`" as the top-level pattern for
operator behavior.

The distinction remains:

- external control-plane intent -> `OperationCommand`
- internal operator intent -> policy/controller output

However, command-handler style is a valid and preferred implementation pattern *inside* the loaded
operation runtime for executing internal operator intent.

For example, the loaded-operation runtime may internally dispatch policy output to handlers such as:

- `StartAgentHandler`
- `ContinueAgentHandler`
- `WaitForAgentHandler`
- `ClarificationHandler`
- `TerminalDecisionHandler`

That internal handler routing does not collapse public external commands and internal operator
decisions into one type.

In other words:

- Command pattern is **useful internally**
- but **incorrect as the only top-level public model**

for the current repository semantics.

## Alternatives Considered

### Treat `OperatorBrain` as the top-level seam for operator variants

Rejected.

`OperatorBrain` is already LLM/provider-shaped and mixes several brain-oriented helper behaviors.
It is too narrow and too implementation-shaped to serve as the canonical boundary for all operator
implementations.

It is a good seam for one operator family, not for all operator families.

### Model each operator variant as a separate top-level loop implementation

Rejected as the primary pattern.

That would duplicate runtime semantics such as:

- wakeup handling,
- reconciliation,
- attached/background waiting semantics,
- deterministic stop/guardrail enforcement,
- and command/persistence interplay.

The motivating example does not require that much divergence.

This route would duplicate the most correctness-sensitive runtime semantics without evidence that
operator variation needs that degree of runtime divergence.

### Make Command pattern the top-level model for all operator behavior

Rejected as the primary pattern.

`OperationCommand` and `BrainDecision` currently serve different semantic layers. Forcing all
internal operator intent into the external command model would either:

- bloat `OperationCommand` with internal orchestration concerns, or
- reintroduce a second command family anyway.

Command-handler style remains acceptable and desirable inside the loaded-operation runtime.

This ADR therefore keeps the semantic split:

- persisted external commands
- internal operator intent

while still allowing handler-based internal execution.

### Introduce a rich domain `Operation` entity that owns runtime behavior

Rejected for now.

The missing boundary is application/runtime ownership, not a side-effectful domain entity. A rich
domain `Operation` risks mixing domain state, persistence, and coordination concerns.

That route would also blur the distinction between:

- durable operation state,
- operation-scoped runtime mechanics,
- and pluggable operator behavior.

## Consequences

- The repository gains a clean story for multiple operator implementations without multiplying the
  runtime loop.
- `OperatorService` remains a top-level shell/composition boundary rather than becoming one class
  per operator flavor.
- `OperationRuntime` and the loaded-operation coordinator become more central architectural
  concepts.
- Future work should move remaining one-operation helper and callback surfaces beneath that loaded
  operation runtime/coordinator.
- `OperatorBrain` should gradually be repositioned in docs and code as a dependency of one operator
  policy family rather than the canonical operator seam.
- If internal intent execution is refactored further, handler-based execution inside the loaded
  operation runtime is preferred to another monolithic decision-execution method.
- `OperatorService` should not become one class per operator flavor; operator variation should
  attach below the shell and above the stable operation runtime.

## Migration direction

This ADR does not require the whole implementation to land at once.

The expected migration direction is:

1. make the loaded-operation runtime/coordinator explicit beneath `OperatorService`
2. move remaining one-operation helper and callback clusters under that boundary
3. introduce a pluggable operator-policy/controller seam above it
4. adapt the current LLM-first operator to that seam using `OperatorBrain` as an internal
   dependency
5. only then consider additional operator implementations such as a trivial
   `BrainlessGoOnOperator`

This ordering keeps runtime invariants stable while opening the operator-variation seam gradually.

## Follow-up

- Write a follow-up ADR for the loaded-operation runtime/coordinator shape if the repository is
  ready to introduce it as a first-class application object beneath `OperatorService`.
- Revisit `OperatorBrain` naming and placement after the policy/controller seam is made explicit in
  code.
- If needed later, add a narrow ADR for internal handler-based execution of operator intent inside
  the loaded-operation runtime.

## Implementation Status

Current repository truth:

- `implemented`: the top-level application seam has moved from direct `OperatorBrain` wiring to
  `OperatorPolicy`.
- `implemented`: the default boot path is now
  `ProviderBackedBrain -> LlmFirstOperatorPolicy -> OperatorService`.
- `implemented`: `LoadedOperation` exists as a first-class application object and already owns a
  substantial one-operation helper cluster:
  - task/session/background bookkeeping helpers,
  - latest-result and restart-instruction helpers,
  - working-directory and attached-session attachment helpers,
  - artifact and result-slot support helpers.
- `implemented`: decision, result, reconciliation, command, drive, and traceability paths already
  use `LoadedOperation` directly in important hot paths.
- `verified`: the repository test suite is green after those changes.

Current limitations:

- `partial`: `OperatorService` still contains a thin wrapper layer and remains the delegate host for
  some orchestration-side effects.
- `partial`: `OperationDriveService` still uses a delegate contract for orchestration behavior; the
  entire delegate surface has not yet collapsed into `LoadedOperation` plus narrow external
  collaborators.
- `partial`: `OperatorBrain` still exists as an active protocol because it remains the LLM-facing
  dependency of the default policy family.

This ADR should therefore be read as:

- decision status: `Accepted`
- implementation status: `partial`, with the core architectural direction already live in code
