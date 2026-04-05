# Involvement Levels And Policy Learning Brainstorm Ideas

## Purpose

This note is a brainstorming artifact, not a final architecture decision.

The target theme is how much autonomy the operator should exercise, when it should ask the user, and how approved decisions become reusable project policy.

## Core Thesis

The operator should not have a single fixed human-in-the-loop behavior.

Different situations and different times of day demand different autonomy levels.

The system needs:

- an explicit involvement model,
- a novelty and uncertainty model,
- and a project-local policy memory that can absorb approved decisions.

## Candidate Involvement Levels

### Level 0: unattended

The user is away.

The operator should:

- continue work autonomously where policy allows,
- defer blocked branches that truly require the human,
- and avoid waking the user except for configured hard-stop conditions.

### Level 1: auto

This should likely be the default.

The operator should ask the user when it encounters a conceptually novel situation that cannot be resolved confidently from:

- existing project policy,
- prior accepted decisions,
- current objective and harness,
- or deterministic runtime rules.

### Level 2: collaborative

The operator asks more readily before major route changes, strategic reprioritization, or destructive actions.

### Level 3: approval-heavy

The operator asks before many classes of consequential decisions.

This is useful for high-risk or unfamiliar projects.

## Novelty And Attention Model

The operator needs more than "confidence".

It needs to detect:

- conceptually new situations,
- unresolved policy gaps,
- repeated failed attempts,
- conflicting evidence from agents,
- and major strategic forks.

Those should become explicit `attention requests`, not just prose in logs.

## Policy Learning

User-approved decisions should be promoted into project-local policy memory.

Examples:

- preferred behavior for repo creation
- what counts as sufficient testing in this project
- whether to auto-run swarm red team for risky changes
- how to handle external-doc sync or manual testing debt

Important constraint:

Policy memory should not silently mutate from every interaction.

It should require explicit promotion of:

- accepted answer,
- accepted route,
- or accepted rule.

## Storage Implications

Likely new durable categories:

- `policy entries`
- `attention requests`
- `resolved decisions`
- `autonomy profile`

These are not the same as task memory or session memory.

## Risks And Tradeoffs

- If "auto" is too eager to ask, the operator becomes annoying.
- If "auto" is too reluctant, it will invent policy in unsafe places.
- If novelty detection is implicit and LLM-only, behavior will be inconsistent.
- If every answer becomes policy automatically, the project will accumulate contradictory rules.
- If involvement level is global only, mixed-sensitivity projects will be awkward.

## Recommended Next ADR Topics

1. User involvement levels and autonomy policy model
2. Attention request semantics and novelty detection boundaries
3. Project-local policy memory and promotion workflow
4. Deferred-branch behavior under unattended mode
5. Human decision provenance and policy supersession rules
