# ADR 0012: Separate Objective From Harness Instructions

## Status

Accepted

## Context

`operator` currently uses a single freeform `OperationGoal.prompt` as the main source of truth
for:

- the objective itself,
- operator-level orchestration guidance,
- and sometimes blocking or escalation policy.

In practice this mixes two different semantic layers:

1. `objective`
   - what outcome should be achieved in the world or repository
2. `harness instructions`
   - how the operator should drive the attached agent while pursuing that objective

This mixing already affects runtime behavior.

Today:

- `OperationGoal.prompt` is copied into `ObjectiveState.prompt`,
- the brain sees that mixed text as `Objective`,
- evaluation judges completion against that mixed text,
- reports print the same mixed text as the operation objective,
- and root task derivation inherits the same blend.

This creates a failure mode where an agent can satisfy the orchestration playbook strongly enough
that the operator marks the run as completed even though the underlying business objective was
not truly closed.

A recent run exposed exactly this problem: the operation mixed a real project objective with
directions such as:

- usually tell the agent to continue,
- use swarm mode when next steps are unclear,
- use swarm red team when prior work is doubtful,
- stop and surface approval or escalation requests.

Those directions are valid operator guidance, but they are not themselves the objective.

## Decision

`operator` will separate `objective` from `harness instructions` in the goal model.

The domain model should evolve toward:

```python
class OperationGoal(BaseModel):
    objective: str
    harness_instructions: str | None = None
    success_criteria: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

The semantic model distinguishes three concepts:

- `objective`
- `harness instructions`
- `guardrails`

The initial goal schema still exposes only explicit `objective` and `harness_instructions`
fields. Until a later ADR changes the schema, guardrails remain represented inside
`harness_instructions` even though they are semantically distinct from orchestration guidance.

Semantic rules:

- `objective` defines the target outcome
- `success_criteria` refine how completion is judged
- `harness_instructions` define how the operator should run orchestration
- `guardrails` are a distinct conceptual subset of non-objective guidance such as:
  - blocking on approval or escalation requests
  - fail or clarification boundaries
  - other execution-policy constraints
- an initial implementation may still keep guardrails inside `harness_instructions`,
  but they remain non-success-bearing execution policy rather than objective text
- `harness_instructions` may influence:
  - agent instruction generation
  - session reuse behavior
  - swarm or red-team routing
  - escalation handling
  - publication hygiene such as commit or push expectations
- `harness_instructions` must not by themselves satisfy the objective

Minimum enforcement points:

- root task derivation should use `objective`, not mixed freeform text
- task goal text should not be derived from `harness_instructions`
- evaluation should judge `goal_satisfied` against `objective` and `success_criteria`
- reports should show `Objective` separately from `Harness Instructions`
- decision prompting should show both explicitly, with clear labels
- blocking or escalation rules may remain in harness for now, but they must be interpreted as
  execution policy, not completion criteria

## Non-Guarantees

This ADR does not by itself guarantee:

- that legacy freeform `prompt` inputs become safe automatically,
- that all non-objective guidance has already been separated into a final schema,
- or that mixed historical operations can be reinterpreted losslessly as objective-only.

Until the explicit structured goal path is implemented and enforced:

- legacy freeform goals remain partially ambiguous,
- reports and evaluation should not claim the stronger guarantee for that legacy path,
- and compatibility behavior should preserve ambiguity rather than silently pretending the split
  already happened.

Compatibility path:

- existing `prompt` input may remain temporarily,
- but legacy `prompt` should be treated as semantically ambiguous when it contains mixed
  objective and harness content,
- legacy mixed prompts must be labeled as ambiguous in operator-facing inspection and reporting
  surfaces,
- evaluation must not imply that the stronger structured-goal guarantee applied to those legacy
  runs,
- the stronger completion and task-derivation guarantees in this ADR apply only to the explicit
  structured path using `objective` and `harness_instructions`,
- and new code paths should prefer explicit `objective` plus `harness_instructions`.

## Alternatives Considered

### Option A: Keep a single mixed prompt and rely on better prompt wording

Rejected because:

- it keeps the semantic ambiguity in the domain model,
- it relies on prompt discipline alone,
- and the same bug can reappear in evaluation, reports, or task derivation.

### Option B: Keep a single prompt and move harness semantics into metadata

Rejected as the main solution because:

- it hides an important semantic distinction in an untyped bucket,
- it weakens readability and traceability,
- and it makes the architecture harder to understand from code and docs.

### Option C: Split objective and harness instructions as first-class fields

Accepted because:

- it matches the real semantic boundary,
- it improves evaluation correctness,
- it keeps task derivation cleaner,
- and it makes reports and traces more honest.

## Consequences

### Positive

- Completion semantics become stricter and more honest.
- Root tasks can represent the real objective instead of an orchestration playbook.
- Reports can distinguish target outcome from operator method.
- Harness guidance remains powerful without being confused for success.

### Negative

- The public goal model changes.
- CLI and service wiring need a compatibility path.
- Prompt builders, evaluation, task synthesis, and tests all need updates.
- Legacy mixed goals will need explicit handling rather than silent reinterpretation.

### Follow-Up Implications

- `build_decision_prompt(...)` should render separate sections:
  - `Objective`
  - `Harness Instructions`
- business-facing root task creation and task-goal updates should derive task goal text from
  `objective` only
- harness may still justify orchestration substeps, but it should not supply the goal text for
  business-progress tasks
- `build_evaluation_prompt(...)` should evaluate only against:
  - `Objective`
  - `Success Criteria`
- `OperationReport` should display both fields separately.
- Existing CLI and API entrypoints should gradually migrate from one freeform goal string toward
  structured goal input.
- A compatibility shim should preserve and label legacy ambiguity instead of silently treating old
  mixed prompts as objective-only.
- If the project later decides to expose guardrails as a third first-class field, that change
  should be captured in a follow-up ADR rather than silently folded into this one.
