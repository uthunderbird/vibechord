# RFC 0007: Traceability Layer Model

## Status

Accepted — Implemented

## Context

The operator produces a significant volume of operational data: raw agent output, domain events,
LLM inputs and outputs, per-iteration summaries, turn-by-turn structured records, and a human
narrative report. Without a canonical model that names each layer, defines what it contains, who
writes it, and who reads it, these artefacts risk collapsing into an undifferentiated pile.

Concretely, the gap prior to this RFC was:

- `TraceRecord` and `IterationBrief` co-existed with no formal model explaining their relationship
  or the read path from one to the other.
- `CommandBrief` and `EvaluationBrief` existed in the domain model but had no documented place in
  the brief layer and no guidance for when they should be written vs read from raw events.
- The `FileTraceStore` method table had no layer mapping, making it unclear which methods write
  to which persistence granularity.
- The two-stream distinction (event stream vs narrative timeline) was implicit in code comments but
  not specified in any canonical document.

## Decision

### Six-Layer Model

The traceability model is organized around the question each layer answers. Six layers exist, from
raw agent output at the bottom to a human narrative at the top.

**Layer 0 — Raw agent output** (outside `FileTraceStore`)

- Produced by: agent adapters (ACP log files, Claude session logs, Codex stdout captures).
- Contains: adapter-managed raw output files and artifact files.
- `FileTraceStore` does not write this layer. Pathnames are referenced by
  `AgentTurnBrief.raw_log_refs` and `AgentTurnBrief.artifact_refs`.

**Layer 1 — Event stream** (`.operator/events/{op-id}.jsonl`)

- Produced by: `OperatorService._emit()` on every domain or trace event.
- Contains: `RunEvent` objects — category, event name, payload, timestamp.
- Durability: append-only, never modified.
- Primary consumers: background worker (wakeup detection), live `watch`/`dashboard` CLI, tests,
  integration audit log.

**Layer 2 — Narrative timeline** (`.operator/runs/{op-id}.timeline.jsonl`)

- Produced by: `FileTraceStore.append_trace_record()`.
- Contains: `TraceRecord` objects — `category`, `title`, `summary`, `refs`, `payload`.
- Two categories in practice: `"decision"` (brain decision traces) and `"agent"` (turn traces).
- New categories can be added freely; `category` is a free-text string.
- Durability: append-only JSONL. Multiple records per iteration are normal.
- Primary consumers: `trace` CLI subcommand, brain history context construction.
- Relationship to Layer 1: Layer 2 is the interpreted record; Layer 1 is the fact record. The brain
  consumes Layer 2 or Layer 4 for history context — not Layer 1.

**Layer 3 — Structured summaries** (per-iteration and per-turn files under `runs/{op-id}/`)

- Produced by: `FileTraceStore.save_decision_memo()` and `FileTraceStore.append_agent_turn_brief()`.
- Contains:
  - `DecisionMemo` (`runs/{op-id}/reasoning/{iter}.json`): brain's authoritative reasoning record —
    `decision_context_summary`, `chosen_action`, `rationale`, `alternatives_considered`,
    `why_not_chosen`, `expected_outcome`, `refs`.
  - `AgentTurnBrief` (`runs/{op-id}/agents/{session-id}-{iter}.summary.json`): per-turn structured
    summary — includes `turn_summary` (`AgentTurnSummary`), `artifact_refs`, `raw_log_refs`,
    `wakeup_refs`.
- Durability: one file per iteration or per (session, iteration) pair; rewritten on update.
- Primary consumers: `trace --drill-down`, report generation, future projection consumers.

**Layer 4 — Operation-scope view** (`runs/{op-id}.brief.json`)

- Produced by: all `FileTraceStore.save_*_brief()` and `append_*_brief()` methods.
- Contains: `TraceBriefBundle` — a single JSON document with:
  - `operation_brief: OperationBrief | None` — current operation status and objective summary.
  - `iteration_briefs: list[IterationBrief]` — one entry per planning cycle; sorted by iteration.
  - `agent_turn_briefs: list[AgentTurnBrief]` — one entry per (iteration, session); mirrors Layer 3
    but inline in the bundle for O(1) operation-scope reads.
  - `command_briefs: list[CommandBrief]` — one entry per command; keyed by `command_id`.
  - `evaluation_briefs: list[EvaluationBrief]` — one entry per iteration; brain verdict history.
- Durability: single mutable JSON file; each write loads, patches, and atomically replaces.
- Primary consumers: `status` CLI, `list` CLI, `dashboard` TUI, brain context injection.

**Layer 5 — Human report** (`runs/{op-id}.report.md`)

- Produced by: `FileTraceStore.write_report()`.
- Contains: a rendered Markdown narrative synthesized from Layers 3 and 4.
- This is a render target, not a queryable layer. It is not parsed by any runtime consumer.
- Primary consumers: human operators reading a completed operation summary.

### Two-Stream Distinction

Layer 1 (event stream) and Layer 2 (narrative timeline) are complementary but distinct:

| Property | Event stream (Layer 1) | Narrative timeline (Layer 2) |
|---|---|---|
| Format | `RunEvent` JSONL | `TraceRecord` JSONL |
| Completeness | All domain + trace events | Selected operational records |
| Semantics | Fact record — what the aggregate did | Interpreted record — how the loop narrated its work |
| Category field | `"domain"` \| `"trace"` (event bucket) | `"decision"` \| `"agent"` \| ... (narrative category) |
| Primary use | Wakeup detection, audit, test assertions | Brain history, `trace` CLI |

The event stream is the authoritative fact record. A reader reconstructing operation state must be
able to do so from domain events alone. The narrative timeline is what the brain consumes for
context; reading raw events would require the brain to interpret every state machine transition.

### Cross-Layer Navigation

The canonical top-down drill-down path is:

1. **Layer 4** (`status` / `list` / `dashboard`) — operation-scope status and outcome brief.
2. **Layer 2** (`trace`) — narrative timeline, filterable by category or iteration.
3. **Layer 3** (`trace --drill-down`) — structured per-iteration reasoning and per-turn summaries,
   including `alternatives_considered` and `why_not_chosen` from `DecisionMemo`.
4. **Layer 0** — referenced via `raw_log_refs` and `artifact_refs` in `AgentTurnBrief`.

No layer should be skipped in the downward direction when building UI or CLI drill-down paths.
Jumping directly from Layer 4 to Layer 0 would bypass the structured context that makes raw output
interpretable.

### `TraceRecord.refs` and `TypedRefs`

`TraceRecord.refs` is `dict[str, str]` — a generic open-ended carrier. This is intentional:
`TraceRecord` is written by many call sites in many contexts; requiring a closed key set at the
type level would create a proliferating enum or a protocol with dozens of optional fields.

`DecisionMemo.refs` and `IterationBrief.refs` use `TypedRefs` — a closed Pydantic model with
specific optional fields (`operation_id`, `iteration`, `task_id`, `session_id`, `artifact_id`,
`command_id`). These models have a known bounded key set, so the closed type is appropriate.

Standard key names for `TraceRecord.refs`:

| Key | Value type | When to use |
|---|---|---|
| `operation_id` | `str` | Always |
| `iteration` | `str(int)` | When iteration is meaningful |
| `task_id` | `str` | When record is task-scoped |
| `session_id` | `str` | When record is session-scoped |
| `artifact_id` | `str` | When record references a produced artifact |
| `command_id` | `str` | When record references a command |

Additional keys may be added freely. No migration is required to add a new key.

### `CommandBrief` and `EvaluationBrief` in `TraceBriefBundle`

Prior to this RFC, `command.*` domain events existed in Layer 1 only. A consumer wanting the
command status history had to scan raw events. `CommandBrief` and a `command_briefs` list in
`TraceBriefBundle` expose this at Layer 4 for O(1) reads.

Similarly, `brain.evaluation` events existed only in Layer 1. An LLM consuming brain history
context would need to reconstruct per-iteration goal satisfaction from raw events. `EvaluationBrief`
and `evaluation_briefs` in `TraceBriefBundle` give the brain (and the CLI) direct access to the
verdict history at Layer 4.

Both are written at their natural event time — `CommandBrief` when a command reaches terminal state,
`EvaluationBrief` when the evaluation result is processed — not post-hoc.

### `FileTraceStore` Method → File Mapping

| Method | Layer | Path |
|---|---|---|
| `save_operation_brief(brief)` | 4 | `runs/{op-id}.brief.json` |
| `append_iteration_brief(op_id, brief)` | 4 | `runs/{op-id}.brief.json` |
| `append_agent_turn_brief(op_id, brief)` | 3 + 4 | `runs/{op-id}/agents/{sid}-{iter}.summary.json` + brief bundle |
| `append_command_brief(op_id, brief)` | 4 | `runs/{op-id}.brief.json` |
| `append_evaluation_brief(op_id, brief)` | 4 | `runs/{op-id}.brief.json` |
| `save_decision_memo(op_id, memo)` | 3 | `runs/{op-id}/reasoning/{iter}.json` |
| `append_trace_record(op_id, record)` | 2 | `runs/{op-id}.timeline.jsonl` |
| `write_report(op_id, report)` | 5 | `runs/{op-id}.report.md` |

Layer 1 is written by the event sink (`JsonlEventSink`), not `FileTraceStore`.

### Delivery Surfaces

The six-layer model maps to CLI surfaces:

| CLI surface | Layers consumed |
|---|---|
| `status` | 4 (operation brief) |
| `list` | 4 (brief bundles across operations) |
| `watch` | 1 (live event stream) |
| `dashboard` | 1 + 4 |
| `trace` | 2 (timeline), 3 (memo drill-down), 4 (brief context) |
| `tasks` / `memory` / `artifacts` | 4 or in-memory aggregate |
| `report` | 5 |

## Alternatives Considered

### Single flat JSONL for all traceability data

Rejected. Mixing `TraceRecord`, `DecisionMemo`, `AgentTurnBrief`, and `OperationBrief` in a single
file requires consumers to filter by type on every read. The per-layer split allows O(1) brief reads
at Layer 4, append-only streaming reads at Layer 2, and targeted per-iteration reads at Layer 3
without scanning the full log.

### Use `TypedRefs` for `TraceRecord.refs`

Rejected. `TraceRecord` is written at dozens of call sites across contexts not all of which have
the same ref structure. A closed type would require every call site to construct a `TypedRefs` and
silently discard keys that don't fit. The open `dict[str, str]` with a documented standard key
table achieves the discoverability goal without the type-level friction.

### Report as Layer 4 appendage

Rejected. The report is a rendered narrative for human readers, not a queryable structured
document. Embedding it in `TraceBriefBundle` would mix machine-readable structure with free-text
prose and make the brief bundle depend on a rendering pass.

## Consequences

- `FileTraceStore` is the sole writer for Layers 2–5. Layer 1 is written by `JsonlEventSink`.
  Layer 0 is written by agent adapters.
- New Layer 3 record types (analogous to `DecisionMemo`) must be added as explicit methods on
  `FileTraceStore`, not as `TraceRecord` entries in the timeline.
- New `TraceRecord.refs` keys may be added freely; no migration is required.
- Consumers that need to reconstruct operation state from scratch must use Layer 1 (domain events),
  not Layer 2 or Layer 4.
- The brain must consume Layer 2 or Layer 4 for context, not Layer 1 — this is the boundary between
  the raw fact record and the interpreted semantic record.
- `TraceBriefBundle` is a mutable JSON file read-modify-write on every write call. This is a known
  performance trade-off accepted because operation state updates are infrequent relative to the
  total operation lifetime.
