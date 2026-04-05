# Operator Involvement And Policy Learning Brainstorm Ideas

## Status

Brainstorm only. Not a source-of-truth architecture document.

## Core Thesis

The operator should not have a single fixed human-in-the-loop posture.
It needs a configurable involvement model that determines:

- when to ask the user,
- what can be decided autonomously,
- what should be deferred,
- and how approved human decisions become future policy.

The default should be `auto`, not always-ask and not fully autonomous.

## Decision Policy Model

The key distinction is not merely confidence.
It is whether the situation is:

- already covered by known project policy,
- mechanically resolvable by existing deterministic rules,
- close enough to previously approved decisions,
- or conceptually novel enough that the operator should ask.

The runtime therefore likely needs a policy check pipeline:

1. deterministic rule applies
2. existing project policy applies
3. analogous accepted precedent applies
4. otherwise ask or defer based on involvement level

## Proposed Involvement Levels

### `0`

The user is unavailable.
The operator should:

- never block the whole operation on ordinary questions
- defer branches that require human-only judgment
- continue other runnable work
- queue attention items for later review

This is the correct "night mode" posture.

### `auto`

Default.
The operator asks when it encounters a conceptually new situation that:

- is not covered by deterministic guardrails,
- is not covered by project policy,
- and is not safely resolved by prior accepted precedent.

Otherwise it should proceed autonomously.

### `guided`

Ask more often:

- on important branch choices
- on ambiguous architectural tradeoffs
- on high-impact scope changes

### `strict`

Almost every nontrivial conceptual decision requires approval before continuing that branch.

## Branch Deferral Model

Low-involvement operation cannot mean "press ahead recklessly."
The operator should be able to:

- mark one branch blocked by missing human input
- preserve the question
- continue unrelated runnable branches
- resurface the deferred issue later

This implies that long-lived task branching becomes more important as involvement semantics mature.

## Policy Learning

When the user answers or approves something, the system should be able to store that as project-local policy.

Candidate policy classes:

- architectural preference
- safety/escalation preference
- repo workflow preference
- testing/review threshold
- publication rules
- branching/commit policy

Important constraint:

not every answer should become durable policy automatically.

There should be a distinction between:

- one-off answer
- accepted precedent
- persistent project policy

## Storage Implications

This probably wants a typed project-level memory/policy store rather than loose notes.

Candidate entity shape:

- `PolicyEntry`
  - scope: project | operation
  - class
  - statement
  - source
  - confidence / approval status
  - supersession info

This should integrate with the existing memory direction, but stay more structured than ordinary summaries.

## Failure Modes

### Risk: autonomy level becomes a vague mood knob

Each level must map to concrete runtime behavior.

### Risk: over-learning from one-off user answers

The system can become brittle if every tactical instruction hardens into policy.

### Risk: novelty detection is too fuzzy

"Conceptually new situation" sounds right, but needs operationalization.
The first implementation should likely use simpler rule-based heuristics plus explicit user marking.

### Risk: branch deferral requires richer task graph than currently exists

True low-involvement operation depends on branch-aware scheduling.
Without that, level `0` will still degrade into "everything blocked."

## Candidate ADR Topics

1. User involvement-level model and runtime semantics
2. Project policy / precedent storage model
3. Novelty detection heuristics vs explicit user-approved precedent
4. Deferred-branch semantics under low-involvement execution
5. Distinction between one-off user answers and durable policy

## Open Questions

- Should involvement level be global, per project, or overridable per operation?
- Should the operator be allowed to lower or raise its own ask-rate adaptively?
- How should the user inspect, edit, or revoke learned project policy?
- Does `auto` need a visible explanation each time it decides not to ask?
