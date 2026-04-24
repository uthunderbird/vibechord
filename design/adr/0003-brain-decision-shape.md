# ADR 0003: Brain Decisions Must Resolve To Structured Actions

## Decision Status

Accepted

## Implementation Status

Verified

## Evidence

- `src/agent_operator/domain/brain.py` defines `BrainDecision` as the structured execution
  contract with explicit `action_type`, `target_agent`, `session_id`, `instruction`,
  `rationale`, `confidence`, and structured follow-on metadata.
- `src/agent_operator/dtos/brain.py` defines `StructuredDecisionDTO` as the provider-facing
  structured output schema, and `src/agent_operator/mappers/brain.py` maps that DTO into the
  domain `BrainDecision` instead of routing execution through free-form prose.
- `src/agent_operator/application/decision_execution.py` executes by branching on
  `decision.action_type` and uses `decision.rationale` only as explanatory summary text when
  marking completion, failure, or attention.
- `src/agent_operator/application/queries/operation_projections.py` and
  `src/agent_operator/cli/workflows/converse.py` serialize both `action_type` and `rationale`
  separately for observability, preserving the ADR rule that reasoning is visible but not the
  executable source of truth. The converse serializer now also stays aligned with the current
  structured feature/task mutation fields instead of relying on stale attribute names.
- `tests/test_decision_execution_service.py`, `tests/test_prompting.py`,
  `tests/test_operation_projections.py`, and `tests/test_cli.py` exercise structured decision
  execution, prompting for structured outputs, and read-model/CLI serialization of decision data,
  including full-context converse serialization for structured feature/task mutation payloads.

## Context

The operator is intentionally `LLM-first` in deliberative control. That means the operator brain is expected to make decisions such as:

- continue an active agent session,
- start a new agent session,
- ask for clarification,
- stop,
- or choose a deterministic control action.

This creates a critical boundary in the system. The operator loop must convert brain output into real execution.

If the brain returns only free-form text reasoning, the application layer must parse implicit intent from prose. That would make the control plane brittle, hard to test, and prone to silent misexecution.

On the other hand, requiring only rigid machine output with no supporting explanation would reduce transparency and make debugging weaker, especially in CLI usage.

The system therefore needs a clear source of truth for execution while still preserving enough reasoning to explain what happened.

## Decision

`OperatorBrain.decide_next_action(...)` must resolve to a structured decision object.

The structured decision is the execution source of truth.

Optional reasoning may accompany the decision, but it is advisory and human-facing. It must not be the only representation of intended control flow.

In other words:

- execution reads `BrainDecision`
- observability may also render `brain_reasoning`

The operator loop should never need to infer the next action by parsing unstructured prose.

## Decision Shape

The exact class names can evolve, but the brain output should contain at least:

- `action_type`
- `target_agent` when relevant
- `session_id` when relevant
- `instruction` or payload for the next action
- `rationale`
- `confidence` or similar optional signal

Illustrative examples of `action_type`:

- `start_agent`
- `continue_agent`
- `wait_for_agent`
- `request_clarification`
- `apply_policy`
- `stop`

The brain may also return optional metadata such as:

- assumptions
- expected outcome
- evaluation notes
- ranked alternatives

But the operator loop should require only the structured core needed for correct execution.

## Alternatives Considered

### Option A: Free-form reasoning only

Pros:

- simplest LLM prompting model
- flexible for experimentation

Cons:

- execution must parse prose
- hard to validate and test
- invites ambiguous or partially specified actions
- weakens deterministic guardrails because intent is not explicit

### Option B: Structured action only

Pros:

- clean execution boundary
- easy to validate
- easy to test

Cons:

- weaker transparency in CLI output
- harder to inspect why the brain chose an action
- poorer debugging when prompts or policies fail

### Option C: Structured action plus optional reasoning

Pros:

- preserves a hard execution contract
- keeps the operator explainable
- fits the transparency goals of the project
- supports both automated tests and human inspection

Cons:

- slightly larger schema
- requires discipline to avoid treating reasoning as executable truth

## Consequences

- The operator loop can validate decisions before execution.
- Tests can assert explicit action selection without parsing natural language.
- CLI output can show both the chosen action and the brain's explanation.
- Prompting and parsing for the brain should target structured outputs first.
- Free-form brain commentary remains useful, but it cannot silently control execution.
- Future ADRs may define:
  - exact action taxonomy
  - schema validation strategy
  - confidence semantics
  - retry behavior for invalid brain decisions

## Notes

The goal is not to eliminate reasoning text. The goal is to prevent reasoning text from becoming an accidental control protocol.

In this architecture, deliberation may be linguistic, but execution must be structurally explicit.
