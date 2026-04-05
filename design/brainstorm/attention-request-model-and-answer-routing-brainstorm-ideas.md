# Attention Request Model And Answer Routing Brainstorm Ideas

## Status

Brainstorm only. Not architecture truth.

## Why This Topic Matters

The future command inbox becomes much more useful if the operator can ask for attention in a
typed way and then accept a typed human answer back.

Without that, the system falls back to:

- generic `BLOCKED`
- prose-only questions in logs
- and freeform human replies with weak provenance

That is too mushy for a true harness.

## Grounding In Current Runtime

Today the runtime can:

- mark an operation `BLOCKED`
- emit `REQUEST_CLARIFICATION`
- surface `WAITING_INPUT` from adapters as an incomplete result
- and detect escalation-like patterns in agent results

But it does not yet have:

- a first-class `AttentionRequest`
- a queue of open attention items
- typed resolution states
- or deterministic routing of a human answer back to one specific open issue

So today the system knows that "human input is needed" only in a coarse way.

## Core Thesis

The operator needs a first-class `AttentionRequest` model.

An attention request should be:

- durable
- typed
- scoped
- visible in CLI/TUI
- and explicitly resolvable

Human answers should target attention requests, not just the operation in general.

## Candidate Attention Types

The most useful first taxonomy looks like:

### 1. `question`

The operator needs a concrete answer from the user.

Examples:

- which strategic route to take
- whether a repo should be created
- whether a risky cleanup is acceptable

### 2. `approval_request`

The action is known, but policy requires explicit human approval.

Examples:

- destructive action
- external write outside allowed roots
- high-risk production-facing step

### 3. `policy_gap`

The operator sees a recurring or important decision with no established project rule.

Examples:

- how to treat manual testing debt
- whether to auto-run red team for certain change classes
- whether to prioritize backlog growth or implementation

### 4. `conflicting_evidence`

Different agents, tests, or artifacts disagree.

Examples:

- one agent says task is complete, another says not
- tests pass, but red-team says the vision is not met

### 5. `blocked_external_dependency`

The operator cannot progress without an external dependency the user may need to resolve.

Examples:

- missing credentials
- required repo access
- missing third-party service state

### 6. `novel_strategic_fork`

The operator has encountered a conceptually new situation that likely requires user judgment,
especially in `auto` involvement mode.

This is the most direct bridge to autonomy levels.

## Candidate Attention Envelope

The runtime likely needs something like:

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

The goal is not a huge form model.
The goal is to make human-required intervention explicit and addressable.

## Strongest Design Principle

Attention requests should be created as explicit control-plane records, not only as prose in
brain rationale or final summaries.

This lets the system:

- show an attention queue in CLI/TUI
- accept typed answers
- reason about blocked vs deferred work
- learn policy from resolved items

## Blocking Vs Non-Blocking Attention

The runtime needs a distinction between:

- `blocking` attention
  - the current path cannot proceed until resolved
- `non-blocking` attention
  - the operator wants user input, but other work may continue

This matters directly for unattended or low-involvement modes.

Without this split, the operator will either:

- over-block,
- or bury important user-facing questions in logs.

## Answer Routing

Human answers should not be free-floating notes whenever possible.

The preferred model:

1. operator creates `AttentionRequest`
2. human replies with `answer_attention_request`
3. the answer references one `attention_id`
4. runtime marks that request resolved
5. operator replans with that answer now part of explicit control truth

This creates clean provenance:

- what was asked
- who answered
- what answer was given
- what policy or plan changed afterward

## Relation To Involvement Levels

Involvement mode should influence:

- which situations become attention requests
- which types are blocking
- whether the operator can defer one branch and continue others

Examples:

### Level 0: unattended

- only hard-stop or policy-critical items become blocking attention
- strategic questions should become deferred branches where possible

### Level 1: auto

- novel strategic forks and unresolved policy gaps create attention requests
- but ordinary tactical questions should be resolved autonomously where precedent exists

### Level 2+: collaborative / approval-heavy

- more situations become visible attention requests
- more of them are blocking

## Relation To Current `BLOCKED`

The future model should not eliminate `OperationStatus.BLOCKED`.

Instead:

- `BLOCKED` should mean the operation cannot currently proceed
- `AttentionRequest` should explain why

So the runtime would move from:

- one coarse blocked summary

to:

- blocked because `attention_request=<id>` remains open

That is much more inspectable.

## Suggested Resolution States

Attention items likely need:

- `open`
- `answered`
- `resolved`
- `superseded`
- `expired`

Why both `answered` and `resolved`:

- the user may have answered
- but the operator may not yet have replanned and fully incorporated that answer

This mirrors the broader command split between:

- deterministic receipt
- and downstream behavioral consequence

## Policy Learning Link

Some resolved attention items should be promotable into project-local policy.

Examples:

- how to handle external-doc sync
- whether certain red-team steps are mandatory
- how to treat manual-only testing requirements

Important constraint:

Not every answer should become policy automatically.

Likely needed:

- explicit `promote_to_policy`
- or human confirmation after resolution

## Risks And Tradeoffs

### Positive

- makes human-required intervention explicit
- gives future TUI a clean attention queue
- improves provenance and auditability
- connects naturally to involvement levels and policy learning

### Risks

- taxonomy sprawl
- over-classifying trivial questions
- forcing structured answers where freeform notes would do
- turning simple clarification into too much ceremony

## Design Warning

The first version does not need a rich decision tree of attention types.

It only needs a small taxonomy that cleanly separates:

- user question
- approval
- policy gap
- external blocker
- novel strategic fork

That is enough to power routing and UI.

## Recommended V1 Slice

1. `AttentionRequest` domain object
2. first attention types:
   - `question`
   - `approval_request`
   - `policy_gap`
   - `blocked_external_dependency`
   - `novel_strategic_fork`
3. `answer_attention_request` command
4. operation state stores:
   - open attention items
   - resolved attention items
5. `inspect` and `trace` show attention queue
6. `BLOCKED` operations should point to the open attention id that caused the block

## Recommended ADR Topics

1. `attention request taxonomy and lifecycle`
2. `answer routing to explicit attention items`
3. `blocking vs non-blocking attention semantics`
4. `attention requests as input to involvement-level policy`
5. `policy promotion from resolved attention items`

## Working Conclusion

The operator should stop asking for human help only through prose and blocked summaries.

It should instead create typed attention requests and accept typed answers routed back to those
requests.

That is the cleanest bridge between:

- true harness control
- human involvement levels
- policy learning
- and future TUI attention surfaces
