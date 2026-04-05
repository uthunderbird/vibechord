# ADR 0099: OperatorService shell completion through workflow-authority extraction

## Status

Accepted

## Context

`OperatorService` has already shed public entrypoint preparation, cancellation, attached-turn
mechanics, and the main drive loop. Even after that, [service.py](../../src/agent_operator/application/service.py)
still remains extremely large because it continues to own several distinct business workflows:

- decision execution
- command application
- agent-result assimilation
- runtime reconciliation
- trace/report projection

That is not helper noise. It means the facade still has multiple reasons to change and remains the
owner of most runtime business logic.

## Decision

`OperatorService` must finish its transition into a shell by extracting workflow authorities rather
than introducing domain-service-first fragmentation.

The extraction order is:

1. `OperationTraceabilityService`
2. `DecisionExecutionService`
3. `OperationCommandService`
4. `AgentResultService`
5. `OperationRuntimeReconciliationService`

### Ownership rule

Blocking transitions such as `NEEDS_HUMAN` and focus changes are owned by the workflow that caused
them:

- decision path owns decision-triggered blocking/focus transitions
- command path owns answer/stop/cancel/policy-command-triggered transitions
- result path owns incomplete/rate-limit/disconnect-triggered transitions

### Non-decision

This ADR does not introduce a standalone first-pass `AttentionService` or `PolicyService`. Those
concerns remain embedded inside the workflow authority that triggered them unless later extraction
proves worthwhile.

## Alternatives Considered

### Extract semantic domain services first

Rejected as the top-level route for now. Attention and policy logic are currently cross-cutting
across decision, command, and result flows. Extracting them first would likely create several
awkward collaborators before the shell is actually reduced.

### Keep shrinking by helper extraction only

Rejected. The remaining size is driven by real business ownership, not just projection helpers.

## Consequences

- `OperatorService` becomes a true composition/facade shell instead of a hidden workflow owner.
- The repo stays consistent with the existing extraction style established by entrypoint,
  cancellation, attached-turn, and drive services.
- Tests must split along the same workflow boundaries instead of preserving one giant
  `tests/test_service.py`.
- This ADR can be accepted only once the named workflow authorities exist and `OperatorService`
  stops owning their substantive implementations.

## Implementation Notes

- `implemented`: the named workflow authorities now exist:
  - `OperationTraceabilityService`
  - `DecisionExecutionService`
  - `OperationCommandService`
  - `AgentResultService`
  - `OperationRuntimeReconciliationService`
- `implemented`: `OperatorService` delegates the main business workflows to those services.
- `verified`: the repository test suite is green after the extraction wave (`353 passed, 11 skipped`).
- `partial`: `OperatorService` still contains orchestration and state-local helper clusters for
  task/session/background bookkeeping, so the shell is materially thinner but not yet minimal.
- `implemented`: the test decomposition now follows service ownership much more closely:
  - `tests/test_decision_execution_service.py`
  - `tests/test_operation_command_service.py`
  - `tests/test_agent_result_service.py`
  - `tests/test_operation_runtime_reconciliation_service.py`
  - `tests/test_operation_traceability_service.py`
  - `tests/test_operation_drive_service.py`
  - `tests/test_attached_turn_service.py`
  - `tests/test_operation_cancellation_service.py`
  - `tests/test_operator_service_shell.py`
- `verified`: `tests/test_service.py` is now a thin shell/integration bucket rather than the old
  monolithic default home for operator behavior.
