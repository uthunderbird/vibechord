# Vision

## Project

`operator` is a minimalist Python library and CLI for running other agents as an operator. The
primary audience is developers and platform engineers building or supervising multi-agent workflows
from the command line.

It is not another agent runtime in which every capability is reimplemented locally. It is a control system that drives goal-directed orchestration through an iterative operator loop — see Core Thesis below.

> **Normative language:** **must** is a binding requirement; **should** is a strong recommendation; **may** is permitted but not required. Prose stating behavior as fact (e.g., "commands are organised in three tiers") is also normative.

The operator itself has a brain: its own LLM client. That brain is used for operator work such as
planning, decomposition, delegation, evaluation, synthesis, and deciding the next move. The project
is therefore intentionally `LLM-first`, not a deterministic workflow engine with an LLM bolted on
top.

At the same time, this is not a license for opaque behavior. Safety and execution constraints are deterministic and not subject to LLM override — stop conditions, iteration limits, budget caps, and concurrency rules are enforced by the runtime regardless of what the brain decides. Observability (event recording, trace emission) is fully algorithmic. Orchestration decisions — decomposition, agent selection, progress evaluation — are LLM-driven but operate within the deterministic constraints.

### What "minimalist" means here

Minimalism does not mean fewer concepts at any cost.

It means:

- a small number of central abstractions,
- explicit boundaries,
- little accidental framework code,
- direct use of modern Python tools,
- and no extra architectural layers unless they buy clear leverage.

A proposed new abstraction fails the minimalism test if it cannot be justified by a concrete capability it enables or a concrete coupling it removes. "It seems cleaner" is not a sufficient justification.

It does not mean collapsing the operator, adapters, runtime state, and CLI into one undifferentiated
module. The system has deliberate structure — task graphs, typed commands, multi-session
coordination — because those are the concepts the problem actually requires, not accidental
complexity.

## Why This Exists

Existing agent tools tend to be optimized for one agent in one surface:

- a coding agent in a terminal,
- a hosted agent behind an API,
- an assistant inside a chat product,
- or a workflow engine that assumes steps are known in advance.

`operator` targets a different problem: goal-directed orchestration across heterogeneous agents with
different invocation models and different strengths.

Examples:

- Use Claude ACP in headless mode for repo inspection and targeted edits.
- Use Codex through an ACP session adapter when no suitable native API exists.
- Use a plain LLM API model as the operator brain.
- Run several iterations where the operator re-evaluates whether to continue with the same agent,
  switch agents, or stop.
- Assign different features of a long-lived objective to different agents running in parallel.

The primary unit of work is not a prompt and not a workflow step. It is an `operation`: an
iterative, potentially long-lived attempt to satisfy a goal under constraints, backed by a task
graph and a coordinated set of agent sessions. A **run** is the execution of an operation —
specifically, one `operator run` invocation. An operation may have multiple runs if it is
interrupted and resumed; `operation` names the persistent entity, `run` names one execution
attempt over it.

## Core Thesis

The center of the system is an `operator loop`.

That loop is responsible for:

1. taking a goal and runtime constraints,
2. building or updating a task graph that represents the working decomposition of the goal,
3. deciding whether to reason internally, call an external agent, or apply deterministic control
   logic,
4. evaluating progress from returned evidence,
5. repeating until the stop policy is satisfied.

The operator is therefore closer to a decision-making control plane than to a bag of utilities.

## Run Constraints and Stop Policy

The operator loop runs until a stop policy is satisfied. A **stop policy** is a set of
deterministic constraints that the runtime evaluates at each iteration boundary, independent of
what the brain decides.

Default stop conditions include:

- **iteration limit** — the run has reached the maximum number of operator iterations.
- **time limit** — the run has exceeded the allowed wall-clock duration.
- **budget limit** — the accumulated token or cost budget has been exhausted.
- **explicit success signal** — the brain has marked the goal as satisfied and the runtime has
  accepted that evaluation.
- **explicit failure signal** — the brain or a guardrail has declared the goal unachievable.
- **user cancellation** — the user has issued a `cancel` command.

Stop conditions are part of the control plane (Principle 2: Deterministic guardrails). They are
not subject to LLM override. When a stop condition fires, the operation moves to `TERMINAL` with
a specific `stop_reason` that is visible in `inspect` and `trace`.

## Design Principles

### 1. LLM-first orchestration

The operator drives all orchestration decisions — decomposition, agent selection, progress evaluation, and iteration — through its own LLM brain. See Core Thesis for the full loop description. This is the default mode of intelligence in the system.

### 2. Deterministic guardrails

Some logic must remain algorithmic because LLM calls are unnecessary or unsafe there. The stop conditions owned by the control plane are listed in Run Constraints and Stop Policy. Broader examples of deterministic control plane responsibilities include: retry policies, concurrency limits, event recording, adapter capability checks, dependency graph cycle detection, and completion propagation through the task graph.

The project should treat all of these as part of the control plane, not as optional polish.

### 3. Protocol-oriented integration

Every external component should be accessed through `typing.Protocol` interfaces.

This keeps the core independent from any one agent vendor or invocation method. Claude ACP, Codex
via ACP, and future agents should all appear as interchangeable implementations of stable
operator-facing contracts.

The operator core should depend on capabilities, not concrete SDKs or terminal hacks. Illustrative
protocol examples: `OperatorBrain`, `AdapterRuntime`, `AgentSessionRuntime`, `OperationRuntime`,
`OperationStore`, `EventSink`, `Clock`, `Console`. The important point is not the names.

**Deliberate exception — forensic vendor specificity without vendor-named top-level commands**:
raw upstream transcripts remain vendor-specific artifacts, but the CLI surface no longer needs
separate vendor-named top-level commands. The forensic surface uses `operator log OP` with
explicit or auto-detected agent selection (`--agent claude|codex|auto`) rather than separate
`claude-log` and `codex-log` commands. This preserves upstream transparency while keeping the
top-level command taxonomy organized by user intent rather than vendor name.

### 4. Minimal layers

The architecture should stay clean without becoming ceremonious.

We want a small number of meaningful layers:

- core domain and policies,
- application services / operator loop,
- integration adapters,
- CLI surface.

Avoid deep onion architecture, generic repository theater, or abstractions that exist only to look
pure. A layer is unjustified if it has no direct callers from an adjacent layer, or if removing it would require no changes to the layers on either side.

### 5. Transparency by default

The operator must be inspectable from the CLI.

Users should be able to see:

- what goal is being pursued,
- what the task graph looks like and which agents are assigned to which tasks,
- what the operator decided,
- which agent was called,
- what came back,
- why the next step was chosen,
- and why the run stopped.

This should be treated as a product requirement, not just a debugging aid.

## Mental Model

The system has three kinds of actors.

### Operator brain

The internal LLM client used by the operator itself.

Its job is to think about orchestration, not to impersonate every external agent. It can plan,
decompose objectives into task graphs, compare options, summarize progress, critique results, and
decide what to do next.

The operator brain also has read-only, project root–scoped access to the project file system for
context building: reading documents, listing directories, and searching text. These reads inform
planning decisions and are recorded as memory entries — they never produce side effects on the
project file system.

#### File tools

The operator brain has read-only access to the project file system for planning purposes: `read_file`, `list_dir`, and `search_text` — read only, no writes. All writes go through agents.

Results of operator file reads either inform the immediate brain decision or are persisted as
`MemoryEntry` with freshness tracking. "Same file" means the same normalized absolute path after symlink resolution — if the same path is read again, the new entry supersedes the prior one regardless of whether the file content changed. File reads emit `operator.context_read` events visible in `trace` and `dashboard`.

`MemoryEntry` supports two scopes:

- **Operation-scope** (default): context built during a single operation. Freshness-tracked per
  file path; superseded when the same path is re-read. Visible in `memory op-id` output.
- **Project-scope**: context that persists across operations for the lifetime of the project or
  until the user explicitly expires it. The brain reads all active project-scope entries at the
  start of every planning cycle, before the first brain call. Project-scope entries are surfaced in
  `memory op-id` output with a `[project]` scope label. The brain may propose new project-scope
  entries via `document_update_proposal` attention requests; the user approves and the entry is
  created or updated. No project-scope write occurs without user action.

### Agent integrations

Concrete ACP-backed implementations translate runtime contracts into the actual invocation
mechanism of the target agent. Public repository truth is expressed through runtime contracts and
runtime bindings, not package-root adapter classes.

### Runtime control plane

Deterministic infrastructure around the loop.

Examples:

- run context,
- cancellation,
- iteration accounting,
- logging,
- persistence,
- concurrency rules,
- execution budgets,
- dependency gate enforcement.

## Operation Lifecycle

An operation moves through three user-visible macro-states:

- **RUNNING** — the operator is actively driving work; agent sessions may be active in parallel.
- **NEEDS_HUMAN** — the operation has surfaced a typed attention request that the user should address:
  - Non-blocking tasks may continue; blocking attentions gate forward progress.
  - Once all blocking attentions are answered, the operation returns to **RUNNING** automatically at the next scheduler cycle — no separate user command required.
  - The operation displays as **NEEDS_HUMAN** until all blocking attentions are cleared.

  `NEEDS_HUMAN` acts as an overlay condition: the scheduler keeps working, but is gated on the blocking attention.
- **TERMINAL** — the operation has completed, failed, or been cancelled.

Internal scheduler states (`pause_requested`, `paused`, `draining`) are control-plane details. They
are visible through `context` and `dashboard` but are not part of the user's primary mental model.

### Failure visibility

When an operation reaches `TERMINAL`, the terminal state carries a `stop_reason` that distinguishes
the three outcomes:

- **completed** — the goal was satisfied.
- **failed** — the operation could not make progress: a stop policy fired (iteration limit, budget
  exhaustion, timeout), an unrecoverable adapter or brain failure occurred, or the brain declared
  the goal unachievable.
- **cancelled** — the user issued a `cancel` command.

The cause is surfaced by `inspect op-id` (human-readable summary) and `trace op-id` (full event
log including the specific guardrail or failure event that triggered the terminal transition). The
user does not need to read raw exception traces to understand what went wrong.

**Attention during drain:** If a new attention request arrives while the scheduler is in a `draining` state (e.g., draining after `pause` or due to an error recovery path), the attention is accepted and queued; the operation transitions to or remains in `NEEDS_HUMAN`. Exception: a drain caused by `cancel` is not interruptible — new attentions arriving during a cancel drain are rejected with `operation_cancelling`, and the operation proceeds to `TERMINAL`.

## Event Model

Every observable state transition in an operation must produce an event. An aggregate state change
with no corresponding event is a correctness violation — not a debugging inconvenience — because
external components cannot distinguish "nothing happened" from "something happened and no one was
told."

### Three-category taxonomy

All events fall into exactly one of three categories:

**Domain events** record aggregate state transitions: an operation changed status, a task was
created, an attention request was opened, a command was applied. Domain events are permanent and
append-only. Any component that wants to reconstruct or project operation state must be able to do
so from domain events alone without re-reading the operation store.

**Trace events** record how the system reached its decisions: brain inputs, agent invocation
details, policy evaluation results, reconciliation steps. Trace events are permanent and best-
effort. They are intended for forensic analysis and debugging, not for reactive logic. A consumer
must not gate behavior on the presence or absence of a trace event.

**Wakeup signals** are loop re-entry primitives. They are ephemeral and consumed-once: once the
loop has re-entered, the signal carries no further meaning. Wakeup signals are not observability
records and must not appear in the domain event log as semantic entries.

### The invariant

Every `state.status` mutation must be followed by an `operation.status.changed` domain event
before the operation is persisted. Every `task.status` mutation must be followed by a
`task.status.changed` domain event. Attention lifecycle transitions (`created`, `answered`,
`resolved`), operator message ingestion and drop, and scheduler pause/resume transitions all must
produce domain events at the point of occurrence.

The event log is the authoritative record of what the aggregate did. If a transition is not in
the event log, it did not happen as far as any downstream consumer is concerned.

### Key domain events by aggregate

The `Operation` aggregate emits `operation.started`, `operation.status.changed`, and
`scheduler.state.changed` to track its top-level lifecycle and control-plane transitions. Attention
lifecycle (`attention.request.created`, `attention.request.answered`, `attention.request.resolved`)
and operator message ingestion (`operator_message.received`, `operator_message.dropped`) are also
owned by the Operation aggregate.

The `Task` entity, embedded within the Operation, emits `task.created` when new tasks are applied
from a brain decision and `task.status.changed` at every subsequent status transition.

The `Session` sub-entity emits `session.force_recovered` and `session.cooldown_expired` to record
recovery and scheduling events within an agent session lifecycle.

Commands emit their own domain events at application time: `command.applied`,
`command.accepted_pending_replan`, and `command.rejected`.

### Loop architecture

The main operator loop is a `while` loop in `_drive_state`. The brain is called pull-style at each
iteration: the loop assembles current state, calls the brain, receives a decision, and executes it.
There is no push path to the brain. This structure is deliberate — it keeps the control flow linear
and the brain's decision context predictable.

Wakeup delivery uses a file-based `WakeupInbox` for cross-restart durability. In-process, a per-
operation `asyncio.Event` is set by a `WakeupWatcher` background task when new wakeup files land.
The loop awaits the `asyncio.Event` with a timeout instead of polling with a fixed sleep. This
eliminates unnecessary latency without changing the pull-loop structure or introducing actor
mailbox semantics.

### Tech debt

`operation.cycle_finished` should eventually be renamed `operation.process_run_ended` to reflect
that it records the end of a single process run within a potentially multi-run operation. The
current name implies a planning-cycle boundary, which it does not reliably represent.
`RunEvent(kind=WAKEUP)` should become a separate `WakeupSignal` type with its own storage path,
removing wakeup artefacts from the event log entirely. Both renames are deferred until external
consumers of the event log exist.

## User Interaction Model

### Typed commands and the operation inbox

The user interacts with a running operation through a **persistent durable inbox**. Every
interaction is a typed command with a unique id.

Two command classes:

1. **Control commands** — affect the scheduler: `pause`, `unpause`, `cancel`, `interrupt`,
   `involvement`.
2. **Attention answers** — address a specific open attention request through the operation:
   `answer op-id [att-id]`.

### Goal-patching commands

A third command family covers bounded live mutations to the operation goal:

- `patch_objective "..."` — replace the objective text while the operation is running.
- `patch_harness_instructions "..."` — update the harness instructions (see below) for the operator and agent path.
- `patch_success_criteria "..."` — revise the completion criteria.

#### harness_instructions

`harness_instructions` is a string (or structured document) that encodes execution policy for the operation: how the brain and agents should behave, not what goal they should achieve. Examples include branch strategy, commit conventions, language or framework constraints, security rules, and review gates. The brain reads the full `harness_instructions` at every planning cycle. Agents receive a scoped subset as part of their task context. `harness_instructions` is distinct from `objective` (which states the goal) and from `success_criteria` (which states when the goal is met).

These are collectively referred to as `patch_*` commands. They route to the operation inbox, are accepted or rejected deterministically, and take effect at the next brain planning decision. Goal-patching does not restart the operation; it supplies the brain with updated goal state for its next deliberation cycle.

**patch_* rejection conditions:** A patch command is rejected with `operation_terminal` if the operation has already reached `TERMINAL` state, with `invalid_payload` if the payload is empty or structurally malformed, and with `concurrent_patch_conflict` if a conflicting patch on the same field is already pending in the inbox.

Commands are acknowledged by the operation (accepted or rejected-with-reason) and applied
deterministically at the next decision point — never mid-turn.

### Free-form operator messages

In addition to typed commands, the user can inject context at any time:

```
operator message op-id "the client moved the deadline to Friday"
```

This is **operator-level context injection**: a free-form message that enters the operator brain's
context at the next planning decision. It is not a typed command and does not directly mutate
persisted state — it changes the brain's next decision.

Operator messages are distinct from typed commands:

| | `message` | typed command |
|---|---|---|
| Structure | free text | typed, structured |
| Routing target | user → brain context | user → state machine |
| Effect | shapes next brain decision | mutates persisted state |
| When it takes effect | next decision / replanning | deterministic on apply |

**Transparency:** active operator messages are visible in `watch` and `dashboard`. Operator
messages persist in the brain's context for a configurable number of planning cycles (the
**operator message window**, set per project or at run time; default is **3 planning cycles**). A window of 0 means the message is injected into the very next planning cycle and then immediately aged out; no minimum beyond 0 is enforced. Very large window values are permitted but may retain stale context across many iterations. When a message ages out of the window, an `operator_message.dropped_from_context` event is emitted — there is no silent expiry.

### Attention requests

When the brain requires user input to proceed — or when user action would materially affect the
outcome — it opens an **attention request**. Attention requests are typed:

- **`question`** — the brain needs a factual answer to continue planning.
- **`approval_request`** — an agent is waiting for the user to approve a proposed action.
- **`policy_gap`** — the brain encountered a situation not covered by any recorded policy and needs
  a policy decision to continue.
- **`novel_strategic_fork`** — the brain has identified a significant strategic choice point where
  user direction would change the course of the objective.
- **`blocked_external_dependency`** — the operation cannot advance until an external condition is
  met (a deploy, an API key, a human approval outside the system).
- **`document_update_proposal`** — the brain proposes an addition to a user-authored planning
  document (e.g. a strategy note, a research journal entry, a backlog item). Carries: target file
  path, proposed content, brief rationale. **Non-blocking by default**: the operation continues
  whether or not the user acts on the proposal. The user is the author of record; accepting a
  proposal means the user edits the file themselves or delegates the edit to an agent task. The
  brain does not write project files.

Blocking attention requests (`approval_request`, `blocked_external_dependency`, and — at
`collaborative` or higher involvement — `policy_gap` and `novel_strategic_fork`) move the operation
to `NEEDS_HUMAN`. The operation resumes when the user answers via `operator answer op-id [att-id]`.
Non-blocking attention requests (including `document_update_proposal`) do not affect operation
state; they appear in `watch` and `dashboard` for user awareness.

### Active turn control

The user can stop a running agent turn without cancelling the operation:

```
operator interrupt op-id --task task-3a7f2b1c
```

The user addresses the turn through its task, not through a session id. Session ids are not a
primary user-facing concept.

If `interrupt` targets a task that is not in `RUNNING` state, the command is rejected with reason `stop_turn_invalid_state` and the actual state of the task is included in the rejection message (e.g., `task is COMPLETED`). The rejection is surfaced as a CLI error message and emitted as an event in the operation trace. No side effects occur.

## Task Graph

The operator maintains an explicit **directed acyclic task graph** for each operation.

### Task lifecycle

A task moves through: `PENDING → READY → RUNNING → COMPLETED | FAILED | CANCELLED`.

The transition from `PENDING` to `READY` is deterministic: when all dependency tasks are complete,
the dependent task becomes runnable automatically — no LLM call required.

`PENDING` is the canonical state for a task that has unresolved dependencies. There is no separate
`BLOCKED` state in the state machine. In the CLI task view, `[BLOCKED]` is a display grouping label
for `PENDING` tasks that have at least one dependency that has not yet completed — it is a
presentation alias, not a distinct lifecycle state.

### Task graph invariants

These are enforced by the runtime, not by the brain:

- **Ацикличность**: the graph is a DAG. Any `add_dependency` that would create a cycle is
  immediately rejected with `dependency_cycle_detected`.
- **Monotonicity**: dependencies are added, not silently removed. The brain is the only actor that may propose dependency removal. Removal requires a non-empty `reason` string supplied as a mandatory parameter on the removal call. The runtime rejects any removal call that omits `reason` or provides an empty string; the rejection reason is `dependency_removal_requires_reason`. Accepted removals are logged with their reason string in the event trace.
- **Completion propagation**: task completion triggers immediate deterministic unblocking of all
  dependent tasks that have no other pending dependencies.
- **No self-dependency**: a task cannot depend on itself.

The `[BLOCKED]` CLI label is a presentation alias — see Task lifecycle above. The invariants apply to the five canonical states only.

### User-facing task view

```
$ operator tasks op-id

[RUNNING]
  task-3a7f2b1c  "Implement ACP session runner"    → claude-acp   iter 4
  task-9e1c4d2a  "Write unit tests for ACP"         → claude-acp   iter 4

[READY]
  task-7b3f1e9d  "Implement Codex adapter"          → codex        (pending assignment)

[BLOCKED]
  task-2c8a5f3b  "Integration tests"
    blocked by: task-3a7f2b1c (RUNNING), task-7b3f1e9d (READY)

[COMPLETED]
  task-a1d4e7c2  "Domain model setup"               ✓
```

### Task IDs

Each task has two identifiers:

- `task_id`: UUID — the primary key. Never changes. Used internally and in all persisted state.
- `task_short_id`: random 8-character lowercase hex — a human-readable display alias, for example
  `task-3a7f2b1c`. Unique within the operation. Created at task creation time and stored alongside
  the UUID.

The short ID exists so users can reference tasks in commands and operator messages without typing
UUIDs. It has no semantic meaning derived from task content.

## Multi-Session Coordination

An operation may run multiple agent sessions in parallel when the task graph and concurrency policy
allow it.

The operator brain remains the single decision serializer. Sessions are execution resources —
parallel in execution, but coordinated by one brain. Serialization is enforced through a single
event queue: completion events, attention requests, and wakeups from all concurrent sessions are
enqueued and processed by the brain one at a time. This means the brain never races against itself;
each planning decision sees a consistent snapshot of operation state before the next event is
consumed.

```
Operation
  ├── operation.inbox    ← user commands (message, pause, answer, patch, cancel)
  ├── session_A.inbox    ← session-level control (interrupt for the bound task)
  ├── session_B.inbox
  └── event_queue        ← events from all sessions → brain processes decisions
```

**Routing rules:**

- `message`, `answer`, `pause`, `patch_*`, `cancel` → operation inbox.
- `interrupt` → addressed by task id, routed to the session bound to that task.
- The user never addresses session ids directly.

**Partial completion:** when one session completes its task while others are still running, the
brain receives a completion event and replans for the next task in the graph. The operation does not
wait for all sessions before making its next decision.

## Long-Lived Objective Hierarchy

Long-lived work is structured in four runtime entity levels:

```
Objective       ← single per operation; jointly owned by user and brain
  └── Feature   ← optional; a bounded deliverable with acceptance_criteria and review_state
        └── Task   ← atomic work unit; brain proposes, runtime enforces
              └── Subtask   ← optional; managed internally by the assigned agent
```

**Feature lifecycle states:** `in_progress → ready_for_review → accepted | needs_rework`.

A Feature is warranted when a delivery unit: (a) has acceptance criteria separate from the
Objective; (b) can be assigned as a whole to one agent or coordinated group; (c) has a meaningful
"ready for review" state for the user. Otherwise, decompose directly into Tasks.

**Feature authority:** Both the brain and the user may propose Features. The brain may propose
Feature decomposition during planning; the user may also introduce or rename Features through goal
patching or direct interaction. The review lifecycle (`ready_for_review → accepted | needs_rework`)
is always user-facing — the brain cannot unilaterally mark a Feature as accepted.

**What is not a runtime entity:** Vision, Strategy, Requirements, Scenarios, Use Cases, User
Stories. These are documentary artifacts. They do not have their own lifecycle in the state machine.
The user may maintain such documents in the project root; the brain reads them via its existing
read-only file access and may persist relevant passages as project-scope `MemoryEntry` context. The
brain never writes to user-authored project documents.

If the brain's planning reasoning should inform an update to a user-authored document — for example,
a strategy note, a research journal entry, or a backlog item — it emits a
**`document_update_proposal`** attention request. This carries the target file path, the proposed
content, and a brief rationale. It is **non-blocking by default**: the operation continues whether
or not the user acts on it. The user is the author of record; accepting a proposal means the user
edits the file themselves (or delegates the edit to an agent task). The brain does not write project
files under any involvement level.

## Operator Workspace (Future Direction)

The current architecture keeps the brain strictly read-only with respect to the project file system.
Planning documents — strategy, roadmap, research journal, backlog — are user-authored and
user-maintained. The brain reads them; it may propose additions via `document_update_proposal`
attentions; it does not write.

A future evolution of this model is a dedicated **operator workspace**: a scoped directory (e.g.
`.operator/workspace/`) where the brain holds write authority over its own planning documents —
strategy notes, a running journal, a roadmap draft, a backlog. In this model the brain is not merely
a reader and proposer; it is the author of its own planning layer, under a defined governance
contract.

**Criteria for when this is worth building:**

1. The `document_update_proposal` attention queue has become a user-review bottleneck in practice —
   proposals accumulate faster than the user can review them, or the user routinely accepts them
   without meaningful review (de facto delegating authorship already).
2. A new involvement level is defined that explicitly grants the brain write authority over a scoped
   workspace, with a clear boundary between the workspace directory and the rest of the project
   file system.
3. Write governance machinery exists: workspace writes are domain events (`workspace.document.written`,
   `workspace.document.updated`), visible in `trace`, revertable via a `workspace revert` command,
   and auditable in `dashboard` without having to read the files directly.
4. The workspace directory is gitignored by default (like `.operator/`), with explicit opt-in for
   committing workspace documents to version control.

Until all four criteria are met, the read-only invariant holds. The workspace concept is not a
shortcut around the review step; it is a promotion of the brain from proposer to author, which
requires explicit governance infrastructure before it is safe to enable. Artifacts are user-facing deliverables — files, diffs, reports, or structured data returned as the concrete output of completed task work. They are distinct from `MemoryEntry` objects, which are operator-internal context used for planning and are not exposed as deliverables. The operator does not produce artifacts; only agent sessions do. Artifacts are accessible via `artifacts op-id` (Tier 3) and may be referenced in task output summaries shown by `inspect`.

## Agent Adapter Contract

An agent adapter should describe the lifecycle that the operator needs, not vendor-specific details.

The following capabilities define the adapter contract. Required capabilities must be implemented by every conforming adapter. Optional capabilities must be declared in the adapter's capability response; the operator checks before calling them.

| Capability | Required / Optional | Semantics |
|---|---|---|
| `start` | Required | Begin a new agent session for a task; returns a session handle. |
| `send` | Required | Continue an active session with a follow-up prompt or response. |
| `status` | Required | Return the current session status without side effects. |
| `collect_output` | Required | Return the normalized outputs produced so far (text, artifacts, structured data). |
| `stop` | Required | Request an orderly stop of the current agent turn; may be a no-op if the turn is already complete. |
| `capabilities` | Required | Return a declaration of which optional capabilities this adapter supports. |
| `cancel` | Optional | Forcibly terminate a session mid-turn. If absent, `stop` is used instead and the operator waits for the turn to complete. |

If an adapter does not support an optional capability that the operator would otherwise invoke, the operator must degrade gracefully — either by skipping the call or by substituting the nearest required capability — without raising an unhandled error.

Different agents may have very different implementations:

- Claude ACP can map naturally to headless requests.
- Codex can map to an ACP session over stdio via `codex-acp`.
- A hosted agent may map to HTTP polling.

Those differences belong in adapters, not in the operator loop.

## Claude ACP And Codex

### Claude ACP

Claude ACP is a first-class target because it already has a headless mode that fits operator-driven
invocation well.

This is now the canonical Claude integration path and the reference shape for Claude-facing
session-oriented adapters.

### Codex

Codex is still a first-class target, but the integration path is different.

The preferred integration path is an ACP adapter built around `codex-acp`, communicating over stdio
with session-oriented messages instead of scraping a terminal UI.

That adapter is responsible for:

- creating and loading Codex ACP sessions,
- sending prompts and follow-ups,
- observing structured progress and stop reasons,
- collecting normalized outputs and artifacts,
- and translating ACP events into the operator runtime contracts (`AdapterRuntime` at transport
  scope, `AgentSessionRuntime` at one-live-session scope).

The operator core should not know or care whether Codex is reached through its own CLI surface, an
ACP bridge, or future native APIs. It should only depend on stable runtime contracts.

## CLI Design

`operator` must be usable as a real command-line tool, not just an embeddable library. The CLI is part of the product definition because operators are especially valuable in shell-driven environments.

The CLI is a thin surface over the same application layer used by Python callers. It must support:

- starting an operation from a goal,
- selecting or constraining available agents,
- watching live what is happening and whether user input is needed,
- answering attention requests and injecting context messages inline,
- inspecting progress, task graph, and decision history on demand,
- drilling down to raw agent transcripts when debugging,
- supervising many operations from a cross-operation agenda,
- non-interactive automation with machine-readable output,
- and preserving transparent logs and artifacts.

### CLI design principles

The CLI UX is governed by these requirements:

- **P1 — User intent, not service architecture.**
  Commands are organized by what the user is trying to do, not by which internal service method
  they invoke. Internal abstractions such as `OperationCommandType` or scheduler cycles must not
  surface at the user level.
- **P2 — Progressive disclosure, not hiding.**
  The default `--help` shows the most important commands first, followed by a smaller secondary
  section for detail and forensic work. Internal debug commands remain reachable, but are hidden
  from the default help surface and shown only in `--help --all`.
- **P3 — Flat is better than artificial grouping.**
  Operation-management commands are top-level. Only genuine domain namespaces such as `project`
  and `policy` earn a subgroup.
- **P4 — Fleet is the default surface.**
  `operator` with no arguments and a TTY opens the fleet view. With no TTY or `--once`, it emits a
  single fleet snapshot. If no operations exist and no TTY is attached, it falls back to help.
- **P5 — Hyphen-case everywhere.**
  User-facing command names use kebab-case. Names such as `stop_turn` are replaced by intentful
  user-facing names such as `interrupt`.
- **P6 — Human-readable by default.**
  Every command has readable default output. `--json` is the machine-readable contract. `--brief`
  is the compact single-line contract where appropriate.
- **P7 — Destructive commands confirm.**
  `cancel` and similarly consequential commands prompt unless the user explicitly passes `--yes`.
- **P8 — Friendly operation references.**
  Commands that accept an operation reference should accept the full id, an unambiguous short
  prefix, `last`, and, where meaningful, an unambiguous project/profile-derived reference.

### Principle: commands named by user intent, not system mechanism

Every command should be named for what the user wants to accomplish, not for the internal mechanism
it triggers. `resume` is better than `tick`. `agenda` is better than `list-scheduled-wakeups`.
Commands that expose implementation details belong in the forensic tier, not the everyday tier.

### Three tiers by frequency

Commands are organised in three tiers. The everyday tier is shown first in `--help` output. Hidden
debug commands remain reachable, but are not part of the default help surface.

#### Tier 1 — Everyday

Needed every run. Always at the top level.

| Command | Purpose |
|---|---|
| `operator` | fleet view (TTY) or fleet snapshot (non-TTY) |
| `run` | start a new operation |
| `fleet` | all active operations across projects |
| `status op-id` | operation state and attention summary |
| `answer op-id [att-id]` | answer a blocking attention request |
| `message op-id "..."` | inject free-form context for the operator brain |
| `pause op-id` | soft pause after the current agent turn |
| `unpause op-id` | resume a paused operation |
| `interrupt op-id [--task task-id]` | stop the current agent turn without cancelling |
| `cancel op-id` | cancel the operation |
| `history [op-id]` | operation history ledger |
| `init` | set up operator in the current project |
| `project ...` | project profile management |

**Note on `run`:** The command is named for the user's intent — "run this goal" — not for the entity it creates. `run` creates an *operation* and begins its first *run*. See the operation/run distinction in Why This Exists.

#### Tier 2 — Situational

Needed in specific circumstances: something went wrong, user wants to understand progress, autonomy
policy needs adjustment.

| Command | Purpose |
|---|---|
| `watch op-id` | live surface — what is happening, is input needed |
| `inspect op-id` | progress snapshot — what has been done |
| `dashboard op-id` | live L2 view: inspect with task board and command receipts |
| `tasks op-id` | task graph with dependency status and agent assignment |
| `memory op-id` | distilled memory entries |
| `artifacts op-id` | durable outputs |
| `attention op-id` | list open and answered attention requests |
| `resume op-id` | continue after interruption or crash |
| `unpause op-id` | remove a soft pause |
| `involvement op-id` | change the autonomy level for a running operation (see below) |
| `report op-id` | operation summary report |
| `list` | list all persisted operations |
| `policy ...` | policy management |

#### Involvement levels

**Definitions:** A **policy gap** is a decision the brain must make for which no applicable rule exists in `harness_instructions` or in prior answered attentions for this operation. A **novel strategic choice** is a subtype of policy gap where the decision could materially alter the operation's scope or approach (e.g., changing a target branch, adopting a different implementation strategy).

The `involvement` command sets the autonomy level for a running operation. Two primary levels:

- **unattended** — the brain proceeds without interrupting for routine decisions. Policy gaps and
  novel strategic choices surface as typed attention requests but do not block non-affected tasks.
  Best for long-running background work where the user prefers to review outcomes rather than
  approve each step.
- **interactive** — the brain surfaces decisions for user confirmation before acting on them. Policy
  gaps and strategic forks block forward progress until the user answers. Best for exploratory or
  high-stakes work where the user wants approval authority at each branch point.

Under `unattended`, both policy gap types surface as attention requests but do not block non-affected tasks. Under `interactive`, both types block forward progress until answered.

The active involvement level is inspectable via `context op-id` and is visible in `dashboard` and
`watch`. It can be changed at any point while the operation is running; the change takes effect at
the next brain decision point.

#### Tier 3 — Forensic and Admin

Needed rarely. For debugging, setup, and one-off recovery operations. A **wakeup** is a scheduled future event that re-activates the scheduler at a specified time or condition — used for retries, polling, and deferred checks.

| Command | Purpose |
|---|---|
| `log op-id [--agent claude|codex|auto]` | raw agent session log |
| `trace op-id` | forensic event log |
| `debug daemon` | background wakeup daemon |
| `debug tick op-id` | single scheduler cycle |
| `debug recover op-id` | force recovery of a stuck agent turn |
| `debug resume op-id` | resume with scheduler-cycle control |
| `debug wakeups op-id` | pending and claimed wakeups |
| `debug sessions op-id` | session and background run records |
| `debug command op-id` | enqueue a typed command |
| `debug context op-id` | effective control-plane context |
| `debug trace op-id` | full forensic trace view |
| `debug inspect op-id` | full forensic dump |

### Namespace structure

Core operational commands are flat. Admin and setup commands use subcommand namespaces (`project`,
`policy`). This keeps the everyday workflow discoverable while grouping less-frequent operations.

### Command structure contract

The CLI command structure is:

#### Primary commands shown in default `--help`

- `operator`
- `operator run [GOAL]`
- `operator fleet`
- `operator status OP`
- `operator answer OP [ATT]`
- `operator cancel OP`
- `operator pause OP`
- `operator unpause OP`
- `operator interrupt OP`
- `operator message OP TEXT`
- `operator history [OP]`
- `operator init`
- `operator project ...`

#### Secondary commands shown below the primary section

- `operator log OP`
- `operator tasks OP`
- `operator memory OP`
- `operator artifacts OP`
- `operator attention OP`
- `operator report OP`
- `operator policy ...`
- `operator list`

#### Hidden debug commands

- `operator debug daemon`
- `operator debug tick OP`
- `operator debug recover OP`
- `operator debug resume OP`
- `operator debug wakeups OP`
- `operator debug sessions OP`
- `operator debug command OP`
- `operator debug context OP`
- `operator debug trace OP`
- `operator debug inspect OP`

### Command-specific UX requirements

#### `operator` with no arguments

- opens fleet view when a TTY is attached and operations exist
- emits one fleet snapshot when non-TTY or when `--once` is requested
- falls back to help when no operations exist and no TTY is attached

#### `operator run`

- accepts `--agent` as the user-facing way to constrain allowed agents
- prompts interactively for a goal when no goal is provided and no active project supplies a
  default objective
- writes the new operation reference to `.operator/last`

#### `operator status`

- is the default human-readable operation summary command
- supports `--brief` as the compact single-line scriptable form
- ends with an explicit action line when the operation is blocked and user action is needed

#### `operator answer`

- takes the operation reference first: `operator answer OP [ATT]`
- if `ATT` is omitted, auto-selects the oldest blocking attention request
- opens `$EDITOR` or prompts inline when `--text` is omitted

#### `operator cancel`

- prompts for confirmation unless `--yes` is passed

#### `operator interrupt`

- is the user-facing replacement for `stop_turn`
- stops the current agent turn without cancelling the whole operation
- may be scoped by task short id or UUID using `--task`

#### `operator log`

- replaces separate vendor-named top-level transcript commands
- auto-detects the active agent unless `--agent` explicitly selects one
- supports `--follow` for live tailing

#### `operator history`

- reads the committed per-project operation ledger rather than live runtime state
- remains distinct from `operator list`, which reads current persisted operation state

#### `operator init`

- is the primary first-run project setup flow
- creates `operator-profile.yaml` in the current directory
- adds `.operator/` to `.gitignore`
- does not silently overwrite an existing project profile

### The `watch` surface

`watch` is the primary live surface. The design goal: the user looks at the screen and within one
second knows whether they need to do anything.

**TTY mode** (interactive terminal):

```
● Running  iter 4/100  ·  last activity: 8s ago

  Task  task-3a7f2b1c  "Implement ACP session runner"
  Agent  claude-acp  ·  writing session lifecycle methods

  ⚠  policy gap: "Should I commit directly to main?"
     → operator answer att-7f2a "use a branch"
```

Key elements:
- First line: macro-state (`● Running` / `⚠ Needs input` / `✓ Done`), iteration counter, and
  **relative timestamp** `last activity: Xs ago` — not a poll heartbeat, but the last event that
  changed visible state
- Active task with short ID and human-readable title
- What the agent is doing right now, in plain language
- Open attention requests with a ready-to-copy answer command template
- No UUIDs in the primary view — only short task IDs and human-readable names
- No internal state labels (`scheduler=active`, `session_status=running`) in the primary view

**Non-TTY / pipe mode:** JSONL events, same as the current `--json` output. Machine-readable output
is not broken by the richer TTY display.

### Drill-down model

The user can navigate from the live surface to raw evidence in four levels:

```
L1  watch op-id           live — "is input needed, what is happening"
      ↓
L2  inspect op-id         snapshot — progress, recent decisions, open attention
    dashboard op-id       live L2 — same content with live updates + task board
      ↓
L3  tasks op-id           task graph with dependency and assignment detail
    trace op-id           forensic event log
    memory / artifacts    distilled state
      ↓
L4  log op-id             raw agent transcript
```

Navigation invariant: moving from any level to the next requires only `operation_id` and optionally
a short task ID. The user never needs to know internal session UUIDs to drill deeper.

The user will rarely go to L3 or L4. When they do, it is because something went wrong and they need
to understand exactly what happened. That path must exist and must be complete — but it should not
intrude on the everyday workflow.

## Non-Goals

At least initially — until the core loop, multi-session coordination, and third-adapter milestone are stable — `operator` should not try to be:

- a generic workflow orchestration platform,
- a visual automation builder,
- a replacement for every agent SDK,
- a full distributed task queue,
- or a benchmark-driven autonomous-agent research project.

The goal is narrower and more practical: a clean operator library and CLI that can drive real agents
toward a goal through iterative control, coordinating multiple sessions across a structured task
graph.

## Early Success Criteria

The first meaningful version should demonstrate:

1. **A stable operator loop driven by an internal LLM brain** — the loop runs at least 10 iterations against a mock brain and mock adapter without crashing, and the brain's planning output is consumed and acted on at each iteration.
2. **Deterministic run policies around that loop** — all six stop conditions (iteration limit, time limit, budget limit, explicit success, explicit failure, user cancellation) fire correctly and move the operation to `TERMINAL` in isolated tests, with no LLM call required to trigger any of them.
3. **One clean headless adapter for Claude ACP** — the adapter implements all six required capabilities from the adapter contract, passes a conformance test suite that exercises each capability, and requires no changes to the operator core when added.
4. **One ACP-backed adapter for Codex** — same conformance requirements as item 3; the operator core is unaware that the underlying transport is stdio.
5. **A usable CLI with transparent event output** — `run`, `watch`, `inspect`, `trace`, and `cancel` work end-to-end; `watch` shows the current task, agent, and any open attention request within one second of state change; `trace` emits a complete JSONL event log for the operation.
6. **An architecture that makes the third adapter easier than the first** — specifically, adding a third adapter must require no changes to the operator core or to any existing protocol definition.

**Phase 2 milestones** (subsequent, after the first working version) add:

7. **Explicit task graph with dependency tracking and short display IDs** — `tasks op-id` shows the five canonical states, dependency edges, and short IDs; cycle detection rejects invalid `add_dependency` calls; completion propagation unblocks dependent tasks without an LLM call.
8. **Multi-session parallel coordination within a single operation** — at least two agent sessions run concurrently on independent tasks; the brain serializes planning decisions through the event queue; no race condition between sessions in the test harness.
9. **User-facing operator messages (context injection) with transparency** — `message op-id "..."` injects context that appears in the brain's next planning prompt; `operator_message.dropped_from_context` is emitted when a message ages out; active messages are visible in `watch` and `dashboard`.
10. **Operator read-only file tools for context building** — `read_file`, `list_dir`, and `search_text` are available to the brain; each read emits an `operator.context_read` event; no file write is possible through these tools.

## CLI Closure Wave

The current CLI/workflow implementation wave is decomposed into:

- [ADR 0093](./adr/0093-cli-command-taxonomy-visibility-tiers-and-default-operator-entry-behavior.md)
- [ADR 0094](./adr/0094-run-init-project-create-workflow-and-project-profile-lifecycle.md)
- [ADR 0095](./adr/0095-operation-reference-resolution-and-command-addressing-contract.md)
- [ADR 0096](./adr/0096-one-operation-control-and-summary-surface.md)
- [ADR 0097](./adr/0097-forensic-log-unification-and-debug-surface-relocation.md)
- [ADR 0098](./adr/0098-history-ledger-and-history-command-contract.md)

These ADRs narrow the command taxonomy, project-entry workflow, addressing model, one-operation
control surface, forensic/debug split, and history-ledger contract needed to make the CLI vision
executable.
