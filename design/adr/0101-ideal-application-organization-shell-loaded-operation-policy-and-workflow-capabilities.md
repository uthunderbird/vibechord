# ADR 0101: Ideal application organization — shell, loaded operation, policy, and workflow capabilities

## Status

Proposed

## Context

`ADR 0099` completed the main workflow-authority extraction from `OperatorService`.

`ADR 0100` established that operator variation should live in a pluggable
operator-policy/controller layer above a stable loaded-operation runtime.

After those two decisions, the repository has a much clearer architecture than before, but one
question remains easy to rediscover in future refactors:

- what is the *ideal final organization* of the top application layer once the current transition
  work finishes?

This question is no longer about one isolated extraction.

It is about the target shape of:

- `OperatorService`,
- `LoadedOperation`,
- `OperatorPolicy`,
- workflow-authority services,
- drive-layer collaborators,
- and the internal execution grammar between them.

The repository now has enough evidence to answer that question directly:

- `OperatorService` has already stopped owning the main decision / command / result /
  reconciliation / traceability workflows,
- `LoadedOperation` already exists as a one-operation boundary,
- `OperatorPolicy` already exists as the top pluggable behavior seam,
- and the drive layer is already split into narrower runtime / control / trace / decision pieces.

The remaining design pressure is therefore no longer "how to shrink `service.py` somehow", but:

- which responsibilities should remain in the shell permanently,
- which responsibilities belong in the one-operation runtime boundary,
- which extracted units are enduring workflow authorities,
- and how explicit the internal execution grammar should become.

## Decision

The ideal application-layer organization for `operator` is:

1. `OperatorService` as a thin system shell
2. `LoadedOperation` as the one loaded-operation runtime boundary
3. `OperatorPolicy` as the pluggable operator-behavior boundary
4. workflow-authority services as the enduring application capabilities
5. drive-layer collaborators as internal execution collaborators rather than top-level enduring
   service concepts
6. restrained internal handler-style execution beneath that architecture

### 1. `OperatorService` is the system shell

`OperatorService` should remain responsible for:

- public application entrypoints (`run`, `resume`, `recover`, `tick`, `cancel`)
- top-level graph assembly
- loading or creating operation state
- constructing and wiring the loaded-operation runtime boundary
- delegating execution into the relevant collaborators

`OperatorService` should not remain the owner of:

- substantive workflow logic
- one-operation bookkeeping truth
- internal decision/result/command business semantics
- or hidden callback meshes that exist only because other collaborators lack the right boundary

In other words, it is a shell and composition root, not the true owner of operation execution.

### 2. `LoadedOperation` is the terminal one-operation boundary

`LoadedOperation` is the final application/runtime boundary for one loaded operation instance.

It owns:

- one-operation mutable coordination mechanics
- task/session/background bookkeeping
- focus and continuation resolution
- working-directory and restart-instruction synthesis
- result-slot and latest-result lookup
- session decoration and attachment
- other operation-local mechanics that should not live in the shell

It does not own:

- top-level application entrypoints
- process-wide infrastructure construction
- operator-policy decisions
- or the full workflow logic currently held by workflow-authority services

It is an application/runtime object, not a rich domain entity and not a passive context bag.

### 3. `OperatorPolicy` is the pluggable behavior seam

Operator variation lives in `OperatorPolicy`.

That seam owns:

- choosing the next internal operator intent
- interpreting returned results for continuation or stopping
- deciding when clarification or escalation is required
- producing operator-visible progress interpretation when needed

It does not own:

- persistence
- wakeups or reconciliation
- command draining
- session/background bookkeeping
- deterministic runtime guardrails
- or operation-lifecycle hosting

This preserves the route established by `ADR 0100`:

- stable runtime substrate
- pluggable operator behavior

### 4. Workflow-authority services are enduring application capabilities

The following units are enduring top-level workflow authorities:

- `DecisionExecutionService`
- `OperationCommandService`
- `AgentResultService`
- `OperationRuntimeReconciliationService`
- `OperationTraceabilityService`

They are not merely extraction leftovers.

They are the right enduring application capabilities because each owns a distinct class of
workflow transitions and side effects.

### 5. Drive-layer splits are internal execution collaborators

The drive-layer pieces should not necessarily be treated as equally important top-level "service"
concepts in the architecture narrative.

Units such as:

- `OperationDriveRuntime`
- `OperationDriveControl`
- `OperationDriveTrace`
- `OperationDriveDecisionExecutor`

are better understood as internal execution collaborators/capabilities that support the operator
loop.

They are valuable, but they are not the same kind of architectural noun as the enduring workflow
authorities above.

### 6. Internal execution grammar should be explicit but restrained

The repository should adopt restrained internal handler-style execution beneath the shell/runtime
split.

This means:

- internal operator intent should be executed through an explicit local grammar
- major action families may have distinct executors/handlers
- but the repository should not adopt a universal "everything is a command/handler" model

This internal grammar is appropriate for action families such as:

- start agent
- continue agent
- wait for agent
- clarification / attention opening
- terminal decision handling

This is an implementation pattern beneath the architecture.

It is not the top-level public model of the repository.

## Alternatives Considered

### Keep the ideal vague and continue shrinking files opportunistically

Rejected.

The repository now has enough architectural evidence that future contributors should not have to
re-derive the target organization from partial refactors and chat history.

### Introduce another mandatory top-level architectural object beyond `LoadedOperation`

Rejected.

Current evidence supports `LoadedOperation` as the one-operation runtime boundary. The remaining
problem is boundary completion and naming clarity, not the absence of another top-level object.

### Make a separate graph assembler/builder mandatory in the ideal architecture

Rejected as part of the ideal target by default.

A separate builder may become a useful later refinement if constructor assembly becomes the dominant
maintenance problem, but the current architectural evidence does not require it as part of the
ideal organization.

### Adopt a universal command pattern for both external control-plane commands and internal operator intent

Rejected.

The repository already has a meaningful semantic distinction between:

- external persisted control-plane commands (`OperationCommand`)
- and internal operator intent

Collapsing them into one universal command model would blur a useful boundary rather than clarify
it.

## Consequences

- The repository has a clear target architecture for the application layer beyond the already
  accepted local extraction decisions.
- `OperatorService` can continue shrinking without ambiguity about its ideal final role.
- `LoadedOperation` has a bounded and explicit architectural purpose.
- Workflow-authority services remain first-class in the architecture narrative instead of looking
  like temporary file moves.
- Drive-layer collaborators can be kept and evolved without overpromoting them into the wrong kind
  of architectural noun.
- Internal handlerization is encouraged where it clarifies execution grammar, but a repo-wide
  universal command architecture is explicitly ruled out.
- A separate builder/assembler layer remains an allowed later refinement, not a currently required
  architectural destination.
