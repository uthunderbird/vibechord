# User Involvement And Policy Learning Brainstorm Ideas

## Core Thesis

`operator` should support adjustable human involvement without becoming either:

- a workflow engine that always asks,
- or a reckless autopilot that silently guesses.

The right center seems to be:

- explicit involvement levels,
- novelty-aware escalation,
- branch deferral when human input is unavailable,
- and project-local policy learning from approved prior decisions.

## Decision Policy Model

The operator should classify decision points into categories, for example:

- routine local execution
- known policy-covered decision
- risky but reversible decision
- conceptually novel decision
- human-required decision

The user involvement level then changes which categories are surfaced immediately and which may
be auto-resolved or deferred.

## Suggested Involvement Levels

### Level 0: unattended

- do not ask the user
- keep working on branches that can proceed autonomously
- defer any branch that requires human-only approval or unavailable context

This is the "night mode" or "away from keyboard" mode.

### Level 1: low-touch

- ask only for clearly human-required blockers
- otherwise keep moving

### Level 2: auto

Default candidate.

- ask when the operator encounters a conceptually novel situation not covered by accepted policy
- do not ask repeatedly for already-settled classes of decision

### Level 3: consultative

- ask for material direction changes
- ask before major branch abandonment or objective reinterpretation

### Level 4: supervised

- ask frequently
- prefer confirmation before consequential new branches

## Policy Learning

Approved user decisions should become project-local policy entries.

Candidate fields:

- scope
  - project
  - objective family
  - agent family
- trigger pattern
- accepted resolution
- confidence / approval source
- reversibility
- created_from_operation_id

This should look like operator policy memory, not like hidden prompt sludge.

## Novelty Detection

The operator should not ask "what do I do?" just because the surface text changed.

Novelty should likely be judged from structured dimensions such as:

- decision class
- affected system boundary
- reversibility
- policy coverage
- conflict with prior approved policy

## Failure Modes

### 1. Silent policy creep

If every user answer becomes a policy forever, the operator will drift into accidental rigidity.

### 2. False novelty

If novelty detection is too sensitive, the operator becomes annoying.
If too weak, it becomes overconfident.

### 3. Hidden deferral debt

Level 0 autonomy is only safe if deferred branches remain visible and prioritized for later
human attention.

### 4. Policy leakage across projects

Project-local policies should not automatically become global operator dogma.

## Near-Term ADR Candidates

1. User involvement levels and decision escalation rules
2. Project-local policy memory schema
3. Novelty detection and policy-match semantics
4. Deferred-branch model for unattended execution
5. Human-required blocker classification
