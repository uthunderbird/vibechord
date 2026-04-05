# ADR 0028: Add Explicit Answer-Time Policy Promotion

## Status

Accepted

## Context

`operator` already has the core pieces of the policy loop:

- typed attention requests
- explicit answering via `operator answer`
- explicit policy promotion via `operator policy record --attention ...`
- and active project policy injected back into future runs

But the current workflow still has a product-level seam.

When the operator raises a `policy_gap` or other reusable attention item, the human often wants to
do two things at once:

- answer the immediate question
- and promote that answer into durable project policy

Today that requires two separate CLI steps. The workflow stays explicit, but it is heavier than the
product vision wants at the exact point where the operator is supposed to learn reusable precedent.

That extra friction risks a bad middle state:

- policy promotion exists on paper
- but users underuse it in live work
- so the operator keeps re-asking questions it should already know how to handle

## Decision

`operator` will support explicit answer-time policy promotion from the existing `answer` command.

The combined workflow remains explicit:

- the user must opt in with `--promote`
- the answer text remains the immediate attention resolution
- and the durable policy entry is still created through the existing `record_policy_decision`
  command path

The first slice will:

- let `operator answer` enqueue the attention answer and policy-promotion commands together
- target the same attention request for provenance
- preserve explicit category, title, text, and rationale overrides when supplied
- and otherwise reuse the answered attention item as the policy source of truth

This decision does not make policy promotion automatic.
It only makes the explicit workflow first-class and low-friction.

## Alternatives Considered

- Option A: keep policy promotion as a separate second command
- Option B: automatically promote some answers into policy
- Option C: add explicit combined answer-time promotion

Option A was rejected because the workflow remains technically complete but practically underused.

Option B was rejected because it recreates the silent-policy-creep risk already rejected by
ADR 0019.

Option C was accepted because it closes the operator learning loop without weakening auditability
or provenance.

## Consequences

- The policy workflow becomes easier to use during live attention handling.
- The operator can accumulate reusable project precedent faster without hiding the promotion step.
- The implementation can stay thin by reusing the existing command inbox and policy record path.
- This ADR still does not define automatic promotion, policy applicability matching, or novelty
  detection semantics.
