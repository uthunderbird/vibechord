# ADR 0016: Attention Request Taxonomy And Answer Routing

## Status

Accepted

## Context

[ADR 0013](/Users/thunderbird/Projects/operator/design/adr/0013-operation-command-inbox-and-command-envelope.md)
introduces a first-class command inbox for live human intervention.

[ADR 0014](/Users/thunderbird/Projects/operator/design/adr/0014-deterministic-command-reducer-vs-brain-mediated-replanning.md)
separates deterministic command control from brain-mediated replanning.

[ADR 0015](/Users/thunderbird/Projects/operator/design/adr/0015-scheduler-state-and-pause-semantics-for-attached-runs.md)
defines the first scheduler-state and pause semantics for attached runs.

These decisions make a broader human-in-the-loop gap more visible:

- the operator can currently become `BLOCKED`
- the brain can emit `REQUEST_CLARIFICATION`
- adapters can surface `WAITING_INPUT`
- and escalation-like patterns can be detected in agent results

But the runtime still lacks a first-class model for:

- what exactly needs human attention,
- whether that attention is blocking,
- how it should be shown to the user,
- and how a human answer should route back into the running operation.

Without that, the system falls back to coarse, mushy behavior:

- one generic blocked state,
- prose-only questions in logs or summaries,
- and freeform human replies with weak provenance.

That is not strong enough for a true harness or for a future live TUI.

The runtime needs a first-class attention model that:

- makes human-required intervention explicit,
- links blocked status to concrete attention items,
- and allows human answers to target a specific unresolved issue.

## Decision

`operator` will introduce a first-class `AttentionRequest` model and explicit answer routing
through `attention_id`.

An attention request should be:

- durable
- typed
- scoped
- visible in CLI and future TUI surfaces
- and explicitly resolvable

The core decision is:

- human-required intervention should be represented as explicit control-plane objects
- not only as freeform blocked summaries or transient prose in logs

The initial model should include a structure like:

```python
class AttentionRequest(BaseModel):
    attention_id: str
    operation_id: str
    attention_type: AttentionType
    severity: AttentionSeverity
    target_scope: CommandTargetScope
    target_id: str | None = None
    title: str
    question: str
    context_brief: str | None = None
    suggested_options: list[str] = Field(default_factory=list)
    blocking: bool = True
    created_at: datetime
    status: AttentionStatus = AttentionStatus.OPEN
    resolved_at: datetime | None = None
    resolution_summary: str | None = None
```

Human answers should route through an explicit command such as:

- `answer_attention_request(attention_id=..., payload=...)`

The runtime should resolve the target deterministically and then mark the attention item as:

- answered
- resolved
- superseded
- or expired

as appropriate.

## Initial Taxonomy

The initial attention taxonomy should remain small and high-value.

The first useful set is:

- `question`
- `approval_request`
- `policy_gap`
- `blocked_external_dependency`
- `novel_strategic_fork`

Additional categories may be added later, but the first implementation should avoid taxonomy
sprawl.

## Blocking Vs Non-Blocking Attention

The attention model must distinguish:

- blocking attention
- non-blocking attention

Blocking means:

- the current path cannot proceed until this attention request is resolved

Non-blocking means:

- the operator wants human input
- but other work may continue if policy permits

This distinction is required to support future unattended and low-involvement modes without
forcing every question into a full stop.

## Relationship To `OperationStatus.BLOCKED`

This ADR does not remove `OperationStatus.BLOCKED`.

Instead, it refines its meaning.

The intended runtime shape is:

- `BLOCKED` remains the coarse operation truth that work cannot currently proceed
- one or more open attention requests explain why

So the system moves from:

- a generic blocked summary

to:

- blocked because `attention_request=<id>` remains open

This is more inspectable and easier to surface in CLI and TUI views.

## Answer Routing Semantics

Human answers should not be treated as generic notes whenever the target issue is known.

The preferred flow is:

1. operator creates `AttentionRequest`
2. user submits `answer_attention_request`
3. the command references one `attention_id`
4. the runtime links the answer to that attention item deterministically
5. the attention item transitions through explicit lifecycle states
6. the operator replans with the resolved answer now part of control-plane truth

Important rule:

- the runtime determines whether the answer references a real open attention item
- the operator brain may decide what to do next after that answer is accepted

This preserves the same deterministic-vs-brain-mediated split established in ADR 0014.

## Attention Lifecycle

The attention model should distinguish at least:

- `open`
- `answered`
- `resolved`
- `superseded`
- `expired`

Why both `answered` and `resolved`:

- a user may have supplied an answer
- but the operator may not yet have fully incorporated that answer into its next plan

This mirrors the distinction between:

- accepted control-plane truth
- and downstream behavioral consequence

## Relation To Involvement Levels

This ADR does not define the full involvement-level model.

But it does define a substrate that future involvement semantics will need.

Involvement mode should eventually influence:

- which situations generate attention requests
- which types are blocking
- and whether the operator may defer one branch and continue others

That future policy depends on having explicit attention objects first.

## Relation To Policy Learning

Some resolved attention requests will be candidates for project-local policy promotion.

Examples:

- how to treat manual-testing debt
- whether a certain review step is mandatory
- how to handle external-doc synchronization

This ADR does not define policy-promotion workflow.

It only establishes that:

- resolved attention items should have enough provenance to support later policy promotion

## Non-Goals

This ADR does not define:

- the full involvement-level policy model
- the final policy-memory and supersession model
- the full user-interface rendering of attention queues
- or the complete command model for every possible human interaction

It also does not require every human message to become an attention request.

Freeform notes and operator messages may still exist.

The point is that explicit human-required intervention should no longer rely only on prose.

## Minimum Requirements

The stronger guarantee of this ADR depends on several minimum rules:

- attention requests must be durable and inspectable
- each attention request must belong to one operation
- answer routing must target a specific `attention_id`
- invalid or stale answer targets must be rejected explicitly
- blocking attention must be distinguishable from non-blocking attention
- blocked operations should surface the open attention item that explains the block
- attention provenance should be visible in trace and inspection surfaces

## Alternatives Considered

### Option A: Keep using generic blocked summaries and freeform clarification

Rejected because:

- it weakens provenance,
- makes human intervention harder to inspect,
- and gives future TUI work too little structured runtime truth.

### Option B: Treat all human replies as generic operator messages

Rejected because:

- it loses the link between the answer and the question,
- weakens deterministic routing,
- and makes blocked-state reasoning less explicit.

### Option C: Introduce typed attention requests and answer routing by `attention_id`

Accepted because:

- it makes human-required intervention explicit,
- preserves auditability and provenance,
- supports future involvement-level behavior,
- and gives the live UI a clean attention queue substrate.

## Consequences

### Positive

- The operator can explain human-required intervention explicitly.
- Blocked state becomes more inspectable.
- Human answers gain stronger provenance.
- Future TUI and CLI surfaces can render an attention queue honestly.
- Later policy-learning work gains better source material.

### Negative

- The runtime and persisted state become richer.
- The project must define attention severity, lifecycle, and answer UX carefully.
- Over-classification is a risk if the taxonomy grows too fast.

### Follow-Up Implications

- The runtime will likely need `AttentionType`, `AttentionSeverity`, and `AttentionStatus`
  models.
- A follow-up ADR should define involvement-level behavior over blocking and non-blocking
  attention.
- A follow-up ADR should define policy promotion and supersession for resolved attention items.
- `inspect`, `trace`, and future live monitoring surfaces should display open and resolved
  attention items explicitly.
