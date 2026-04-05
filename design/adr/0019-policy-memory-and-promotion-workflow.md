# ADR 0019: Policy Memory And Promotion Workflow

## Status

Accepted

## Context

[ADR 0016](/Users/thunderbird/Projects/operator/design/adr/0016-attention-request-taxonomy-and-answer-routing.md)
introduces typed `AttentionRequest` objects and explicit answer routing.

[ADR 0017](/Users/thunderbird/Projects/operator/design/adr/0017-involvement-levels-and-autonomy-policy.md)
introduces involvement levels and makes future autonomy depend partly on existing project policy.

[ADR 0018](/Users/thunderbird/Projects/operator/design/adr/0018-project-profile-schema-and-override-model.md)
defines project profiles as hand-authored declarative defaults rather than a home for learned
runtime truth.

These decisions create the next missing boundary:

- how should approved user decisions become reusable project policy
- and how should that policy remain explicit, inspectable, and revocable

The system needs this because future `auto` and `unattended` behavior depends on more than:

- objective text
- harness instructions
- and global runtime rules

It also depends on project-specific precedent such as:

- what counts as sufficient testing here
- when to run red team
- how to handle manual-testing debt
- how to treat external canonical-doc synchronization
- whether certain repo bootstrap steps should be automatic

Without a first-class policy memory model, the system risks one of two bad outcomes:

### Failure mode 1: silent policy creep

If every accepted answer or user message silently hardens into policy, the operator will
accumulate accidental rules with weak provenance and no clear revocation path.

### Failure mode 2: no reusable precedent

If approved decisions never become reusable policy, the operator will repeatedly ask the same
questions and fail to become meaningfully more autonomous over time.

The project therefore needs an explicit model for:

- policy entries
- promotion into policy
- provenance
- and later revocation or supersession

## Decision

`operator` will introduce explicit project-local policy memory and require policy promotion to be
an explicit, inspectable workflow rather than an automatic side effect of every interaction.

The core decision is:

- policy memory is a first-class control-plane layer
- distinct from project profiles
- distinct from task memory
- distinct from session memory
- and distinct from one-off user answers

The operator may learn from prior approved decisions, but only decisions that have been
explicitly promoted into policy should gain durable reusable authority.

## What Counts As Policy

Project-local policy entries are reusable project-specific rules or precedents that the operator
may rely on in future similar situations.

Examples:

- testing sufficiency expectations
- repo bootstrap preferences
- whether a red-team step is mandatory for certain changes
- how to handle manual-only testing requirements
- how to treat external canonical-doc sync
- preferred commit or publication workflow rules

Policy is not:

- a one-off tactical instruction
- a transient branch note
- a raw agent transcript
- or generic configuration better expressed in a project profile

## Policy Vs Profile

This ADR preserves the boundary established in ADR 0018.

Project profile:

- hand-authored declarative defaults
- stable project configuration

Policy memory:

- runtime-derived and provenance-bearing learned project precedent

Profiles may contain default preferences.
Policy memory contains decisions learned or confirmed through operation history.

They may later be layered together, but they must remain distinguishable.

## Policy Promotion Rule

The default rule is:

- approved answers and accepted decisions do not become durable policy automatically

Instead, policy promotion should require one of:

- an explicit `record_policy_decision` command
- an explicit `promote_to_policy` action on a resolved attention item
- or another equally explicit promotion workflow

This avoids silent policy creep.

The operator may still reference:

- prior answered attention items
- or prior accepted routes

as local history.

But only promoted policy entries should count as durable reusable precedent for future autonomy
decisions.

## Candidate Policy Entry Shape

The runtime likely needs a model like:

```python
class PolicyEntry(BaseModel):
    policy_id: str
    project_scope: str
    title: str
    category: PolicyCategory
    rule_text: str
    rationale: str | None = None
    source_refs: list[PolicySourceRef] = Field(default_factory=list)
    status: PolicyStatus = PolicyStatus.ACTIVE
    created_at: datetime
    superseded_by: str | None = None
```

The important point is not the exact field list.
The important point is that policy must have:

- explicit content
- provenance
- lifecycle
- and revocability

## Source Of Policy Truth

The most useful sources for policy promotion will be:

- resolved attention requests
- explicit human approvals
- explicit route approvals or rejections
- explicit operator-user command exchanges recorded in the command history

Policy should not be inferred from:

- ambiguous freeform chat alone
- or raw agent outputs without human ratification

This keeps policy tied to actual accepted human judgment.

## Policy Lifecycle

The policy layer should support at least:

- `active`
- `revoked`
- `superseded`

The runtime should preserve prior policy history rather than rewriting it silently.

If one rule replaces another, supersession should be explicit.

This is important because:

- future autonomy decisions may depend on the current active policy set
- but auditability requires a trail of how the policy set changed

## Relation To Involvement Levels

Involvement levels decide how willing the operator is to proceed without asking.

Policy memory decides what approved precedent the operator may rely on when making that choice.

The intended relationship is:

- stronger policy coverage reduces unnecessary interruptions at a given involvement level
- but involvement level still determines when novelty, risk, or policy gaps must be surfaced as
  attention requests

So policy memory supports autonomy.
It does not replace involvement policy.

## Relation To Attention Requests

Resolved attention items are the natural source material for policy promotion.

A useful future workflow is:

1. operator raises `policy_gap` attention
2. user answers or approves a route
3. attention item becomes resolved
4. user or operator explicitly promotes that resolution into `PolicyEntry`
5. future runs may rely on that policy as precedent

This makes the path from:

- novel question
- to accepted answer
- to durable precedent

explicit and auditable.

## Initial Implementation Notes

The first accepted slice implements:

- explicit file-backed `PolicyEntry` records under the operator data directory
- human-invoked CLI promotion via `operator policy record`
- explicit promotion from a resolved attention item via `operator policy record --attention ...`
- inspectable listing and inspection via `operator policy list` and `operator policy inspect`
- revocation without deletion via `operator policy revoke`
- inclusion of active project policy in `run --project ...` goal context

The first accepted slice does not yet implement:

- automatic promotion from resolved attention items
- policy applicability matching beyond explicit project inclusion
- or novelty detection for policy gaps

## Non-Goals

This ADR does not define:

- the full matching algorithm for when a policy entry applies
- the novelty-detection algorithm that decides policy coverage is missing
- the final user interface for policy inspection and editing
- secret or sensitive-policy handling
- or the exact storage location for project-level policy files

Those are follow-up decisions.

This ADR also does not require every approved answer to be promotable automatically.

It only requires that:

- durable reusable policy must come through an explicit promotion path

## Minimum Requirements

The stronger guarantee of this ADR depends on several minimum rules:

- project-local policy memory must be distinct from project profiles
- policy promotion must be explicit, not automatic
- policy entries must be inspectable and auditable
- policy entries must support revocation or supersession
- source provenance must be preserved
- future autonomy decisions should rely only on active policy entries, not on vague historical
  chat memory

## Alternatives Considered

### Option A: Automatically treat every accepted answer as durable policy

Rejected because:

- it creates silent policy creep,
- weakens provenance,
- and makes accidental past judgments too sticky.

### Option B: Keep no durable project policy memory at all

Rejected because:

- the operator would repeatedly ask the same questions,
- `auto` and `unattended` would remain weak,
- and the system would fail to benefit from prior accepted precedent.

### Option C: Introduce explicit project-local policy memory with explicit promotion workflow

Accepted because:

- it balances autonomy with auditability,
- preserves a clean distinction between one-off answers and durable precedent,
- and supports future involvement-level behavior without hiding policy drift.

## Consequences

### Positive

- The operator can become more autonomous over time without inventing hidden rules.
- Reusable project precedent gains explicit provenance.
- Future `auto` and `unattended` behavior can rely on something more disciplined than prompt
  memory.
- Users retain the ability to inspect, revoke, and supersede policy deliberately.

### Negative

- The runtime gains another durable concept that must be kept understandable.
- The system still needs future work to define policy matching and editing ergonomics.
- Users may underuse policy promotion if the workflow is too heavy.

### Follow-Up Implications

- A follow-up ADR should define policy inspection, editing, and revocation surfaces.
- A follow-up ADR should define policy applicability and matching semantics.
- The implementation will likely need:
  - `PolicyEntry`
  - `PolicyStatus`
  - `PolicyCategory`
  - and explicit links from resolved attention items or command history into policy provenance
