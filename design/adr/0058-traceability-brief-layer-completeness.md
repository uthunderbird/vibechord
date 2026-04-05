# ADR 0058: Traceability brief layer completeness

## Status

Accepted

## Context

The traceability model defines six layers from raw agent output to human-readable report. Layer 4
(`TraceBriefBundle`) is the operation-scope view — the layer that post-hoc consumers (report
generation, CLI history views, dashboard) query to answer "what happened in this operation?" without
reading raw events.

Three gaps existed in this layer:

### Gap 1: `refs` field — no typed vocabulary

`refs: dict[str, str]` appeared on `IterationBrief`, `DecisionMemo`, and `TraceRecord`. The
field carried cross-layer navigation references (operation_id, iteration, task_id, session_id,
artifact_id, command_id), but the key names and value semantics were undocumented and unchecked.
Any code could store arbitrary keys; no reader could rely on a specific key being present or having
a consistent meaning. `AgentTurnBrief` was already well-typed: it uses separate list fields
(`artifact_refs`, `raw_log_refs`, `wakeup_refs`).

Grounding: `_build_refs()` in `service.py` revealed the actual keys in use:
`operation_id`, `iteration` (stored as `str(int)`), `task_id`, `session_id`, `artifact_id`,
`command_id`. This is a closed set for structured types; `TraceRecord` is a generic carrier that
legitimately needs extensible keys (`policy_id`, `wakeup_id`, `attention_id` as new event paths
are added).

### Gap 2: Command history absent from brief layer

`command.*` domain events exist in the event stream (Layer 1) but have no representation in
`TraceBriefBundle`. Post-hoc consumers wanting command history had to scan the raw event log.
This violated the layer-separation principle: the brief layer should be sufficient for post-hoc
queries; the event stream is for real-time streaming consumers.

Note: `cli/main.py` reads `command.*` events live during an attached run — this is a real-time
stream subscription and is not a layer violation. The violation risk was for post-hoc consumers
(report generation, etc.).

### Gap 3: Evaluation verdict absent from brief layer

`evaluation.completed` trace events carry the brain's per-iteration verdict (continue / stop /
block) but had no representation in `TraceBriefBundle`. A post-hoc consumer wanting to understand
why an operation ran for N iterations had to scan raw events. There was also no structured history
of evaluation outcomes accessible at the brief layer.

## Decision

### Typed `refs` vocabulary — split by type role

`refs` fields are typed differently based on whether the type has a predictable vs. extensible
key set:

**`DecisionMemo.refs` and `IterationBrief.refs`** use a `TypedRefs` Pydantic model with a closed
key set:

```python
class TypedRefs(BaseModel):
    operation_id: str
    iteration: int | None = None   # int, not str — fixes historical str(int) convention
    task_id: str | None = None
    session_id: str | None = None
    artifact_id: str | None = None
    command_id: str | None = None
```

`iteration` is typed as `int` (not `str`) — this corrects the historical `str(int)` convention
used by `_build_refs()`. The migration window is now, before any external consumers of serialized
refs exist.

**`TraceRecord.refs`** remains `dict[str, str]`. `TraceRecord` is an extensible carrier and must
support keys that do not exist at schema-definition time. The standard vocabulary is:

| Key | Value |
|---|---|
| `operation_id` | operation UUID |
| `iteration` | iteration index as string |
| `task_id` | task UUID |
| `session_id` | agent session UUID |
| `command_id` | command UUID |

**`AgentTurnBrief`** is unchanged — it already uses typed list fields.

Rationale for the split: a `TypedRefs` model for `TraceRecord` would require an escape hatch
(`other: dict[str, str]`) immediately, collapsing back to a dict. Splitting the design by type
role avoids this. `dict[Literal[key_names], str]` was considered as an alternative for
`TraceRecord` but Pydantic v2 does not enforce Literal dict keys at runtime — the benefit would
be mypy-only.

### `CommandBrief` added to `TraceBriefBundle`

```python
class CommandBrief(BaseModel):
    operation_id: str
    command_id: str
    command_type: str          # OperationCommandType.value
    status: str                # CommandStatus.value: "applied" | "rejected"
    iteration: int             # iteration index when the command was processed
    applied_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
```

Written at the terminal command event — `command.applied` or `command.rejected`. A command that
is `accepted_pending_replan` is not written until it reaches its terminal state.

`TraceBriefBundle` gains `command_briefs: list[CommandBrief] = Field(default_factory=list)`.

`OperationCommand` (the domain entity) was not reused directly because it is a mutable entity
whose status changes during its lifecycle. Brief records are immutable snapshots of terminal state.

### `EvaluationBrief` added to `TraceBriefBundle`

```python
class EvaluationBrief(BaseModel):
    operation_id: str
    iteration: int
    goal_satisfied: bool
    should_continue: bool
    summary: str
    blocker: str | None = None
```

Written when `evaluation.completed` fires (once per loop iteration). `EvaluationBrief` is an
immutable projection of the `Evaluation` domain type.

`TraceBriefBundle` gains `evaluation_briefs: list[EvaluationBrief] = Field(default_factory=list)`.

## Consequences

- `domain/traceability.py`: add `TypedRefs`, `CommandBrief`, `EvaluationBrief`; update
  `DecisionMemo.refs` and `IterationBrief.refs` to use `TypedRefs`; add `command_briefs` and
  `evaluation_briefs` to `TraceBriefBundle`
- `application/service.py`: update `_build_refs()` to return `TypedRefs`; add `CommandBrief`
  write at `command.applied` / `command.rejected` emit sites; add `EvaluationBrief` write at
  `evaluation.completed` emit site
- `runtime/trace.py`: add `append_command_brief` and `append_evaluation_brief` methods to
  `FileTraceStore`
- All callers of `_build_refs()` receive a `TypedRefs` object instead of `dict[str, str]` —
  any code that accessed `refs["iteration"]` as a string must be updated to `refs.iteration`
- `TraceRecord.refs` callers are unaffected — the type remains `dict[str, str]`
