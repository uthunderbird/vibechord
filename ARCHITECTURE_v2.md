# Operator v2 Architecture

> **Status:** Living document — updated every 5 swarm iterations.
> **Last updated:** Iteration 62 — FINAL (repaired Rounds 1–5 + MemGPT multi-action design + Round 10 consistency fixes)
> **Process:** Swarm Mode — Moderator/Executor with 5 expert team (Liskov, Armstrong, Hickey, Fowler, Vogels)
> **Section numbering:** Section numbers are stable identifiers from the design process; gaps (§16, §20, §24, §28, §31, §36, §41) indicate sections removed during iteration and are intentional. Cross-references use these stable numbers.

---

## 0. Executive Summary

Operator v2 is a ground-up redesign that eliminates the architectural errors of v1 while preserving its core strengths. The central insight is that v1 conflates **four distinct concerns** in `OperationState` and the drive loop:

1. **Domain state** (what happened — event-sourced, canonical)
2. **Read model** (projections for querying — derived, not canonical)
3. **Process Manager state** (drive loop coordination — ephemeral, reconstructible)
4. **Runtime configuration** (operation-scoped settings — immutable after creation)

Separating these four concerns eliminates: the drive loop complexity, the OperationState blob, the `pending_*` field opacity, and the daemon/standalone ambiguity.

---

## 1. Verified Architectural Problems in v1

All items below are **verified facts** grounded in the actual codebase.

### 1.1 OperationState God Object (37 fields)

`OperationState` holds 37 top-level fields across 6 distinct concern categories:

| Category | Fields | Count |
|----------|--------|-------|
| Domain canonical | operation_id, goal, policy, status, objective, tasks, features, sessions, executions, artifacts, memory_entries | 11 |
| Traceability/read-model | operation_brief, iteration_briefs, agent_turn_briefs | 3 |
| **Process Manager state** | current_focus, scheduler_state, operator_messages, pending_wakeups, attention_requests, processed_command_ids, pending_attention_resolution_ids, pending_replan_command_ids | 8 |
| Policy/coverage | active_policies, policy_coverage, involvement_level | 3 |
| Operational config | execution_budget, runtime_hints, execution_profile_overrides | 3 |
| Timestamps/meta | run_started_at, created_at, updated_at, final_summary, schema_version, canonical_persistence_mode | 6 |

**Critical finding:** The 8 "Process Manager state" fields are PM coordination state, not domain state:
- `pending_attention_resolution_ids` — "run one more cycle to process this attention answer" signal
- `processed_command_ids` — command idempotency deduplication
- `pending_replan_command_ids` — next-cycle replan scheduling

These should not be persisted as canonical aggregate state.

### 1.2 Drive Loop Complexity (verified: 12+ branching conditions)

`operation_drive.py` conflates three distinct concerns:

1. **Lifecycle gating** — should this cycle run at all? (timeout, budget, status checks)
2. **Runtime reconciliation** — background runs, cooldowns, wakeups, stale sessions
3. **Policy execution** — decide → execute → evaluate

The `while` loop condition itself has 4 clauses. The loop body has 12+ `if` branches before `_execute_decision`. The `attached inner-while loop` (now fixed) was a symptom of this conflation.

### 1.3 Missing State Machine Formalization

Three state machines are embedded in OperationState with no formal transition graph:

- `OperationStatus`: RUNNING → {COMPLETED, FAILED, CANCELLED, NEEDS_HUMAN} (+ NEEDS_HUMAN → RUNNING retry)
- `SessionObservedState`: IDLE → RUNNING → WAITING → TERMINAL
- `SchedulerState`: ACTIVE → PAUSE_REQUESTED → PAUSED | ACTIVE → DRAINING

Invalid transitions are not prevented by construction — any code can write any status value.

### 1.4 ACP Adapter Issues (largely fixed, but architecture unclear)

- `-c` flag ordering bug: **fixed** — `_build_codex_acp_command` now correctly inserts before `--`
- Adapter-key string comparisons in `session_runtime.py`: `if adapter_name == "codex_acp"` — fragile ownership
- No formal ownership boundary between `AcpSessionRunner` and `CodexAcpAgentAdapter`

### 1.5 Two Time Domains Not Separated

"Slow time" (decisions, outcomes — event-sourced) and "fast time" (active ACP subprocess I/O — ephemeral) are handled in the same drive loop, causing the `attached inner-while` pattern. They must be separated by design.

---

## 2. Core Architecture Principles for v2

### 2.1 Two Time Domains

| Domain | Content | Persistence | Owner |
|--------|---------|-------------|-------|
| **Slow time** | Decisions, task assignments, session outcomes, events | Event log (canonical) | Operation Aggregate |
| **Fast time** | Active ACP subprocess I/O, streaming output, permission requests | Ephemeral (in-memory) | AdapterRuntime |

The drive loop only touches slow time. Fast time is handled entirely within the AdapterRuntime. The bridge is the `collect()` call — when an agent turn completes, it produces outcome events that enter the event log.

### 2.2 Event Log is Canonical, Snapshot is Cache

The event log is the single source of truth. The `OperationState` snapshot is a cache of the event log for fast access. If the process dies, replay the event log to reconstruct the snapshot. This is already the v1 intent with `canonical_persistence_mode = EVENT_SOURCED` — v2 makes it strict and non-negotiable.

### 2.3 Process Manager is Stateless

The drive loop (`DriveService`) is a pure function: `drive(snapshot, config) -> commands`. It has no state of its own. All "drive loop state" (current_focus, scheduler_state, operator_messages, etc.) is either:
- Reconstructible from the event log (and becomes part of the snapshot), or
- Ephemeral coordination state that lives in `ProcessManagerContext` (a local struct, not persisted)

### 2.4 Illegal States are Unrepresentable

State machine transitions are implemented via methods that validate, not via field mutation:
```python
operation.complete(summary="...")  # validates RUNNING → COMPLETED
session.mark_terminal(SessionTerminalState.FAILED)  # validates RUNNING/WAITING → TERMINAL
```
Direct field writes to `status` are not possible from outside the aggregate.

---

## 3. Domain Model Decomposition

### 3.1 OperationAggregate (event-sourced, canonical)

```python
class OperationAggregate:
    """Root aggregate. Produces domain events. All mutations through methods."""
    operation_id: str
    goal: OperationGoal
    policy: OperationPolicy
    status: OperationStatus          # private setter — use methods
    objective: ObjectiveState
    tasks: list[TaskState]
    features: list[FeatureState]
    scheduler_state: SchedulerState  # ACTIVE | PAUSE_REQUESTED | PAUSED (event-sourced, see §22.6)
    attention_requests: list[AttentionRequest]  # canonical owner — see §32 for lifecycle
    read_model: OperationReadModel    # projection target; drive loop appends iteration_briefs and decision_records directly (see §3.5, §11.2)
    sessions: SessionRegistry         # child aggregate; owns session lifecycle (see §3.2)
    execution_registry: ExecutionRegistry  # child aggregate; owns background execution tracking (see §3.3)
    operator_messages: list[OperatorMessage]  # projected from OperatorMessageReceived events (see §22.6, §47)
    
    # State machine methods — validate transitions
    def start(self) -> OperationStarted: ...
    def complete(self, summary: str) -> OperationCompleted: ...
    def fail(self, summary: str) -> OperationFailed: ...
    def needs_human(self, summary: str) -> OperationNeedsHuman: ...
    def cancel(self) -> OperationCancelled: ...
    def resume(self) -> OperationResumed: ...
    def to_checkpoint(self) -> "OperationCheckpoint": ...
    # Packages self + session_registry + execution_registry + config + seq (epoch counter)
    # into OperationCheckpoint. session_registry and execution_registry are stored on the
    # aggregate for this purpose (see §15.3 for full OperationCheckpoint field list).
```

### 3.2 SessionRegistry (event-sourced child aggregate)

```python
class SessionRegistry:
    """Owns session lifecycle within one operation."""
    sessions: list[SessionRecord]
    
    # SessionRecord — trimmed to domain-relevant fields only
    # Removed: cooldown_until, recovery_count, execution_profile_stamp (runtime concerns)
    
    def register(self, adapter_key: str) -> SessionRegistered: ...
    def mark_running(self, session_id: str) -> SessionRunning: ...
    def mark_waiting(self, session_id: str, reason: str) -> SessionWaiting: ...
    def mark_terminal(self, session_id: str, state: SessionTerminalState) -> SessionTerminated: ...
    def mark_cancelled(self, session_id: str, cancelled_by: str) -> SessionCancelled: ...
```

### 3.3 ExecutionRegistry (event-sourced child aggregate)

```python
class ExecutionRegistry:
    """Owns background execution tracking within one operation."""
    executions: list[ExecutionRecord]
```

**`ExecutionRecord` fields:**

```python
class ExecutionRecord(BaseModel):
    """Tracks one background agent execution. Domain-relevant fields only."""
    execution_id: str
    session_id: str
    task_id: str | None           # None for untasked background runs
    observed_state: ExecutionObservedState
    started_at: datetime
    completed_at: datetime | None = None
    result_status: AgentResultStatus | None = None   # set on completion; see §8.3 for enum definition
```

**`ExecutionObservedState` enum:**

| Value | Meaning |
|-------|---------|
| `RUNNING` | Background asyncio Task is in flight |
| `COMPLETED` | Task completed successfully (maps to `AgentTurnCompleted` event) |
| `FAILED` | Task completed with error (maps to `AgentTurnFailed` event) |
| `LOST` | Process died while task was RUNNING; detected by RuntimeReconciler on restart |

Execution state is derived from domain events — there is no separate `ExecutionStateMachine`. On `AgentTurnStarted`, an `ExecutionRecord` with `observed_state=RUNNING` is created. On `AgentTurnCompleted` / `AgentTurnFailed`, the corresponding record is updated. On process restart, any record still in `RUNNING` state is set to `LOST` by the RuntimeReconciler (see §30.4).

### 3.4 OperationConfig (immutable operational configuration)

```python
@dataclass(frozen=True)
class OperationConfig:
    """
    Set at operation creation. Immutable-by-value (frozen dataclass) — never mutated in place.
    Rebuilt by OperationConfigProjector (see §9.3) when config-change domain events arrive.
    Not the same as "not event-sourced" — config changes ARE event-sourced via
    ExecutionProfileOverrideUpdated, BudgetExtended, and InvolvementLevelChanged events (see §22.8).
    """
    execution_budget: ExecutionBudget
    runtime_hints: RuntimeHints
    execution_profile_overrides: dict[str, ExecutionProfileOverride]
    involvement_level: InvolvementLevel
```

### 3.5 OperationReadModel (projection — not canonical)

```python
class OperationReadModel:
    """Built by projectors from event stream. Never written by aggregates.
    
    Exception: DriveService appends IterationBrief and DecisionRecord directly to
    agg.read_model.iteration_briefs and agg.read_model.decision_records within
    the drive loop (§11.2), rather than via projector events. This is a pragmatic
    shortcut — these records are drive-loop artifacts, not domain events, and do
    not need event-sourced history. All other read model fields are projector-only.
    """
    iteration_briefs: list[IterationBrief]    # one per drive loop cycle
    decision_records: list[DecisionRecord]    # one per brain.decide() call (finer than IterationBrief)
    agent_turn_briefs: list[AgentTurnBrief]
    artifacts: list[ArtifactRecord]
    memory_entries: list[MemoryEntry]
    operation_brief: OperationBrief | None
```

### 3.6 ProcessManagerContext (ephemeral — drive loop only)

> **Superseded by §23.2** — use §23.2 as the authoritative definition. This entry is retained as a design-iteration record only.

```python
@dataclass
class ProcessManagerContext:
    """Drive loop working memory. Never persisted. Reconstructible from event log + runtime."""
    processed_command_ids: set[str]
    pending_attention_resolution_ids: list[str]
    pending_replan_command_ids: list[str]
    current_focus: FocusState | None
    # Note: scheduler_state is aggregate state (in OperationAggregate.scheduler_state),
    # not duplicated here. ProcessManagerContext only holds ephemeral/runtime values.
    operator_messages: list[OperatorMessage]  # REMOVED in v2 — moved to OperationAggregate (§23.1)
    pending_wakeups: list[WakeupRef]
    # Note: attention_requests are owned by OperationAggregate (see §3.1, §32).
    # ProcessManagerContext does not duplicate this list.
    policy_context: PolicyCoverage | None
    available_agents: list[AgentDescriptor]
```

---

## 4. Drive Loop Architecture v2

### 4.1 Three Distinct Services (not one loop)

```
LifecycleGate          — should this cycle run? (synchronous, fast)
RuntimeReconciler      — background runs, cooldowns, wakeups (async, side-effecting)
PolicyExecutor         — decide → execute → evaluate (async, the core loop)
```

### 4.2 Cleaned Drive Loop

> **Conceptual sketch only.** This pseudocode illustrates the three-phase structure; it does not match the authoritative `DriveService.drive()` signature. See §11.2–§11.3 for the authoritative definition (including constructor-injected `event_log`, `epoch_id` parameter, and `ProcessManagerContext` construction via `build_pm_context()` — §23.3).

```python
# SKETCH — not the real signature; see §11.2–§11.3 for authoritative version
async def drive(aggregate: OperationAggregate, config: OperationConfig) -> OperationOutcome:
    ctx = await build_pm_context(aggregate)  # reconstruct from event log (see §23.3)
    
    # Phase 1: Lifecycle gate
    if gate := lifecycle_gate.check(aggregate, config):
        return gate.outcome
    
    # Phase 2: Runtime reconciliation (no decisions, just state sync)
    await reconciler.reconcile(aggregate, ctx, config)
    
    # Phase 3: Policy execution loop
    while lifecycle_gate.should_continue(aggregate, ctx, config):
        await reconciler.reconcile_cycle(aggregate, ctx, config)
        
        decision = await policy.decide(aggregate, ctx, config)
        events = await executor.execute(aggregate, ctx, decision, config)
        
        aggregate.apply_events(events)
        await event_log.append(aggregate.operation_id, events)
        
        if executor.should_break(decision, aggregate):
            break
    
    return lifecycle_gate.finalize(aggregate, config)
```

### 4.3 No More attached inner-while

The attached session waiting loop is eliminated: `executor.execute()` for `START_AGENT` either:
- Returns immediately with a `SessionStarted` event (non-blocking), or
- Awaits `adapter_runtime.collect()` which handles fast-time internally

The drive loop does not poll. It executes, then moves to the next cycle.

---

## 5. Lifecycle Model

### 5.1 Operation Lifecycle

```
Created ──► Running ──► Completed
                  └──► Failed
                  └──► Cancelled
                  └──► NeedsHuman ──► Running (retry)
                                 └──► Completed
                                 └──► Cancelled
```

**Invariants:**
- Only `Running` and `NeedsHuman` are resumable
- Terminal states (Completed, Failed, Cancelled) are permanent
- The transition `NeedsHuman → Running` requires an external trigger (command)

### 5.2 Session Lifecycle

```
[Unregistered] ──► Idle ──► Running ──► Waiting ──► Terminal(Completed|Failed|Cancelled)
                       └──────────────────────────────────────────────────────────┘
                                     (any non-terminal → Terminal)
```

**Invariants:**
- `SessionRecord.observed_state` (`SessionObservedState` enum — see §25.1) is the canonical state
- Cooldown, recovery, execution_profile are `RuntimeSessionContext` — not SessionRecord fields
- One-shot sessions transition directly to Terminal after completion

### 5.3 Adapter Lifecycle

```
Created ──► describe() ──► start(request) ──► AgentSessionHandle
                                         ──► collect(handle) ──► AgentResult
                                         ──► cancel(handle) ──► None  (fire-and-forget; result arrives via wakeup inbox as a wakeup signal; RuntimeReconciler emits the SessionCancelled domain event on the next cycle — see §8.3)
                                         ──► close()
```

**Invariants:**
- Adapter instances are stateless (except connection pools)
- Session state lives in `SessionRegistry`, not in the adapter
- Adapters do not know about Operations — they only know about sessions

### 5.5 Task Lifecycle

```
Created ──► PENDING ──► READY ──► IN_PROGRESS ──► COMPLETED
                                              └──► FAILED
                                              └──► CANCELLED
           (any non-terminal → CANCELLED)
```

**`TaskStatus` enum:**

| Value | Meaning |
|-------|---------|
| `PENDING` | Task exists but dependencies are not yet met (shown as `blocked_tasks` in BrainContext §17.1) |
| `READY` | All dependencies met; available for agent assignment |
| `IN_PROGRESS` | Agent assigned and running |
| `COMPLETED` | Terminal — task goal achieved |
| `FAILED` | Terminal — task goal not achieved after retries |
| `CANCELLED` | Terminal — explicitly cancelled (operation cancel or plan rewrite) |

**Event → transition mapping:**

| Event | Transition |
|-------|-----------|
| `TaskCreated` | (none) → PENDING |
| `TaskUpdated(status="ready")` | PENDING → READY |
| `AgentTurnStarted` (for task) | READY → IN_PROGRESS |
| `TaskCompleted` | IN_PROGRESS → COMPLETED |
| `TaskFailed` | IN_PROGRESS → FAILED |
| `TaskUpdated(status="cancelled")` | any non-terminal → CANCELLED |

**Invariants:**
- COMPLETED, FAILED, CANCELLED are terminal — no further transitions
- `BrainContext.ready_tasks` = tasks with status READY
- `BrainContext.blocked_tasks` = tasks with status PENDING (dependencies unmet)
- RuleBrain "all tasks terminal" = all tasks are COMPLETED | FAILED | CANCELLED

### 5.4 Operator Lifecycle (Daemon Model)

```
boot() ──► accepting_connections
       ──► handle_run_request(operation_id) ──► spawns OperationProcess
       ──► handle_command(operation_id, cmd) ──► routes to OperationProcess
       ──► shutdown() ──► graceful drain of active operations
```

### 5.6 Commander Lifecycle

```
boot()
  ├── Load audit log (JSONL — read-only on startup, for context)
  ├── Start health probing loop (ping each known operator endpoint)
  ├── Re-register any operators that respond healthy (see §13.2)
  └── accepting_connections ──► handle NL commands, fleet queries

SIGTERM received
  ├── Stop accepting new NL commands
  ├── Drain in-flight fleet commands (timeout: 10s)
  ├── Append "commander.shutdown" record to audit log
  └── Exit cleanly

Process crash (SIGKILL/OOM)
  └── State lost — Commander is effectively stateless; see restart below

restart()
  ├── CommanderRegistry starts empty
  ├── Health probing loop begins immediately
  ├── Operators that respond to health probes are re-registered automatically
  └── Orphaned operations on dead operators handled per §33.2
```

**Commander state persistence:**
- `CommanderRegistry` (in-memory) is rebuilt on startup via health probing — no checkpoint needed.
- `CommanderSessionStore` (SQLite, for NL session history §27.3) persists across restarts; stale sessions (TTL=30min) are expired on startup.
- Audit log (JSONL, §38) is append-only and persists across restarts.
- Commander does NOT have an event log or checkpoint — it is effectively stateless and re-discovers the fleet on every restart.

---

## 6. Process Model: Daemon vs Standalone

### 6.1 Decision: Operator v2 is a Daemon

**Rationale:** Fleet management (Commander) requires multiple operators to be addressable. Standalone processes cannot receive commands after launch. The MCP server already implies daemon semantics. The supervision model requires persistent process identity.

### 6.2 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Commander                            │
│  (NL interface + fleet management + policy application) │
└────────────────────────┬────────────────────────────────┘
                         │  Operator Control API (HTTP/gRPC)
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │ Operator │   │ Operator │   │ Operator │
   │  Daemon  │   │  Daemon  │   │  Daemon  │
   └──────────┘   └──────────┘   └──────────┘
         ▲
         │ CLI API (streaming, human-facing)
   ┌──────────┐
   │  CLI     │
   │ (thin)   │
   └──────────┘
```

### 6.3 Two Distinct APIs

| API | Audience | Protocol | Features |
|-----|----------|----------|---------|
| **CLI API** | Human operators | HTTP + SSE streaming | Interactive, single-operation focus, streaming output |
| **Operator Control API** | Commander, automation | HTTP/gRPC, batch | Fleet queries, policy application, multi-operation control |

### 6.4 Commander Design

Commander is a daemon that:
1. Maintains a registry of known Operator daemons (their endpoints + health)
2. Exposes a natural language interface (LLM-backed) for fleet control
3. Routes control commands to specific operators via the Operator Control API
4. Aggregates fleet status for dashboards and policies

Commander does NOT run operations itself — it delegates to Operators.

---

## 7. Library Decomposition

> **Superseded by §12 (Final Design).** This section records the initial five-library candidate decomposition from the design process. The authoritative package structure is in §12. Gaps (§16, §20, §24, §28, §31, §36, §41) indicate sections removed during iteration and are intentional.
>
> **Library → Package mapping (old → new):**
> | v1-design library | §12 package |
> |-------------------|-------------|
> | `acp-core` | `acp-core` (unchanged) |
> | `agent-domain` | merged into `operator` (`domain/` sub-package) |
> | `operator-core` | merged into `operator` (`application/` sub-package) |
> | `operator-cli` | merged into `operator` (`cli/` sub-package) |
> | `commander-core` | merged into `commander` |

### 7.1 Candidate Libraries

| Library | Contents | Used By |
|---------|---------|---------|
| `acp-core` | ACP protocol (jsonrpc session management, subprocess management) | operator, femtobot, lifechanger-tg |
| `agent-domain` | Domain model: Operation, Session, Task, Event types | operator, commander |
| `operator-core` | Drive loop, PolicyExecutor, LifecycleGate, ReconcilerService | operator daemon |
| `operator-cli` | CLI client, rendering, TUI | CLI tools |
| `commander-core` | Fleet registry, NL interface, Commander API client | commander daemon |

### 7.2 Reuse from Femtobot

Femtobot's `core` package has:
- `EventBusProtocol` — generic pub/sub bus (reusable)
- `JournalWriterProtocol` — event persistence abstraction (reusable)
- `AdapterProtocol` / `PollingStatefulAdapterProtocol` — polling adapters (relevant pattern)
- `AttentionSet` / `AttentionGate` — attention flow model (relevant concept)
- `HeartbeatScheduler` — heartbeat-driven event processing (reusable for background reconciliation)

**Recommendation:** Extract `EventBusProtocol` + `JournalWriterProtocol` into `acp-core` or a shared `operator-events` package.

### 7.3 ACP Protocol Abstraction

The current ACP client (`acp/client.py`, `acp/session_runner.py`) should become `acp-core`:

```python
# acp-core public API
class AcpConnection(Protocol): ...       # jsonrpc transport
class AcpSessionManager(Protocol): ...  # session lifecycle
class AcpSessionRunner: ...             # concrete runner
```

lifechanger-tg's `AcpSession` is a simpler synchronous version of the same concept — confirms the pattern is universal.

---

## 8. ACP Protocol Abstraction

### 8.1 Current Problems

- `AcpSessionRunner` vs `AcpAgentSessionRuntime` — two layers with unclear boundary
- Adapter hooks pattern (`_CodexAcpHooks`) is good but not formalized
- String comparisons for adapter identity (`if adapter_name == "codex_acp"`) instead of protocol dispatch

### 8.2 v2 ACP Architecture

```python
class AcpTransport(Protocol):
    """Low-level jsonrpc transport over subprocess or SDK."""
    async def request(self, method: str, params: dict) -> dict: ...
    async def notifications(self) -> AsyncIterator[dict]: ...

class AcpSessionLifecycle(Protocol):
    """Session management — start, load, fork, close."""
    async def new_session(self, params: SessionParams) -> str: ...
    async def load_session(self, session_id: str, params: LoadParams) -> None: ...
    async def prompt(self, session_id: str, prompt: str) -> AsyncIterator[AcpEvent]: ...


# AcpEvent — discriminated union of events yielded during a prompt() call
AcpEvent = Annotated[
    AcpOutputChunk | AcpPermissionRequest | AcpToolCallNotification | AcpSessionComplete | AcpSessionError,
    Field(discriminator="event_type")
]

class AcpOutputChunk(BaseModel):
    """Streaming text output from the agent."""
    event_type: Literal["output_chunk"] = "output_chunk"
    text: str

class AcpPermissionRequest(BaseModel):
    """Agent is requesting permission before performing an action."""
    event_type: Literal["permission_request"] = "permission_request"
    request_id: str
    action_type: str    # e.g. "file_write", "shell_exec", "network_request"
    description: str

class AcpToolCallNotification(BaseModel):
    """Agent is executing a tool (informational — no response required)."""
    event_type: Literal["tool_call"] = "tool_call"
    tool_name: str
    input_preview: str  # truncated representation of tool input

class AcpSessionComplete(BaseModel):
    """Agent turn is complete. This is the terminal event in a prompt() stream."""
    event_type: Literal["session_complete"] = "session_complete"
    exit_code: int | None = None

class AcpSessionError(BaseModel):
    """Agent turn failed with an error."""
    event_type: Literal["session_error"] = "session_error"
    error_code: str
    message: str

@dataclass(frozen=True)
class AgentRunRequest:
    """
    Parameters for starting one agent turn. Part of acp-core public API — no
    operator-specific fields. Operator adapters may subclass this to add
    policy or budget fields, but the base stays generic.
    """
    session_id: str            # ACP session to use (new or resumed)
    goal: str                  # turn goal / prompt text
    context: str | None = None # optional additional context for the agent
    tool_permissions: tuple[str, ...] = ()  # e.g. ("file_read", "shell_exec"); tuple for frozen-dataclass safety


class AgentAdapter(Protocol):
    """High-level agent interface — what the Operator sees."""
    async def describe(self) -> AgentDescriptor: ...
    async def start(self, request: AgentRunRequest) -> AgentSessionHandle: ...
    async def collect(self, handle: AgentSessionHandle) -> AgentResult: ...
    async def cancel(self, handle: AgentSessionHandle) -> None: ...
```

The `AgentAdapter` protocol is the only interface the drive loop uses. `AcpTransport` and `AcpSessionLifecycle` are internal to each adapter implementation.

> **Note:** `AgentRunRequest`, `AgentSessionHandle`, `AgentResult`, and `AgentAdapter` are `acp-core` public API, defined here for context. The authoritative library design for `acp-core` (including extraction guidance) is in §21.

### 8.3 AgentSessionHandle and AgentResult Schemas

These are the two primary types flowing across the `AgentAdapter` interface.

```python
class AgentResultStatus(str, Enum):
    """Terminal status of one agent turn. Used in AgentResult.status and AgentTurnCompleted.result_status."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"  # controlled termination; maps to AgentTurnCompleted, not AgentTurnFailed


@dataclass(frozen=True)
class AgentSessionHandle:
    """
    Opaque handle returned by AgentAdapter.start(). Carries the minimum context
    needed for the adapter to resume, collect from, or cancel an in-flight turn.
    The drive loop treats this as opaque — only the adapter implementation reads its fields.
    """
    session_id: str          # matches SessionRecord.session_id in the operator layer
    adapter_key: str         # which adapter issued this handle
    run_id: str              # adapter-internal run identifier (e.g. ACP run_id)
    # Note: operation_id is intentionally absent. AgentSessionHandle is part of acp-core
    # and must not carry operator-domain concepts. Operator adapter implementations that
    # need to correlate session_id → operation_id do so via SessionRegistry (operator layer),
    # not via this handle.


@dataclass(frozen=True)
class AgentResult:
    """
    Outcome of one agent turn, returned by AgentAdapter.collect().
    The drive loop maps this to domain events (see mapping below).
    """
    status: AgentResultStatus          # SUCCESS | FAILED | CANCELLED
    output_text: str                   # agent output (may be empty on failure)
    error_code: str | None = None      # set when status=FAILED; None otherwise
    usage: dict[str, Any] | None = None  # token counts etc.; None if unavailable
```

**`AgentResult.status` → domain event mapping** (applied in `PolicyExecutor` after `collect()` returns):

| `AgentResult.status` | Domain event emitted |
|----------------------|---------------------|
| `SUCCESS` | `AgentTurnCompleted(result_status="SUCCESS", output_preview=..., usage=...)` |
| `FAILED` | `AgentTurnFailed(error_code=..., error_message=..., retryable=...)` |
| `CANCELLED` | `AgentTurnCompleted(result_status="CANCELLED", output_preview="", usage=None)` |

Note: `CANCELLED` maps to `AgentTurnCompleted` (not `AgentTurnFailed`) because a cancel is a controlled termination, not an error. The `result_status` field on `AgentTurnCompleted` carries the `CANCELLED` value.

**`cancel()` is fire-and-forget — `-> None`:**
`AgentAdapter.cancel(handle)` returns `None`. It signals the adapter to abort the in-flight turn; the result arrives later as a `SessionCancelled` event delivered via the wakeup inbox (not as a direct return value). This is consistent with the drive loop's event-sourced design: all outcomes are expressed as domain events, not as return values from control calls. The sequence is:

```
drive loop calls cancel(handle)  →  adapter signals abort  →  adapter posts SessionCancelled to wakeup inbox
RuntimeReconciler (next cycle):  →  receives SessionCancelled  →  emits SessionCancelled domain event
```

---

## 9. Event Sourcing Architecture v2

### 9.1 Decision: Keep ES, Make it Strict

Event sourcing is retained as the canonical persistence mechanism. The v1 "snapshot-legacy" mode is eliminated. All new operations are event-sourced. Snapshot = cache only.

### 9.2 Event Log Structure

**`EventLog.append()` atomicity contract:** Each `append(events)` call is an atomic batch — either all events in the list are durably committed or none are. Partial writes are not possible. The drive loop always calls `agg.apply_events(events)` before `await event_log.append(events)` (apply first, then persist). If `append()` raises:
- The drive loop does **not** attempt to roll back in-memory state.
- The exception propagates to the supervisor, which treats it as a fatal infrastructure error and lets the process crash (let-it-crash policy, see §30.4).
- On restart, the aggregate is rebuilt from the last durable checkpoint + event log suffix. The in-memory state that was not persisted is simply not replayed — no corruption, because the event log is the source of truth.

This "apply-then-persist" ordering means in-memory aggregate state can briefly be ahead of the durable log within a single cycle, but the mismatch is always in the safe direction: the process can lose uncommitted in-memory state on crash, but the event log is never ahead of reality.

**Dual-append-per-cycle:** The authoritative drive loop in §11.2 performs TWO separate `event_log.append()` calls per while-loop cycle — one for `reconcile_events` (from `RuntimeReconciler.reconcile()`) and one for `exec_events` (from `PolicyExecutor.decide_and_execute()`). This does not violate the apply-then-persist safety invariant. The invariant holds because:
1. Each append call is individually atomic (all-or-nothing per call — see the protocol definition in §35.1).
2. The checkpoint is written AFTER both appends complete (the checkpoint block comes after both `event_log.append()` calls in §11.2).
3. If the process crashes between the reconcile append and the exec append, the reconstructed aggregate at restart has reconcile events from the current cycle but not exec events. This is correct and safe: the checkpoint predates both appends and still represents a valid state. The partially-committed cycle is simply re-run on restart (starting from the prior checkpoint + the reconcile events that were durably committed to the suffix). The aggregate is never in a state that was not explicitly committed to the event log — it can only be AHEAD of the log in memory, never behind.

```
OperationEventLog
├── OperationCreated
├── OperationStarted
├── TaskCreated × N
├── SessionRegistered × N
├── AgentTurnStarted
├── AgentTurnCompleted (with result)
├── AttentionRequested
├── AttentionAnswered
├── OperationCompleted | OperationFailed | OperationCancelled
└── ...
```

### 9.3 Projectors

```python
class OperationSnapshotProjector:
    """Builds OperationAggregate from event stream.
    
    CONTRACT: This projector handles ALL OperationDomainEvent types without exception,
    including terminal lifecycle events (OperationCompleted, OperationFailed,
    OperationCancelled, OperationNeedsHuman). Applying a terminal event to an aggregate
    whose status is RUNNING is a VALID operation and MUST produce the correct terminal state
    (OperationStatus.COMPLETED / FAILED / CANCELLED / NEEDS_HUMAN).
    
    This contract is REQUIRED for the resumption protocol (§42.1): when an operation is
    resumed after a crash or graceful shutdown, the last checkpoint may have status=RUNNING
    (or scheduler_state=PAUSED), and the event log suffix after the checkpoint may contain
    terminal events (e.g., OperationCompleted emitted in the last drive cycle before the
    crash). The projector must apply those suffix events correctly to reconstruct the true
    final state. Implementations that skip or no-op terminal events will silently produce
    a RUNNING-status aggregate from what was actually a completed operation.
    
    See §42.1 for the full checkpoint + suffix projection flow.
    """

class OperationReadModelProjector:
    """Builds OperationReadModel (briefs, artifacts) from event stream."""

class ProcessManagerContextProjector:
    """Reconstructs ProcessManagerContext from event stream + runtime state."""

class OperationConfigProjector:
    """
    Builds OperationConfig from the OperationCreated event and any subsequent
    config-change events (ExecutionProfileOverrideUpdated, BudgetExtended,
    InvolvementLevelChanged). Returns a new frozen OperationConfig instance —
    never mutates the existing one in place.
    """
```

---

## 10. Brain/Policy Separation

### 10.1 Current Confusion

In v1, `operator_policy.py` holds both:
- **Brain**: what action to take next (`decide_next_action`)
- **Policy**: governance rules (`evaluate_result`, approval policies)

### 10.2 v2 Separation

Brain and OperatorPolicy are separated into two distinct protocols.

**Brain** is the sole decision maker — stateless, fast (LLM call or rule engine), called every cycle. The canonical `Brain` protocol definition (with `decide()` and `plan()` methods operating on `BrainContext` and returning `NextActionDecision` / `PlanningDecision`) is in **§17.1**. `OperationSnapshot` and `BrainDecision` are v1 type names that do not exist in v2; do not use them.

**OperatorPolicy** is the governance layer — may consult external state (policy stores, approval databases, humans). The canonical `OperatorPolicy` protocol definition is in **§17.4** and **§37.2**. The key contract:

```python
class OperatorPolicy(Protocol):
    """Governance layer. May consult external state (policy store, approvals)."""
    async def evaluate_result(self, context: BrainContext) -> ResultEvaluation: ...
    async def should_approve(self, request: ApprovalRequest) -> ApprovalDecision: ...
    async def apply_coverage(self, context: BrainContext) -> PolicyCoverage: ...
```

**Key difference:** Brain is stateless and fast. Policy may consult external stores, call humans, check approval databases. See §17 for complete protocol definitions.

---

## 11. Drive Loop v2 — Three Services

### 11.1 Decomposition

The v1 drive loop is decomposed into three distinct services. Each has a clear concern, clean interface, and no cross-cutting mutations.

```python
@dataclass(frozen=True)
class LifecycleGateResult:
    """Returned by LifecycleGate.check_pre_run() when the operation must not run.

    Does NOT carry a full OperationOutcome — LifecycleGate is a pure function and
    cannot know started_at, finished_at, or iterations_executed. DriveService.drive()
    constructs the OperationOutcome from these two fields plus its own tracking state.
    """
    outcome_status: OperationStatus  # terminal status to report (e.g. COMPLETED, FAILED)
    reason: str                      # e.g. "timeout_exceeded", "budget_exhausted", "already_terminal"


class LifecycleGate:
    """Synchronous, fast. Pure checks — no I/O, no mutations.
    Drain signaling lives on ProcessManagerContext.request_drain() (see §23.2), not here."""
    
    def check_pre_run(
        self, agg: OperationAggregate, config: OperationConfig
    ) -> LifecycleGateResult | None:
        """Returns non-None if operation should not run (timeout, budget exceeded, etc.)"""
        ...
    
    def should_continue(
        self, agg: OperationAggregate, ctx: ProcessManagerContext, config: OperationConfig
    ) -> bool:
        """True if drive loop should execute another cycle."""
        ...
    
    def should_pause(self, agg: OperationAggregate, ctx: ProcessManagerContext) -> bool:
        """True if SchedulerState requires pause."""
        ...


class RuntimeReconciler:
    """Async, side-effecting. Syncs external state with aggregate. Produces events, not mutations."""
    
    async def reconcile(
        self, agg: OperationAggregate, ctx: ProcessManagerContext
    ) -> list[DomainEvent]:
        """
        - Sync background runs (poll asyncio tasks, check run files)
        - Expire cooldowns
        - Process wakeup inbox
        - Refresh policy context
        Returns domain events for any state changes found.
        """
        ...


class PolicyExecutor:
    """Async. Gets Brain decision, executes it, returns events. No direct state mutation."""
    
    async def decide_and_execute(
        self,
        agg: OperationAggregate,
        ctx: ProcessManagerContext,
        config: OperationConfig,
    ) -> tuple[NextActionDecision, list[DomainEvent], AgentResult | None, IterationBrief]:
        """
        1. Call Brain.decide(context) → NextActionDecision  (called every cycle)
        2. If a planning trigger fires, call Brain.plan(context, trigger) → PlanningDecision
           and fold the resulting task/feature events into the returned event list.
        3. Execute the NextActionDecision (start session, send message, etc.)
        4. Return (decision, events, agent_result, iteration_brief) — do NOT mutate aggregate.
           agent_result: AgentResult from collect() if an agent turn completed, else None.
           iteration_brief: IterationBrief for this drive loop cycle (§47); one per while-loop
                            iteration regardless of more_actions=True sub-calls; drive loop appends it to
           agg.read_model.iteration_briefs. This avoids the need for a separate domain event
           just to populate read-model traceability data.
        """
        ...
```

### 11.2 Cleaned Drive Loop

> **Authoritative drive loop logic** (together with §11.3). `event_log`, `policy_store`, `adapter_registry`, and `wakeup_inbox` are constructor-injected into `DriveService` (not passed as parameters). `epoch_id` is an explicit parameter. `ProcessManagerContext` is constructed by calling `build_pm_context()` (§23.3) as the first step inside `drive()` — see §11.3 for the full `DriveService.__init__` signature.

```python
async def drive(
    agg: OperationAggregate,
    config: OperationConfig,
    epoch_id: int,
    # event_log, policy_store, adapter_registry, wakeup_inbox injected at construction — see §11.3
) -> OperationOutcome:
    # Build ephemeral drive-loop context (external lookups: policy coverage, available agents)
    ctx = await build_pm_context(
        agg,
        policy_store=self._policy_store,
        adapter_registry=self._adapter_registry,
        wakeup_inbox=self._wakeup_inbox,
    )  # see §23.3 for full build_pm_context definition
    
    # Phase 1: Pre-run lifecycle gate
    # LifecycleGate is pure — returns only (outcome_status, reason); drive() builds the full OperationOutcome
    if early_exit := lifecycle_gate.check_pre_run(agg, config):
        return OperationOutcome(
            operation_id=agg.operation_id,
            status=early_exit.outcome_status,
            summary=early_exit.reason,
            final_result=None,
            iterations_executed=0,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
    
    # Phase 2: Initial reconciliation
    events = await reconciler.reconcile(agg, ctx)
    agg.apply_events(events)
    await event_log.append(agg.operation_id, events)
    
    # Phase 3: Main policy execution loop
    # Tracking variables for OperationOutcome (§47 schema)
    started_at: datetime = datetime.now(UTC)
    iterations_executed: int = 0
    last_agent_result: AgentResult | None = None
    # wake_cycle_id: unique ID for this drive() call, passed to PolicyExecutor so that
    # DecisionRecord.wake_cycle_id groups all brain calls within the same wake cycle.
    # NOT epoch_id — epoch_id is a checkpoint fencing key, not a cycle identifier.
    wake_cycle_id: str = str(uuid.uuid4())

    # fast_cycle_active: set by prior iteration's decision.fast_cycle=True (§17.2, §29.1)
    # When True, reconciliation is skipped and Brain is called directly
    fast_cycle_active: bool = False
    # consecutive_actions: counts brain calls since the last checkpoint (sleep boundary).
    # Incremented unconditionally on EVERY while-loop iteration (not only when
    # more_actions=True), then reset to 0 at the checkpoint block (whether or not the
    # more_actions path was taken). This means the counter represents the depth of the
    # current more_actions series: it is 1 after the first call, 2 after the second, etc.
    # When more_actions=False (normal path), consecutive_actions is incremented to 1 and
    # then immediately reset to 0 at the checkpoint — so it never accumulates across
    # normal (non-continuation) cycles. Prevents infinite more_actions=True loops.
    # Limit: DriveService.max_consecutive_actions (see §11.3 for the guard semantics).
    consecutive_actions: int = 0
    while lifecycle_gate.should_continue(agg, ctx, config):
        if lifecycle_gate.should_pause(agg, ctx):
            break
        
        # Reconcile each cycle — unless fast_cycle was set by the previous decision
        # (fast_cycle=True: used after START_BACKGROUND_AGENT to rapidly start N background
        #  agents in N cycles without waiting for reconciliation between starts — see §29.1)
        if not fast_cycle_active:
            reconcile_events = await reconciler.reconcile(agg, ctx)
            agg.apply_events(reconcile_events)
            await event_log.append(agg.operation_id, reconcile_events)
        
        # Get decision and execute.
        # decide_and_execute returns a 4-tuple: decision, domain events, AgentResult (or None),
        # and IterationBrief. AgentResult is from collect() if an agent turn completed this cycle.
        decision, exec_events, cycle_agent_result, iteration_brief = await policy_executor.decide_and_execute(agg, ctx, config)
        agg.apply_events(exec_events)
        await event_log.append(agg.operation_id, exec_events)
        agg.read_model.iteration_briefs.append(iteration_brief)
        agg.read_model.decision_records.append(DecisionRecord(
            action_type=decision.action_type.value,
            more_actions=decision.more_actions,
            wake_cycle_id=wake_cycle_id,
            timestamp=datetime.now(UTC),
        ))
        iterations_executed += 1  # counts every brain.decide() call — see OperationOutcome §47
        # Track last agent result for OperationOutcome.final_result (§47)
        if cycle_agent_result is not None:
            last_agent_result = cycle_agent_result
        
        # more_actions: brain requests another decision in the same wake cycle.
        # Re-reconcile before next brain call; skip checkpoint until the series ends.
        # LifecycleGate checks at the top of the loop still apply to each sub-call.
        consecutive_actions += 1
        if (decision.more_actions
                and consecutive_actions < self._max_consecutive_actions
                and not agg.status.is_terminal
                and decision.action_type is not BrainActionType.STOP):
            fast_cycle_active = False   # always re-reconcile between more_actions calls
            # iterations_executed is already incremented above; each sub-call in a
            # more_actions series counts as a separate brain call (DecisionRecord granularity).
            continue  # → next while iteration → reconcile → brain again (no checkpoint)
        
        # If more_actions=True but the cap was reached, log a WARNING so operators can
        # diagnose brains that consistently hit the limit.
        if decision.more_actions and consecutive_actions >= self._max_consecutive_actions:
            logger.warning(
                "max_consecutive_actions cap reached",
                operation_id=agg.operation_id,
                consecutive_actions=consecutive_actions,
                max_consecutive_actions=self._max_consecutive_actions,
                last_action_type=decision.action_type.value,
            )
            # The capped decision's action was already executed by decide_and_execute().
            # The drive loop proceeds normally (checkpoint, terminal check) — no action
            # is reverted. The Brain will be informed of the cap on the next cycle via
            # the new DecisionRecord in recent_decisions (more_actions=True, wake_cycle_id
            # matching the cap cycle) — Brain can detect repeated cap hits from this history.
        
        # Reset consecutive_actions counter on sleep (checkpoint boundary)
        consecutive_actions = 0
        
        # Drain check — must be evaluated BEFORE saving the checkpoint so that
        # the drain exit path can save a final checkpoint with SchedulerState=PAUSED.
        # ctx.draining is set by ctx.request_drain() on SIGTERM (see §14, §23.2).
        if ctx.draining:
            # Emit SchedulerPaused so the checkpoint reflects SchedulerState=PAUSED on disk.
            # This bypasses the normal PAUSE_REQUESTED → PAUSED path (RuntimeReconciler)
            # because no PAUSE command arrives during a graceful drain — DriveService
            # emits SchedulerPaused directly on the drain exit path (see §14, §22.6).
            paused_event = SchedulerPaused(
                operation_id=agg.operation_id,
                iteration=agg.iteration,
            )
            agg.apply_events([paused_event])
            await event_log.append(agg.operation_id, [paused_event])
            # Save final checkpoint with SchedulerState=PAUSED.
            # This is the ONE case where a checkpoint IS written after the loop
            # exits — drain exit requires a durable PAUSED checkpoint so the
            # operation can be resumed by the next operator startup (§42.1).
            await checkpoint_store.save(agg.operation_id, agg.to_checkpoint(), epoch_id=epoch_id)
            break  # Exit the drive loop; OperationStatus remains RUNNING (resumable)
        
        # Checkpoint (normal path — only reached when ctx.draining is False)
        await checkpoint_store.save(agg.operation_id, agg.to_checkpoint(), epoch_id=epoch_id)
        # StaleEpochError propagates unhandled → supervisor treats it as fatal conflict (§33.3)
        
        # Check terminal conditions
        if agg.status.is_terminal:
            break
        if decision.action_type is BrainActionType.STOP:
            break
        
        # Carry fast_cycle flag into the next iteration
        fast_cycle_active = decision.fast_cycle
    
    # NOTE: No final checkpoint is saved after a TERMINAL break above (agg.status.is_terminal
    # or action_type=STOP). This is intentional: the event log is canonical. The last in-loop
    # checkpoint may lag the terminal state by one cycle. Callers must not assume the checkpoint
    # reflects the terminal status immediately after drive() returns — query the event log
    # (or the returned OperationOutcome) for the definitive final state.
    # EXCEPTION: the drain exit path (ctx.draining=True, above) DOES save a final checkpoint
    # with SchedulerState=PAUSED before breaking — resumption depends on finding PAUSED on disk.
    return OperationOutcome(
        operation_id=agg.operation_id,
        status=agg.status,
        summary=agg.final_summary or "",
        final_result=last_agent_result,
        iterations_executed=iterations_executed,
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )
```

**Key properties of v2 drive loop:**
- Services communicate only through domain events and the event log — no service directly writes to another service's internal state (the aggregate is passed to all three services but mutations go through `agg.apply_events()` only; there are no direct field writes from service to service)
- No `attached inner-while` — PolicyExecutor.decide_and_execute() awaits the agent turn internally
- No string comparisons for adapter identity — adapters implement protocol
- LifecycleGate is unit-testable (pure functions)
- Each service is independently mockable

### 11.3 Constructor Dependency Surfaces

> **Authoritative `DriveService.drive()` signature.** The `event_log` is injected into `DriveService` at construction, not passed as a parameter. The `epoch_id` parameter is required for checkpoint epoch-fencing (§33.3).

```python
class LifecycleGate:
    """No injected dependencies — all inputs come via method parameters."""
    def __init__(self) -> None: ...
    # All methods are pure functions: (agg, ctx, config) → result


class AgentRunStore(Protocol):
    """Read interface for live asyncio.Task state. Implemented by InProcessAgentRunSupervisor.
    
    RuntimeReconciler uses this to poll task status each cycle without holding a direct
    reference to the supervisor. InProcessAgentRunSupervisor implements both this protocol
    and the spawn/cancel interface used by PolicyExecutor.
    """
    def get_tasks_for_operation(self, operation_id: str) -> list[asyncio.Task]: ...
    # Returns tasks spawned for the given operation_id (used by RuntimeReconciler each cycle)
    def get_task_status(self, session_id: str) -> TaskRunStatus | None: ...
    # TaskRunStatus: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]


class RuntimeReconciler:
    def __init__(
        self,
        *,
        wakeup_inbox: WakeupInbox,
        command_inbox: OperationCommandInbox,
        adapter_registry: AdapterRegistry,
        policy_store: PolicyStore,
        run_store: AgentRunStore,  # InProcessAgentRunSupervisor satisfies this protocol
    ) -> None: ...


class PolicyExecutor:
    def __init__(
        self,
        *,
        brain: Brain,
        policy: OperatorPolicy,
        adapter_registry: AdapterRegistry,
        event_log: OperationEventLog,  # for posting wakeup events from background runs
        supervisor: InProcessAgentRunSupervisor,
        # PolicyExecutor calls supervisor.spawn(coro) when executing START_BACKGROUND_AGENT.
        # The supervisor creates the asyncio.Task, registers it by session_id, and posts a
        # wakeup to WakeupInbox when the task completes. RuntimeReconciler polls via AgentRunStore.
    ) -> None: ...


class DriveService:
    """
    Owns the three services and the drive loop. Constructed once per OperatorServiceV2
    instance — NOT once per run() call. The same DriveService handles all operations
    on this operator daemon; each drive() call is independent (no shared mutable state).
    
    policy_store, adapter_registry, and wakeup_inbox are injected here so that
    drive() can call build_pm_context() (§23.3) internally on each invocation.
    """
    def __init__(
        self,
        *,
        lifecycle_gate: LifecycleGate,
        reconciler: RuntimeReconciler,
        policy_executor: PolicyExecutor,
        event_log: OperationEventLog,
        checkpoint_store: OperationCheckpointStore,
        # Required for build_pm_context() (§23.3) called at the start of each drive() call:
        policy_store: PolicyStore,
        adapter_registry: AdapterRegistry,
        wakeup_inbox: WakeupInbox,
        max_consecutive_actions: int = 10,
        # Safety guard: max brain calls per wake cycle when more_actions=True is used.
        # The guard in §11.2 is `consecutive_actions < max_consecutive_actions` where
        # consecutive_actions is incremented BEFORE the check. This means the effective
        # maximum number of brain calls in a single more_actions series is
        # max_consecutive_actions (the default value of 10 allows up to 10 calls total;
        # consecutive_actions reaches 10 on the 10th call, and 10 < 10 is False, so
        # the 10th call is the last one allowed). If you want to allow N calls, set
        # max_consecutive_actions = N. Do NOT set max_consecutive_actions = N+1 expecting N.
        # Infrastructure-level guardrail — NOT per-operation config (OperationConfig).
        # Brain cannot modify this limit via actions.
    ) -> None: ...
    
    async def drive(
        self,
        agg: OperationAggregate,
        config: OperationConfig,
        epoch_id: int,
    ) -> OperationOutcome: ...
```

**`OperatorServiceV2` ownership model:** `OperatorServiceV2` owns one `DriveService` instance, constructed internally from its injected dependencies (see §39.2 for the full dependency list). It does not construct a new `DriveService` per `run()` call. The `DriveService` is effectively stateless across calls — its injected dependencies are shared infrastructure (event log, checkpoint store, etc.) that are themselves thread-safe and operation-isolated by `operation_id`.

---

## 12. Library Decomposition (Final Design)

### 12.1 Three-Package Model

| Package | Contents | Consumers |
|---------|---------|----------|
| **`acp-core`** | ACP protocol (jsonrpc transport, session runner, event types), `AgentAdapter` protocol | operator, femtobot, lifechanger-tg |
| **`operator`** | Domain model, event sourcing, drive loop, adapters, CLI, MCP server, HTTP daemon API | operator daemon process |
| **`commander`** | Fleet registry, NL controller, Commander APIs, health probing | commander daemon process |

**Phase 5 future extractions (not required for MVP — see §12.5):**

| Package | Source | Consumers |
|---------|--------|----------|
| **`event-store-core`** | `operator/domain/` DomainEvent base + projector pattern | swarm-evo, eval-framework |
| **`inbox-core`** | `operator/application/` WakeupInbox + OperationCommandInbox protocols | swarm-evo, femtobot |

### 12.2 Internal Structure of `operator` Package

```
operator/
├── domain/           # OperationAggregate, SessionRegistry, ExecutionRegistry, events
├── application/      # Drive loop, LifecycleGate, RuntimeReconciler, PolicyExecutor
│   ├── drive/        # DriveService, LifecycleGate, RuntimeReconciler, PolicyExecutor
│   ├── commands/     # Command handling services
│   └── queries/      # Query services, projectors
├── runtime/          # Supervisor, event log, checkpoint store, adapters
├── adapters/         # claude_acp, codex_acp, opencode_acp (use acp-core)
└── cli/              # CLI commands, rendering, TUI
```

### 12.3 Key Boundary Rules

- `domain/` has no imports from `application/` or `runtime/`
- `application/` imports type definitions (protocols) from `domain/` and defines its own protocols (e.g. `OperationEventLog`, `OperationCheckpointStore`, `WakeupInbox`) in `application/protocols.py`. It does NOT import concrete `runtime/` implementations.
- `runtime/` imports from `application/` and `domain/` only to implement protocols; it provides the concrete implementations injected at the composition root.
- `cli/` imports from `application/` query services (not domain directly)
- `commander/` imports from `acp-core` only; speaks `operator` via HTTP Control API

### 12.4 Async Backbone Decision

**asyncio everywhere.** Remove `anyio` dependency. Rationale: anyio's unique features (CancelScope, backend flexibility) are not actually used in the operator codebase. The mixed asyncio/anyio pattern in v1 is a maintenance burden. Python 3.11+ provides `asyncio.timeout()` as a CancelScope equivalent.

### 12.5 Cross-Project Primitive Map

The following primitives are candidates for extraction into shared libraries that sibling projects (lifechanger-tg, swarm-evo, femtobot, eval-framework) can consume without depending on the full `operator` package.

| Primitive | Current home | Target shared library | lifechanger-tg | swarm-evo | femtobot | eval-framework | Preconditions |
|-----------|-------------|----------------------|---------------|-----------|----------|---------------|--------------|
| `AcpTransport` + `AcpSessionRunner` | `operator/adapters/` | `acp-core` (already planned) | ✓ | — | ✓ | — | None — already clean |
| `AgentAdapter` protocol + `AgentSessionHandle` + `AgentResult` + `AgentRunRequest` | `operator/application/` (interface) + `operator/adapters/types.py` (types) | `acp-core` (`acp_core/agent_adapter.py`) | ✓ | ✓ | ✓ | ✓ | `operation_id` removed from `AgentSessionHandle` (done — §8.3); `AgentRunRequest` verified operator-agnostic (done — §8.2) |
| `DomainEvent` base class + projector pattern | `operator/domain/` | new `event-store-core` | — | ✓ | — | ✓ | `operation_id` and `iteration` fields must move to an operator-layer subclass (`OperationEvent`); generic base keeps only `(event_id, type, timestamp)`; partitioning key becomes `StreamId` (str newtype) |
| `OperationEventLog` protocol (append-only event log) | `operator/application/` | new `event-store-core` | — | ✓ | — | ✓ | Same as above; `operation_id: str` parameter becomes `stream_id: StreamId` |
| `WakeupInbox` + `OperationCommandInbox` protocols + `WakeupRef` type | `operator/application/` | new `inbox-core` | — | ✓ | ✓ | — | `operation_id` parameter on protocols and `WakeupRef.operation_id` field must be renamed to `inbox_id: str` (generic); operator maps `operation_id → inbox_id` at the composition root |

**Extraction timing:** `event-store-core` and `inbox-core` are not required for v2 operator MVP. They belong in Phase 5 cleanup (§35.2 step 20). The boundary decisions during Phase 1–2 (domain and drive loop decomposition) should preserve clean protocol definitions that make future extraction non-breaking.

**Note on femtobot overlap:** §7.2 identifies `EventBusProtocol` and `JournalWriterProtocol` in femtobot as analogous patterns. Before creating `event-store-core`, verify whether femtobot's protocols are close enough to merge with `OperationEventLog`, or whether the semantics differ enough to warrant separate libraries.

---

## 13. Commander Design

### 13.1 Architecture

```
Commander Daemon
├── CommanderRegistry           — operator registration, health probing, routing
├── NLFleetController           — NL text → FleetCommand → execute
├── Commander Public API (HTTP) — human/CLI facing: /fleet/status, /fleet/command
└── health probing loop         — ping each operator every N seconds
```

### 13.2 CommanderRegistry

```python
# Canonical OperatorRecord definition is in §47 (type stubs). The field names below
# match §47 exactly. Do not redeclare OperatorRecord here — use the §47 definition.
#
# §47 OperatorRecord fields (for reference):
#   operator_id: str
#   endpoint: str            # "http://localhost:8421" — added to §47 for routing
#   health: HealthStatus     # HEALTHY | DRAINING | DEAD
#   active_operations: list[str]  # operation_ids currently assigned
#   last_heartbeat_at: datetime
#   epoch_id: int            # current epoch for stale-write detection

@dataclass
class CommandResult:
    """Result of routing one command to one operator."""
    operator_id: str
    success: bool
    status_code: int           # HTTP status code received from the operator
    error_message: str | None  # set when success=False; None on success


class CommanderRegistry:
    async def register(self, operator_id: str, endpoint: str) -> OperatorRecord: ...
    async def deregister(self, operator_id: str) -> None: ...
    async def route(
        self,
        operator_id: str,
        command: FleetCommand,
        timeout: float = 10.0,  # seconds; raises asyncio.TimeoutError on expiry
    ) -> CommandResult:
        """
        Route one command to the named operator.
        If the operator responds 503 DRAINING: returns CommandResult(success=False, status_code=503).
        The caller is responsible for deciding whether to retry on a different operator.
        Raises asyncio.TimeoutError after `timeout` seconds with no response.
        """
        ...
    async def broadcast(self, command: FleetCommand, filter: OperatorFilter) -> list[CommandResult]:
        """
        Broadcast to all matching operators. Returns one CommandResult per operator.
        Never raises — failures are captured per-operator in CommandResult.success=False.
        """
        ...
    async def get_fleet_snapshot(self) -> FleetSnapshot: ...
    async def select_best_operator(self, filter: OperatorFilter) -> OperatorRecord: ...
```

### 13.3 NLFleetController

```python
class NLFleetController:
    """Natural language interface to the fleet."""
    
    async def handle(self, text: str) -> FleetCommandResult:
        # 1. Fast tier: rule-based classifier (see §27.1)
        fast_decision = self.fast_classifier.classify(text)
        if fast_decision is not None:
            # Fast tier handles simple, unambiguous commands — no LLM call needed
            return await self._execute_intent(fast_decision)
        
        # 2. Slow tier: LLM parse intent
        try:
            context = await self.registry.get_fleet_snapshot()
            intent = await self.brain.parse_fleet_intent(text, context)
        except LLMError as exc:
            # LLM failure: return a structured error result to the caller.
            # Do NOT propagate silently — the Commander is the fleet control plane and
            # a silent failure would cause dropped commands.
            return FleetCommandResult(
                success=False,
                error="llm_parse_failed",
                message=f"Could not parse fleet command: {exc}. Please retry or use an explicit command.",
            )
        
        # 3. Route and execute
        return await self._execute_intent(intent)
```

**Fast tier as LLM failure guard:** The fast tier (§27.1) is both a performance optimization and a reliability guard. Simple, unambiguous commands (see §27.2) are handled by the fast tier without any LLM call — they are immune to LLM failures. The slow tier (LLM agent) is only invoked for commands that the fast tier cannot classify confidently.

Fleet commands: `StartOperation`, `StopOperation`, `PauseOperation`, `ResumeOperation`, `QueryFleetStatus`, `ApplyPolicy`, `RouteToOperator`.

### 13.4 Operator Control API (what each Operator exposes)

```
GET  /health                         — health status
GET  /operations                     — list active operations (summaries)
GET  /operations/{id}                — get one operation status
POST /operations/{id}/commands       — send command {type, payload}
POST /operations/{id}/messages       — send operator message
POST /operations                     — start new operation
GET  /operations/{id}/events         — SSE stream of events (for CLI streaming)
```

Commander uses the control commands; CLI uses the SSE streaming endpoint.

**HTTP status codes and error response contract:**

All error responses return a JSON body with this schema:
```python
class ApiErrorResponse(BaseModel):
    error: str        # machine-readable error code (e.g. "not_found", "conflict", "draining")
    message: str      # human-readable description
    operation_id: str | None = None
```

Key status codes per endpoint:

| Endpoint | Scenario | Status | `error` value |
|----------|----------|--------|---------------|
| `POST /operations` | Created successfully | 201 | — |
| `POST /operations` | Daemon is DRAINING | 503 | `"draining"` |
| `GET /operations/{id}` | Operation not found | 404 | `"not_found"` |
| `POST /operations/{id}/commands` | Operation not found | 404 | `"not_found"` |
| `POST /operations/{id}/commands` | Command rejected (terminal state) | 409 | `"conflict"` |
| `POST /operations/{id}/commands` | Command accepted | 202 | — |
| `GET /health` | Healthy | 200 | — |
| `GET /health` | Draining (SIGTERM received) | 503 | `"draining"` |
| Any | Internal error | 500 | `"internal_error"` |

---

## 14. Graceful Shutdown Protocol

```
SIGTERM received
    │
    ▼
OperatorDaemon.shutdown(timeout=30s)
    │
    ├─► Health endpoint → 503 DRAINING
    ├─► Notify Commander: operator is draining
    ├─► Stop accepting new operation start requests
    │       # Guard placement: OperatorServiceV2 sets an internal `_accepting: bool = True`
    │       # flag to False in _on_sigterm(), before iterating _active_contexts.
    │       # The HTTP handler for POST /operations checks this flag at the SERVICE METHOD
    │       # level (inside OperatorServiceV2.run()) and raises a DrainError (→ HTTP 503
    │       # with error="draining") if _accepting is False. The guard lives at the service
    │       # method level (not HTTP middleware and not a separate LifecycleGate check) so
    │       # that the MCP server and any other callers of OperatorServiceV2.run() also
    │       # receive the same rejection without needing their own guard.
    │
    ▼
Drain active drive loops
    │
    ├─► Each drive loop: ctx.request_drain()  (ProcessManagerContext, not LifecycleGate)
    ├─► Drive loops complete current iteration, then stop
    ├─► Each drive loop: emits `SchedulerPaused` domain event directly (DriveService, on seeing ctx.draining=True after current cycle completes) — no pause command arrives during drain, so the PAUSE_REQUESTED → PAUSED reconciler path is bypassed; DriveService emits `SchedulerPaused` itself and applies it to the aggregate before writing the final checkpoint
    ├─► Each operation: checkpoint with SchedulerState=PAUSED (OperationStatus remains RUNNING)
    │
    ▼
Drain background asyncio tasks
    │
    ├─► Correct shutdown sequence (Python 3.11+):
    │       # remaining_time = total shutdown_timeout minus time already spent draining
    │       # drive loops above. Computed as:
    │       #   shutdown_deadline = asyncio.get_event_loop().time() + shutdown_timeout
    │       #   (recorded when SIGTERM was received, before drive loop drain begins)
    │       #   remaining_time = max(0.0, shutdown_deadline - asyncio.get_event_loop().time())
    │       # shutdown_timeout is the total budget (default 30s, see OperatorDaemon.shutdown(timeout=30s)).
    │       # remaining_time may be 0 if drive loop drain exhausted the full budget,
    │       # in which case asyncio.wait() returns immediately and all tasks are cancelled.
    │       done, pending = await asyncio.wait(
    │           supervisor.get_active_tasks(),
    │           timeout=remaining_time,
    │       )
    │       for task in pending:
    │           task.cancel()
    │       if pending:
    │           await asyncio.gather(*pending, return_exceptions=True)
    │           # CRITICAL: awaiting cancelled tasks allows their finally: blocks to run,
    │           # including AcpSessionRunner subprocess cleanup (see §21).
    │           # Without this await, ACP subprocesses may outlive the operator process.
    │       for task in pending:
    │           emit AgentTurnLost(lost_reason="graceful_shutdown_timeout") → ExecutionObservedState.LOST
    │
    ▼
Exit cleanly
    └─► All operations: SchedulerState=PAUSED on disk, OperationStatus=RUNNING (resumable by next startup)
```

**Resume on next startup:** Load all operations with `SchedulerState=PAUSED` → reconstruct from checkpoint + event log → resume drive loop where it left off.

**SIGTERM handling — how `ctx.request_drain()` is called on all active contexts:**

SIGTERM is caught via `loop.add_signal_handler(signal.SIGTERM, shutdown_callback)` installed on the main asyncio event loop at daemon startup. `OperatorServiceV2` (not `InProcessAgentRunSupervisor`) owns the active context registry:

```python
class OperatorServiceV2:
    _active_contexts: dict[str, ProcessManagerContext] = {}
    # operation_id → active ctx for that drive() call
    # Registered on drive() entry; removed on drive() return.
    
    def _on_sigterm(self) -> None:
        """Called by loop.add_signal_handler(signal.SIGTERM, ...) on SIGTERM."""
        for ctx in self._active_contexts.values():
            ctx.request_drain()
        # Also: stop accepting new run() calls, notify Commander (DRAINING)
```

`ProcessManagerContext` is registered in `_active_contexts[operation_id]` when `drive()` is called and removed when `drive()` returns. If three operations are running concurrently, there are three entries and all three receive `request_drain()` on SIGTERM.

**Note:** `InProcessAgentRunSupervisor` manages asyncio Tasks for background agent runs. It is NOT responsible for calling `ctx.request_drain()` — that is the responsibility of `OperatorServiceV2._on_sigterm()`.

**Clarification — PAUSED is a SchedulerState, not an OperationStatus:** `OperationStatus` only has the values defined in §5.1 (Created, Running, Completed, Failed, Cancelled, NeedsHuman). During a graceful drain, operations retain `OperationStatus=RUNNING`; the pause signal lives in `SchedulerState=PAUSED` (a domain event — see §22.6). There is no `OperationStatus.PAUSED` value in v2.

---

## 15. Event Sourcing — v2 Fixes

### 15.1 Keep the Infrastructure

The `EventSourcedReplayService` (checkpoint + suffix pattern) is architecturally correct. Preserve it.

### 15.2 Typed Domain Events

> **Superseded by §22** — §22 contains the authoritative typed event schemas with the correct field name (`type`, not `event_type`). This section records the design motivation only. Use §22 for all implementation work.

Replace untyped `RunEvent(event_type="string", payload=dict)` with typed domain events. The base class uses `type` (not `event_type`) as the discriminator field — see §22.1 for the base class definition.

Illustrative sketch (field name `type` matches the §22 base class):

```python
class OperationStarted(DomainEvent):
    type: Literal["operation.started"] = "operation.started"  # authoritative schema in §22.2
    run_started_at: datetime

class TaskCreated(DomainEvent):
    type: Literal["task.created"] = "task.created"  # authoritative schema in §22.3
    task_id: str
    title: str
    goal: str

# ... see §22 for complete schemas
```

Wire format: `DomainEvent` serializes to the same `EventFileRecord` format (backwards compatible).

### 15.3 Checkpoint = Pure Domain Aggregate

The v2 checkpoint contains ONLY domain aggregate state (OperationAggregate + SessionRegistry + ExecutionRegistry + OperationConfig). No PM state in the checkpoint.

**`OperationCheckpoint` schema:**

```python
@dataclass
class OperationCheckpoint:
    aggregate: OperationAggregate
    session_registry: SessionRegistry
    execution_registry: ExecutionRegistry
    config: OperationConfig
    seq: int  # monotonically increasing write counter; used for epoch fencing
```

`OperationAggregate.to_checkpoint()` packages all four domain objects into this struct (see §3.1). `OperationCheckpointStore.save()` takes `OperationCheckpoint` directly — there is no wrapper record.

PM state (`ProcessManagerContext`) is reconstructed from:
1. Domain events (e.g., pending wakeups from WAKEUP kind events)
2. Runtime calls (policy context, available agents)
3. Defaults (empty processed_command_ids, etc.)

---

## 17. Brain/Policy Design v2

### 17.1 Core Principle: Brain is a Pure Stateless Function

Brain takes a structured context (prepared by the drive loop) and returns a decision. No internal state. No conversation history in the Brain object. All memory is in the aggregate.

**`build_brain_context()` — how BrainContext is constructed:**

`PolicyExecutor` calls this helper before each `brain.decide()` call. It is a method on `PolicyExecutor` (not a free function), because it needs access to `PolicyExecutor`'s injected `memory_store` (if present).

```python
def build_brain_context(
    self,
    agg: OperationAggregate,
    ctx: ProcessManagerContext,
    config: OperationConfig,
    *,
    max_recent_iterations: int = 10,        # last N full iterations for context window
    max_recent_decisions: int = 10,         # last N brain calls (includes more_actions sub-calls)
    max_recent_turns: int = 5,              # last N agent turns
    max_recent_operator_messages: int = 20, # last N user messages shown to brain
) -> BrainContext:
    _operator_message_types = frozenset({"INSTRUCTION", "RESPONSE_REQUESTED"})
    return BrainContext(
        operation_id=agg.operation_id,
        goal=str(agg.goal),
        current_status=agg.status,
        ready_tasks=[TaskBrief.from_task(t) for t in agg.tasks if t.status == TaskStatus.READY],
        blocked_tasks=[TaskBrief.from_task(t) for t in agg.tasks if t.status == TaskStatus.PENDING],
        recent_iterations=agg.read_model.iteration_briefs[-max_recent_iterations:],
        recent_decisions=agg.read_model.decision_records[-max_recent_decisions:],
        recent_agent_turns=agg.read_model.agent_turn_briefs[-max_recent_turns:],
        recent_operator_messages=[
            m for m in agg.operator_messages if m.type in _operator_message_types
        ][-max_recent_operator_messages:],
        relevant_memories=agg.read_model.memory_entries,  # last-N; semantic retrieval is a Phase 2 enhancement
        available_agents=ctx.available_agents,
        active_sessions=[SessionBrief.from_record(s) for s in agg.sessions.sessions
                         if s.observed_state not in {SessionObservedState.TERMINAL}],
                         # NOTE: `active_sessions` includes ALL non-terminal sessions:
                         # IDLE, RUNNING, and WAITING. "Active" here means "not terminated"
                         # (i.e., the session still exists and could receive work), NOT
                         # "currently executing." Brain logic that needs only RUNNING sessions
                         # must filter active_sessions by SessionBrief.observed_state == RUNNING.
                         # The field is named active_sessions (not non_terminal_sessions) for
                         # backwards compatibility; the filtering criterion is documented here.
        pending_attention=next((a for a in agg.attention_requests
                                if a.status == AttentionRequestStatus.PENDING), None),
    )
```

**Note on `relevant_memories`:** In the initial implementation, `relevant_memories` is simply the last N `MemoryEntry` records from the read model (chronological). Semantic retrieval (embedding-based ranking) is a Phase 2 enhancement and is not required for v2 MVP.

```python
class BrainContext(BaseModel):
    """Structured view of operation state prepared for Brain. NOT the full aggregate."""
    operation_id: str
    goal: str
    current_status: OperationStatus
    ready_tasks: list[TaskBrief]          # only tasks that can run
    blocked_tasks: list[TaskBrief]         # tasks waiting on dependencies
    recent_iterations: list[IterationBrief]  # last N full iterations (reconcile+brain+execute)
    recent_decisions: list[DecisionRecord]   # last N brain calls (finer grained — includes more_actions sub-calls)
    recent_agent_turns: list[AgentTurnBrief]
    recent_operator_messages: list[OperatorMessage]  # last N user messages (INSTRUCTION + RESPONSE_REQUESTED types)
    relevant_memories: list[MemoryEntry]   # semantic memory, retrieved by relevance
    available_agents: list[AgentDescriptor]
    active_sessions: list[SessionBrief]
    # Contains ALL non-terminal sessions (IDLE + RUNNING + WAITING). Brain logic
    # that needs only currently-executing sessions must filter by SessionBrief.observed_state.
    pending_attention: AttentionRequest | None

class Brain(Protocol):
    async def decide(self, context: BrainContext) -> NextActionDecision: ...
    async def plan(self, context: BrainContext, trigger: PlanningTrigger) -> PlanningDecision: ...
```

### 17.2 Planner / Decider Split

```python
class BrainActionType(str, Enum):
    """Exhaustive set of actions the brain may request in one drive cycle."""
    START_AGENT = "START_AGENT"
    START_BACKGROUND_AGENT = "START_BACKGROUND_AGENT"
    CONTINUE_AGENT = "CONTINUE_AGENT"
    STOP = "STOP"
    WAIT = "WAIT"
    REQUEST_ATTENTION = "REQUEST_ATTENTION"
```

**Decider (called every cycle):**
```python
class NextActionDecision(BaseModel):
    action_type: BrainActionType  # START_AGENT | CONTINUE_AGENT | STOP | WAIT | REQUEST_ATTENTION
    target_agent: str | None
    session_id: str | None
    instruction: str | None
    focus_task_id: str | None
    rationale: str
    confidence: float | None = None
    fast_cycle: bool = False  # if True, skip reconciliation and go directly to next Brain cycle (used after START_BACKGROUND_AGENT — see §29.1)
    # Note: fast_cycle=True is ignored on NON-FINAL decisions within a more_actions series.
    # The drive loop always re-reconciles between more_actions sub-calls for correctness.
    # However, fast_cycle=True on the FINAL decision of a more_actions series (the call
    # where more_actions=False) is valid and takes effect: it causes the NEXT drive cycle
    # (after the checkpoint) to skip reconciliation. Brain implementations in multi-action
    # sequences may legitimately set fast_cycle=True on the last call to trigger a rapid
    # follow-up cycle (e.g., start a background agent, then immediately skip reconcile to
    # start another one). fast_cycle=True is NOT useless in multi-action sequences.
    more_actions: bool = False
    # If True, brain will be called again in the same wake cycle after reconcile.
    # The drive loop re-runs reconcile before each subsequent brain call (aggregate state
    # may have changed even within milliseconds). No checkpoint is saved between
    # more_actions=True calls — all decisions in the series form one transactional unit.
    # Consecutive calls are limited by DriveService.max_consecutive_actions (default 10).
    # The guard is `consecutive_actions < max_consecutive_actions` where consecutive_actions
    # is incremented before the check; with the default of 10 this allows up to 10 total
    # brain calls per wake cycle (the initial call + up to 9 more_actions continuations).
    # LifecycleGate and budget/timeout checks take priority — more_actions is ignored on early-exit.
    # Use case: send intermediate user message, then check agent status, then sleep — all in one cycle.
    #
    # CONSTRAINT: more_actions=True is SILENTLY IGNORED when action_type=STOP.
    # The drive loop guard is: `decision.more_actions and ... and decision.action_type is not BrainActionType.STOP`
    # Brain implementations MUST NOT combine more_actions=True with action_type=STOP expecting
    # the loop to execute the STOP and then call them again — the STOP takes precedence and
    # more_actions is discarded without warning. If you need to perform cleanup before stopping,
    # use more_actions=True with action_type=WAIT (or another non-STOP type) in an intermediate
    # call, then issue action_type=STOP in the final call.
```

**Planner (called on planning trigger):**
```python
class PlanningDecision(BaseModel):
    new_tasks: list[TaskDraft]
    task_updates: list[TaskPatch]
    new_features: list[FeatureDraft]
    feature_updates: list[FeaturePatch]
    rationale: str
```

Drive loop calls `brain.plan()` only when a planning trigger fires. `brain.decide()` is called every cycle and operates on the CURRENT task plan (no modifications).

**`PlanningTrigger` — definition and detection:**

```python
class PlanningTrigger(str, Enum):
    INITIAL_PLAN = "initial_plan"       # No tasks exist yet (first cycle of a new operation)
    TASK_FAILED   = "task_failed"       # A task transitioned to FAILED; Brain must decide to retry or replan
    EXPLICIT_REPLAN = "explicit_replan" # Operator command (REPLAN_COMMAND) arrived in inbox
    GOAL_CHANGED  = "goal_changed"      # InvolvementLevelChanged or similar config event received
```

**Detection:** `PolicyExecutor.decide_and_execute()` checks for planning triggers before calling `brain.decide()`:

```python
# Inside PolicyExecutor.decide_and_execute():
# Note: _detect_planning_trigger takes only agg — ctx is not needed for current trigger types
# (INITIAL_PLAN and TASK_FAILED inspect agg.tasks; EXPLICIT_REPLAN inspects recent command events
# already applied to agg; GOAL_CHANGED inspects recent config events on agg).
trigger = _detect_planning_trigger(agg)
if trigger is not None:
    planning_decision = await brain.plan(context, trigger)
    plan_events = _apply_planning_decision(agg, planning_decision)
    # plan_events are folded into the returned event list; aggregate is NOT mutated here.
    # brain.decide() sees the updated task plan via a working-copy aggregate (see below).

# Rebuild BrainContext from the working copy so brain.decide() sees the updated task plan.
# If plan_events is non-empty, apply them to a shallow working copy of the aggregate first.
if plan_events:
    working_agg = copy.copy(agg)          # shallow copy — sufficient because apply_events
    working_agg.tasks = list(agg.tasks)   # replaces the tasks list, not mutates it in place
    working_agg.apply_events(plan_events) # mutates working_agg only; agg is untouched
    brain_context = self.build_brain_context(working_agg, ctx, config)
else:
    brain_context = self.build_brain_context(agg, ctx, config)
decision = await brain.decide(brain_context)
```

**`_apply_planning_decision()` specification:**

```python
def _apply_planning_decision(
    agg: OperationAggregate,
    planning_decision: PlanningDecision,
) -> list[DomainEvent]:
    """
    Convert a PlanningDecision into domain events. Does NOT mutate agg.
    
    Returns a list of TaskCreated, TaskUpdated, and FeatureCreated/FeatureUpdated events
    that represent the planned changes. The caller (decide_and_execute) applies these
    events to a shallow working copy of agg for BrainContext construction, and folds
    them into the returned event list for the drive loop to apply to the real aggregate.
    
    The 'working copy' is a shallow copy of OperationAggregate with a new tasks list
    (list(agg.tasks)) so that apply_events() can append to or replace list elements
    without affecting the original agg. Other aggregate fields (goal, policy, status,
    attention_requests, etc.) are shared by reference — PlanningDecision events only
    touch the tasks and features lists, so shared-reference aliasing is safe here.
    """
    events: list[DomainEvent] = []
    for task_draft in planning_decision.new_tasks:
        events.append(TaskCreated(
            operation_id=agg.operation_id,
            iteration=agg.iteration,
            task_id=task_draft.task_id or str(uuid4()),
            title=task_draft.title,
            goal=task_draft.goal,
            definition_of_done=task_draft.definition_of_done,
            brain_priority=task_draft.brain_priority,
            assigned_agent=task_draft.assigned_agent,
            dependencies=task_draft.dependencies,
        ))
    for task_patch in planning_decision.task_updates:
        events.append(TaskUpdated(
            operation_id=agg.operation_id,
            iteration=agg.iteration,
            task_id=task_patch.task_id,
            status=task_patch.status,
            assigned_agent=task_patch.assigned_agent,
            brain_priority=task_patch.brain_priority,
            append_notes=task_patch.append_notes,
        ))
    # FeatureDraft / FeaturePatch follow the same pattern (omitted for brevity)
    return events
```

`brain.plan()` is called in the same cycle as `brain.decide()` — the planning events are returned together with the decision events. `brain.decide()` sees the updated task plan via the working copy described above. The real `agg` is NOT mutated until the drive loop applies all returned events via `agg.apply_events(exec_events)` after `decide_and_execute()` returns.

### 17.3 Stratified Brain: RuleBrain + LLMBrain

```python
class StratifiedBrain:
    """Try RuleBrain first (deterministic, free). Fall back to LLMBrain."""
    
    def __init__(self, rule_brain: RuleBrain, llm_brain: LLMBrain):
        ...
    
    async def decide(self, context: BrainContext) -> NextActionDecision:
        decision = self.rule_brain.decide(context)
        if decision is not None:
            return decision
        return await self.llm_brain.decide(context)
```

**RuleBrain deterministic cases (handles ~70-80% of steady-state):**
- All tasks terminal → STOP
- All tasks terminal but goal not satisfied → REQUEST_ATTENTION
- Exactly one READY task with assigned agent + reusable session → CONTINUE_AGENT (deterministic)
- Exactly one READY task with assigned agent, no session → START_AGENT (deterministic)
- Active attention request pending → WAIT
- Status=NEEDS_HUMAN → WAIT

**LLMBrain cases:**
- Multiple READY tasks → prioritization (LLM)
- Task failed → retry/replan decision (LLM)
- No READY tasks but not all terminal → unblock decision (LLM)
- Complex dependency resolution (LLM)

### 17.4 OperatorPolicy (Governance Layer)

Policy is separate from Brain. Policy enforces governance rules:

```python
class OperatorPolicy(Protocol):
    async def evaluate_result(self, context: BrainContext) -> ResultEvaluation: ...
    async def should_approve(self, request: ApprovalRequest) -> ApprovalDecision: ...
    async def apply_coverage(self, context: BrainContext) -> PolicyCoverage: ...
```

Drive loop calls `policy.evaluate_result()` after each agent turn to check if the goal is satisfied or if human review is needed. Policy can call external systems (approval databases, human-in-the-loop APIs).

---

## 18. Migration Strategy: v1 → v2

### 18.1 The Problem

v1 operations in `snapshot_legacy` mode have no event log — they have only a mutable `OperationState` snapshot. v2 requires all operations to be event-sourced.

### 18.2 Migration Tool

A one-time migration tool that:
1. Loads a legacy `OperationState` snapshot from disk
2. Generates a synthetic `operation.migrated_from_snapshot` event with the full snapshot as payload
3. Creates a checkpoint from the snapshot
4. Writes both to the event store

**Concurrency guard:** In a multi-operator deployment (§33), two operators could both attempt to migrate the same operation before either completes. To prevent duplicate `OperationMigratedFromSnapshot` birth events, migration uses an atomic "migration claimed" file marker:
- Before step 2, write a `migration.lock` marker file for the operation atomically (using `O_CREAT | O_EXCL` — fails if the file already exists).
- If the lock already exists: return `MigrationResult(skipped=True, reason="concurrent_migration")`.
- The lock is cleaned up only after step 4 completes successfully.
- On process crash between lock acquisition and completion: the lock file remains. The operator that resumes the operation will see `canonical_persistence_mode == EVENT_SOURCED` (if step 4 completed on the crashed process) and skip migration cleanly; or it will see the lock file and skip. An operator restart script may optionally clean stale lock files older than 5 minutes.

```python
class SnapshotMigrationService:
    async def migrate(self, operation_id: str) -> MigrationResult:
        # 0. Claim migration lock (atomic; returns skipped if already claimed)
        if not await self.migration_lock_store.try_acquire(operation_id):
            return MigrationResult(skipped=True, reason="concurrent_migration")
        
        try:
            # 1. Load legacy snapshot
            state = await self.snapshot_store.load(operation_id)
            if state.canonical_persistence_mode == EVENT_SOURCED:
                return MigrationResult(skipped=True)
            
            # 2. Generate migration event (using the proper typed event class from §22.2)
            birth_event = OperationMigratedFromSnapshot(
                operation_id=operation_id,
                iteration=0,
                legacy_snapshot=state.model_dump(mode="json"),
            )
            await self.event_store.append(operation_id, [birth_event])
            
            # 3. Create initial checkpoint
            # Build aggregate from legacy state, then package into OperationCheckpoint (§15.3 schema)
            agg = OperationAggregate.from_legacy_state(state)
            checkpoint = agg.to_checkpoint()  # OperationCheckpoint — no wrapper record
            await self.checkpoint_store.save(operation_id, checkpoint, epoch_id=0)
            
            # 4. Mark as migrated
            # state is a v1 OperationState object — canonical_persistence_mode is a v1 field marking migration complete
            state.canonical_persistence_mode = EVENT_SOURCED
            await self.snapshot_store.save(state)
            
            return MigrationResult(migrated=True)
        finally:
            await self.migration_lock_store.release(operation_id)
```

### 18.3 v1 Compatibility Shim (transition period)

During the transition period:
- v2 can READ v1 snapshots (backwards compatible)
- v2 WRITES to event log only
- The `snapshot_legacy` code paths are removed in v2 (no new legacy operations can be created)
- The migration tool runs on first startup for each operation

---

## 19. Test Architecture

### 19.1 Principles

1. **Pure unit tests for pure functions** — `LifecycleGate` tests use no async, no mocks (`request_drain()` was moved to `ProcessManagerContext` to preserve this purity — see §23.2)
2. **Protocol fakes instead of mocks** — `InMemoryEventLog`, `InMemoryCheckpointStore`, `FakeAgentAdapter`
3. **Command side / Query side separation** — drive loop tests assert on event log; projector tests take event lists
4. **No OperationState blob construction** — tests work with `OperationAggregate.create(...)` + events

### 19.2 Test Layers

```
Unit Tests
├── LifecycleGate                     — pure functions, no async, no I/O
├── RuleBrain                         — pure function, parameterized test cases
├── Domain event projector            — event list → assert read model
└── Individual domain events          — serialization/deserialization

Integration Tests  
├── PolicyExecutor + FakeBrain + FakeAdapter
├── RuntimeReconciler + InMemoryRunStore + InMemoryWakeupInbox
└── Full drive loop: InMemoryEventLog + FakeBrain + FakeAdapter

End-to-End Tests
├── Full operation lifecycle (single operation)
└── Multi-operation fleet scenarios
```

### 19.3 Key Test Fixtures

```python
# These fixtures replace the v1 "fakes.py" + "operator_service_support.py"

class InMemoryEventLog:
    """Real in-memory event log with real append/query semantics."""
    def events_for(self, operation_id: str) -> list[DomainEvent]: ...
    async def append(self, operation_id: str, events: list[DomainEvent]) -> None: ...

class FakeBrain:
    """Returns predetermined decisions in sequence."""
    def __init__(self, decisions: list[NextActionDecision]): ...

class FakeAgentAdapter:
    """Returns predetermined AgentResult instances in sequence."""
    def __init__(self, results: list[AgentResult]): ...
    async def collect(self, handle: AgentSessionHandle) -> AgentResult: ...

async def run_operation(goal: str, *, brain: Brain, adapter: AgentAdapter) -> OperationOutcome:
    """Test helper: create + run one operation to terminal state.
    
    brain and adapter are injected into PolicyExecutor / RuntimeReconciler at
    construction time (not passed to drive()). DriveService.drive() only takes
    (agg, config, epoch_id) — see §11.3 for the authoritative signature.
    """
    agg = OperationAggregate.create(goal=goal)
    event_log = InMemoryEventLog()
    adapter_registry = FakeAdapterRegistry(adapter)
    policy_executor = PolicyExecutor(
        brain=brain,
        policy=NoOpOperatorPolicy(),
        adapter_registry=adapter_registry,
        event_log=event_log,
        supervisor=InMemoryAgentRunSupervisor(),
    )
    drive_service = DriveService(
        lifecycle_gate=LifecycleGate(),
        reconciler=RuntimeReconciler(
            wakeup_inbox=InMemoryWakeupInbox(),
            command_inbox=InMemoryCommandInbox(),
            adapter_registry=adapter_registry,
            policy_store=NoOpPolicyStore(),
            run_store=InMemoryRunStore(),
        ),
        policy_executor=policy_executor,
        event_log=event_log,
        checkpoint_store=InMemoryCheckpointStore(),
        policy_store=NoOpPolicyStore(),
        adapter_registry=adapter_registry,
        wakeup_inbox=InMemoryWakeupInbox(),
    )
    return await drive_service.drive(agg, OperationConfig.defaults(), epoch_id=0)
```

---

## 21. ACP v2 Library Design

### 21.1 What Becomes `acp-core`

The current `AcpSessionRunner` + `AcpSessionRunnerHooks` + `AcpSessionState` in `acp/session_runner.py` is already the core of what `acp-core` should export.

**Moves to `acp-core`:**
- `acp/client.py` → `acp_core/transport.py` (AcpConnection, AcpSubprocessConnection, AcpSdkConnection)
- `acp/session_runner.py` → `acp_core/session_runner.py` (AcpSessionRunner, AcpSessionRunnerHooks Protocol, AcpSessionState)
- `acp/adapter_runtime.py` → `acp_core/adapter_runtime.py`
- `AgentRunRequest`, `AgentSessionHandle`, `AgentResult`, `AgentAdapter` protocol (§8.2–§8.3) → `acp_core/agent_adapter.py`

**Stays in `operator` (adapter implementations):**
- `adapters/codex_acp.py` — Codex-specific hooks + command building
- `adapters/claude_acp.py` — Claude-specific hooks
- `adapters/opencode_acp.py` — OpenCode-specific hooks

### 21.2 AcpSessionRunnerHooks Protocol (public acp-core API)

The hooks protocol is already formalized. In v2, it's the primary extension point:

```python
class AcpSessionRunnerHooks(Protocol):
    """Implement this to create a new ACP-based agent adapter."""
    adapter_key: str
    running_message: str
    completed_message: str
    follow_up_running_error: str
    
    async def configure_new_session(self, connection: AcpConnection, session_id: str) -> None: ...
    async def configure_loaded_session(self, connection: AcpConnection, session_id: str) -> None: ...
    async def handle_server_request(self, session: AcpSessionState, payload: JsonObject) -> None: ...
    def classify_collect_exception(self, exc: Exception, stderr: str) -> AcpCollectErrorClassification: ...
    def should_reuse_live_connection(self, session: AcpSessionState) -> bool: ...
    def should_keep_connection_after_collect(self, handle: AgentSessionHandle) -> bool: ...
    def unknown_session_error(self, session_id: str) -> str: ...
```

Any new agent type (e.g., a hypothetical `gemini_acp`) just implements `AcpSessionRunnerHooks` and passes it to `AcpSessionRunner`. No need to touch the operator core.

**`session_id` in `AcpSessionRunnerHooks`** refers to the ACP-level session identifier (the same `str` that becomes `AgentSessionHandle.session_id`). It is NOT a reference to `SessionRecord` from the operator domain. Hook implementations in `operator/adapters/` may look up the corresponding `SessionRecord` if needed, but `acp-core` itself is unaware of `SessionRecord` and has no import from `operator/domain/`.

### 21.3 Subprocess Lifetime Contract

**`AcpSessionRunner.collect()` MUST wrap its subprocess interaction in a `try/finally` block that kills the subprocess on any exception, including `CancelledError` injected during asyncio Task cancellation:**

```python
async def collect(self, handle: AgentSessionHandle) -> AgentResult:
    try:
        # ... drive the subprocess interaction (stream events, await completion) ...
    finally:
        # Kill subprocess if still running — this runs on CancelledError too.
        # Required for graceful shutdown: when the asyncio Task wrapping collect()
        # is cancelled (§14 shutdown sequence), this finally: block kills the ACP
        # subprocess before the coroutine exits. Without it, subprocesses become orphans.
        if self._subprocess is not None and self._subprocess.returncode is None:
            self._subprocess.kill()
            await self._subprocess.wait()
```

**Why this is required:** When `InProcessAgentRunSupervisor.cancel_all()` is called during graceful shutdown (§14), it calls `task.cancel()` on each background asyncio Task. This injects `CancelledError` into the coroutine at the next `await` point. If `collect()` does not have a `finally:` block, the underlying ACP subprocess continues running after the operator process exits — becoming an orphan that consumes resources and holds file descriptors.

**Process group note:** On Linux, if the ACP subprocess is started without `setsid()`, it is in the same process group as the operator. A SIGKILL to the operator (e.g., OOM kill) will NOT automatically kill the subprocess unless the subprocess is killed explicitly or the OS sends SIGHUP to the process group. The `finally: subprocess.kill()` contract handles the graceful shutdown case; for SIGKILL, see §30.4.

---

## 22. Typed Domain Events — Concrete Schema

### 22.1 Base Class

```python
class DomainEvent(BaseModel):
    # Declared on the base so to_event_file_record() can access self.type.
    # Concrete subclasses narrow this to Literal["<event.type>"] = "<event.type>".
    type: str
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    # NOTE: operation_id and iteration are operator-domain-specific fields.
    # They are on this base class for operator convenience, but if DomainEvent
    # is ever extracted to event-store-core (§12.5), these must move to a
    # subclass (e.g. OperationEvent) and the generic base must use only
    # (event_id, type, timestamp). The partitioning key becomes StreamId (a str newtype).
    operation_id: str
    iteration: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    task_id: str | None = None
    session_id: str | None = None
    
    def to_event_file_record(self) -> EventFileRecord:
        """Serialize to the stable wire format."""
        return EventFileRecord(
            event_id=self.event_id,
            event_type=self.type,
            kind=RunEventKind.DOMAIN,
            category="domain",
            operation_id=self.operation_id,
            iteration=self.iteration,
            task_id=self.task_id,
            session_id=self.session_id,
            timestamp=self.timestamp,
            payload=self.model_dump(mode="json", exclude={"event_id", "operation_id", "iteration", "timestamp", "task_id", "session_id"}),
        )
```

### 22.2 Operation Lifecycle Events

```python
class OperationCreated(DomainEvent):
    type: Literal["operation.created"] = "operation.created"
    goal: str
    harness_instructions: str | None
    success_criteria: list[str]
    allowed_agents: list[str]
    involvement_level: str

class OperationStarted(DomainEvent):
    type: Literal["operation.started"] = "operation.started"
    run_started_at: datetime
    run_mode: str  # "attached" | "background"

class OperationCompleted(DomainEvent):
    type: Literal["operation.completed"] = "operation.completed"
    summary: str

class OperationFailed(DomainEvent):
    type: Literal["operation.failed"] = "operation.failed"
    summary: str
    error_code: str | None = None

class OperationNeedsHuman(DomainEvent):
    type: Literal["operation.needs_human"] = "operation.needs_human"
    summary: str
    blocker: str | None = None

class OperationCancelled(DomainEvent):
    type: Literal["operation.cancelled"] = "operation.cancelled"
    summary: str

class OperationResumed(DomainEvent):
    type: Literal["operation.resumed"] = "operation.resumed"

class OperationMigratedFromSnapshot(DomainEvent):
    type: Literal["operation.migrated_from_snapshot"] = "operation.migrated_from_snapshot"
    legacy_snapshot: dict[str, Any]  # full v1 OperationState dump
```

### 22.3 Task Events

```python
class TaskCreated(DomainEvent):
    type: Literal["task.created"] = "task.created"
    title: str
    goal: str
    definition_of_done: str
    brain_priority: int
    assigned_agent: str | None
    dependencies: list[str]

class TaskUpdated(DomainEvent):
    type: Literal["task.updated"] = "task.updated"
    status: str | None = None
    assigned_agent: str | None = None
    brain_priority: int | None = None
    append_notes: list[str] = Field(default_factory=list)

class TaskCompleted(DomainEvent):
    type: Literal["task.completed"] = "task.completed"

class TaskFailed(DomainEvent):
    type: Literal["task.failed"] = "task.failed"
    reason: str | None = None
```

### 22.4 Session Events

```python
class SessionRegistered(DomainEvent):
    type: Literal["session.registered"] = "session.registered"
    adapter_key: str
    one_shot: bool

class SessionRunning(DomainEvent):
    type: Literal["session.running"] = "session.running"

class SessionWaiting(DomainEvent):
    type: Literal["session.waiting"] = "session.waiting"
    waiting_reason: str | None = None

class SessionCompleted(DomainEvent):
    type: Literal["session.completed"] = "session.completed"

class SessionFailed(DomainEvent):
    type: Literal["session.failed"] = "session.failed"
    error_code: str | None = None

class SessionCancelled(DomainEvent):
    type: Literal["session.cancelled"] = "session.cancelled"
    cancelled_by: str  # "operator_command" | "policy" | "graceful_shutdown"
    # How RuntimeReconciler determines the value when processing a wakeup from a
    # task cancelled during drain (§14):
    #   When OperatorServiceV2._on_sigterm() calls ctx.request_drain(), it also calls
    #   supervisor.mark_draining() which sets InProcessAgentRunSupervisor._draining=True.
    #   When InProcessAgentRunSupervisor._on_task_complete() fires for a task that was
    #   cancelled while _draining=True, it posts a WakeupRef with
    #   payload={"drain_cancelled": True} in addition to kind="TASK_COMPLETED".
    #   RuntimeReconciler.reconcile() checks wakeup.payload.get("drain_cancelled", False)
    #   when building the SessionCancelled event — if True, sets cancelled_by="graceful_shutdown".
    #   Otherwise, cancelled_by is determined by the prior operation command context
    #   ("operator_command" if a CANCEL command was in the command inbox, "policy" if
    #   a policy decision triggered the cancel).
```

### 22.5 Agent Turn Events

```python
class AgentTurnStarted(DomainEvent):
    type: Literal["agent_turn.started"] = "agent_turn.started"
    instruction: str | None = None
    launch_kind: str  # "new" | "follow_up" | "background"

class AgentTurnCompleted(DomainEvent):
    type: Literal["agent_turn.completed"] = "agent_turn.completed"
    result_status: AgentResultStatus  # SUCCESS | CANCELLED (see §8.3 for enum definition)
    output_preview: str  # first 500 chars
    usage: dict[str, Any] | None = None

class AgentTurnFailed(DomainEvent):
    type: Literal["agent_turn.failed"] = "agent_turn.failed"
    error_code: str
    error_message: str
    retryable: bool

class AgentTurnLost(DomainEvent):
    type: Literal["agent_turn.lost"] = "agent_turn.lost"
    lost_reason: str | None = None  # e.g. "process_crash" | "graceful_shutdown_timeout"
    # Emitted by RuntimeReconciler on restart for any ExecutionRecord still in RUNNING state.
    # Transitions ExecutionRecord.observed_state from RUNNING → LOST.
    # See §30.4 for the recovery context.
```

### 22.6 Control Events (formerly PM state)

**SchedulerState in v2:** Three values are event-sourced aggregate state — `ACTIVE`, `PAUSE_REQUESTED`, `PAUSED` — and have corresponding domain events below. `DRAINING` is **not** event-sourced in v2: it is a pure in-process signal set by `ctx.request_drain()` on the `ProcessManagerContext` (ephemeral, never persisted), initialized to non-draining on every drive() call. A process receiving SIGTERM sets `ProcessManagerContext.draining=True`; when drive() sees this, it stops accepting new cycles after the current one completes. No `SchedulerDraining` domain event is needed because the drain is process-scoped, not operation-scoped — operations retain `SchedulerState=ACTIVE` (or `PAUSED`) in the aggregate.

**SchedulerState transition diagram:**

```
ACTIVE ──────────────────────────────────────────────────────────► PAUSED
  │      (drain path: ctx.draining=True; DriveService emits SchedulerPaused             │
  │       directly — see §11.2, §14. No PAUSE command needed on this arc.)              │
  │                                                                                      │
  └──► PAUSE_REQUESTED ──► PAUSED                                                       │
         (normal pause:   (RuntimeReconciler emits SchedulerPaused                      │
          operator PAUSE   when it sees PAUSE_REQUESTED — see §43.)                     │
          command)                                                                       │
                                                                                        │
PAUSED ──► ACTIVE  (on startup: OperatorServiceV2.resume() emits SchedulerResumed      │
                   — see §42.1)                                                         │
```

**Valid source states for `SchedulerPaused` event:**
- `PAUSE_REQUESTED → PAUSED`: normal pause path (RuntimeReconciler, §43).
- `ACTIVE → PAUSED`: drain exit path only (DriveService, §11.2, §14).

**Idempotency contract for `SchedulerPaused`:** The aggregate's `SchedulerPaused` event handler MUST be idempotent with respect to duplicate application. If the aggregate is already in `SchedulerState=PAUSED` when `SchedulerPaused` is applied, the handler MUST be a no-op (not raise, not transition to an invalid state). This guards against the race where a PAUSE command arrives while SIGTERM is being processed: both the normal RuntimeReconciler path and the drain-exit path might emit `SchedulerPaused`; the second application must be harmless.

```python
class SchedulerPauseRequested(DomainEvent):
    type: Literal["scheduler.pause_requested"] = "scheduler.pause_requested"
    requested_by: str  # "operator_command" | "policy"

class SchedulerPaused(DomainEvent):
    type: Literal["scheduler.paused"] = "scheduler.paused"

class SchedulerResumed(DomainEvent):
    type: Literal["scheduler.resumed"] = "scheduler.resumed"

class OperatorMessageReceived(DomainEvent):
    type: Literal["operator_message.received"] = "operator_message.received"
    message_id: str
    message_type: str   # "INSTRUCTION" | "RESPONSE_REQUESTED" | "SYSTEM"
    content: str        # the message text (renamed from text for alignment with OperatorMessage §47)
    source: str         # who sent it: "user" | "system" | "commander"
    # Projector mapping → OperatorMessage (§47):
    #   message_id → message_id, message_type → type, content → content,
    #   DomainEvent.timestamp → received_at, source → source  (field exists on both sides)
    # **IMPORTANT:** The event field is `message_type` but the projected model field is `type`.
    # Do NOT use `message_type` as the field name on OperatorMessage — use `type`.
    # BrainContext filters on `m.type in _operator_message_types` (§17.1); using the
    # wrong field name produces AttributeError at runtime.
```

### 22.7 Discriminated Union

```python
OperationDomainEvent = Annotated[
    OperationCreated | OperationStarted | OperationCompleted | OperationFailed |
    OperationNeedsHuman | OperationCancelled | OperationResumed | 
    OperationMigratedFromSnapshot |
    TaskCreated | TaskUpdated | TaskCompleted | TaskFailed |
    SessionRegistered | SessionRunning | SessionWaiting | SessionCompleted | SessionFailed | SessionCancelled |
    AgentTurnStarted | AgentTurnCompleted | AgentTurnFailed | AgentTurnLost |
    SchedulerPauseRequested | SchedulerPaused | SchedulerResumed |
    OperatorMessageReceived |
    AttentionRequested | AttentionAnswered | AttentionResolved |
    ExecutionProfileOverrideUpdated | BudgetExtended | InvolvementLevelChanged,
    Field(discriminator="type")
]
```

### 22.8 Configuration-Change Events

These events are projected by `OperationConfigProjector` (§9.3) to produce an updated `OperationConfig`. They are part of the operation event log and are event-sourced in the same way as all other domain events.

```python
class ExecutionProfileOverrideUpdated(DomainEvent):
    type: Literal["config.execution_profile_override_updated"] = "config.execution_profile_override_updated"
    adapter_key: str
    model: str | None = None    # None = clear override (revert to default)
    effort: str | None = None   # None = clear override

class BudgetExtended(DomainEvent):
    type: Literal["config.budget_extended"] = "config.budget_extended"
    new_max_iterations: int | None = None
    new_timeout_seconds: int | None = None

class InvolvementLevelChanged(DomainEvent):
    type: Literal["config.involvement_level_changed"] = "config.involvement_level_changed"
    new_level: str  # InvolvementLevel value
```

---

## 23. ProcessManagerContext v2 — Revised Design

### 23.1 Fields That Move to the Aggregate

Based on expert discussion (Fowler + Armstrong): PM context fields that need to survive restarts belong in the aggregate as domain events.

| Field | Move to aggregate? | Reason |
|-------|-------------------|--------|
| `scheduler_state` | YES | `SchedulerPauseRequested`/`SchedulerPaused`/`SchedulerResumed` events |
| `operator_messages` | YES | `OperatorMessageReceived` event; message window tracking is aggregate state |
| `attention_requests` | YES (already is) | Already domain aggregate field |
| `pending_wakeups` | YES (via wakeup inbox) | Wakeup inbox is durable; reconstructed from it on startup |

### 23.2 ProcessManagerContext v2 (ephemeral only)

**Lifecycle:** `ProcessManagerContext` is created once at the start of each `drive()` call (via `build_pm_context()` in §23.3) and destroyed when `drive()` returns. It is never persisted, never written to the event log, and never shared between concurrent `drive()` calls. Each operation's drive loop has its own independent `ProcessManagerContext` instance with no shared state between operations.

```python
@dataclass
class ProcessManagerContext:
    """
    Ephemeral drive loop working memory. Never persisted.
    Rebuilt fresh at the start of each run from aggregate + external calls.
    Lifetime: one drive() call. Never shared across operations or drive() invocations.
    """
    # Runtime caches (rebuilt on each run)
    policy_context: PolicyCoverage | None = None
    available_agents: list[AgentDescriptor] = field(default_factory=list)
    # Owner: RuntimeReconciler — created on first session start, destroyed with this drive() call
    session_contexts: dict[str, RuntimeSessionContext] = field(default_factory=dict)
    
    # Current cycle derived state (derived from aggregate)
    current_focus: FocusState | None = None
    
    # Session-level command deduplication (starts empty each run — idempotent)
    processed_command_ids: set[str] = field(default_factory=set)
    
    # Pending signals for next cycle (volatile; set and cleared within same run)
    pending_replan_command_ids: list[str] = field(default_factory=list)
    
    # Graceful shutdown signal — in-process only, never persisted (see §22.6)
    # Set to True by ctx.request_drain() on SIGTERM; never event-sourced
    draining: bool = False

    def request_drain(self) -> None:
        """
        Signal that no new drive iterations should start after the current one completes.
        Called by OperatorServiceV2._on_sigterm() on SIGTERM — NOT by InProcessAgentRunSupervisor.
        InProcessAgentRunSupervisor manages asyncio Tasks for background agent runs only;
        drain signaling is the responsibility of the operator-level shutdown coordinator
        (OperatorServiceV2._on_sigterm() iterates _active_contexts and calls this on each).
        Not on LifecycleGate — LifecycleGate is purely a check layer (no side effects);
        this mutation lives on the context it mutates.
        """
        self.draining = True
```

### 23.3 Reconstruction on Startup

```python
async def build_pm_context(
    agg: OperationAggregate,
    *,
    policy_store: PolicyStore,
    adapter_registry: AdapterRegistry,
    wakeup_inbox: WakeupInbox,
) -> ProcessManagerContext:
    ctx = ProcessManagerContext()
    
    # External lookups (not from events)
    ctx.policy_context = await policy_store.get_coverage(agg.operation_id)
    ctx.available_agents = await adapter_registry.describe_all()
    
    # Derive focus from aggregate state
    ctx.current_focus = derive_current_focus(agg)
    
    # Wakeup draining is NOT done here.
    # build_pm_context() only builds the static context (policy coverage, available agents,
    # current focus). WakeupInbox.drain() is called at the start of each drive cycle by
    # RuntimeReconciler.reconcile(), which processes each WakeupRef into domain events.
    # processed_command_ids starts empty each run (idempotent re-processing is safe —
    # see OperationCommandInbox.drain() at-least-once contract in §35.1).
    
    return ctx
```

---

## 25. Session Record v2

### 25.1 SessionRecord (Domain — Event-Sourced)

```python
class SessionRecord(BaseModel):
    """Domain aggregate field. 10 fields only. Event-sourced."""
    session_id: str
    adapter_key: str
    one_shot: bool = False
    observed_state: SessionObservedState = SessionObservedState.IDLE
    terminal_state: SessionTerminalState | None = None
    bound_task_ids: list[str] = Field(default_factory=list)
    current_execution_id: str | None = None
    last_terminal_execution_id: str | None = None
    last_result_iteration: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

### 25.2 RuntimeSessionContext (Ephemeral — Supervised by RuntimeReconciler)

```python
@dataclass
class RuntimeSessionContext:
    """Runtime tracking for one session. Never persisted to event log."""
    session_id: str
    waiting_reason: str | None = None
    cooldown_until: datetime | None = None
    cooldown_reason: str | None = None
    last_rate_limited_at: datetime | None = None
    recovery_count: int = 0
    recovery_attempted_at: datetime | None = None
    last_recovered_at: datetime | None = None
    execution_profile_stamp: ExecutionProfileStamp | None = None
    last_progress_at: datetime | None = None
    last_event_at: datetime | None = None
    attached_turn_started_at: datetime | None = None
    latest_iteration: int | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

The `RuntimeSessionContext` lives in the `ProcessManagerContext.session_contexts: dict[str, RuntimeSessionContext]` and is updated by the `RuntimeReconciler` each cycle.

---

## 26. Operation Bootstrap API

### 26.1 OperationFactory

```python
class OperationFactory:
    def create(
        self,
        goal: OperationGoal,
        *,
        policy: OperationPolicy | None = None,
        budget: ExecutionBudget | None = None,
        runtime_hints: RuntimeHints | None = None,
        execution_profile_overrides: dict[str, ExecutionProfileOverride] | None = None,
        involvement_level: InvolvementLevel = InvolvementLevel.AUTO,
        operation_id: str | None = None,
    ) -> tuple[OperationAggregate, OperationConfig, OperationCreated]:
        """
        Returns: (aggregate, config, birth_event)
        Caller must persist birth_event to the event log.
        """
```

### 26.2 OperationConfig (Immutable-by-value, Rebuilt by Projector)

```python
@dataclass(frozen=True)
class OperationConfig:
    """
    Set at operation creation. Immutable-by-value (frozen dataclass) — never mutated in place.
    Config changes are expressed as domain events (ExecutionProfileOverrideUpdated, BudgetExtended,
    InvolvementLevelChanged — see §22.8) and are projected by OperationConfigProjector (§9.3)
    to produce a new OperationConfig instance. See §3.4 for the canonical class documentation.
    """
    execution_budget: ExecutionBudget
    runtime_hints: RuntimeHints
    execution_profile_overrides: dict[str, ExecutionProfileOverride]
    involvement_level: InvolvementLevel
```

**Mid-operation configuration changes** use domain events:
- `ExecutionProfileOverrideUpdated(adapter_key, model, effort)` — change model/effort
- `BudgetExtended(new_max_iterations, new_timeout_seconds)` — extend budget
- `InvolvementLevelChanged(new_level)` — change oversight level

These events are projected by the config projector to produce an updated `OperationConfig`.

---

## 27. Commander Brain Design

### 27.1 Two-Tier Architecture

```
NL Text Input
    │
    ▼
Fast Tier: Intent Classifier (rule-based / small model)
    │
    ├─► Simple commands (identified, unambiguous) → Direct handler → FleetCommand
    │
    └─► Complex / ambiguous → Slow Tier
                                    │
                                    ▼
                          LLM Agent with Fleet Tools
                                    │
                                    ├─ list_operators()
                                    ├─ list_operations(filter)
                                    ├─ get_operation_detail(op_id)
                                    ├─ start_operation(goal, operator_id?)
                                    ├─ send_command(op_id, type, reason?)
                                    └─ broadcast_command(type, filter, reason?)
                                    │
                                    ▼
                              FleetCommandResult
```

### 27.2 Fast Tier Commands

| Pattern | Command Type |
|---------|-------------|
| "status" / "show fleet" / "what's running" | `QUERY_FLEET_STATUS` |
| "stop [op_id / goal text]" | `STOP_OPERATION` |
| "pause everything" / "pause all" | `BROADCAST_PAUSE` |
| "resume [op_id]" | `RESUME_OPERATION` |
| "start [goal text]" | `START_OPERATION` |
| "cancel [op_id]" | `CANCEL_OPERATION` |

### 27.3 Two-Mode Operation

| Mode | session_id | History | Use Case |
|------|-----------|---------|----------|
| **Stateless** | None | None (fresh fleet context each call) | One-shot commands |
| **Session-based** | provided | Stored in CommanderSessionStore (SQLite) | Multi-turn interactive sessions |

Session TTL: 30 minutes. After TTL expiry, session is dropped; user starts fresh.

### 27.4 Fleet Tools (Slow Tier LLM Agent)

```python
class FleetTools:
    async def get_fleet_status(self) -> FleetSnapshot: ...
    async def get_operation_detail(self, operation_id: str) -> OperationDetail: ...
    async def search_operations(self, query: str) -> list[OperationSummary]: ...
    async def start_operation(self, goal: str, *, operator_id: str | None = None) -> str: ...
    async def send_command(
        self, operation_id: str, command_type: str, reason: str | None = None
    ) -> CommandResult: ...
    async def broadcast_command(
        self, command_type: str, *, filter: OperatorFilter | None = None, reason: str | None = None
    ) -> list[CommandResult]: ...
```

---

## 29. Multi-Agent Concurrency Model

### 29.1 Design Decisions

1. **One decision per cycle** — preserved. Clean event semantics.
2. **Background agent starts are non-blocking** — drive loop issues `START_BACKGROUND_AGENT`, creates asyncio Task, records `AgentTurnStarted` event, immediately proceeds to next cycle.
3. **RuleBrain `fast_cycle` flag** — after a background start decision, `fast_cycle=True` triggers an immediate next Brain cycle without waiting. Enables rapid parallel startup of N agents in N rapid cycles.
4. **RuntimeReconciler handles completions** — background task completions arrive via wakeup inbox, not via polling in the main loop.
5. **Attached agent starts are blocking** — drive loop awaits current turn before proceeding (interactive/attached semantic).

### 29.2 Concurrent Agent Execution Flow

```
Cycle 1: Brain → START_BACKGROUND_AGENT(task=A), fast_cycle=True
    → asyncio.Task created for task A
    → AgentTurnStarted(task_id=A) event emitted
    → fast_cycle=True → skip reconciliation → go directly to Cycle 2

Cycle 2: Brain → START_BACKGROUND_AGENT(task=B), fast_cycle=True
    → asyncio.Task created for task B
    → AgentTurnStarted(task_id=B) event emitted
    → fast_cycle=True → go directly to Cycle 3

Cycle 3: Brain → WAIT (blocking focus on background tasks)
    → RuntimeReconciler polls: task A still running, task B still running
    → Drive loop sleeps briefly

[Background: tasks A and B run concurrently as asyncio Tasks]
[WakeupInbox receives: background_run.completed for task A]

Cycle N: RuntimeReconciler sees wakeup → AgentTurnCompleted(task_id=A) event
    → Brain → START_BACKGROUND_AGENT(task=C) or STOP
```

---

## 30. Error Recovery Architecture

### 30.1 Error Classification

Three error domains with distinct recovery paths:

| Domain | Examples | Recovery Owner |
|--------|---------|----------------|
| **Agent errors** | Rate limit, disconnect, protocol error | Adapter → RuntimeReconciler |
| **Operation errors** | Max iterations, goal not achievable, task failure | Drive loop → Brain |
| **Infrastructure errors** | Process crash, disk full | Supervisor (checkpoint resume) |

### 30.2 Retry Strategies

Three explicit retry modes (from `AcpCollectErrorClassification.recovery_mode`):

| Strategy | When | Effect |
|----------|------|--------|
| `same_session` | Transient disconnect, brief error | Reconnect + same prompt |
| `new_session` | Session state corrupted, provider error | New ACP session, same task |
| `replan` | Task fundamentally failed | Brain reassesses entire task plan |

The adapter's `classify_collect_exception()` returns the suggested strategy. Brain can override.

### 30.3 Circuit Breaker (Session Cooldown)

**States (implicit in RuntimeSessionContext):**

| State | Condition | Behavior |
|-------|-----------|---------|
| CLOSED (normal) | `cooldown_until=None`, `recovery_count=0` | Sessions run normally |
| OPEN (backing off) | `cooldown_until > now` | New sessions blocked for this adapter+task |
| HALF_OPEN (testing) | `cooldown_until < now`, `recovery_count > 0` | One test session allowed |

**Cooldown formula:**
```python
cooldown_seconds = min(30.0 * (2 ** (recovery_count - 1)) * random.uniform(0.8, 1.2), 3600.0)
# 1st failure: ~30s, 2nd: ~60s, 3rd: ~120s, ..., 10th+: ~3600s (1 hour)
```

**Ownership:** `RuntimeReconciler.handle_session_failure()` sets `cooldown_until` using the formula above, increments `recovery_count`. On success, `RuntimeReconciler.handle_session_success()` resets `recovery_count=0, cooldown_until=None`.

### 30.4 Let-It-Crash for Infrastructure Errors

Process crashes are handled by the OS-level process supervisor (e.g., systemd, Docker restart policy), NOT by in-process recovery logic. Note: "supervisor" here means the OS process manager — not `InProcessAgentRunSupervisor` (which manages asyncio Tasks, not process restarts).
1. Process crashes → OS kills the process. All asyncio coroutines stop (no `finally:` blocks run on SIGKILL). Subprocesses started by `AcpSessionRunner` are killed only if they are in the same process group (receive SIGHUP on parent death) or if the OS reclaims them as orphans (platform-specific timing). See §21.3 for the subprocess cleanup contract in graceful-shutdown cases.
2. Checkpoint was written before crash (after each cycle)
3. Supervisor restarts process
4. Process loads checkpoint + event log suffix → resumes where it left off
5. Background Tasks that were running: RuntimeReconciler emits an `AgentTurnLost` domain event for each `ExecutionRecord` still in `RUNNING` state, transitioning its `observed_state` to `ExecutionObservedState.LOST` (see §22.5 for the event schema, §3.3 for the state value)

---

## 32. Attention Request Flow v2

### 32.0 AttentionRequest State Machine

**Ownership:** `OperationAggregate.attention_requests` (§3.1) is the canonical owner. `ProcessManagerContext` does NOT hold a duplicate list.

**`AttentionRequestStatus` enum:**

| Value | Meaning |
|-------|---------|
| `PENDING` | Request raised; awaiting human or policy response |
| `ANSWERED` | Answer recorded via `AttentionAnswered` event; not yet delivered to ACP session |
| `RESOLVED` | Answer delivered to ACP session via `AttentionResolved` event |

**State diagram:**
```
PENDING ──► ANSWERED ──► RESOLVED
```

**Invariants:**
- RESOLVED is terminal
- RuntimeReconciler queries aggregate for `status=ANSWERED` requests and delivers them (§32.1 step 8)
- There is at most one PENDING or ANSWERED attention request per session at a time

### 32.1 Flow

```
1. ACP permission notification → handle_server_request() hook
2. Hook → attention_service.open_request(context, ...) 
3. → AttentionRequested domain event emitted
4. → Aggregate records attention_request (status=PENDING)
5. PolicyExecutor: if blocking → NextActionDecision(action_type=REQUEST_ATTENTION)
6. Drive loop: Operation.needs_human(summary="Waiting for permission")
7. User command: ANSWER_ATTENTION_REQUEST → AttentionAnswered domain event emitted
8. RuntimeReconciler (next cycle): detects ANSWERED+not-RESOLVED attention requests
9. RuntimeReconciler → delivers answer to ACP session (sends permission response)
10. → AttentionResolved domain event emitted
11. Drive loop: Operation.resume() → RUNNING state
```

### 32.2 Eliminated Complexity

- `pending_attention_resolution_ids` list: **eliminated** — RuntimeReconciler queries aggregate for ANSWERED+not-RESOLVED attention requests
- Manual `_finalize_pending_attention_resolutions()` call: **eliminated** — handled by RuntimeReconciler
- Attached inner-while loop for attention polling: **eliminated** — `LifecycleGate.should_pause()` detects `agg.scheduler_state == PAUSE_REQUESTED` and returns `True`, causing the drive loop to break out of the while-loop (§11.2). The next cycle starts only after the attention request is answered and a `SchedulerResumed` event restores `ACTIVE` state. RuntimeReconciler stops delivering new attention answers mid-flight because the loop does not continue.

### 32.3 New Domain Events

```python
class AttentionRequested(DomainEvent):
    type: Literal["attention.requested"] = "attention.requested"
    attention_id: str
    attention_type: str  # AttentionType value
    title: str
    question: str
    blocking: bool
    suggested_options: list[str]

class AttentionAnswered(DomainEvent):
    type: Literal["attention.answered"] = "attention.answered"
    attention_id: str
    answer_text: str
    answered_by: str  # "human" | "policy_auto_approve"

class AttentionResolved(DomainEvent):
    type: Literal["attention.resolved"] = "attention.resolved"
    attention_id: str
    resolution_summary: str | None = None
```

---

## 33. Fleet Failover Protocol

### 33.1 Three Scenarios

| Scenario | Detection | Recovery |
|----------|-----------|---------|
| **Clean shutdown** (SIGTERM handled) | Operator notifies Commander (DRAINING) | Operations marked PAUSED, available for reassignment |
| **Crash** (SIGKILL/OOM) | Commander health probe: 3 failures in 30s | Checkpoint-age-based recovery (see below) |
| **Network partition** | Same as crash detection | Require human confirmation before reassignment (split-brain risk) |

### 33.2 Crash Recovery

```
Commander detects operator DEAD (3 consecutive health failures)
    │
    ▼
Query last checkpoint timestamp for each orphaned operation
    │
    ├─ Checkpoint age < 5 minutes → status=PAUSED, mark as reassignable
    └─ Checkpoint age ≥ 5 minutes → status=NEEDS_HUMAN, require review
    │
    ▼
Reassign PAUSED operations to a healthy operator
    │
    ▼
New operator loads checkpoint + event log suffix → resumes drive loop
```

### 33.3 Fencing (Split-Brain Prevention)

Each checkpoint record includes an `epoch_id` (monotonically increasing integer). When an operation is reassigned:
1. **Commander increments the epoch:** Commander reads the current `epoch_id` from the checkpoint store (via `OperationCheckpointStore.current_epoch()`), then calls `OperationCheckpointStore.advance_epoch(operation_id, current_epoch + 1)` to atomically write the new epoch without changing the checkpoint payload. The new operator receives the new `epoch_id` as part of its run-request. The old operator's next `save()` call will use the old `epoch_id` and will raise `StaleEpochError`, fencing it out (§35.1 for the `advance_epoch()` contract).
2. **Checkpoint store rejects stale writes:** `OperationCheckpointStore.save()` raises `StaleEpochError` if the provided `epoch_id` does not match the store's current epoch (see §35.1 for the protocol definition).
3. **Drive loop on `StaleEpochError`:** The drive loop does not catch `StaleEpochError`. The exception propagates to the supervisor, which logs the conflict and stops the drive loop cleanly without retrying. The operation is now owned by the new operator.
4. **Old operator on restart:** If the old operator comes back alive after a crash and attempts to resume an operation that was reassigned, its first `checkpoint_store.save()` call raises `StaleEpochError` → supervisor detects CONFLICT → old operator stops processing that operation.

---

## 34. Observability Architecture

### 34.1 Four-Tier Model

| Tier | What | Who consumes |
|------|------|-------------|
| **Event log** | Complete domain + trace events per operation (JSONL) | Replay, debugging, CLI |
| **SSE streaming** | Real-time event stream per operation | CLI `run --attached`, Commander dashboards |
| **Metrics** | Counters/gauges for fleet health | Prometheus, monitoring |
| **Structured briefs** | OperationBrief, IterationBrief (human-readable summaries) | Human operators, Commander status |

### 34.2 Metrics (Prometheus-compatible)

```
# Operations
operator_operations_total{status="completed|failed|cancelled"} counter
operator_operations_active gauge
operator_operations_iterations_total counter
operator_iterations_duration_seconds histogram

# Agent turns
operator_agent_turns_total{adapter_key, status} counter
operator_agent_turn_duration_seconds{adapter_key} histogram
operator_agent_tokens_total{adapter_key, type="input|output"} counter

# Circuit breaker
operator_session_cooldowns_active{adapter_key} gauge
operator_session_recoveries_total{adapter_key} counter

# Fleet (Commander)
commander_operators_total{status="healthy|draining|dead"} gauge
commander_fleet_operations_total gauge
```

### 34.3 Structured Logs

Every log line carries `operation_id`, `iteration`, `session_id` as structured fields (JSON). Log levels:
- DEBUG: ACP protocol messages, drive loop cycle details
- INFO: iteration starts/ends, agent turn starts/ends, state transitions
- WARNING: circuit breaker opens, attention requests, plan replanning
- ERROR: operation failures, infrastructure errors

---

## 35. Implementation Plan

### 35.1 Key Infrastructure Preserved from v1

- **Dishka DI container** — kept for dependency injection
- **File-based stores** — FileOperationEventStore, FileOperationCheckpointStore, FileWakeupInbox, FileOperationCommandInbox all kept
- **AcpSessionRunner** — moved to `acp-core`, kept as-is
- **Event file format** — EventFileRecord wire format kept (backwards compatible)

**Protocol definitions for the four core infrastructure types:**

> **File placement:** These four protocols are defined in `operator/application/protocols.py`. All four are consumed by `application/` services. `runtime/` implementations (`FileOperationEventStore`, etc.) import from `application/protocols.py` and provide concrete implementations injected at the composition root.


```python
class OperationEventLog(Protocol):
    """Append-only event log. append() is an atomic batch (all or nothing). See §9.2."""
    async def append(self, operation_id: str, events: list[DomainEvent]) -> None:
        """Atomically persist all events. Raises on any failure — no partial writes.
        If events is empty, this method is a no-op and returns immediately without writing.
        
        CORRECTNESS REQUIREMENT for empty-list no-op: Implementations MUST NOT write
        any bytes to the event log when events==[]. This includes zero-event batch records,
        empty JSON arrays, empty JSONL lines, or any other sentinel. Downstream replay
        code counts event log records and determines seq numbers by line count — a spurious
        empty-batch record causes seq numbering to diverge from the actual event count,
        silently corrupting replay. The no-op contract is behavioral, not enforced by the
        type signature; implementations must check `if not events: return` as the first line.
        """
        ...
    async def load_suffix(self, operation_id: str, after_seq: int) -> list[DomainEvent]:
        """Load all events with seq > after_seq (used to replay suffix after checkpoint)."""
        ...
    async def load_all(self, operation_id: str) -> list[DomainEvent]:
        """Load full event history for an operation."""
        ...


class StaleEpochError(Exception):
    """Raised by CheckpointStore.save() when the provided epoch_id is not current."""
    pass


class OperationCheckpointStore(Protocol):
    """Stores the latest aggregate checkpoint per operation. Epoch-fenced (see §33.3).
    
    CORRECTNESS REQUIREMENT — ATOMIC WRITES: All implementations MUST use
    write-to-temp-then-rename semantics for every method that writes to disk
    (save() and advance_epoch()). In-place writes violate correctness: a crash
    mid-write produces a corrupt checkpoint file that is byte-for-byte
    indistinguishable from a valid one. The Protocol type signature does not
    enforce this — it is a behavioral contract on the implementing class, not
    on the interface. Implementations that use in-place writes will satisfy the
    type checker while silently violating this contract.
    
    Canonical implementation pattern (must be applied in both save() and advance_epoch()):
        tmp_path = f"{checkpoint_path}.tmp"
        write_serialized_checkpoint(tmp_path, checkpoint)
        os.fsync(fd)                           # flush to disk before rename
        os.rename(tmp_path, checkpoint_path)   # POSIX: atomic on same filesystem
    
    See save() docstring for the full explanation of why in-place writes fail.
    """
    async def save(
        self,
        operation_id: str,
        checkpoint: OperationCheckpoint,
        epoch_id: int,
    ) -> None:
        """
        Persist checkpoint. Raises StaleEpochError if epoch_id != the stored current
        epoch for this operation (exact equality — not >=). The drive loop always calls
        save() with the same epoch_id it received at drive() construction time; it does
        not attempt to advance the epoch itself. Only Commander may advance the epoch
        (via advance_epoch() — see below).
        
        The caller must not catch StaleEpochError —
        it propagates to the supervisor as a fatal conflict signal (see §33.3, §11.2).
        
        Implementations MUST use write-to-temp-then-rename semantics to guarantee atomic
        checkpoint writes. In-place writes are NOT acceptable — a crash mid-write produces
        a corrupt checkpoint file that is indistinguishable from a valid one:
        
            tmp_path = f"{checkpoint_path}.tmp"
            write_serialized_checkpoint(tmp_path, checkpoint)
            os.fsync(fd)                           # flush to disk before rename
            os.rename(tmp_path, checkpoint_path)   # POSIX: atomic on same filesystem
        
        If the process is killed between write and rename, the .tmp file is left behind
        and the previous checkpoint remains valid (no corruption).
        """
        ...
    async def advance_epoch(self, operation_id: str, new_epoch_id: int) -> None:
        """
        Atomically write new_epoch_id as the current epoch WITHOUT replacing the
        checkpoint payload. Used exclusively by Commander when reassigning an operation
        to a new operator (§33.3 step 1).
        
        Semantics:
        - new_epoch_id MUST equal current_epoch(operation_id) + 1. Raises ValueError if not.
        - The stored OperationCheckpoint payload is unchanged (same aggregate, same seq).
        - After this call, any save() with epoch_id != new_epoch_id raises StaleEpochError,
          including the OLD operator's next save() — this is the fencing mechanism.
        
        Implementation pattern (same write-to-temp-then-rename as save()):
            Read existing checkpoint record from disk.
            Write a new checkpoint record with epoch_id = new_epoch_id (same payload).
            Rename atomically.
        """
        ...
    async def load(self, operation_id: str) -> OperationCheckpoint | None:
        """Load latest checkpoint, or None if no checkpoint exists."""
        ...
    async def current_epoch(self, operation_id: str) -> int:
        """Return the current epoch_id for this operation (0 if never written)."""
        ...


class WakeupInbox(Protocol):
    """Durable inbox for wakeup signals delivered to the drive loop."""
    async def drain(self, operation_id: str) -> list[WakeupRef]:
        """Return and remove all pending wakeup signals for this operation.
        
        Delivery is at-least-once: if the process crashes between drain (read) and
        delete, wakeups are replayed on restart. Callers must handle duplicate
        wakeups idempotently (e.g. by checking ExecutionRecord.observed_state before
        emitting AgentTurnCompleted a second time).
        """
        ...
    async def post(self, operation_id: str, wakeup: WakeupRef) -> None:
        """Post a wakeup signal (used by background task completion handlers).
        
        Implementations MUST fsync before returning. Raw file-based implementations
        must call os.fsync(fd) before post() completes. SQLite WAL implementations
        satisfy this requirement ONLY when the `synchronous` pragma is set to `FULL`
        (the SQLite default). Under `NORMAL` or `OFF` synchronous modes, SQLite WAL
        does NOT guarantee fsync before returning from a commit, and a lost wakeup is
        possible. Operator v2 SQLite-backed WakeupInbox implementations MUST assert or
        enforce `PRAGMA synchronous=FULL` on the database connection. A lost wakeup
        (unsynced before crash) leaves the operation permanently stuck in WAIT state —
        it will exhaust its iteration budget waiting for a signal that never arrives.
        """
        ...


class OperationCommandInbox(Protocol):
    """Durable inbox for external commands addressed to a running operation."""
    async def drain(self, operation_id: str) -> list[OperationCommand]:
        """Return and remove all pending commands for this operation.
        
        Delivery is at-least-once: if the process crashes between returning commands
        and deleting them, commands are redelivered on restart. ProcessManagerContext
        .processed_command_ids deduplicates within one drive() session, but starts
        empty each run — it does NOT deduplicate across restarts.
        
        The operator v2 implementation resolves this with BOTH layers applied together:
        - The inbox implementation MUST use atomic drain semantics: read + delete in
          one filesystem operation (e.g., rename() the pending command file to a
          processing file before returning its contents). This eliminates redelivery in
          the common case (no crash between read and delete).
        - All command handlers MUST ALSO be idempotent as a defence-in-depth measure
          covering the narrow crash window between the rename and the handler completing.
          For example: applying a CANCEL command to an already-cancelled operation is a
          no-op (not an error). This redundancy is intentional — the two layers are not
          alternatives; both are required.
        """
        ...
    async def post(self, operation_id: str, command: OperationCommand) -> None:
        """Post a command (used by HTTP command endpoint and MCP send_command)."""
        ...
```

### 35.2 Recommended Implementation Order

**Phase 1: Domain decomposition**
1. Split `OperationState` → `OperationAggregate` + `OperationConfig` + `SessionRegistry` + `ExecutionRegistry` + `ProcessManagerContext`
2. Add typed domain events (discriminated union)
3. Update projectors for new aggregate structure
4. Remove PM-state fields from checkpoint

**Phase 2: Drive loop refactoring**
5. Extract `LifecycleGate` (pure functions) from drive loop
6. Extract `RuntimeReconciler` (async reconciliation) from drive loop
7. Extract `PolicyExecutor` (events only, no mutation) from drive loop
8. Wire three services back into `DriveService`

**Phase 3: Brain/Policy split**
9. Implement `RuleBrain` (deterministic cases)
10. Wrap existing LLM brain as `LLMBrain`
11. Compose `StratifiedBrain` (RuleBrain → LLMBrain fallback)
12. Implement `PlanningDecision` and `plan()` method on `LLMBrain` per §17.2

**Phase 4: Daemon + Commander**
13. Add Operator Control API (HTTP endpoints)
14. Implement `OperatorDaemonShutdownCoordinator`
15. Implement `CommanderRegistry` + health probing
16. Implement `NLFleetController` (two-tier: fast classifier + LLM agent)

**Phase 5: Cleanup**
17. Remove `anyio` dependency (replace with asyncio)
18. Remove `snapshot_legacy` code paths
19. Add migration tool (SnapshotMigrationService)
20. Extract `acp-core` package

---

## 37. OperatorPolicy Evaluation Design

### 37.1 When evaluate_result() Is Called

NOT after every agent turn. ONLY when:
1. Brain returns `action_type=STOP` (claiming completion)
2. Brain returns `action_type=REQUEST_ATTENTION` (uncertain, asking for help)
3. Budget exhaustion (max iterations or timeout)

This reduces evaluation LLM calls from O(iterations) to O(completion attempts).

### 37.2 evaluate_result() Contract

```python
class OperatorPolicy(Protocol):
    async def evaluate_result(
        self,
        context: BrainContext,
    ) -> ResultEvaluation: ...

class ResultEvaluation(BaseModel):
    goal_satisfied: bool
    should_continue: bool
    summary: str
    blocker: str | None = None
```

### 37.3 Two Evaluator Implementations

```python
class LLMResultEvaluator:
    """For qualitative success criteria. Uses a separate evaluator LLM (not the Brain)."""
    async def evaluate(self, context: BrainContext) -> ResultEvaluation: ...

class DeterministicResultEvaluator:
    """For quantitative success criteria (exit codes, file existence)."""
    def evaluate(self, context: BrainContext) -> ResultEvaluation: ...
```

The success criteria format determines which evaluator is used:
- `"exit_code == 0"` → deterministic
- `"The code compiles and all tests pass"` → LLM evaluator

---

## 38. Commander Audit Log

Commander maintains a simple append-only JSONL audit log (not full ES):

```jsonl
{"ts": "...", "type": "operator.registered", "operator_id": "...", "endpoint": "..."}
{"ts": "...", "type": "fleet.command.issued", "command_type": "STOP_OPERATION", "by": "nl", "input": "stop everything"}
{"ts": "...", "type": "operation.assigned", "operation_id": "...", "to_operator": "..."}
{"ts": "...", "type": "health_probe.result", "operator_id": "...", "status": "dead"}
```

This is for audit and debugging, not for replay or state reconstruction.

---

## 39. OperatorService v2 (Simplified Constructor)

### 39.1 InProcessAgentRunSupervisor Interface

```python
class InProcessAgentRunSupervisor:
    """
    Manages asyncio.Task lifecycle for background agent runs within one operator daemon.
    
    One instance per OperatorServiceV2. Shared across all concurrent operations.
    Tasks are keyed by session_id — each background session gets one asyncio.Task.
    """
    
    def spawn(self, session_id: str, operation_id: str, coro: Coroutine) -> asyncio.Task:
        """
        Create an asyncio.Task for the given coroutine and register it by session_id.
        Uses asyncio.create_task(coro, name=f"agent-run-{session_id}") for debuggability.
        Registers a done_callback that posts a WakeupRef to WakeupInbox when the task
        completes (success, failure, or cancellation). RuntimeReconciler picks up the
        wakeup on the next drive cycle.
        operation_id is stored so get_tasks_for_operation() can filter by operation.
        """
        task = asyncio.create_task(coro, name=f"agent-run-{session_id}")
        task.add_done_callback(lambda t: self._on_task_complete(session_id, t))
        self._tasks[session_id] = task
        self._task_operation[session_id] = operation_id  # for get_tasks_for_operation()
        return task
    
    def get_active_tasks(self) -> list[asyncio.Task]:
        """Return ALL registered tasks that are not yet done — used by shutdown sequence (§14)."""
        return [t for t in self._tasks.values() if not t.done()]
    
    def get_tasks_for_operation(self, operation_id: str) -> list[asyncio.Task]:
        """Return active tasks for a specific operation — used by RuntimeReconciler (AgentRunStore protocol).
        Tasks are tagged with operation_id when spawned via self._task_operation[session_id] = operation_id.
        """
        return [
            t for sid, t in self._tasks.items()
            if not t.done() and self._task_operation.get(sid) == operation_id
        ]
    
    def cancel_all(self) -> None:
        """
        Cancel all registered tasks. Called by the shutdown sequence in §14 after
        asyncio.wait() times out. Does NOT await cancellation — caller must await
        asyncio.gather(*pending, return_exceptions=True) after this call.
        """
        for task in self._tasks.values():
            task.cancel()
    
    # AgentRunStore protocol implementation (used by RuntimeReconciler):
    def get_task_status(self, session_id: str) -> TaskRunStatus | None:
        """Return the current status of the task for session_id, or None if unknown."""
        task = self._tasks.get(session_id)
        if task is None:
            return None
        if not task.done():
            return "RUNNING"
        if task.cancelled():
            return "CANCELLED"
        if task.exception() is not None:
            return "FAILED"
        return "COMPLETED"
```

### 39.2 OperatorServiceV2

```python
class OperatorServiceV2:
    """Thin facade over drive loop services. ~10 dependencies vs v1's 30+."""
    
    def __init__(
        self,
        *,
        event_log: OperationEventLog,
        checkpoint_store: OperationCheckpointStore,
        command_inbox: OperationCommandInbox,
        wakeup_inbox: WakeupInbox,
        adapter_registry: AdapterRegistry,
        brain: Brain,
        policy: OperatorPolicy,
        supervisor: InProcessAgentRunSupervisor,
        # InProcessAgentRunSupervisor: manages asyncio.Task lifecycle for background agent runs.
        # Responsibilities: spawn tasks on START_BACKGROUND_AGENT, poll completion status,
        # post wakeup signals to WakeupInbox when tasks complete, cancel tasks on shutdown.
        # Used by RuntimeReconciler to check live task state each cycle.
        policy_store: PolicyStore,
    ) -> None: ...
    
    # Active context registry — for SIGTERM drain (see §14)
    # operation_id → ProcessManagerContext for the currently-running drive() call.
    # Registered on drive() entry, removed on drive() return.
    _active_contexts: dict[str, ProcessManagerContext]
    
    # Public API (same as v1 for backwards compatibility)
    async def run(self, goal: OperationGoal, **kwargs) -> OperationOutcome: ...
    async def resume(self, operation_id: str, **kwargs) -> OperationOutcome: ...
    async def tick(self, operation_id: str, **kwargs) -> OperationOutcome: ...
    async def send_command(self, operation_id: str, command: OperationCommand) -> bool: ...
    async def get_operation(self, operation_id: str) -> OperationSummary: ...
```

---

## 40. Operator Control API (HTTP + MCP)

Both the MCP server and the HTTP Operator Control API are thin wrappers over `OperatorServiceV2`.

### 40.1 HTTP Operator Control API

```
POST   /operations                           → run_operation
GET    /operations                           → list_operations
GET    /operations/{id}                      → get_status  
POST   /operations/{id}/attention            → answer_attention
POST   /operations/{id}/cancel               → cancel_operation
POST   /operations/{id}/interrupt            → interrupt_operation
GET    /operations/{id}/events               → SSE event stream
GET    /health                               → daemon health
GET    /metrics                              → Prometheus metrics
```

### 40.3 SSE Event Stream Wire Format

`GET /operations/{id}/events` delivers a standard SSE stream. Each event has the following wire format:

```python
class OperationStreamEvent(BaseModel):
    """Wire envelope for one event on the SSE stream."""
    seq: int                      # monotonically increasing sequence number within this operation's stream
    event_type: str               # mirrors DomainEvent.type (e.g. "agent_turn.completed")
    operation_id: str
    payload: dict[str, Any]       # full DomainEvent fields (same as what is stored in the event log)
    timestamp: datetime
```

The payload is the full `DomainEvent` serialized as JSON — not a separate projection type. Consumers can deserialize using the `OperationDomainEvent` discriminated union (§22.7).

**Replay-on-connect policy:** When a client connects (or reconnects), the stream **replays all historical events** for the operation from the beginning of the event log, then transitions to live delivery. Clients must be idempotent with respect to replayed events — they should use `seq` to detect and skip already-processed events.

**Reconnect semantics:**
- Clients may pass `?since_seq=N` to request only events with `seq > N`, avoiding full replay on reconnect.
- The server delivers events in `seq` order with no gaps.
- If the operation reaches a terminal state, the server sends a final event and closes the stream.

**Backpressure:** The server does not buffer unboundedly. If a slow client cannot keep up, the connection is closed and the client must reconnect with `?since_seq=N`.

### 40.2 MCP Tools (preserved from v1)

```
list_operations(status_filter?)
run_operation(goal, agent?, wait?, timeout_seconds?)
get_status(operation_id)
answer_attention(operation_id, attention_id?, answer)
cancel_operation(operation_id, reason?)
interrupt_operation(operation_id)
```

Both protocol surfaces share the same OperatorServiceV2 calls.

---

## 42. Operation Resumption Protocol

### 42.1 How Resumption Works

```
OperatorServiceV2.resume(operation_id)
    │
    ▼
EventSourcedReplayService.load(operation_id)
    → Load latest checkpoint
    → Load event log suffix after checkpoint
    → Project: checkpoint + suffix → OperationAggregate + OperationConfig
    #   IMPORTANT: OperationSnapshotProjector MUST handle terminal lifecycle events
    #   (OperationCompleted, OperationFailed, etc.) applied to a RUNNING-status aggregate.
    #   The checkpoint may reflect status=RUNNING while the suffix contains a terminal event
    #   from the last cycle before the process stopped. See §9.3 for the full projector contract.
    │
    ▼
OperatorServiceV2.resume() — pre-drive step (NOT LifecycleGate — LifecycleGate is pure/check-only):
    ├─ If aggregate.scheduler_state == PAUSED:
    │      emit SchedulerResumed event → event_log.append([SchedulerResumed(...)])
    │      aggregate.apply_events([SchedulerResumed(...)]) → aggregate.scheduler_state = ACTIVE
    │      (LifecycleGate sees ACTIVE state, not PAUSED — it never emits events itself)
    │
    └─ If aggregate.status is terminal: return OperationOutcome immediately
    │
    ▼
build_pm_context(aggregate, policy_store, adapter_registry, wakeup_inbox)
    → ProcessManagerContext (empty processed_command_ids, fresh policy/agents)
    │
    ▼
LifecycleGate.check_pre_run(aggregate, config)
    → Pure check only — no event emission, no mutation. Returns early if terminal/timeout.
    │
    ▼
DriveService.drive(aggregate, config, epoch_id=current_epoch)
    # event_log and ProcessManagerContext are injected/built internally — see §11.3, §23.3
```

### 42.2 Resumption Modes

| Mode | RunOptions.run_mode | max_cycles | Effect |
|------|---------------------|-----------|--------|
| **Attached** | ATTACHED | unlimited | CLI watches, waits for completion |
| **Tick** | RESUMABLE | 1 | One cycle, CLI detaches |
| **Background** | RESUMABLE | unlimited | Daemon runs until terminal |

---

## 43. RuleBrain — Hard-Coded Logic

RuleBrain is NOT configurable via YAML. Retry thresholds use `OperationConfig.execution_budget.max_task_retries`.

Adapter-specific retry policies live in adapter configuration, not in Brain.

**Rule summary:**
1. All tasks terminal → STOP
2. Exactly one READY task with assigned agent → deterministic START/CONTINUE (no LLM)
3. Active PENDING attention request → WAIT
4. scheduler_state == PAUSE_REQUESTED → WAIT (let reconciler materialize pause)
5. Ambiguous cases → defer to LLMBrain

---

## 44. Architecture Summary Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          OPERATOR V2 ARCHITECTURE                         │
└──────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐     HTTP/gRPC      ┌─────────────────────────────────┐
│   Commander     │◄──────────────────►│        Operator Daemon           │
│                 │  Operator Control  │                                   │
│ ┌─────────────┐ │       API          │ ┌─────────────────────────────┐  │
│ │CommanderReg.│ │                    │ │      OperatorServiceV2      │  │
│ └─────────────┘ │                    │ └──────────────┬──────────────┘  │
│ ┌─────────────┐ │                    │                │                  │
│ │NLFleetCtrl  │ │                    │    ┌───────────▼────────────┐    │
│ └─────────────┘ │                    │    │      DriveService      │    │
│ ┌─────────────┐ │                    │    │                        │    │
│ │AuditLog     │ │                    │    │ ┌──────────────────┐   │    │
│ └─────────────┘ │                    │    │ │  LifecycleGate   │   │    │
└─────────────────┘                    │    │ │  (pure, sync)    │   │    │
                                       │    │ └──────────────────┘   │    │
┌─────────────────┐                    │    │ ┌──────────────────┐   │    │
│   CLI (thin)    │◄──────────────────►│    │ │RuntimeReconciler │   │    │
│                 │    CLI API (SSE)   │    │ │  (async, facts)  │   │    │
└─────────────────┘                    │    │ └──────────────────┘   │    │
                                       │    │ ┌──────────────────┐   │    │
┌─────────────────┐                    │    │ │ PolicyExecutor   │   │    │
│   MCP Server    │◄──────────────────►│    │ │ (events only)    │   │    │
│  (Claude, etc.) │      MCP tools     │    │ └──────────────────┘   │    │
└─────────────────┘                    │    └───────────────────────────┘    │
                                       │                                      │
                                       │  ┌─────────────────────────────┐   │
                                       │  │       Domain Model           │   │
                                       │  │                              │   │
                                       │  │  OperationAggregate          │   │
                                       │  │  ├── OperationStatus SM      │   │
                                       │  │  ├── TaskPlan                │   │
                                       │  │  └── AttentionRequests       │   │
                                       │  │                              │   │
                                       │  │  SessionRegistry             │   │
                                       │  │  └── SessionRecord × N       │   │
                                       │  │                              │   │
                                       │  │  ExecutionRegistry           │   │
                                       │  │  └── ExecutionRecord × N     │   │
                                       │  │                              │   │
                                       │  │  OperationConfig (frozen)    │   │
                                       │  └─────────────────────────────┘   │
                                       │                                      │
                                       │  ┌─────────────────────────────┐   │
                                       │  │   File-Based Infrastructure  │   │
                                       │  │  ┌──────────────────────┐   │   │
                                       │  │  │  EventLog (JSONL)    │   │   │
                                       │  │  ├──────────────────────┤   │   │
                                       │  │  │  CheckpointStore     │   │   │
                                       │  │  ├──────────────────────┤   │   │
                                       │  │  │  WakeupInbox         │   │   │
                                       │  │  ├──────────────────────┤   │   │
                                       │  │  │  CommandInbox        │   │   │
                                       │  │  └──────────────────────┘   │   │
                                       │  └─────────────────────────────┘   │
                                       │                                      │
                                       │  ┌─────────────────────────────┐   │
                                       │  │   Adapters (acp-core)        │   │
                                       │  │  ┌───────────────────────┐  │   │
                                       │  │  │  AcpSessionRunner     │  │   │
                                       │  │  ├───────────────────────┤  │   │
                                       │  │  │  codex_acp hooks      │  │   │
                                       │  │  │  claude_acp hooks     │  │   │
                                       │  │  │  opencode_acp hooks   │  │   │
                                       │  │  └───────────────────────┘  │   │
                                       │  └─────────────────────────────┘   │
                                       └─────────────────────────────────────┘
```

---

## 45. Resolved Questions (as of iteration 50 — FINAL)

All architecture-shaping questions are resolved. No remaining blockers for implementation.

| # | Question | Resolved in |
|---|----------|------------|
| Q-1 | Typed domain events: discriminated union or Protocol? | §22.7 (discriminated union on `type` field) |
| Q-2 | Commander Brain: NL→FleetCommand prompting + tool design | §27 (two-tier: fast classifier + LLM agent with FleetTools) |
| Q-3 | Commander ↔ Operator authentication (tokens? mTLS?) | Deferred to implementation (out of scope for v2 architecture) |
| Q-4 | Migration path: v1 snapshot-legacy operations → v2? | §18 (SnapshotMigrationService) |
| Q-5 | Test strategy: how to test the drive loop in isolation? | §19 (InMemoryEventLog + FakeBrain + FakeAgentAdapter) |
| Q-6 | ACP v2: how to formalize the adapter hook pattern? | §21.2 (AcpSessionRunnerHooks Protocol) |
| Q-7 | ProcessManagerContext: events vs computed fresh? | §23.3 (build_pm_context — external lookups, not events) |
| Q-8 | Operation bootstrap: how is OperationConfig set at creation? | §26.1 (OperationFactory) |
| Q-9 | Session lifecycle refactoring: what fields stay in SessionRecord? | §25.1 (10 fields, domain-relevant only) |
| Q-10 | Fleet failover: operator daemon dies with active operations? | §33 (crash recovery + fencing) |
| Q-11 | Observability: what metrics should the Operator expose? | §34.2 (Prometheus-compatible metrics) |
| Q-12 | Multi-agent: how does drive loop handle concurrent sessions? | §29 (background asyncio Tasks + RuleBrain fast_cycle) |
| Q-13 | Attention request flow in v2? | §32 (10-step flow + AttentionRequest state machine) |
| Q-14 | Formal policy for operation resumption after PAUSED state? | §42 (OperationServiceV2.resume + SchedulerResumed event) |
| Q-15 | Should Commander have its own event log? | No — Commander uses an audit log (§38), not an event-sourced log |
| Q-16 | Should RuleBrain decisions be configurable (YAML rules)? | No — RuleBrain is hard-coded; retry thresholds via OperationConfig (§43) |

**Minor implementation details deferred** (not architecture blockers):
- Exact HTTP framework for Operator Control API (FastAPI recommended)
- Specific Prometheus metric naming conventions
- Commander health probe interval and timeout tuning
- Commander session TTL (30min default, configurable)

---

## SWARM PROCESS SUMMARY

**50 iterations completed.** Expert team: Barbara Liskov (Critic), Joe Armstrong (Critic · Reframer), Rich Hickey (Evangelist · Constraint Relaxer), Martin Fowler (Balanced · Synthesizer), Werner Vogels (Balanced · Implementer).

**Options executed:** E×19, A×7, C×12, A1×5, D×2, G×2, H×1

**All 25 major design decisions: CLOSED**
**All Open Items (OI-1 through OI-16): CLOSED**
**All verified problems from v1: structurally solved in v2**

*Document finalized.*

---

## 46. Type Glossary — Enum Values

This appendix lists the valid values for key enum types referenced throughout the document. Types with full definitions elsewhere (e.g., `TaskStatus` in §5.5, `ExecutionObservedState` in §3.3, `AttentionRequestStatus` in §32.0) are noted with a cross-reference only.

| Type | Values | Defined / Used in |
|------|--------|-------------------|
| `TaskStatus` | PENDING, READY, IN_PROGRESS, COMPLETED, FAILED, CANCELLED | §5.5 (full definition) |
| `ExecutionObservedState` | RUNNING, COMPLETED, FAILED, LOST | §3.3 (full definition) |
| `AttentionRequestStatus` | PENDING, ANSWERED, RESOLVED | §32.0 (full definition) |
| `BrainActionType` | START_AGENT, START_BACKGROUND_AGENT, CONTINUE_AGENT, STOP, WAIT, REQUEST_ATTENTION | §17.2, §29.1 |
| `SessionObservedState` | IDLE, RUNNING, WAITING, TERMINAL | §5.2 lifecycle diagram; `SessionRecord.observed_state` (§25.1) |
| `SessionTerminalState` | COMPLETED, FAILED, CANCELLED | §5.2 lifecycle diagram; narrows the `TERMINAL` observed state |
| `AgentResultStatus` | SUCCESS, FAILED, CANCELLED | §22.5 `AgentTurnCompleted.result_status`; §8.3 `AgentResult` |
| `HealthStatus` | HEALTHY, DRAINING, DEAD | §13.2 / §47 `OperatorRecord.health` (definition); §33.1 (crash detection), §34.2 (fleet metrics) |
| `InvolvementLevel` | AUTO, LOW, MEDIUM, HIGH | §3.4, §26.1 `InvolvementLevel.AUTO`; drives policy oversight level |
| `SchedulerState` (aggregate) | ACTIVE, PAUSE_REQUESTED, PAUSED | §22.6 (events); DRAINING is in-process only (ProcessManagerContext.draining flag) |

---

## 47. Type Stubs — Boundary Types

Minimal field schemas for types referenced at component boundaries. Full behavior is defined in the sections that use each type; this section provides the field list to prevent incompatible implementations.

```python
@dataclass(frozen=True)
class IterationBrief:
    """Summary of one completed drive loop iteration. Stored in OperationReadModel.
    
    Referenced in BrainContext.recent_iterations (§17.1) and OperationReadModel (§3.5).
    One IterationBrief is produced per while-loop cycle in DriveService.drive() (§11.2),
    regardless of how many more_actions=True sub-calls occurred within that cycle.
    """
    iteration: int
    action_type: str           # e.g. "START_AGENT", "WAIT_FOR_AGENT", "STOP"
    reasoning: str             # truncated to ~200 chars for context efficiency
    outcome: str               # brief description: "agent started", "waiting for reply", etc.
    timestamp: datetime


@dataclass(frozen=True)
class DecisionRecord:
    """Record of one brain call within a drive cycle. Stored in OperationReadModel.
    
    Referenced in BrainContext.recent_decisions (§17.1).
    More fine-grained than IterationBrief: one record per brain.decide() call,
    including more_actions=True sub-calls within a single drive iteration.
    Allows brain to recognize its own decision patterns (e.g. repeated START_AGENT).
    reasoning is intentionally excluded — too verbose for history; available via IterationBrief.
    """
    action_type: str           # same as NextActionDecision.action_type
    more_actions: bool         # whether brain requested continuation in the same cycle
    wake_cycle_id: str         # ties decisions to the same wake cycle; generated as uuid4 at
                               # the start of each drive() call (NOT epoch_id — epoch_id is a
                               # checkpoint fencing key that does not change within a wake cycle)
    timestamp: datetime


@dataclass(frozen=True)
class OperatorMessage:
    """A message from the user (human operator) to the running operation.
    
    Referenced in BrainContext.recent_operator_messages (§17.1).
    Stored in OperationAggregate.operator_messages via OperatorMessageReceived events (§22.6).
    Only INSTRUCTION and RESPONSE_REQUESTED types are passed to BrainContext by default.
    
    Projector mapping from OperatorMessageReceived event:
        message_id   ← event.message_id
        type         ← event.message_type
        content      ← event.content
        source       ← event.source
        received_at  ← event.timestamp  (DomainEvent base field)
    """
    message_id: str
    type: str              # "INSTRUCTION" | "RESPONSE_REQUESTED" | "SYSTEM"
    content: str
    source: str            # "user" | "system" | "commander"
    received_at: datetime


@dataclass
class WakeupRef:
    """A signal posted to WakeupInbox to wake the drive loop. §23.2, §23.3, §35.1.
    
    Note: if WakeupInbox is extracted to inbox-core (§12.5), operation_id must be
    renamed to inbox_id: str (generic partitioning key) — same pattern as DomainEvent.
    """
    operation_id: str
    kind: str           # "TASK_COMPLETED" | "ATTENTION_ANSWER" | "COMMAND" | "HEARTBEAT"
    session_id: str | None   # which session the wakeup originates from (None for heartbeats)
    payload: dict[str, object]  # event-specific data; empty dict if unused


@dataclass
class FocusState:
    """Drive loop's current attention target. §23.2."""
    kind: FocusKind              # TASK | SESSION | ATTENTION_REQUEST
    target_id: str               # task_id or session_id depending on kind
    mode: FocusMode              # ADVISORY | BLOCKING
    blocking_reason: str | None  # human-readable; set when mode=BLOCKING
    interrupt_policy: InterruptPolicy | None  # None when mode=ADVISORY
    resume_policy: ResumePolicy | None        # None when mode=ADVISORY


@dataclass
class OperationCommand:
    """A command sent to a running operation via OperationCommandInbox. §35.1, §39."""
    command_id: str          # uuid; used for idempotency deduplication
    operation_id: str
    kind: str                # "PAUSE" | "RESUME" | "CANCEL" | "SEND_MESSAGE" | "REPLAN"
    payload: dict[str, object]  # kind-specific; e.g. {"message": "..."} for SEND_MESSAGE
    issued_at: datetime


@dataclass
class OperationOutcome:
    """Returned by DriveService.drive() and OperatorServiceV2 public methods. §11.2, §39, §42."""
    operation_id: str
    status: OperationStatus      # terminal status at the time drive() returned
    summary: str                 # human-readable outcome; either policy-provided or default
    final_result: AgentResult | None  # last agent turn result if any, else None
    iterations_executed: int     # number of brain.decide() calls this drive() call ran.
                               # Counts DecisionRecord entries, NOT IterationBrief entries.
                               # Each more_actions=True sub-call counts as a separate brain call
                               # because iterations_executed is incremented once per brain.decide()
                               # call in §11.2 (above the more_actions continue branch).
                               # A wake cycle with 3 more_actions=True calls + 1 final call
                               # contributes 4 to this counter.
                               # Equals len(decision_records) in OperationReadModel after the
                               # drive() call completes (one DecisionRecord per brain call).
                               # NOTE: len(iteration_briefs) != len(decision_records) when
                               # more_actions=True is used — IterationBrief is one-per-while-cycle
                               # (one per call to decide_and_execute()); DecisionRecord is
                               # one-per-brain-call within that cycle (finer granularity).
    started_at: datetime
    finished_at: datetime


# OperationGoal — a plain string in the current design.
# Defined as a type alias so it can be promoted to a structured dataclass later.
OperationGoal = str


class HealthStatus(str, Enum):
    """Operator daemon health as reported via heartbeat. Used in OperatorRecord.health."""
    HEALTHY = "HEALTHY"
    DRAINING = "DRAINING"   # graceful shutdown in progress; no new operations accepted
    DEAD = "DEAD"            # heartbeat timeout exceeded or explicit crash signal received


@dataclass
class FleetSnapshot:
    """Point-in-time view of all operators tracked by the Commander. §13.2, §27.4."""
    captured_at: datetime
    operators: list[OperatorRecord]  # one entry per known operator daemon

@dataclass
class OperatorRecord:
    """Canonical definition. §13.2 references this definition; do not redefine there."""
    operator_id: str
    endpoint: str               # "http://localhost:8421" — needed for routing in CommanderRegistry
    health: HealthStatus        # HEALTHY | DRAINING | DEAD
    active_operations: list[str]  # operation_ids currently assigned
    last_heartbeat_at: datetime
    epoch_id: int               # current epoch for stale-write detection
```
