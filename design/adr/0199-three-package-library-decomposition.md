# ADR 0199: Three-Package Library Decomposition — operator / acp-core / commander

- Date: 2026-04-21

## Decision Status

Proposed

## Implementation Status

Planned

## Context

The current `operator` package contains everything: ACP transport logic, agent adapter protocols, domain events, drive loop, CLI, and Commander coordination. This creates two problems:

**Problem 1 — Cross-project reuse is impossible.** `lifechanger-tg`, `femtobot`, and `swarm-evo` all need agent session management (start ACP session, collect result, manage lifecycle). Currently they would have to vendor or copy the relevant code from `operator`, which carries the entire operator domain as a dependency.

**Problem 2 — `operator`-specific concepts leak into generic libraries.** The existing `AgentSessionHandle` carried an `operation_id` field — an operator-domain concept. A `femtobot` session has no "operation"; it would have to pass a meaningless value. This is the classic bounded context leakage problem.

### Adjacent projects that need shared infrastructure

- `lifechanger-tg` — Telegram bot that manages agent sessions; needs ACP session management but has no concept of "operations"
- `femtobot` — lightweight agent runtime; same need
- `swarm-evo` — evolutionary swarm framework; needs event-store infrastructure but no operator domain
- Evaluation framework — needs both agent session management and event-store replay; no operator domain

## Decision

Split the codebase into three packages with explicit boundary rules:

### Package 1: `acp-core`
Agent communication protocol library. Usable by any project that manages agent sessions.

**Contains:**
- `AgentAdapter` protocol: `start(request: AgentRunRequest) -> AgentSessionHandle`, `collect(handle) -> AgentResult`
- `AgentSessionHandle`: `(session_id, adapter_key, run_id)` — no `operation_id`
- `AgentResult`, `AgentRunRequest`, `AgentResultStatus`
- `AcpSessionRunner`, `AcpSessionRunnerHooks`
- Concrete adapter implementations: `CodexAdapter`, `ClaudeAdapter`

**Boundary rule:** `acp-core` must not import from `operator`. It must not contain any type with `operation_id`. Adapter implementations in `acp-core` may be used by `operator` but are not aware of it.

### Package 2: `operator`
The operator runtime. Depends on `acp-core` for agent management.

**Contains:**
- `OperationAggregate`, `DomainEvent` types, drive loop, `PolicyExecutor`, `RuntimeReconciler`, `LifecycleGate`
- `OperatorServiceV2`, CLI, brain protocol
- Operator-specific adapter wrappers (add `operation_id` context via `SessionRegistry`)
- `Commander` client

**Boundary rule:** `operator.application/` imports from `operator.domain/` only (not from `operator.runtime/` implementation classes). `operator.runtime/` implements protocols defined in `operator.application/`.

### Package 3: `commander`
Fleet coordination. Manages epoch fencing, health monitoring, operation assignment.

**Contains:**
- `CommanderRegistry`, `FleetSnapshot`, `OperatorRecord`
- `Commander` process implementation
- Epoch advancement protocol (see ADR 0197)

**Boundary rule:** `commander` knows about operations (by `operation_id`) but does not import `OperationAggregate` — it coordinates at the operator-process level, not the aggregate level.

### Future extractions (not in scope for v2 initial implementation)

- `event-store-core`: generic `DomainEvent` base + projector pattern, usable by `swarm-evo` and eval framework. Requires removing `operation_id` and `iteration` from the base class (operator-specific).
- `inbox-core`: generic `WakeupInbox` + `OperationCommandInbox`. Requires removing `operation_id` from `WakeupRef` (replace with generic `StreamId`).

These are documented as future extractions in ARCHITECTURE_v2.md §12.5 and are not part of the v2 initial delivery.

## Alternatives Considered

**Single package with internal namespace separation.** Keep everything in `operator`; use `operator.acp`, `operator.commander` sub-packages. Rejected: `lifechanger-tg` would still depend on the entire `operator` package including domain events and drive loop.

**Two packages only (operator + acp-core), no commander.** Commander is part of `operator`. Rejected: Commander is a separate process with a separate deployment lifecycle. Coupling its code to the operator process increases the deployment surface and makes the epoch-fencing mechanism harder to reason about.

**Full microservice decomposition at the start.** Extract `event-store-core` and `inbox-core` immediately. Rejected: premature — these extractions require removing operator-specific fields from base types, which is a design exercise that benefits from concrete usage in the other projects first.

## Startup Sequence (Commander + Operator)

Commander and Operator are separate processes (see Package 3 above). The startup sequence is:

1. **Commander starts first.** Commander must be running before any operator process starts. If Commander is unavailable, operators cannot safely accept operation assignments — they have no way to obtain an epoch, and epoch fencing (ADR 0197) would be non-functional.

2. **Operator registers with Commander on startup.** Before entering its main loop, `OperatorServiceV2` sends a registration request to Commander: `register_operator(operator_id, endpoint)`. Commander responds with the current epoch for each operation assigned to that operator.

3. **Operator behavior when Commander is unreachable on startup.** If the registration request times out or fails:
   - The operator logs the failure and retries with exponential backoff (3 attempts, max 30 seconds total).
   - If all retries fail, the operator exits with a non-zero status code. It does not enter the main loop without a valid epoch.
   - This is a fail-fast, not a degraded mode. Running without an epoch would disable stale-write protection for all operations.

4. **Operator behavior if Commander becomes unreachable during operation.** If Commander becomes unreachable after the operator has already registered and received epochs, the operator continues running with its last-known epoch. It does not exit. If Commander reassigns an operation while the operator is running (advancing the epoch), the next checkpoint write will raise `StaleEpochError`, which the drive loop treats as a fatal conflict (ADR 0197) — the operation stops, and Commander's reassignment takes effect naturally.

5. **Single-process development mode.** For local development without a Commander process, `OperatorServiceV2` may be configured with `commander_url=None`. In this mode, epoch fencing is disabled — `OperationCheckpointStore` uses epoch 0 for all operations and `advance_epoch()` is a no-op. This mode must not be used in any environment where multiple operator processes might run concurrently. `OperatorServiceV2` must emit a `WARNING`-level log at startup when `commander_url=None`: "Epoch fencing disabled (commander_url=None) — unsafe for multi-process deployment." This is a runtime signal, not just a documentation guard.

## Package Split Sequencing

The three-package split is a **post-rewrite cleanup step**. It does not happen concurrently with the v2 rewrite.

**Rationale**: The v2 rewrite changes almost every interface. Splitting packages before the rewrite is complete would require three-way coordination on every interface change — every `acp-core` API change would require simultaneous updates in `operator` and any dependent project. This triples coordination cost during the highest-turbulence phase.

**Sequencing**:

1. Complete the v2 rewrite entirely inside the monorepo as a single `operator` package. All 187 source files are updated; all 78 test files are rewritten; the v2 test suite passes.
2. Extract `acp-core`: move `AgentAdapter`, `AgentSessionHandle`, `AgentResult`, `AcpSessionRunner`, `CodexAdapter`, `ClaudeAdapter` to a new package. Update import paths in `operator`. Run full test suite.
3. Extract `commander`: move `CommanderRegistry`, `FleetSnapshot`, `OperatorRecord`, and the Commander process implementation. Update import paths. Run full test suite.

`lifechanger-tg`, `femtobot`, and other consumers depend on `acp-core` only after step 2. They cannot depend on it before, because the package does not exist until step 2 completes.

## Consequences

- `AgentSessionHandle.operation_id` is removed (breaking change; no migration path per ADR 0194)
- Adapter implementations in `acp-core` must not assume they are called by an "operator" — they are protocol-generic
- `operator` depends on `acp-core`; `acp-core` does not depend on `operator`
- `lifechanger-tg`, `femtobot`, and eval framework can depend on `acp-core` without pulling in the operator domain
- The `commander` package is a deployment artifact; it can be versioned and deployed independently of `operator`
