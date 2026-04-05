# RFC / ADR Roadmap

This file tracks decisions that need RFC or ADR coverage. It is a living document — update it when
new decisions are made or existing entries are completed.

## Principle: RFC vs ADR

| Type | When to use |
|---|---|
| **ADR** | One decision with a clear "before / after / why this and not that". Narrow scope. |
| **RFC** | Multiple interrelated decisions that form a single specification or canonical reference. Also: explicitly deferred future directions with documented activation criteria. |
| **Neither** | Behavior is obvious from VISION/ARCH, no risk of rediscovery, no alternatives worth documenting. |

## Priority 1 — Urgent

These cover decisions that have already been made but have no provenance record. Rediscovering them
without context is likely.

### RFC 0006 → Status: Accepted

**Action:** Update status only — the document is already written and iterated through three critique
rounds. Transition from `Proposed` to `Accepted`.

**Covers:** Three-category event taxonomy (domain / trace / wakeup), domain event catalog,
producer/consumer/state-effect tables, task status transitions, atomicity and failure model,
WakeupWatcher specification, loop invariants.

---

### ADR 0058: Traceability brief layer completeness

**Covers:**
- `TypedRefs` Pydantic model for `DecisionMemo` / `IterationBrief` vs `dict[str, str]` for
  `TraceRecord` — rationale for the split: `TraceRecord` is an extensible carrier, the others have
  a closed key set
- `CommandBrief` in `TraceBriefBundle` — why written at terminal command event, why for post-hoc
  consumers rather than live stream subscribers
- `EvaluationBrief` in `TraceBriefBundle` — per-iteration brain verdict history, why this belongs
  in the brief layer

**Rationale for ADR (not RFC):** Three related decisions from one design session with clear
adjudication reasoning. `ARCHITECTURE.md` carries the schema; this ADR carries the provenance.

---

### ADR 0059: Brain — project file system boundary

**Covers:**
- Invariant: brain is read-only with respect to all project files at every involvement level
- Rationale: why not "write when unattended"
- `document_update_proposal` as the only write path — why non-blocking by default
- Project-scope `MemoryEntry` as provenance-bearing cross-operation context — why not direct file
  write
- Relation to Operator Workspace (Future Direction): what criteria must be met before the invariant
  can be lifted

**Rationale for single ADR:** Brain read-only invariant, `document_update_proposal` mechanism, and
project-scope MemoryEntry write semantics are three aspects of one boundary. Splitting them would
require cross-referencing between three documents to understand the full picture.

---

## Priority 2 — High

New concepts in the current VISION/ARCH without provenance.

### ADR 0093: CLI command taxonomy, visibility tiers, and default `operator` entry behavior → Status: Accepted

**Extends:** ADR 0038, VISION, CLI-UX-VISION

**Covers:**
- fleet-first no-argument `operator` behavior
- primary / secondary / hidden debug command tiers
- `operator debug` as the home for runtime/internal surfaces
- top-level CLI taxonomy by user intent rather than implementation history

**Rationale for ADR (not RFC):** This is the top-level command-map decision for the CLI closure
wave. It is narrow enough to execute independently and constrains later command-specific ADRs
without reopening product vision.

---

### ADR 0094: `run` / `init` / `project create` workflow and project-profile lifecycle → Status: Accepted

**Extends:** CLI-UX-VISION, WORKFLOW-UX-VISION, ADR 0085

**Covers:**
- top-level `init`
- `project create`
- committed vs local profile variant lifecycle
- profile precedence
- `run --agent` and missing-goal behavior

**Rationale for ADR (not RFC):** This is one bounded project-entry and profile-lifecycle decision
beneath the broader CLI/workflow vision.

---

### ADR 0095: Operation reference resolution and command addressing contract → Status: Accepted

**Extends:** VISION, CLI-UX-VISION

**Covers:**
- accepted operation references
- `last`
- ambiguity behavior
- operation-first answer addressing
- task-scoped interrupt addressing

**Rationale for ADR (not RFC):** This is a single shared CLI addressing contract that should not
be re-decided per command.

---

### ADR 0096: One-operation control and summary surface → Status: Accepted

**Extends:** CLI-UX-VISION, ADR 0016, ADR 0037

**Covers:**
- `status`
- `message`
- `pause`
- `unpause`
- `interrupt`
- `cancel`

**Rationale for ADR (not RFC):** This is the core one-operation user-control slice for the CLI
wave and is narrower than the overall command-taxonomy decision.

---

### ADR 0097: Forensic log unification and debug-surface relocation → Status: Accepted

**Extends:** ADR 0030, VISION, CLI-UX-VISION

**Covers:**
- unified `log`
- retirement of vendor-named top-level transcript commands
- migration of runtime/internal commands under `operator debug`
- visible-vs-hidden resolution for `trace` and `inspect`

**Rationale for ADR (not RFC):** This is the forensic/debug cleanup boundary for the CLI wave and
resolves a narrow but blocking taxonomy conflict.

---

### ADR 0098: History ledger and `history` command contract → Status: Implemented

**Extends:** CLI-UX-VISION, WORKFLOW-UX-VISION

**Covers:**
- committed `operator-history.jsonl`
- terminal-state write point
- opt-out semantics
- `history [OP]`
- distinction between history and live runtime state

**Rationale for ADR (not RFC):** This is a narrow workflow-visible history decision beneath the
broader workflow vision and intentionally excludes PM integration.

---

### ADR 0099: OperatorService shell completion through workflow-authority extraction → Status: Accepted

**Extends:** ADR 0080, ADR 0088, ADR 0092

**Covers:**
- workflow-authority extraction for remaining business logic in `OperatorService`
- `OperationTraceabilityService` as the first low-risk shrink slice
- later extraction of decision, command, result, and runtime-reconciliation workflows
- aligned test decomposition so service ownership and test ownership converge

**Rationale for ADR (not RFC):** This is a bounded architecture-execution wave for completing the
shell boundary of `OperatorService`, not a new product-level architecture proposal.

**Current truth:** the workflow-authority services are now present and live in code, and the test
suite has been split along the same ownership boundaries. `OperatorService` still retains some
orchestration-side shell logic, but the workflow-authority extraction and aligned test-decomposition
wave described by this ADR are now established repository truth.

---

### ADR 0100: Pluggable operator policy boundary above loaded-operation runtime → Status: Accepted

**Extends:** ADR 0083, ADR 0099, RFC 0010

**Covers:**
- stable loaded-operation runtime/coordinator as the shared execution substrate
- pluggable operator-policy/controller layer for multiple operator implementations
- `OperatorBrain` as a dependency of one policy family rather than the top-level operator seam
- external `OperationCommand` vs internal operator intent
- command-handler style as an internal runtime pattern rather than the top-level public model

**Rationale for ADR (not RFC):** This is one architectural boundary decision about where operator
variation lives. It does not yet redefine the full runtime/event/intent model and therefore does
not warrant a broader RFC.

**Current truth:** the policy seam is already live in code, and `LoadedOperation` now exists as a
first-class application object used by decision, result, reconciliation, command, drive, and
traceability paths. The overall cutover is still `partial` because `OperatorService` retains a thin
wrapper/delegate layer for orchestration-side effects.

---

### ADR 0101: Ideal application organization — shell, loaded operation, policy, and workflow capabilities → Status: Proposed

**Extends:** ADR 0099, ADR 0100

**Covers:**
- `OperatorService` as the thin system shell and composition root
- `LoadedOperation` as the terminal one-operation runtime boundary
- `OperatorPolicy` as the pluggable behavior seam
- workflow-authority services as enduring application capabilities
- drive-layer collaborators as internal execution collaborators rather than top-level enduring
  service nouns
- restrained internal handler-style execution beneath the shell/runtime split

**Rationale for ADR (not RFC):** This is one architectural organization decision about the ideal
shape of the top application layer. It builds on already accepted lower-level decisions rather than
introducing a new multi-part runtime specification.

---

### ADR 0107: Repository module hierarchy policy and low-ambiguity application tightening → Status: Proposed

**Extends:** ADR 0101

**Covers:**
- repository-wide classification of top-level packages by hierarchy pressure
- first-pass application hierarchy tightening through `drive/` and `event_sourcing/` subpackages
- runtime-specific future hierarchy signals without precommitting a final runtime package map
- selective relocation of shared contract-like modules out of `application`
- explicit defer of bulk `operation_*` packaging until a stricter membership rule exists
- anti-symmetry, root-package, and export-surface rules for future hierarchy work

**Rationale for ADR (not RFC):** This is one bounded code-organization decision about module
hierarchy and placement. It establishes package-shape policy for the repository without turning into
a broader runtime or product specification.

---

### ADR 0108: Legacy compatibility retirement fronts and parallel-truth policy → Status: Proposed

**Extends:** ADR 0077, ADR 0086

**Covers:**
- distinction between target-architecture retirement fronts and still-live architectural debt
- retirement framing for `snapshot_legacy`, old operation-status hydration, and deprecated
  prompt-shaped goal-input compatibility
- explicit classification of `legacy_ambiguity_reason` propagation as compatibility residue rather
  than enduring target truth
- separate treatment of `active_session`, `sync_legacy_active_session`, and legacy rate-limit
  recovery as still-live debt rather than dead-code cleanup
- status-label and claim-discipline rules for documenting live compatibility paths during
  retirement waves

**Rationale for ADR (not RFC):** This is one bounded architectural cleanup-policy decision about
how the repository should classify and retire remaining compatibility residue. It does not redefine
the full runtime model.

---

### ADR 0106: Public documentation surface and committed design corpus separation → Status: Accepted

**Extends:** DOCS-UX-VISION, AGENTS, current repository documentation layout

**Covers:**
- root `README.md` as the evaluator-facing front door
- `docs/` as the public product documentation namespace
- `design/` as the committed design authority and design-history namespace
- explicit rejection of gitignoring the design corpus
- minimum public docs set needed so the move is semantic rather than cosmetic

**Rationale for ADR (not RFC):** This is one bounded repository-information-architecture decision
about documentation namespaces and audience routing. It does not require a larger RFC.

**Current truth:** the repository now has a root `README.md`, a public `docs/` surface, a
committed `design/` corpus, and a committed `policies/` tree. `pyproject.toml` now points its
readme at `README.md`, MkDocs is the public docs toolchain, and generated docstring-based API
reference is scoped to curated public technical surfaces rather than the entire internal module
graph.

---

### ADR 0102: Explicit operation lifecycle coordinator above `LoadedOperation` → Status: Accepted

**Extends:** ADR 0100, ADR 0101

**Covers:**
- explicit one-operation lifecycle authority for fold/suspend/terminate transitions
- why current composition across drive/cancellation/reconciliation is only `partial`
- why `LoadedOperation` should remain the owner of operation-local mechanics rather than absorb
  lifecycle choreography
- lifecycle-significant notify/finalize/persist/outcome/history sequencing
- the intended boundary between `OperatorService`, `LoadedOperation`, workflow authorities, and the
  new lifecycle coordinator

**Rationale for ADR (not RFC):** This is one narrow architectural boundary decision about who owns
operation-wide lifecycle transitions. It does not redefine the whole runtime model.

**Current truth:** the coordinator now exists in code and already owns durable terminal closure,
most explicit top-level lifecycle transitions, and both whole-operation and scoped
session/run-cancellation sequencing. It also now owns the repeated post-reconciliation terminal
fold step. Supervisor/runtime-side `finalize_background_turn(...)` mechanics remain in
runtime-reconciliation by design rather than as an unresolved lifecycle-coordinator gap.

---

### ADR 0103: Dishka composition-root migration → Status: Accepted

**Extends:** ADR 0101

**Covers:**
- current truth that composition is still wired manually
- adopting `dishka` at the composition root and bootstrap boundary
- keeping `dishka` out of domain and application-core contracts
- why this should be a composition-root migration rather than a repo-wide DI rewrite

**Rationale for ADR (not RFC):** This is one bounded stack-and-assembly decision about dependency
injection at the outer wiring layer. It does not redefine the application architecture itself.

**Current truth:** the migration is now `partial`. `bootstrap.py` uses `dishka` for top-level
composition-root assembly, `build_service(...)` still preserves the same public entrypoint, and
the bootstrap graph is already split into semantic provider slices. Application and domain-layer
constructors remain explicit and do not depend on `dishka`. The governing rule is now
ownership-based rather than blanket injection purity: cross-boundary collaborators should be
injected, while private mechanism objects may still be constructed locally. The production
bootstrap path now injects peer application collaborators into `OperatorService`, and test-facing
service assembly can use a dedicated `dishka`-backed support provider instead of shell-local
fallback graph construction.

---

### ADR 0104: Top application/control-layer boundary completion after shell thinning → Status: Accepted

**Extends:** ADR 0101, ADR 0102, ADR 0103

**Covers:**
- why `OperatorService` still remains too heavy after workflow-authority extraction
- the distinction between enduring missing authorities and smaller capability boundaries
- `OperationControlStateCoordinator` as a missing top-layer authority beside lifecycle
- runtime gating / runtime context as a smaller named capability boundary
- why current drive runtime/control/trace splits should still be treated as transitional unless
  their ownership becomes direct

**Rationale for ADR (not RFC):** This is one bounded architectural repair decision about completing
the remaining top application/control layer. It does not redefine the full runtime model.

**Current truth:** the repository now partially matches this target in code:
- `implemented`: `OperationControlStateCoordinator`
- `implemented`: `OperationRuntimeContext`
- `implemented`: `OperationLifecycleCoordinator`
- `implemented`: `OperatorService` is now close to a true shell/composition root
- `verified`: [service.py](../src/agent_operator/application/service.py) is down to a shell-sized
  method surface
- `partial`: the remaining work is no longer broad shell thinning, but narrower lifecycle
  sequencing under `ADR 0102`.

---

### ADR 0105: Repository-wide lint normalization as a separate quality wave → Status: Accepted

**Extends:** ADR 0103

**Covers:**
- why repo-wide lint closure should be treated as its own quality wave
- why touched-file cleanliness is not the same as repository normalization
- scope boundaries for mechanical lint cleanup vs semantic refactor work
- the target of making full `ruff check src tests` an always-green repository gate

**Rationale for ADR (not RFC):** This is one bounded repository-quality decision about how lint
debt should be normalized and scheduled. It does not redefine architecture or runtime behavior.

**Current truth:** the repository-wide lint wave is now complete.
- `verified`: `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests`
- `verified`: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q`
- `implemented`: touched-file cleanliness has been raised to repository-wide cleanliness

---

### RFC 0009: Operation event-sourced state model and runtime architecture → Status: Proposed

**Extends:** RFC 0006, RFC 0007

**Covers:**
- Why `OperationState` snapshot truth should be replaced by a canonical domain event stream plus
  replayable `OperationCheckpoint`
- Which child state machines live inside an operation (`Operation`, `Task`, `Session`,
  `Execution`, `Attention`, `Scheduler`) and why this is still one canonical operation stream
- Event pipeline boundaries: `Command -> AdapterFact -> TechnicalFact -> DomainEvent -> Checkpoint`
- Runtime component boundaries: thin `OperatorService`, event store, fact store, projector,
  reducer slices, process managers
- Checkpoint and replay contract: what belongs in canonical state and what remains technical/trace
- Migration route: versioned cutover for new operations; no dual-write canonicality

**Rationale for RFC (not ADR):** This is not one isolated decision. It bundles the canonical
state model, event taxonomy refinement, reducer/process-manager architecture, replay contract, and
migration route into one interdependent specification.

**Current truth:** foundation ADRs `0069`–`0074` are implemented and accepted, but the repository
is still snapshot-first in the main runtime path. The RFC remains `Proposed` until the canonical
event-sourced path becomes the live operation truth.

**Current closure tail:** `ADR 0092` is now accepted. The remaining work is final live-runtime
cutover under `ADR 0086` and `ADR 0088`, not data-model cleanup around the old constraints
aggregate.

---

### RFC 0010: Async runtime lifecycles and session ownership → Status: Accepted

**Extends:** RFC 0009, ADR 0070

**Covers:**
- Why `AdapterRuntime`, `AgentSessionRuntime`, and `OperationRuntime` are distinct runtime layers
- Why adapter, agent-session, and operation runtimes should expose explicit async lifecycle
  boundaries
- Why the public runtime contract is command ingress plus async event egress rather than generator
  protocol mechanics
- Where event translation happens: `AdapterFact` at the adapter boundary, `TechnicalFact` at the
  agent-session boundary, `DomainEvent` only at the fact-translator boundary
- Single-session ownership invariant for one live agent session at a time
- Naming boundary: `operation-profile` for per-operation semantics vs process-wide operator
  defaults

**Rationale for RFC (not ADR):** This is not one narrow runtime contract. It couples lifecycle
ownership, async concurrency model, event-layer boundaries, session continuity invariants, and
configuration scope naming into one coherent lower-runtime specification beneath RFC 0009.

**Current truth:** the repository now exposes `AdapterRuntime` / `AgentSessionRuntime` /
`OperationRuntime` as the public runtime architecture, uses async lifecycle boundaries and
async event egress as runtime truth, and retains `operator-profile` naming per ADR 0085.

---

### ADR 0060: Project-scope MemoryEntry

**Extends:** ADR 0005, ADR 0006

**Covers:**
- Why two scopes (operation-scope vs project-scope) rather than one unified model
- Read-at-planning-cycle semantics: why all active project-scope entries are loaded before every
  brain call
- Expiration and lifecycle: when entries become stale, how they are invalidated
- Relationship to project files: why MemoryEntry is the right model instead of direct file writes
  for cross-operation context

---

### ADR 0069: Operation event store and checkpoint store contracts → Status: Accepted

**Extends:** RFC 0009

**Covers:**
- Why `OperationEventStore` is canonical and `OperationCheckpointStore` is derived
- Sequence and concurrency contract for per-operation event appends
- Checkpoint contract: `last_applied_sequence`, replay from checkpoint + suffix
- Crash semantics: stale checkpoints acceptable, checkpoints ahead of stream forbidden
- Why event append atomicity is required but joint event-plus-checkpoint transactions are not

**Rationale for ADR (not RFC):** This is a narrower executable boundary beneath RFC 0009. The
architectural route is already chosen; this ADR fixes the first concrete storage contract needed to
implement it without reopening the broader event-sourced architecture debate.

---

### ADR 0070: Fact store and fact translator contracts → Status: Accepted

**Extends:** RFC 0009, ADR 0069

**Covers:**
- Why `FactStore` is persisted but non-canonical
- Difference between `AdapterFact` and `TechnicalFact`
- Required translation path: adapter fact -> technical fact -> domain event
- Translator contract: deterministic mapping, no direct checkpoint mutation
- Idempotency and ordering requirements for retryable translation

**Rationale for ADR (not RFC):** This is the second executable boundary beneath RFC 0009. It
specifies the seam between runtime observations and canonical business events without reopening the
broader state-model decision.

---

### ADR 0071: Operation projector and reducer slices → Status: Accepted

**Extends:** RFC 0009, ADR 0069, ADR 0070

**Covers:**
- Why there is one canonical `OperationProjector` per operation stream
- Reducer-slice contract and purity requirements
- Cross-slice coordination within one event fold
- Boundary between projector and process managers
- Replay rule: projector depends only on prior checkpoint and domain events

**Rationale for ADR (not RFC):** This is the third executable boundary beneath RFC 0009. It
specifies how canonical domain events become `OperationCheckpoint` without letting side effects or
runtime concerns leak back into the fold logic.

---

### ADR 0072: Process manager policy boundary and builder assembly → Status: Accepted

**Extends:** RFC 0009, ADR 0071

**Covers:**
- Why `ProcessManager` is restricted to control-plane reactions and planning triggers
- Explicit anti-pattern: hidden deterministic orchestration that chooses substantive next work
- Harness authority boundary: substantive next-step choice remains with the brain
- Why process-manager behavior is assembled from `Policy` via `ProcessManagerBuilder`

**Rationale for ADR (not RFC):** This is the fourth executable boundary beneath RFC 0009. It fixes
the exact point where event-driven deterministic logic must stop so that the system remains
LLM-first rather than collapsing into a workflow engine.

**Action:** Implemented as a bridge slice with `CodeProcessManagerBuilder`,
`ProcessManagerSignal`, code-defined policies, and `PlanningTrigger`-only outputs.

---

### ADR 0073: Command bus and planning trigger semantics → Status: Accepted

**Extends:** RFC 0009, ADR 0072

**Covers:**
- Why planning triggers are distinct control-plane intents rather than substantive commands
- How planning triggers flow through the same durable command bus as user/internal commands
- Allowed planning-trigger payload vs forbidden hidden strategy payload
- Coalescing and deduplication rules for repeated planning obligations

**Rationale for ADR (not RFC):** This is the fifth executable boundary beneath RFC 0009. It
specifies how event-driven process-manager outputs cause new brain cycles without shrinking harness
or reintroducing invisible in-memory orchestration flags.

**Action:** Implemented as a bridge slice with `FileControlIntentBus`, planning-trigger
coalescing/deduplication, and `FileOperationCommandInbox` as a user-command facade over the shared
bus.

---

### ADR 0074: Bridge-slice cleanup after process-manager and planning-trigger integration

**Extends:** ADR 0072, ADR 0073, RFC 0009

**Covers:**
- Explicit cleanup obligation for transitional bridge seams left after implementing `0072`/`0073`
- Retirement of temporary compatibility aliases and service-level drift
- Alignment of runtime terminology, status handling, and event-emission assumptions
- Closure criteria for declaring the bridge stable rather than merely landed

**Rationale for ADR (not RFC):** This is a narrow follow-up decision about transitional
architecture debt introduced or surfaced by an accepted bridge slice. It does not reopen the
underlying design route; it constrains the cleanup obligation around it.

---

### ADR 0077: Event-sourced operation cutover and legacy coexistence policy → Status: Accepted

**Extends:** RFC 0009, ADR 0069, ADR 0071

**Covers:**
- Per-operation canonical mode declaration: `snapshot_legacy` vs `event_sourced`
- No-dual-canonicality rule during migration
- New-operations-first cutover policy
- Legacy-operation resumability during migration
- Demotion of mutable snapshot state to compatibility/read-model role for event-canonical
  operations

**Rationale for ADR (not RFC):** This is the first remaining rollout boundary beneath RFC 0009. It
does not reopen event sourcing itself; it defines how the repository can migrate without ambiguous
truth ownership.

---

### ADR 0078: Command application and single-writer domain-event append boundary → Status: Accepted

**Extends:** RFC 0009, ADR 0069, ADR 0073, ADR 0077

**Covers:**
- One command-application authority per operation
- Validation against canonical replay state rather than mutable snapshot truth
- Acceptance/rejection as explicit domain-event outcomes
- Single-writer rule for business domain-event append
- Relation between append and downstream checkpoint refresh

**Rationale for ADR (not RFC):** This is the write-path boundary needed to make event sourcing real
in the runtime rather than only in storage components.

---

### ADR 0079: Live replay and checkpoint materialization authority → Status: Accepted

**Extends:** RFC 0009, ADR 0069, ADR 0071, ADR 0077

**Covers:**
- Canonical live replay path: checkpoint + event suffix
- Replay authority for `run`, `resume`, and recovery
- Acceptable checkpoint staleness
- Demotion of mutable snapshots from hot-path business truth
- Coherent checkpoint materialization ownership

**Rationale for ADR (not RFC):** This is the read-path counterpart to ADR 0078. It fixes who loads
canonical truth during live runtime.

---

### ADR 0080: OperatorService shell extraction and runtime ownership after event-sourced cutover → Status: Accepted

**Extends:** RFC 0009, ADR 0072, ADR 0073, ADR 0078, ADR 0079

**Covers:**
- Final responsibilities retained by `OperatorService`
- Responsibilities removed from `OperatorService` after event-sourced cutover
- Delegation boundary toward narrower application/runtime components
- Sunset rule for snapshot-era helper logic

**Rationale for ADR (not RFC):** This is the service-boundary decision needed to make RFC 0009
true by repository structure rather than by storage intent alone.

---

### ADR 0081: AdapterRuntime public protocol and transport ownership → Status: Accepted

**Extends:** RFC 0010, ADR 0070

**Covers:**
- Transport/subprocess ownership boundary
- Explicit async lifecycle contract for adapter runtimes
- `AdapterFact` as outward event surface
- Transport-scoped cancellation responsibility
- Relationship to current adapter implementations and helpers

**Rationale for ADR (not RFC):** This is the first narrow runtime contract beneath RFC 0010. It
defines the transport-focused layer without absorbing session semantics.

---

### ADR 0082: AgentSessionRuntime public protocol and single-live-session invariant → Status: Accepted

**Extends:** RFC 0010, ADR 0070, ADR 0081

**Covers:**
- Session ownership boundary
- One-live-session invariant
- Explicit discontinuity observability as `TechnicalFact`
- Session-scoped command ingress
- `AdapterFact` -> `TechnicalFact` normalization ownership

**Rationale for ADR (not RFC):** This is the session-layer runtime contract needed to make the
agent layer architecturally real rather than a thin adapter rename.

---

### ADR 0083: OperationRuntime coordination boundary and relationship to OperatorService → Status: Accepted

**Extends:** RFC 0010, RFC 0009, ADR 0080, ADR 0082

**Covers:**
- Per-operation concurrency and subscription ownership
- Relationship between `OperationRuntime` and `OperatorService`
- Dispatch into multiple agent session runtimes
- Handoff into translation and canonical event append boundaries
- Operation-scoped cancellation ownership

**Rationale for ADR (not RFC):** This is the operation-level runtime counterpart to ADR 0080. It
creates a concrete coordination boundary without collapsing back into one service object.

---

### ADR 0084: Async event-stream and cancellation semantics for runtime layers → Status: Accepted

**Extends:** RFC 0010, ADR 0081, ADR 0082, ADR 0083

**Covers:**
- Single-consumer semantics for live runtime event streams
- Buffering/backpressure expectations
- No-implicit-replay rule
- Terminal behavior after cancellation or lifecycle exit
- Explicit cancellation vs iterator abandonment

**Rationale for ADR (not RFC):** This is the protocol-behavior layer beneath the broader runtime
ownership choices in RFC 0010.

---

### ADR 0085: Retain operator-profile naming for operation-scoped project configuration → Status: Accepted

**Extends:** RFC 0010

**Covers:**
- Keep `operator-profile` as repository truth
- Clarify that retained naming remains operation-scoped in meaning
- Record the need to revise RFC 0010 accordingly
- Reject rename churn as part of the current runtime-architecture wave

**Rationale for ADR (not RFC):** This is a narrow naming-boundary correction that resolves the
current RFC/repository mismatch without reopening the rest of RFC 0010.

---

### ADR 0086: Event-sourced operation birth and snapshot-legacy retirement policy → Status: Implemented

**Extends:** RFC 0009, ADR 0077

**Covers:**
- All new operations are born `event_sourced`
- Canonical event-stream birth instead of snapshot-first operation creation
- Retirement of `snapshot_legacy` as a live runtime mode
- Explicit non-fallback treatment of pre-cutover snapshot operations

**Rationale for ADR (not RFC):** This is the first closure ADR beneath RFC 0009. It turns the
migration bridge from `ADR 0077` into a real cutover rule for live runtime truth.

---

### ADR 0087: Canonical operation loop and fact-to-domain append authority → Status: Accepted

**Extends:** RFC 0009, ADR 0078, ADR 0079, ADR 0083

**Covers:**
- One named live authority for replay, fact persistence, translation, append, and checkpoint
  materialization
- Serialized per-operation canonical append ownership
- Process-manager follow-up generation from the canonical loop
- Explicit prohibition on direct business mutation outside that authority

**Rationale for ADR (not RFC):** This is the live event-sourced loop boundary required to replace
procedural service mutation with one coherent business authority.

---

### ADR 0088: Main entrypoint cutover and final OperatorService shell boundary → Status: Implemented

**Extends:** RFC 0009, ADR 0080, ADR 0087

**Covers:**
- Event-sourced truth for `run` / `resume` / `recover` / `tick` / `cancel`
- Final shell-only responsibilities of `OperatorService`
- Removal of snapshot-era business ownership from the public application facade
- Delegation boundary into canonical runtime services

**Rationale for ADR (not RFC):** This is the final service-boundary closure decision needed to make
RFC 0009 true by repository behavior.

---

### ADR 0089: Runtime factory composition root and AgentAdapter retirement → Status: Accepted

**Extends:** RFC 0010, ADR 0081, ADR 0082, ADR 0083

**Covers:**
- Runtime-oriented composition root instead of `AgentAdapter` bootstrap truth
- Retirement of `AgentAdapter` from public runtime architecture
- ACP implementations expressed through runtime contracts rather than legacy adapter facade
- Factory/registry ownership for runtime instantiation

**Rationale for ADR (not RFC):** This is the composition-root closure decision needed to make
RFC 0010 true by repository wiring rather than parallel protocol scaffolding.

---

### ADR 0090: Single-process async runtime hosting and background-worker removal → Status: Accepted

**Extends:** RFC 0010, RFC 0009, ADR 0083, ADR 0089

**Covers:**
- Single-process async runtime hosting as target architecture
- Removal of background-worker canonical execution semantics
- Attached/background execution as scheduling modes within one runtime host
- Elimination of poll/collect worker lifecycle as repository truth

**Rationale for ADR (not RFC):** This is the hosting-model closure decision that prevents the
repository from retaining a second protocol family beneath the new runtime contracts.

---

### ADR 0091: Legacy runtime cleanup and document supersession after cutover → Status: Accepted

**Extends:** RFC 0009, RFC 0010, ADR 0086, ADR 0087, ADR 0088, ADR 0089, ADR 0090

**Covers:**
- Mandatory cleanup obligations after the closure cutover
- Removal of legacy runtime protocols, paths, and tests
- Supersession or annotation of stale architecture docs
- Explicit closure hygiene for RFC 0009/0010 acceptance

**Rationale for ADR (not RFC):** This is the cleanup ADR required to keep the closure wave honest
and prevent half-removed architecture truth from lingering.

---

### ADR 0061: Operator messages — context injection and window semantics

**Covers:**
- Operator messages vs typed commands: structural difference and rationale (free-text context
  injection vs state machine mutation)
- Window parameter: why N planning cycles, not persistent-until-answered
- Valid range: window = 0 means inject into next cycle only; no enforced minimum
- Drop event: why `operator_message.dropped_from_context` is explicit, not silent expiry
- Transparency: why active messages must be visible in `watch` and `dashboard`

---

### ADR 0062: Feature level in task hierarchy

**Extends:** ADR 0005

**Covers:**
- When a Feature is warranted vs direct Task decomposition (three criteria)
- Feature lifecycle states: `in_progress → ready_for_review → accepted | needs_rework`
- Authority model: why the review lifecycle is always user-facing; the brain cannot unilaterally
  mark a Feature as accepted
- Why four levels (Objective → Feature → Task → Subtask) rather than three or five

---

## Priority 3 — Normal

Useful for completeness; lower rediscovery risk.

### ADR 0063: Task graph structural invariants

**Covers:**
- Acyclicity: cycle detection fires on `add_dependency`; `dependency_cycle_detected` rejection
- Monotonicity: why dependencies cannot be silently removed
- Dependency removal requires reason: why the friction exists (audit trail, prevents casual removal
  of constraints the brain set deliberately)
- No self-dependency

---

### RFC 0007: Traceability layer model → Status: Accepted

**Action:** Document written. Transition from Proposed to Accepted.

**Covers:**
- Layer 0–5: what each contains, who writes it, who reads it
- Two-stream distinction: event log (machine, complete, atomic) vs narrative timeline (human/LLM,
  selective, semantic spans)
- Cross-layer navigation model: top-down drill-down path from `watch` to raw evidence
- `TypedRefs` vocabulary and `TraceRecord.refs` standard key table
- `FileTraceStore` contract (method → file mapping)
- `TraceBriefBundle` complete structure including `CommandBrief[]` and `EvaluationBrief[]`

---

## Priority 5 — Vision gap closure

Gap analysis (2026-04-02) identified seven gaps between VISION behavioral contracts and the
current implementation. Three are blocking (prevent claiming the stop-condition contract is met);
four are non-blocking (named contracts unmet or tech debt).

### ADR 0065: Operation run-time stop conditions → Status: Accepted

**Priority: Urgent — blocking gaps**

**Covers:**
- `timeout_seconds` enforcement: why the field existed without a loop check; how the started-at
  timestamp anchors wall-clock enforcement at each iteration boundary
- Budget/cost stop condition: why token tracking is a prerequisite for enforcement; what fields
  accumulate cost (provider response → `OperationState`); why hard budget stop is deferred until
  tracking exists
- Stop condition enumeration: the six conditions from VISION and which are fully enforced vs.
  partially implemented vs. absent; rationale for the current state

**Rationale for single ADR:** All three stop conditions (iteration, timeout, budget) share one
enforcement point (`_drive_state` loop boundary). The decision to implement timeout now and defer
budget until tracking infrastructure exists is a single adjudication, not three separate ones.

---

### ADR 0066: `stop_turn` task-addressing model → Status: Accepted

**Priority: High — blocking for multi-session operations**

**Covers:**
- Why `stop_turn` addresses a turn through its task, not through a session id: session ids are
  internal routing artefacts; the user's mental model is tasks, not sessions
- `--task` flag semantics: how the task id resolves to the bound session; what happens if the task
  is not in `RUNNING` state (`stop_turn_invalid_state` rejection with actual state in message)
- Multi-session motivation: in single-session operations, a taskless `stop_turn` is unambiguous;
  as multi-session becomes the common case, task-addressed targeting is required for correctness

---

### ADR 0067: `patch_*` command rejection model → Status: Accepted

**Priority: Normal — non-blocking contract gap**

**Covers:**
- Three rejection conditions for `patch_*` commands: `operation_terminal`, `invalid_payload`,
  `concurrent_patch_conflict`
- Why `concurrent_patch_conflict` matters: silent overwrite of a pending patch loses the first
  user intent; the second patch should be rejected, not silently applied
- Detection approach: check `pending_replan_command_ids` at drain time for same-type patch
  already pending; reject with `concurrent_patch_conflict`
- Why soft enforcement (event + rejection) rather than hard queue serialization

---

### ADR 0068: `NEEDS_HUMAN` operation status alignment → Status: Accepted

**Priority: Normal — naming contract gap**

**Covers:**
- VISION's `NEEDS_HUMAN` macro-state vs. current `OperationStatus.BLOCKED` value: what the VISION
  specifies ("overlay condition: scheduler keeps working, but gated on blocking attention") vs.
  what the code currently expresses
- Why the rename matters: `BLOCKED` is ambiguous — it also describes dependency-blocked tasks in
  `TaskStatus`; `NEEDS_HUMAN` is unambiguous and user-intent-named
- Migration: `OperationStatus.BLOCKED → NEEDS_HUMAN`; `TaskStatus.BLOCKED` remains (different
  semantic); event log compatibility — `operation.status.changed` payload values change

**Rationale for ADR (not silent rename):** The rename touches the event log format (persisted),
CLI output, tests, and any external consumers. The provenance record prevents the rename from
looking arbitrary to future contributors.

---

## Priority 4 — Deferred

Not for near-term implementation. Exists to record the decision to defer and the criteria for
revisiting.

### RFC 0008: Operator workspace (Status: Deferred — Written)

**Rationale:** The Operator Workspace concept is documented in VISION.md as a Future Direction
with explicit activation criteria. This RFC formalises that deferral with full governance design
so the criteria are not relitigated from scratch when they are met.

**Covers:**
- Why brain is currently read-only (positions this as the baseline for the workspace promotion)
- Four activation criteria (proposal backlog bottleneck, new involvement level with write authority,
  write governance machinery, gitignore-by-default)
- Governance contract: workspace writes as domain events (`workspace.document.written`,
  `workspace.document.updated`), visible in `trace`, revertable via `workspace revert`
- Relationship to `document_update_proposal`: workspace is a promotion of the brain from proposer
  to author, not a replacement for the proposal pathway

---

## Completed

| Document | Title | Date |
|---|---|---|
| RFC 0005 | Data directory layout and profile storage | 2026-04-01 |
| RFC 0006 | Event model | 2026-04-02 |
| ADR 0058 | Traceability brief layer completeness | 2026-04-02 |
| ADR 0059 | Brain — project file system boundary | 2026-04-02 |
| ADR 0060 | Project-scope MemoryEntry | 2026-04-02 |
| ADR 0061 | Operator messages — context injection and window semantics | 2026-04-02 |
| ADR 0062 | Feature level in task hierarchy | 2026-04-02 |
| ADR 0063 | Task graph structural invariants | 2026-04-02 |
| RFC 0007 | Traceability layer model | 2026-04-02 |
| ADR 0064 | Memory strata and scope model | 2026-04-02 |
