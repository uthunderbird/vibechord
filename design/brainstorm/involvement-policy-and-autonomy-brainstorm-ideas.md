# Involvement Policy And Autonomy Brainstorm Ideas

## Status

Brainstorm only. Not architecture truth.

## Context

The operator should support different user involvement levels.

The motivating use cases include:

- unattended overnight work,
- default adaptive behavior,
- and higher-touch modes where the operator asks more often.

The user also wants accepted decisions to become project-local policy over time.

## Core Thesis

User involvement should be modeled as an explicit autonomy policy, not as a vague prompt convention.

The operator needs a deterministic layer that decides:

- when it may continue autonomously,
- when it should ask the user,
- and what it should do when the user is unavailable.

## Main Design Axes

### 1. Availability vs authority

Separate:

- whether the user is available now,
- from whether the operator is authorized to decide without them.

A user can be unavailable, but the operator may still have authority to proceed under policy.

### 2. Novelty detection

The default `auto` mode should ask the user when the operator encounters a conceptually new case not already covered by accepted project policy.

This implies a policy memory layer, not just prompt text.

### 3. Policy capture

When the user answers a novel question, the result should be capturable as a reusable project policy candidate.

Those policies should be:

- inspectable,
- scoped,
- revisable,
- and attributable to a decision event.

### 4. Deferred fronts

At low involvement levels, blocked fronts should be postponed rather than stalling the whole operation if other actionable work remains.

This implies the scheduler must reason in fronts or tasks, not one serial thread only.

## Likely Architecture Direction

### Involvement levels

Possible first model:

- `zero`
  - no human expected
  - operator must defer human-required fronts
- `auto`
  - ask on conceptually novel or high-impact policy gaps
- `guided`
  - ask more often on major branching choices
- `manual`
  - require approval for many decisions

### Policy memory

Introduce a project-scoped policy journal with entries like:

- condition or situation pattern
- accepted decision
- scope
- confidence
- source event or conversation
- whether it is user-approved or operator-inferred

### Human question semantics

Questions to the user should be first-class pending items with:

- question type
- affected scope
- blocking severity
- whether other fronts may continue

## Risks And Tradeoffs

### Positive

- makes autonomy adjustable without rewriting prompts,
- creates project-specific learning,
- and reduces repetitive human arbitration.

### Risks

- novelty detection can become vague or overclaiming,
- bad policy capture can silently encode poor past choices,
- and too much automation can hide when the operator is actually guessing.

### Design warning

Do not let "auto" mean "ask rarely because that feels smoother."
It should mean "ask when policy coverage is genuinely missing."

## Recommended ADR Topics

1. `user involvement levels and autonomy policy model`
2. `project-scoped policy memory and approval provenance`
3. `novelty detection and policy-gap escalation semantics`
4. `defer-vs-block scheduling behavior under low involvement`
