# Architecture

## Purpose

ARCHITECTURE.md is a structural reference for contributors. It describes how the vision in VISION.md is implemented: what the layers are, where the boundaries live in the code, what the key design invariants are, and how the major protocols relate. VISION.md is the normative reference for the why, the what, and the behavioral contracts. This document describes the how.

**How to navigate**: Start with System Shape and Architectural Layers for the high-level structure. Refer to Core Runtime Model and Operator Loop for execution mechanics. Use Protocols and State Objects for the contract and data surfaces. Known Technical Debt marks items that are intentionally deferred.

**Implementation status**: Present-tense statements describe implemented behavior. Future or roadmap items are marked with `> **Roadmap:**` blocks. The Known Technical Debt section lists explicitly deferred items.

## System Shape

`operator` has four major parts:

1. domain model
2. operator application loop
3. integration adapters
4. delivery surfaces

The center is the operator application loop. Everything else either informs its decisions or executes them.

## Architectural Layers

### Domain

The domain layer defines the language of the system.

Examples:

- `Operation`
- `OperationGoal`
- `OperationPolicy`
- `ExecutionBudget`
- `RuntimeHints`
- `Iteration`
- `AgentInvocation`
- `AgentResult`
- `StopReason`
- `RunEvent`

Domain objects use `pydantic` models with a bias toward small explicit types and minimal framework leakage.

`RunEvent` carries a `kind` discriminator. Note: `RunEvent(kind=WAKEUP)` is known tech debt — see Known Technical Debt section.

### Application

The application layer owns the operator loop.

Its responsibilities:

- accept a goal and runtime options,
- maintain operation state,
- ask the active operator policy/controller for the next move when needed,
- apply deterministic guardrails,
- invoke agent adapters,
- evaluate returned evidence,
- emit events,
- accept and route operator messages,
- stop when policy says to stop.

This is the layer where the system behaves like an operator rather than a collection of clients.

Inside that layer, the ideal organization is:

- `OperatorService` as the thin system shell and composition root,
- `LoadedOperation` as the one-operation runtime boundary,
- `OperatorPolicy` as the pluggable behavior seam,
- workflow-authority services as the enduring application capabilities,
- and smaller drive/execution collaborators beneath those top-level boundaries.

Current repository truth is closer to that shape than before, but not fully there yet:

- `implemented`: major workflow-authority services now exist as separate application units
- `implemented`: `LoadedOperation` exists as the one-operation local mechanics boundary
- `partial`: `OperatorService` is thinner than the earlier monolith, but still hosts some
  top-layer callback glue and several remaining control/runtime responsibility clusters

The main remaining completion work is no longer generic shell thinning.

Under `ADR 0104`, the remaining top-layer repair is understood as:

- an explicit lifecycle authority above `LoadedOperation`
- an explicit control-state synchronization/persistence authority
- and a smaller runtime gating/runtime-context capability boundary

Those boundaries are the intended reason the shell can become smaller, rather than shell size
being the primary architectural goal in itself.

The application layer handles **operator messages** (`message op-id "..."`): free-form context
injected into the brain's next planning decision. Messages are not typed commands — they do not
directly mutate persisted state but shape the brain's next deliberation. Each message persists
in the brain's context for a configurable number of planning cycles (the **operator message
window**; default 3 cycles; set per project or at run time). When a message ages out, an
`operator_message.dropped_from_context` event is emitted — there is no silent expiry. Active
operator messages are visible in `watch` and `dashboard`. See VISION.md User Interaction Model →
Free-form operator messages for the full semantics.

### Integration

The integration layer implements protocols for external systems.

Examples:

- LLM providers for the operator brain
- Claude ACP adapter
- Codex ACP adapter
- file-backed stores
- JSONL event sinks
- clock and process services

This layer contains vendor and environment details.

For ACP-backed coding agents, this layer includes an operator-owned ACP substrate seam beneath
the runtime-contract layer (`AdapterRuntime` and `AgentSessionRuntime`).

That seam exists so `operator` can bind each ACP adapter independently to either:

- the current bespoke ACP connection path, or
- an ACP Python SDK-backed connection path.

The seam is below the runtime-contract layer, not above it. `operator` still owns lifecycle
semantics, approval policy, persisted truth, and observability.

Above that substrate, ACP-backed adapters share a session-runner layer for common
session-execution mechanics such as create/load, prompt/send, notification draining, transcript
accumulation, terminal collection, and cancel/close flow.

Vendor adapters remain as thin policy shells above that runner. They still own vendor-specific
session configuration, permission handling, error classification, and connection reuse semantics.

The runner also hosts shared ACP-side helpers where they reduce duplicated client-side
bookkeeping without becoming the source of truth for operator semantics.

Examples include:

- a shared normalized permission-policy layer for ACP permission-like requests,
- a derived structured session snapshot fed by SDK accumulation helpers,
- background progress snapshots for active ACP turns so resumable runs do not wait for terminal
  collection before surfacing live status,
- inbound SDK notification logging so ACP forensic logs remain comparable across subprocess-backed and
  SDK-backed substrates,
- and ACP-native usage propagation into adapter progress and result reporting when that data is
  present.

### Delivery

The delivery layer exposes the application to users.

Examples:

- CLI commands
- machine-readable console output

> **Planned**: Python convenience APIs.
> **Planned**: TUI supervisory workbench.

Delivery composes the application layer, not duplicates its logic.

In hexagonal terms, delivery surfaces are driving adapters over application-facing contracts.

- CLI is the authoritative shell-facing driving adapter.
- The future TUI is a supervisory driving adapter over the same underlying contracts.
- State-changing delivery actions must drive the same application-facing command/use-case paths.
- Supervisory and inspection delivery surfaces must consume shared application-facing
  query/projection services rather than delivery-local state assembly.
- Rendering, navigation, help behavior, keybindings, and other surface-specific interaction rules
  remain adapter-local concerns.

Current package placement may temporarily keep TUI code under `agent_operator.cli`, but that should
be understood as a transitional delivery-package shape rather than the ideal long-term architecture.
The better long-term package boundary is sibling delivery adapters under a common delivery family,
not permanent `cli/tui` nesting and not a standalone top-level `agent_operator.tui` authority root.
See [RFC 0011](./rfc/0011-delivery-package-boundary-for-cli-and-tui.md) for the boundary choice and
[RFC 0012](./rfc/0012-delivery-package-migration-tranche.md) for the later migration tranche.

That means the repository should not grow a separate enduring architectural layer between delivery
and application for TUI work. When delivery extractions are needed, they should expose
application-facing command/query contracts more explicitly rather than creating a second workflow
authority above or beside the existing application layer.

The CLI commands are organized in a three-tier model (Everyday / Situational / Forensic). See
`Inspection Surfaces` below for the full surface list and VISION.md CLI Design for the tier
descriptions.

## Core Runtime Model

**Operation vs run:** `operation` names the persistent entity — an iterative, potentially
long-lived attempt to satisfy a goal under constraints. `run` names one execution attempt over
that operation — specifically, one `operator run` invocation. An operation may have multiple runs
if it is interrupted and resumed. This distinction matters for resumable mode and multi-run
operations. See VISION.md Why This Exists for the canonical statement.

The main runtime unit is an `operation run`.

An operation run contains:

- the user goal,
- execution constraints,
- available agent roster,
- available agent descriptors and declared capabilities,
- iteration history,
- emitted events,
- current route or plan state,
- final outcome or stop reason.

Each iteration produces a visible state change:

- internal reasoning result,
- agent invocation,
- deterministic control decision,
- evaluation outcome,
- or final stop.

Terminal control decisions distinguish:

- successful completion,
- explicit failure,
- and user-blocking clarification.

The architectural split inside that run is:

- durable operation state as the persisted source of truth,
- a loaded-operation runtime/coordinator as the per-operation execution owner,
- and an operator-policy/controller layer that decides how to drive the next step.
- above that, `OperatorService` as the system shell and composition boundary,
- and beside that, enduring workflow-authority services for decision execution, command
  application, result assimilation, runtime reconciliation, and traceability.

Current repository truth:

- `implemented`: `OperatorPolicy` is already the top-level application seam.
- `implemented`: `LoadedOperation` already exists as a first-class application object and owns a
  growing share of one-operation local mechanics.
- `partial`: `OperatorService` still retains a callback-host role for parts of the top
  control/runtime layer.
- `planned`: `OperationLifecycleCoordinator` is the intended enduring authority for one-operation
  lifecycle closure.
- `planned`: a separate control-state synchronization/persistence authority is still needed above
  the current shell/runtime split.
- `planned`: runtime gating and runtime-context projection should move behind a smaller named
  capability boundary rather than remain shell-local predicates.

That means operator variation should not fork the runtime loop by default. Different operator
implementations should usually share the same loaded-operation runtime and differ only in the
policy/controller that chooses and interprets internal operator intent.

The operator brain does not fake failure through a successful stop summary.

The ideal repository shape under `ADR 0101` is therefore:

- `OperatorService` = shell
- `LoadedOperation` = one-operation runtime boundary
- `OperatorPolicy` = pluggable behavior seam
- workflow-authority services = enduring application capabilities
- drive/runtime/control/trace splits = internal execution collaborators rather than equally
  important top-level architectural nouns

The practical completion route under `ADR 0102` and `ADR 0104` is:

- `OperationLifecycleCoordinator` as an enduring authority above `LoadedOperation`
- a separate control-state coordination boundary for command/checkpoint/state refresh concerns
- runtime gating / runtime context treated as a smaller capability boundary
- current drive runtime/control/trace splits treated as useful collaborator cuts, but not yet
  assumed to be the final enduring top-level architecture

## Preferred Runtime Surface

The preferred runtime surface is an attached long-lived `operator run`.

That means normal use looks like:

- start `operator run`,
- let the operator keep driving work,
- and stop only on terminal outcome or explicit blocking.

The persisted control plane remains authoritative, but it is not the preferred product story.

Instead, the runtime split is:

- attached run mode for normal execution,
- resumable mode for recovery and control.

### Runtime Modes

#### Attached mode

Attached mode is the preferred runtime surface. One live foreground operator process owns the
active turn.

That ownership does not imply that the active turn must always be polled directly through the
adapter in the same process.

Attached mode may use a background worker for the active agent turn, as long as the attached
process remains the reconciler that:

- waits on that background turn through the same wakeup/evidence path used by resumable mode,
- drains commands while the wait is active,
- consumes wakeups in-process,
- and advances scheduling without requiring `resume` or the resumable daemon.

The key distinction is ownership, not whether a subprocess exists.

In attached mode:

- one active agent turn remains the contract,
- `WAIT_FOR_AGENT` is valid only for a real in-flight dependency with blocking focus,
- wakeup consumption is part of the normal progression path,
- and the foreground attached process remains responsible for deciding what to do next after the
  turn yields.

The live control seam supports:

- draining human commands while attached waits are active,
- representing scheduler states such as `pause_requested` and `paused`,
- and surfacing human-required attention explicitly rather than only through coarse blocked status.

The attached-mode delivery surfaces (`watch`, `agenda`, `fleet`, `dashboard`) are projections over
persisted operation state. See VISION.md CLI Design for the full surface descriptions.

The most important boundary rule is:

- the TUI must not invent control semantics.

The control plane defines the semantics first, and delivery surfaces render them.

The distinct control paths are:

- pause: do not launch new work after the current turn yields
- interrupt: ask the active attached agent turn to stop now
- stop-operation: cancel the broader operation

#### Resumable mode

Resumable mode keeps:

- wakeup inboxes,
- stale/orphan reconciliation,
- in-process background execution,
- and explicit `resume` / `tick` / `cancel` control.

This mode exists to preserve recoverability and transparency after interruption, not as the
preferred normal-use path.

For short runs, this model is sufficient as-is.

For long-lived work, the runtime does not collapse the objective into a single session thread.

The durable source of truth is the objective state plus its distilled memory and artifacts.
Sessions are execution resources, not the canonical memory model.

### ADR References

- ADR 0013: operation command inbox and command envelope
- ADR 0014: deterministic command reducer vs brain-mediated replanning
- ADR 0015: scheduler state and pause semantics for attached runs
- ADR 0016: attention request taxonomy and answer routing
- ADR 0017: involvement levels and autonomy policy
- ADR 0018: project profile schema and override model
- ADR 0019: policy memory and promotion workflow
- ADR 0029: policy applicability and matching semantics
- ADR 0032: bounded live goal-patching slice
- ADR 0036: bounded live constraints patching
- ADR 0037: deterministic constraint control

## Long-Lived Objectives

Long-lived work is structured in four entity levels: Objective → Feature → Task → Subtask. See VISION.md Long-Lived Objective Hierarchy for the full model, Feature lifecycle states, authority model, and the `document_update_proposal` mechanism for planning document contributions.

Vision, Strategy, Requirements, Scenarios, and User Stories are documentary artifacts — not runtime entities. The brain reads them via its read-only file access and may propose additions to user-authored planning documents via `document_update_proposal` attention requests. See VISION.md Operator Workspace (Future Direction) for the criteria under which the brain may be granted write authority over a scoped workspace.

## True Harness Direction

### Live control

The implemented live control model includes:

- a durable command inbox for each operation,
- deterministic command acceptance and lifecycle,
- brain-mediated replanning after accepted command effects where needed,
- explicit pause, resume, stop-operation, interrupt, answer, policy, and operator-message flows,
- bounded live constraints patching and deterministic constraint control,
- and bounded live goal patching for objective, harness instructions, and success criteria.

These semantics are captured by ADR 0013, ADR 0014, ADR 0032, ADR 0036, and ADR 0037.

`patch_*` commands are rejected with `operation_terminal` if the operation has already reached
`TERMINAL` state, with `invalid_payload` if the payload is empty or structurally malformed, and
with `concurrent_patch_conflict` if a conflicting patch on the same field is already pending in
the inbox. `stop_turn` targeting a task not in `RUNNING` state is rejected with
`stop_turn_invalid_state`; the rejection message includes the actual task state. When a new
attention request arrives during a `draining` scheduler state it is accepted and queued; the
exception is a cancel-drain, where new attentions are rejected with `operation_cancelling`. See
VISION.md User Interaction Model for the full rejection and drain-time semantics.

### Scheduler state

The attached-run control model carries a scheduler-facing state distinct from coarse operation
terminal status.

Valid states:

- `active`
- `pause_requested`
- `paused`
- `draining`

This direction is captured by ADR 0015.

### Involvement levels

Two levels are defined. See VISION.md CLI Design → Involvement levels for the full behavioral specification.

- **`unattended`**: the brain proceeds without interrupting for routine decisions. Policy gaps and
  novel strategic choices surface as typed attention requests but do not block non-affected tasks.
  Best for long-running background work.
- **`interactive`**: policy gaps and strategic forks block forward progress until the user answers.
  Best for exploratory or high-stakes work.

The active level is inspectable via `context op-id` and visible in `dashboard` and `watch`. It
can be changed while the operation is running; the change takes effect at the next brain decision
point.

### Attention and autonomy

The implemented attention taxonomy covers six types: `question`, `approval_request`,
`policy_gap`, `novel_strategic_fork`, `blocked_external_dependency`, and
`document_update_proposal`. See VISION.md Attention Requests for the full semantics and blocking
rules for each type.

`document_update_proposal` is the attention pathway for brain-proposed additions to
user-authored planning documents (Vision, Strategy, Requirements, etc.). It is distinct from
the workspace write authority described in `Operator Workspace (Future Direction)`: that future
capability concerns a scoped `.operator/workspace/` directory and is gated on separate criteria.
Until those criteria are met, the brain remains read-only with respect to all project files, and
`document_update_proposal` is the only route for surfacing planning document contributions to
the user for review.

The current runtime truth carries explicit policy-coverage state so CLI surfaces can distinguish
between:

- no policy scope
- no stored policy for the scope
- matching policy coverage
- and uncovered scope where policy exists but none currently applies

The `policy_gap` guardrail fires when:

- the brain marks that the immediate next step needs reusable project precedent,
- and the scoped policy layer is `no_policy` or `uncovered`.

The runtime surfaces typed `policy_gap` attention instead of proceeding silently.

The `novel_strategic_fork` guardrail fires when:

- the brain marks that the immediate next step needs a human strategy choice before acting.

The runtime surfaces typed `novel_strategic_fork` attention instead of proceeding silently.

At `interactive` involvement, both `policy_gap` and `novel_strategic_fork` block forward progress
until the user answers. At `unattended` involvement, they surface as attention requests but do not
block non-affected tasks.

Note: VISION.md's Attention requests section uses the word `collaborative` in the blocking-rule
sentence, but the defined involvement levels are `unattended` and `interactive` only. The word
`collaborative` does not map to any defined level; treat the defined levels as normative.

These guardrails keep policy-shaped and strategy-shaped autonomy boundaries on the same explicit
attention path instead of relying only on prompt compliance.

### Project defaults and learned precedent

Hand-authored project profiles provide stable defaults. Runtime-derived policy memory provides
reusable approved precedent.

Profiles remain declarative defaults. Policy memory remains provenance-bearing learned control
truth.

The initial implemented profile slice includes:

- YAML profiles under the operator data directory
- explicit top-level `init` scaffolding for bounded YAML profile creation
- explicit `project list`, `project inspect`, and `project resolve` CLI surfaces
- `run --project ...` profile resolution with stable precedence:
  - CLI override
  - profile value
  - global default
- persisted recording of the selected profile name and resolved profile config in operation goal
  metadata

The initial implemented policy slice includes:

- explicit project-local `PolicyEntry` records under the operator data directory
- inspectable `policy list`, `policy inspect`, `policy record`, and `policy revoke` CLI surfaces
- explicit promotion from resolved attention by attention id via `policy record --attention ...`
- explicit separate policy-promotion flow via `policy record --from-attention ...`
- explicit revocation instead of silent policy deletion
- active project policy injected into `run --project ...` context for operator decisions
- explicit applicability filters on policy entries for objective/task keywords, agent keys, run
  mode, and involvement level
- deterministic matching of active policy against persisted operation truth instead of project
  scope alone
- an operation-centric `context` CLI surface that shows the effective profile, policy scope,
  active policy set, and runtime control state steering one operation

Delivery surfaces for these layers (`tasks`, `memory`, `artifacts`, `report`, `agenda`, `fleet`,
`dashboard`, `context`) are described in VISION.md CLI Design.

## Traceability

The operator traceability model is organized around the question each layer answers, not around
implementation types. The full model has six layers, from raw agent output to a human-readable
report. Types are defined in `domain/traceability.py`; storage is in `runtime/trace.py`
(`FileTraceStore`).

### The Six Layers

**Layer 0 — Raw agent output** (outside `FileTraceStore`)
- *Answers:* "What exactly did the agent produce?"
- Contains: stdio/stderr, background run logs, artifact files.
- Referenced by `AgentTurnBrief.raw_log_refs` and `artifact_refs`. Storage is agent-managed; `FileTraceStore` does not write this layer.

**Layer 1 — Event stream** (`.operator/events/{op-id}.jsonl`)
- *Answers:* "What system events occurred, in what order, at what time?"
- Contains: `RunEvent` objects — domain events (`operation.started`, `task.created`,
  `scheduler.state.changed`, `command.*`, etc.) and trace events (`brain.decision.made`,
  `agent.invocation.*`, `evaluation.completed`, etc.).
- Consumer: live `watch` (real-time streaming), state reconstruction, automated monitoring.
- Properties: append-only, complete (no editorial selection), atomic events (state transitions at
  system boundaries). Written by the runtime event bus, not by `FileTraceStore`.

**Layer 2 — Narrative timeline** (`.operator/runs/{op-id}.timeline.jsonl`)
- *Answers:* "What happened, narrated by the operator loop?"
- Contains: `TraceRecord` objects — operational records with `category`, `title`, `summary`, `refs`.
- Consumer: `trace` CLI (human-browsable), report generation, dashboard views, LLM context
  injection into the brain.
- Properties: append-only, editorially selective (a subsystem chose to write this record), semantic
  spans (one record may summarize multiple events).

**Layer 3 — Structured summaries** (per-iteration and per-turn files)
- *Answers:* "What did the brain decide? What did each agent actually do?"
- Contains:
  - `DecisionMemo` (`runs/{op-id}/reasoning/{iter}.json`): brain's authoritative reasoning record —
    chosen action, rationale, alternatives considered, why each was rejected, expected outcome.
  - `AgentTurnBrief` + embedded `AgentTurnSummary` (`runs/{op-id}/agents/{session-id}-{iter}.summary.json`):
    agent's structured turn record — declared goal, actual work done, route chosen, repo changes,
    state delta, verification status, remaining blockers, recommended next step.
- Consumer: iteration-level drill-down, accountability audit, report generation.

**Layer 4 — Operation-scope view** (`runs/{op-id}.brief.json`)
- *Answers:* "What is the current state of this operation?"
- Contains: `TraceBriefBundle` — a container holding:
  - `OperationBrief`: live snapshot of status, scheduler state, involvement level, objective,
    current focus, latest outcome, current blockers, runtime alerts.
  - `IterationBrief[]`: per-iteration prose summaries accumulated across the operation's lifetime.
  - `AgentTurnBrief[]`: per-turn summaries accumulated across the operation's lifetime.
  - `CommandBrief[]`: terminal record for each command processed during the operation (applied or
    rejected), written at `command.applied` / `command.rejected`.
  - `EvaluationBrief[]`: brain's per-iteration verdict — continue / stop / block — written at
    `evaluation.completed`.
- Consumer: `watch`/`inspect` commands, report generation, command history CLI views.

**Layer 5 — Human report** (`runs/{op-id}.report.md`)
- *Answers:* "What happened in plain language, suitable for sharing?"
- Contains: a rendered narrative synthesized from Layers 3 and 4.
- This is a render target, not a queryable layer.

### Cross-Layer Navigation

A user wanting to understand what happened moves top-down:

1. **`status` / `watch` / `inspect`** — read `OperationBrief` and adjacent projections. Current
   status, blockers, active attention, latest outcome.
2. **`trace`** — reads the `TraceRecord` timeline. Chronological narrative, filterable by
   iteration, category, task.
3. **Iteration detail** — reads `IterationBrief` and `DecisionMemo` for the target iteration.
   Brain's decision and rationale.
4. **Agent turn detail** — reads `AgentTurnBrief`. Declared goal vs. actual work, repo changes,
   remaining blockers.
5. **Raw evidence** — follows `refs`, `raw_log_refs`, `artifact_refs` on `AgentTurnBrief` to
   Layer 0 files (raw agent output, artifacts). The user-facing CLI drill-down command for this
   layer is `log`, with explicit or auto-detected agent selection.

The `refs` field is the cross-referencing mechanism. Its semantics differ by type:

- `DecisionMemo.refs` and `IterationBrief.refs` use `TypedRefs` — a typed Pydantic model with a
  closed key set (`operation_id`, `iteration: int`, `task_id`, `session_id`, `artifact_id`,
  `command_id`). See Design Decisions below.
- `TraceRecord.refs` remains `dict[str, str]` — a generic carrier with a documented but open
  vocabulary (see Design Decisions for the standard key table).
- `AgentTurnBrief` uses separate typed list fields (`artifact_refs`, `raw_log_refs`, `wakeup_refs`)
  instead of a generic `refs` dict.

### The Two Streams Are Not Parallel

The event log (`events/{op-id}.jsonl`) and the narrative timeline (`runs/{op-id}.timeline.jsonl`)
are frequently confused. They are orthogonal:

| | Event stream | Narrative timeline |
|---|---|---|
| Unit | Atomic event (state transition at a boundary) | Semantic span (narrated, author-selected) |
| Coverage | Complete | Selective |
| Author | System — automatic | Subsystem writer — editorial |
| Consumer | Machines: replay, alerting, watch | Humans / LLM: trace CLI, report, brain context |

The event stream is the fact record of the operation. The narrative timeline is the interpreted
record. The brain should consume the timeline or brief layer for operation history — not the raw
event stream.

### Storage Implementation

`FileTraceStore` (`runtime/trace.py`) implements the `TraceStore` protocol:

| Method | Writes |
|---|---|
| `save_operation_brief(brief)` | `{op-id}.brief.json` (Layer 4) |
| `append_iteration_brief(op_id, brief)` | Brief bundle — `iteration_briefs[]` |
| `append_agent_turn_brief(op_id, brief)` | Brief bundle + `{op-id}/agents/{session-id}-{iter}.summary.json` |
| `append_command_brief(op_id, brief)` | Brief bundle — `command_briefs[]` |
| `append_evaluation_brief(op_id, brief)` | Brief bundle — `evaluation_briefs[]` |
| `save_decision_memo(op_id, memo)` | `{op-id}/reasoning/{iter}.json` (Layer 3) |
| `append_trace_record(op_id, record)` | `{op-id}.timeline.jsonl` (Layer 2) |
| `write_report(op_id, report)` | `{op-id}.report.md` (Layer 5) |

### Design Decisions

The following decisions were finalized to close traceability gaps and prevent architectural drift.

#### Typed `refs` vocabulary

`refs` fields on traceability types serve different roles depending on the type:

- **`DecisionMemo.refs` and `IterationBrief.refs`** — use a typed `TypedRefs` Pydantic model.
  Known keys form a closed, predictable set for these types:

  ```python
  class TypedRefs(BaseModel):
      operation_id: str
      iteration: int | None = None   # int, not str — corrects historical str(int) convention
      task_id: str | None = None
      session_id: str | None = None
      artifact_id: str | None = None
      command_id: str | None = None
  ```

  `AgentTurnBrief` already uses separate typed list fields (`artifact_refs`, `raw_log_refs`,
  `wakeup_refs`) and does not use a `refs` dict.

- **`TraceRecord.refs`** — remains `dict[str, str]`. `TraceRecord` is a generic carrier and
  legitimately needs extensible keys (`policy_id`, `wakeup_id`, `attention_id` etc. as new
  event paths are added). Standard vocabulary is documented here:

  | Key | Value |
  |---|---|
  | `operation_id` | operation UUID |
  | `iteration` | iteration index as string |
  | `task_id` | task UUID |
  | `session_id` | agent session UUID |
  | `command_id` | command UUID |

  New ref keys may be added freely to `TraceRecord.refs`; no migration is needed.

#### `CommandBrief` in `TraceBriefBundle`

`command.*` domain events exist in the event stream (Layer 1) but no brief-layer representation
exists. Post-hoc consumers (report generation, CLI history views) need command history without
scanning raw events. Add `CommandBrief` and a `command_briefs` list to `TraceBriefBundle`:

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

Written when the command reaches its terminal state: `command.applied` or `command.rejected`.
CLI real-time stream subscriptions continue to read Layer 1 directly (correct — not a layer
violation).

#### `EvaluationBrief` in `TraceBriefBundle`

`evaluation.completed` trace events carry the brain's per-iteration verdict (continue / stop /
block). This verdict is not accessible from any summary layer without scanning raw events.
Add `EvaluationBrief` and an `evaluation_briefs` list to `TraceBriefBundle`:

```python
class EvaluationBrief(BaseModel):
    operation_id: str
    iteration: int
    goal_satisfied: bool
    should_continue: bool
    summary: str
    blocker: str | None = None
```

Written when `evaluation.completed` fires (once per loop iteration). This gives post-hoc
consumers a structured history of why the operation ran for N iterations and how it ended.

### Known Gaps

The following remain open. Priority indicates implementation urgency.

- **[normal] `TraceRecord` severity.** `category` is a free-text string; there is no enumerated
  `severity` field (`info` | `warning` | `error`). The `trace` CLI cannot filter for error-level
  records without string matching.
- **[low] Cost and token tracking.** No layer captures input tokens, output tokens, latency, or
  estimated cost per agent turn or per operation. Natural location: a `cost_summary` sub-object on
  `AgentTurnBrief`, aggregated into `OperationBrief.cost_total_brief`.

## Memory Layers

The target design uses multiple memory strata:

### Turn context

Immediate context visible to the operator brain for the current decision.

### Session snapshot

Short summary of one agent session:

- purpose,
- current thread,
- latest terminal result,
- open local questions,
- whether the session is reusable or disposable.

### Task memory

Distilled memory needed to continue one task independent of any one vendor session.

Task memory carries:

- source references,
- freshness state,
- and supersession or invalidation semantics.

### Objective memory

Distilled memory for the overall long-lived goal:

- accepted decisions,
- open fronts,
- unresolved blockers,
- completed work,
- and strategic constraints.

### Artifact store

Durable outputs produced by agent sessions — for example:

- normalized agent returns,
- structured data returned as the concrete output of completed task work,
- and files, diffs, or reports surfaced as deliverables.

Artifacts are agent-session outputs, not operator-internal planning material. Planning notes,
research summaries, and context-building records belong in `MemoryEntry` (task memory or
objective memory), not the artifact store. See VISION.md Mental Model → Operator brain → File tools
for the `MemoryEntry` scope model.

This is the main route for keeping long-lived work portable across agents and sessions.

`MemoryEntry` objects support two scopes:
- **Operation-scope** (default): freshness-tracked per file path within one operation; superseded when the same path is re-read.
- **Project-scope**: persists across operations; the brain reads all active project-scope entries at the start of every planning cycle; only writable via user-accepted `document_update_proposal` attention.

See VISION.md Mental Model → Operator brain → File tools for the full freshness, supersession, and two-scope semantics.

The initial CLI surfacing for these durable layers includes:

- `report` sections for tasks, current memory, and artifacts
- `tasks` for direct task-graph inspection
- `memory` for distilled memory inspection
- `artifacts` for durable artifact inspection

These are delivery projections over the persisted operation state and shared read models, not a
separate knowledge store.

## Memory Correctness

Memory stratification is not enough by itself.

For memory to be trustworthy in long-lived work, the design defines:

- provenance,
- freshness,
- invalidation,
- and supersession.

A `MemoryEntry` model answers:

- what sources produced this entry,
- whether it is current, stale, or superseded,
- and what later artifact or finding invalidated it if it is no longer current.

The freshness, supersession, and two-scope semantics are now normatively specified in VISION.md (Mental Model → Operator brain → File tools). The original minimum semantics were captured in ADR 0006.

## Operator Loop

The operator loop is the main service of the system.

Implementation summary — for the normative loop architecture and invariants, see VISION.md Event Model → Loop architecture.

1. create operation state
2. emit `operation_started`
3. inspect constraints and available agents
4. choose the next action
5. execute that action
6. evaluate whether the goal is satisfied, blocked, or still active
7. either stop or continue to the next iteration

The choice at step 4 can be:

- ask the operator brain to decide,
- use deterministic policy directly,
- continue an active agent session,
- switch to another agent,
- request more information,
- stop.

The system does not require an LLM call when deterministic logic is enough, but LLM-guided orchestration remains the default posture.

The loop uses a file-based `WakeupInbox` for cross-restart durability and an in-process `asyncio.Event` for zero-latency wakeup delivery, set by a `WakeupWatcher` background task. This eliminates fixed-sleep polling while preserving the pull-loop structure. The focus object points to the active task, not to a session. See VISION.md Event Model → Loop architecture for the implemented wakeup delivery model.

See Decision Split below for the authority model governing step 4. For failure handling and abnormal loop termination, see Failure Model below.

## Task Graph

The operator maintains an explicit directed acyclic task graph for each operation.

### Task lifecycle

A task moves through: `PENDING → READY → RUNNING → COMPLETED | FAILED | CANCELLED`.

The transition from `PENDING` to `READY` is deterministic: when all dependency tasks are
complete, the dependent task becomes runnable automatically — no LLM call required.

`PENDING` is the canonical state for a task with unresolved dependencies. There is no separate
`BLOCKED` state. In the CLI task view, `[BLOCKED]` is a **display grouping label** for `PENDING`
tasks that have at least one dependency not yet completed — it is a presentation alias, not a
distinct lifecycle state.

Each task carries a `task_short_id`: a random 8-character lowercase hex display alias (e.g.
`task-3a7f2b1c`), unique within the operation, used for user-facing commands and operator
messages.

### Task graph invariants

Enforced by the runtime, not by the brain:

- **DAG**: the graph is acyclic. Any `add_dependency` that would create a cycle is immediately
  rejected with `dependency_cycle_detected`.
- **Monotonicity**: dependencies are added, not silently removed. Removal requires a non-empty
  `reason` string; the runtime rejects any removal call that omits or provides an empty `reason`
  with `dependency_removal_requires_reason`. Accepted removals are logged with their reason string.
- **Completion propagation**: task completion triggers immediate deterministic unblocking of all
  dependent tasks that have no other pending dependencies. No LLM call is required.
- **No self-dependency**: a task cannot depend on itself.

See VISION.md Task Graph for the canonical state model and user-facing task view.

## Task Authority Model

Long-lived work does not leave task state ownership ambiguous.

The split is:

- the brain may propose:
  - task creation,
  - task reprioritization,
  - assignment choices,
  - and suggested next actions
- the deterministic runtime enforces:
  - dependency gates,
  - retry ceilings,
  - concurrency limits,
  - deadline and timeout rules,
  - runnable vs blocked state,
  - and effective runnable priority distinct from brain-proposed priority

## Decision Split

The system separates two kinds of control.

### Deliberative control

Usually handled by the operator brain.

Examples:

- what subproblem matters most now,
- which agent is most suitable,
- what context should be sent,
- whether the returned work is sufficient,
- whether to continue with the same agent or switch.

### Mechanical control

Always handled deterministically.

Examples:

- max iteration check,
- timeout check,
- retry count,
- cancellation,
- adapter capability validation,
- event persistence,
- structured output formatting.

This split is central. The first is where the system is agentic. The second is where the system stays operable.

## Protocols

Protocols define the seams between layers. Each is a `typing.Protocol` with a narrow, testable surface.

## `OperatorBrain`

`OperatorBrain` provides the LLM-facing reasoning capability used by the current LLM-first operator
family.

Responsibilities include:

- propose the next action (`decide_next_action`)
- evaluate an agent result against the goal (`evaluate_result`)
- summarize progress (`summarize_progress`)
- provide LLM-mediated interpretation helpers such as turn summarization, artifact normalization,
  and memory distillation

The brain reasons about agent invocations — it does not directly own vendor agent calls.
Provider-specific structured output is mapped into domain decisions before the application layer
consumes it. See VISION.md Operator brain.

`OperatorBrain` is **not** the top-level seam for all operator implementations. It is better
understood as a dependency used by one operator-policy family, especially the current LLM-first
policy/controller. Simpler or lower-LLM operator variants do not need to implement this exact
protocol directly.

## Operator Policy / Controller Layer

Above the loaded-operation runtime sits a pluggable operator-policy/controller layer.

This layer owns:

- choosing the next internal operator intent,
- interpreting returned results for continuation or termination,
- deciding when clarification or human escalation is required,
- and deciding what operator-visible progress interpretation is needed.

This layer does **not** own:

- persistence,
- wakeup or reconciliation mechanics,
- background-run bookkeeping,
- deterministic stop/timeout/concurrency guardrails,
- or per-operation runtime lifecycle ownership.

The current repository implements this behavior largely through the LLM-first brain path, but the
architectural direction is broader: multiple operator implementations should vary at this
policy/controller layer while sharing the same loaded-operation runtime/coordinator beneath them.

## Runtime Contracts

The active runtime architecture is described in terms of three public contracts:

- `AdapterRuntime`
- `AgentSessionRuntime`
- `OperationRuntime`

The public repository truth is runtime-native: `AdapterRuntime`, `AgentSessionRuntime`, and
`OperationRuntime`. Older adapter-era terminology remains only in historical ADR/RFC context.

### `AdapterRuntime`

Owns transport and subprocess lifecycle, adapter-shaped command ingress, and raw adapter-facing
event egress.

### `AgentSessionRuntime`

Owns exactly one live logical session at a time, exposes session-scoped command ingress, and
normalizes transport facts into session-scoped technical facts.

### `OperationRuntime`

Owns per-operation concurrency and coordination scope, including background dispatch, polling,
collection, finalization, and grouped cancellation.

This contract should be read together with the application-side loaded-operation runtime/coordinator
direction:

- `OperationRuntime` is the stable per-operation execution substrate,
- `OperatorService` is the top-level shell and composition boundary,
- operator policies/controllers vary above this runtime rather than replacing it with separate loop
  implementations.

Command-handler style may be used inside the loaded-operation runtime/coordinator to execute
internal operator intent, but the repository does not treat all operator behavior as one public
command model. External `OperationCommand` and internal operator intent remain distinct semantic
layers.

## `OperationStore`

Purpose:

- persist operation state and retrieve prior runs

Responsibilities:

- create run records
- append iteration state
- store outcomes
- load historical runs

The current implementation is file-backed. The protocol exposes the minimum surface needed for the application loop: create run records, append iteration state, store outcomes, and load historical runs. It does not expose query or aggregation operations.

> **Roadmap:** As long-lived work grows, the store will need to persist: objective state, task
> state, memory entries, active and historical sessions, and durable artifacts.

Embedded assignment fields inside `Task` are sufficient for the current long-lived version.
A separate assignment entity is warranted only when that simpler shape stops carrying the runtime cleanly.

## `EventSink`

Records structured events for transparency, debugging, and scheduling. One run may write to
multiple sinks: CLI renderer, JSONL trace, test capture.

For the three event categories (domain events, trace events, wakeup signals) and their semantics,
see the `Event Model` section below. ADR 0007 captures the original wakeup and wait semantics.

## `Clock`

Purpose:

- abstract time and deadlines for testability

## `Console`

Purpose:

- abstract user-visible rendering from the operator core

This keeps the application layer from depending directly on `rich`.

## State Objects

The exact schema can evolve, but the architecture assumes these categories.

### Inputs

- `OperationGoal`
- `OperationPolicy`
- `ExecutionBudget`
- `RuntimeHints`
- `AgentSelectionPolicy` — constrains brain assignment proposals; governs which agents may be
  selected for a task. Assignment policy is embedded in project profile configuration (see
  `run --project` profile resolution above) and injected into the brain's planning context.
- `RunOptions` — run-time execution parameters (e.g. involvement level, run mode, project
  profile selection) passed at invocation time to configure a single run.

`OperationGoal` is not a single mixed freeform prompt bucket.

The split is:

- `objective`
- `harness instructions`
- `success criteria`

`objective` is the success target.
`harness instructions` are execution policy for the operator and agent orchestration path.
They may shape routing and blocking behavior, but do not by themselves count as objective
completion.

### Runtime

- `OperationState`
- `IterationState`
- `SessionRecord` — runtime record of one agent session lifecycle: session id, adapter key,
  creation time, session policy, and accumulated status. Persisted as part of operation state.
- `BrainDecision`
- `Evaluation`
- `MemoryEntry` — supports operation-scope and project-scope; see VISION.md Mental Model → Operator brain → File tools.

### Outputs

- `OperationOutcome`
- `AgentResult`
- `RunSummary` — end-of-run summary produced after the operation loop exits; includes outcome,
  iteration count, and a human-readable status digest.

## Event Model

The event model is normatively specified in VISION.md (Event Model section). Three categories:

- **Domain events** — permanent; record aggregate state transitions; the authoritative record.
- **Trace events** — permanent, best-effort; forensic use only; must not gate behavior.
- **Wakeup signals** — ephemeral, consumed-once; must not appear in the domain event log.

Key invariant: every `state.status` mutation must produce a domain event before the operation is
persisted. Operator message ingestion (`operator_message.received`) and aging out
(`operator_message.dropped_from_context`) also produce domain events. See VISION.md Event Model
for the full invariant specification and the key event catalog by aggregate.

## Known Technical Debt

The following named items are known tech debt — a contributor encountering these names in the code should not treat them as permanent design:

- **`operation.cycle_finished`** should be renamed `operation.process_run_ended`. The current name implies a planning-cycle boundary; it actually records the end of a single process run within a potentially multi-run operation. Deferred until external event log consumers exist.
- **`RunEvent(kind=WAKEUP)`** should become a separate `WakeupSignal` type with its own storage path, removing wakeup artifacts from the domain event log entirely. Deferred for the same reason.

## Agent Adapters

### Claude ACP adapter

Design notes:

- stateful ACP session over stdio
- canonical launch command `npx @agentclientprotocol/claude-agent-acp`
- ACP Python SDK-backed substrate by default; migration timing is a deferred implementation decision
- adapter-local handling for Claude-specific model, effort, permission, and cooldown semantics

This is the canonical Claude integration path and a reference implementation of the runtime
contracts for Claude-facing sessions.

### Codex ACP adapter

Design notes:

- stateful ACP session over stdio
- session bootstrap and load logic
- prompt submission and follow-up messaging
- structured progress and stop notifications
- adapter-local execution-policy control for Codex runtime settings such as
  approval mode and sandbox mode

This adapter is more protocol-heavy than Claude ACP, but the complexity remains local to the adapter.

The rest of the system interacts with it through the runtime-contract layer.

See VISION.md Agent Adapter Contract for the normative capability table.

## Composition And DI

`dishka` wires the system at the composition root.

Root responsibilities:

- configure brain provider
- register available agent adapters
- configure stores and event sinks
- construct the operator service
- bind CLI commands to application entrypoints

The domain and application layers do not depend on `dishka` types directly.

## Concurrency

The system stays conservative by default.

Default bias:

- one active operator loop per run
- concurrency governed by involvement level and operation configuration
- explicit concurrency only when policy allows it

`anyio` provides cancellation, timeouts, and structured concurrency primitives.

When policy allows parallel sessions, the operator loop uses the routing rules in VISION.md Multi-Session Coordination to schedule and serialize them. Multi-session parallel coordination within a single operation is supported — see VISION.md Multi-Session Coordination for the routing rules and serialization model.

## Failure Model

The architecture assumes failures are normal.

Failure classes:

- brain provider failure
- adapter startup failure
- active session stall
- malformed or partial agent output
- timeout
- budget exhaustion
- user cancellation

The operator loop turns these into explicit evaluation and stop decisions rather than leaking raw
exceptions to the user by default. Failures that terminate a task produce a `FAILED` task state
transition (see Task Graph → Task lifecycle) and a corresponding domain event in the event log
(see Event Model). Failures that do not yet terminate the operation produce best-effort trace events for
forensic inspection. The `StopReason` domain type records the cause when the operation itself
stops.

## Inspection Surfaces

The default CLI inspection surfaces stay grounded in persisted operation truth and shared
projections:

- `list`
- `agenda`
- `fleet`
- `status`
- `watch`
- `dashboard`
- `context`
- `inspect`
- `tasks`
- `memory`
- `artifacts`
- `attention`
- `report`
- `trace`
- `log`

When a run is backed by Codex ACP, the most detailed upstream evidence still lives in the native
Codex transcript under `~/.codex/sessions/...jsonl`.

`operator` does not duplicate that full transcript into its own trace store. Instead, it exposes
a condensed drill-down surface keyed by `operation_id` through `operator log`, which resolves the
attached session and renders only the important transcript events in a human-readable form.

This keeps:

- operation-centric UX in the operator CLI,
- the full Codex transcript as upstream evidence,
- and Codex-specific transcript parsing localized to the CLI/runtime edge.

The three-tier CLI model (Everyday / Situational / Forensic) and each command's purpose are described in VISION.md CLI Design.

## Operator Workspace (Future Direction)

The current architecture keeps the brain strictly read-only with respect to the project file
system. A future Operator Workspace evolution would grant the brain write authority over a scoped
`.operator/workspace/` directory. This is described in VISION.md Operator Workspace (Future
Direction), gated on four explicit criteria. Until those criteria are met, the read-only invariant
holds.

## Testability

The architecture supports three testing levels.

### Unit tests

For:

- domain policies
- deterministic guardrails
- stop logic
- decision routing around the brain

### Contract tests

For:

- runtime contracts (`AdapterRuntime`, `AgentSessionRuntime`, `OperationRuntime`)
- `OperatorBrain`
- `OperationStore`
- `EventSink`

### End-to-end tests

For:

- CLI flows
- event traces
- file-backed persistence
- selected real or simulated adapters

The system is testable with fake brains and fake adapters. Fake implementations live in `testing/fakes.py` (see Repository Direction).

## Repository Direction

The current source tree looks roughly like this:

```text
operator/
  domain/
  application/
  protocols/
  adapters/
    acp/
  providers/
  runtime/
  cli/
  dtos/
  mappers/
  testing/
docs/
  VISION.md
  ARCHITECTURE.md
  rfc/
  adr/
```

This is a directional sketch, not a frozen filesystem contract. The `domain/`, `application/`, `protocols/`, and `adapters/` directories correspond to the Architectural Layers described above.

## Standing Architectural Policy

The following principles are active architectural policy for this system:

- small protocol surface,
- async application core,
- file-backed transparency,
- LLM-driven deliberation,
- deterministic guardrails,
- and adapters that localize vendor complexity.

Deviations from these principles should be captured in an ADR. For decisions already made, see `design/adr/`.

## CLI / Workflow ADR Wave

The current CLI/workflow implementation decomposition is captured by:

- [ADR 0093](./adr/0093-cli-command-taxonomy-visibility-tiers-and-default-operator-entry-behavior.md)
- [ADR 0094](./adr/0094-run-init-project-create-workflow-and-project-profile-lifecycle.md)
- [ADR 0095](./adr/0095-operation-reference-resolution-and-command-addressing-contract.md)
- [ADR 0096](./adr/0096-one-operation-control-and-summary-surface.md)
- [ADR 0097](./adr/0097-forensic-log-unification-and-debug-surface-relocation.md)
- [ADR 0098](./adr/0098-history-ledger-and-history-command-contract.md)
