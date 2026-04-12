# Design And ADR Repo-Truth Status - 2026-04-11

Internal audit note. Not end-user documentation.

## Purpose

This note audits the committed design corpus against current repository truth.

It does three things:

- enumerates the current design corpus under `design/`
- maps active design authority and ADRs to implemented code, tests, and public docs
- records concrete gaps where accepted design is still ahead of implementation truth

This is intentionally evidence-first. Acceptance of an ADR does not count as implementation.

## Audit Scope

Audited inputs:

- repository entry and policy guidance: `README.md`, `policies/README.md`,
  `policies/engineering.md`, `policies/documentation.md`, `policies/architecture.md`,
  `policies/verification.md`
- active design authority: `design/README.md`, `design/VISION.md`, `design/ARCHITECTURE.md`,
  `design/*-UX-VISION.md`, `design/AGENT-INTEGRATION-VISION.md`, `design/WORKFLOW-UX-VISION.md`,
  `design/RFC-ADR-ROADMAP.md`, `design/BACKLOG.md`, `design/user-stories-and-surface-model.md`
- decision corpus: all files under `design/adr/`
- supporting design history: RFCs, implementation plans, critiques, brainstorm notes, and
  `design/internal/`
- implementation truth: `src/agent_operator/`
- verification truth: `tests/`
- public-doc truth: `docs/`

Repository counts at audit time:

- top-level design markdown files: `22`
- ADR files: `144`
- RFC files: `21`
- brainstorm files: `19`
- internal design-note files: `27`
- total markdown files under `design/`: `236`

## Evidence Anchors

High-signal implementation anchors:

- `src/agent_operator/application/service.py`
- `src/agent_operator/application/drive/operation_drive.py`
- `src/agent_operator/application/operation_entrypoints.py`
- `src/agent_operator/application/operation_lifecycle.py`
- `src/agent_operator/application/commands/operation_control_state.py`
- `src/agent_operator/application/event_sourcing/`
- `src/agent_operator/application/runtime/`
- `src/agent_operator/application/queries/`
- `src/agent_operator/acp/`
- `src/agent_operator/adapters/`
- `src/agent_operator/cli/`
- `src/agent_operator/runtime/`
- `src/agent_operator/bootstrap.py`

High-signal verification anchors:

- `tests/test_application_structure.py`
- `tests/test_bootstrap.py`
- `tests/test_operator_service_shell.py`
- `tests/test_event_sourced_birth.py`
- `tests/test_event_sourced_command_application.py`
- `tests/test_event_sourced_operation_loop.py`
- `tests/test_event_sourced_replay.py`
- `tests/test_operation_entrypoints.py`
- `tests/test_operation_runtime.py`
- `tests/test_operation_traceability_service.py`
- `tests/test_operation_projections.py`
- `tests/test_operation_dashboard_queries.py`
- `tests/test_operation_project_dashboard_queries.py`
- `tests/test_cli.py`
- `tests/test_project_cli.py`
- `tests/test_policy_cli.py`
- `tests/test_policy_coverage.py`
- `tests/test_policy_coverage_cli.py`
- `tests/test_tui.py`
- `tests/test_tui_session_view.py`
- `tests/test_tui_session_summary_jump_to.py`
- `tests/test_acp_session_runner.py`
- `tests/test_acp_permissions.py`
- `tests/test_adapter_runtime.py`
- `tests/test_agent_session_runtime.py`
- `tests/test_runtime_bindings.py`
- `tests/test_codex_acp_adapter.py`
- `tests/test_claude_acp_adapter.py`
- `tests/test_opencode_acp_adapter.py`

## Status Legend

- `implemented`: current code, tests, and public/internal docs match the design closely enough that
  no material contradiction surfaced in this audit
- `partial`: meaningful implementation exists, but the design still runs ahead of current repo truth
- `planned`: design intent exists but is not yet a committed implementation target in current code
- `historical`: superseded or process-only design history retained for provenance, not a live
  implementation target

## Executive Summary

- The repository broadly matches the current design corpus on package shape, ACP adapter layering,
  CLI/TUI supervisory surfaces, and the extracted application-service wave.
- The strongest still-open architecture gap is the `RFC 0009` closure tail: current operations are
  born `event_sourced`, but the live loop still persists mutable `OperationState` snapshots through
  `save_operation()` and still routes some live behavior outside the canonical event-append path.
- The next strongest gap is now sharper than the earlier note stated: `ADR 0104` is not only
  implementation-partial by repo truth, it also still uses the old single `Status` header even
  though repository policy now requires separate `Decision Status` and `Implementation Status`
  fields for ADRs. Its present-tense closure language overclaims relative to current code.
- The main product/runtime gap after that is the attached-live continuity tail tracked by
  `ADR 0143`: targeted metadata and stale-wait fixes are real, but current verification evidence
  still does not close repeated end-to-end attached-live progression without manual recovery.
- The design corpus has a governance defect: ADR numbers `0028`, `0030`, and `0031` are reused by
  multiple different documents. `design/BACKLOG.md` already records this correctly.

## Design Corpus Inventory

### Active Design Authority

| Document | Role | Repo-truth status | Notes |
|---|---|---|---|
| `design/README.md` | corpus index | implemented | Accurately describes `design/` as design authority/history, separate from `docs/`. |
| `design/VISION.md` | product and behavioral authority | implemented with open tails | Core thesis, stop-policy, CLI/TUI mental model, memory model, and transparency claims match current code; some newer UX slices remain partial. |
| `design/ARCHITECTURE.md` | structural authority | implemented with explicit partial sections | Current package shape and runtime boundaries largely match; its own partial-status language is honest about shell-thinning and event-sourcing tails. |
| `design/CLI-UX-VISION.md` | CLI intent | partial | Current CLI family exists and is broad, but shell-summary grammar/help/example closure is still incomplete in the `ADR 0132` to `ADR 0134` tranche. |
| `design/TUI-UX-VISION.md` | TUI intent | partial | Fleet -> operation -> session -> forensic path and attention flows are implemented; later density/filter/focus refinements remain planned/partial. |
| `design/WORKFLOW-UX-VISION.md` | workspace/project lifecycle intent | implemented | `init`, project-profile lifecycle, fleet/project surfaces, and history/entry workflows have concrete code/tests/docs. |
| `design/DOCS-UX-VISION.md` | docs IA intent | implemented | `README.md`, `docs/`, `design/`, and `policies/` are correctly separated in current repo truth. |
| `design/CONFIG_UX_VISION.md` | config/runtime-state storage direction | partial/planned | The config-vs-state split is visible, but the file itself is still explicitly planned and overstates some pending storage evolution. |
| `design/AGENT-INTEGRATION-VISION.md` | agent-facing integration strategy | planned/partial | CLI and JSONL/event-file surfaces exist; MCP/programmatic surfaces remain design direction rather than current product truth. |
| `design/NL-UX-VISION.md` | natural-language operator UX | planned | No public NL surface matching this document was found in current CLI/TUI/app code. |
| `design/RFC-ADR-ROADMAP.md` | decision backlog/provenance roadmap | partial | Still useful as planning input, but parts are stale relative to current implemented ADR wave and should not be treated as current product truth without re-checking code. |
| `design/BACKLOG.md` | explicit open cleanup fronts | implemented | Correctly records the two highest-signal open issues: RFC 0009 closure tail and ADR numbering hygiene. |
| `design/user-stories-and-surface-model.md` | product companion / UX framing | partial historical companion | Still directionally consistent, but newer CLI/TUI implementation details have moved beyond this document. Useful context, not canonical authority over current interactions. |
| `design/VISION_v2.md` | forward-looking next-stage vision | historical/forward-looking | Explicitly marked as non-authoritative for current architecture. |

### Design-Process And Supporting Documents

These documents were enumerated and classified, but they are not all live implementation contracts.

| Category | Count | Audit treatment | Current repo-truth reading |
|---|---:|---|---|
| `design/rfc/` | 21 | supporting specification/history | Important for provenance; some remain active inputs, especially event-sourcing and CLI-output RFCs. |
| implementation plans at `design/*.md` | 6 | supporting implementation history | Useful for open-tail reading; not canonical by themselves. |
| critique docs at `design/*.md` | 6 | editorial/process history | Historical critique artifacts, not direct implementation targets. |
| `design/brainstorm/` | 19 | exploratory only | Enumerated for completeness; no direct conformance audit beyond noting they are non-binding. |
| `design/internal/` | 27 | internal status/process notes | Useful recent repo-truth evidence; not end-user nor top-level design authority. |

### Supporting Design-Doc Index

Enumerated supporting docs under `design/` outside `design/adr/`:

- `design/AGENT-INTEGRATION-VISION.md`
- `design/ARCHITECTURE.md`
- `design/BACKLOG.md`
- `design/CLI-UX-VISION.md`
- `design/CONFIG_UX_VISION.md`
- `design/DOCS-UX-VISION.md`
- `design/NL-UX-VISION.md`
- `design/README.md`
- `design/RFC-ADR-ROADMAP.md`
- `design/TUI-UX-VISION.md`
- `design/VISION.md`
- `design/VISION_v2.md`
- `design/WORKFLOW-UX-VISION.md`
- `design/adr-0104-implementation-plan.md`
- `design/adr-0105-implementation-plan.md`
- `design/agent-turn-summary-implementation-plan.md`
- `design/attached-turn-recovery-implementation-plan.md`
- `design/critique-arch-round-1.md`
- `design/critique-arch-round-2.md`
- `design/critique-arch-round-3.md`
- `design/critique-round-1.md`
- `design/critique-round-2.md`
- `design/critique-round-3.md`
- `design/resident-reconciler-implementation-plan.md`
- `design/user-stories-and-surface-model.md`

Supporting subtrees:

- `design/rfc/` contains `21` markdown files
- `design/brainstorm/` contains `19` markdown files
- `design/internal/` contains `27` markdown files

## Concrete Gap List

### Gap 1: Live runtime is still mixed snapshot/event-sourced

Why this is real:

- `design/BACKLOG.md` records that `run` / `resume` / `recover` / `cancel` are not yet
  event-sourced-only by repo truth.
- `src/agent_operator/application/drive/operation_drive.py` still performs repeated
  `save_operation()` writes on mutable `OperationState`.
- `src/agent_operator/application/service.py` still persists snapshot-shaped state in public
  run-path entrypoints.
- `src/agent_operator/application/commands/operation_commands.py` only routes a subset of
  operation-target commands through `EventSourcedCommandApplicationService`; attention answers,
  stop-turn, and stop-operation still mutate in-memory state directly and then persist snapshots
  through `OperationControlStateCoordinator.persist_command_effect_state()`.

ADRs affected:

- `ADR 0077`
- `ADR 0078`
- `ADR 0079`
- `ADR 0086`
- `ADR 0087`
- `ADR 0088`
- `ADR 0091`

Execution slices:

1. Route the remaining live command paths through `EventSourcedCommandApplicationService`.
2. Remove snapshot-first business writes from `OperationDriveService` and adjacent collaborators.
3. Make event stream plus checkpoint the only canonical live write path for `event_sourced`
   operations.
4. Reclassify event-sourcing ADRs honestly once the runtime is actually event-sourced-only.

### Gap 2: `ADR 0104` still overstates shell completion and does not follow current ADR status policy

Why this is real:

- `policies/documentation.md` and `policies/architecture.md` require ADRs to expose both
  `Decision Status` and `Implementation Status`; `design/adr/0104-top-application-control-layer-boundary-completion-after-shell-thinning.md`
  still uses a single `## Status` section.
- That ADR currently claims repo truth is materially matched and even `verified` as a shell-sized
  shape, but `src/agent_operator/application/service.py` still constructs
  `AttachedSessionRuntimeRegistry`, `LoadedOperation`, `OperationRuntimeContext`,
  `AttachedTurnService`, `SupervisorBackedOperationRuntime`, and process-manager state inside the
  facade constructor.
- `design/ARCHITECTURE.md` is already more accurate than the ADR here: it still calls the top
  application/control layer `partial`.
- Existing tests such as `tests/test_operator_service_shell.py` verify useful outcomes, but they do
  not establish the stronger claim that `OperatorService` is only a thin shell over injected
  collaborators.

ADRs affected:

- `ADR 0099`
- `ADR 0100`
- `ADR 0101`
- `ADR 0102`
- `ADR 0104`

Execution slices:

1. Rewrite `ADR 0104` to use `Decision Status` plus `Implementation Status` and make its skim-safe
   status language match current code truth.
2. Stop constructing operation-local mechanics inside `OperatorService`; inject them from
   bootstrap/composition only.
3. Narrow `OperationRuntimeContext` into a smaller named capability boundary and remove remaining
   shell-local runtime assembly.
4. Add verification that asserts shell-only ownership boundaries rather than only behavioral
   outcomes.

### Gap 3: Attached-live continuity is improved but not fully closed

Why this is real:

- `ADR 0143` is still partial by its own implementation-status language.
- Current tests cover recovery metadata and stale-wait truth, but not full end-to-end attached-live
  progression across repeated background turns without manual intervention.
- `ADR 0143` itself explicitly records `not yet verified` for full end-to-end attached-live
  progression across repeated background turns without manual recovery.

ADRs affected:

- `ADR 0041`
- `ADR 0042`
- `ADR 0044`
- `ADR 0046`
- `ADR 0057`
- `ADR 0135`
- `ADR 0143`

Execution slices:

1. Add end-to-end attached-live progression coverage across repeated background turns without
   manual `resume`.
2. Close the remaining scheduler bridge from persisted wakeups to automatic next-step progression.
3. Preserve effective adapter runtime settings across repeated attached re-delegations.

### Gap 4: Newer shell/live-follow command family is only partially closed

Why this is real:

- `ADR 0132`, `ADR 0133`, and `ADR 0134` are still partial.
- Command existence is no longer the issue; family-level help/output/docs closure is.

ADRs affected:

- `ADR 0130`
- `ADR 0132`
- `ADR 0133`
- `ADR 0134`

Execution slices:

1. Finish `RFC 0014`-aligned shell-summary grammar for `status`, `watch`, and workspace lifecycle
   help/docs.
2. Normalize action-line wording and current-state explanation across the one-operation family.
3. Add broader docs/examples coverage, not only tests.

### Gap 5: Planned TUI supervisory refinements remain open by design, not by surprise

Why this is real:

- `ADR 0127`, `ADR 0128`, `ADR 0129`, and `ADR 0131` still declare planned work.
- Existing TUI and projection surfaces are real; the remaining work is refinement, not missing
  foundations.

Execution slices:

1. Cross-level filter persistence and focus carryover.
2. Richer pane-density and information-architecture modes.
3. Cross-operation supervisory snapshot convergence for CLI/TUI.

### Gap 6: ADR numbering is ambiguous

Why this is real:

- Multiple different ADR files reuse numbers `0028`, `0030`, and `0031`.
- That weakens design provenance and makes later references ambiguous.

Execution slices:

1. Decide renumbering strategy.
2. Rewrite inbound references.
3. Add a simple ADR-number uniqueness check in tests or lint.

## Recommended Next Implementation Slice

Single best next bounded slice:

1. Cut the live operation loop over to a single canonical write path for `event_sourced`
   operations by removing direct `save_operation()` mutation checkpoints from
   `OperationDriveService` and routing command-effect persistence through canonical event append
   plus checkpoint refresh.

Why this is the best next slice:

- It closes the highest-leverage architectural contradiction still recorded in `design/BACKLOG.md`
  and across `ADR 0077` through `ADR 0091`.
- It unlocks honest status closure for multiple accepted/implemented ADRs at once instead of only
  improving wording.
- It reduces the remaining shell/control ambiguity indirectly, because much of the surviving top
  layer complexity still exists to support mixed snapshot/event-sourced truth.
- It is narrower and more evidence-driven than a full "finish shell thinning" wave: the target
  seam is concrete (`OperationDriveService` write path plus command application path), and the
  repository already has the event-store/checkpoint primitives needed for it.

## ADR Status Matrix

Shared evidence anchors used throughout this matrix:

- domain/runtime model: `src/agent_operator/domain/`, `src/agent_operator/runtime/`
- application/service boundaries: `src/agent_operator/application/`
- adapters and ACP substrate: `src/agent_operator/acp/`, `src/agent_operator/adapters/`
- delivery surfaces: `src/agent_operator/cli/`, `docs/reference/cli.md`, `docs/tui-workbench.md`
- broad test evidence: the `tests/test_*.py` files listed in Evidence Anchors above

### Core Brain, Goal, Memory, And Result ADRs

- `ADR 0001` - historical. Superseded by later runtime-protocol and adapter-runtime ADRs.
- `ADR 0002` - implemented. Structured agent progress/result core exists in domain models and agent-result flow.
- `ADR 0003` - implemented. Brain decisions resolve to structured actions through domain/provider/application mapping.
- `ADR 0004` - implemented. ACP is the Codex integration boundary in current adapters.
- `ADR 0005` - partial. Long-lived objective and memory model exist, but end-to-end memory workflow verification is lighter than newer CLI/TUI coverage.
- `ADR 0006` - partial. Freshness and invalidation are modeled; broader workflow closure remains open.
- `ADR 0007` - implemented. Wakeup/preemption semantics exist in runtime and command flow.
- `ADR 0008` - implemented. Attached mode is the primary runtime surface in code/docs.
- `ADR 0009` - implemented. Explicit brain failure action exists in decision/result shapes.
- `ADR 0010` - implemented. Codex ACP execution policy is exposed through config and adapter behavior.
- `ADR 0011` - implemented. Condensed codex session-log / forensic surface exists through unified log/debug flows.
- `ADR 0012` - implemented. Objective and harness instructions remain separate in goal/entrypoint flow.

### Command, Attention, Task, And Stop-Policy ADRs

- `ADR 0013` - implemented. Operation command inbox/envelope semantics exist in domain/runtime/application layers.
- `ADR 0014` - implemented. Deterministic command application remains distinct from planning/replanning.
- `ADR 0015` - implemented. Scheduler pause semantics for attached runs exist.
- `ADR 0016` - implemented. Attention taxonomy and answer-routing behavior exist in command/TUI/CLI paths.
- `ADR 0017` - implemented. Involvement levels and autonomy policy are represented in policy/profile/runtime behavior.
- `ADR 0018` - implemented. Project-profile schema and override behavior exist.
- `ADR 0019` - implemented. Policy memory and promotion workflow exist in policy/runtime/CLI surfaces.
- `ADR 0020` - implemented. Live attached transparency surface exists in CLI/TUI/traceability output.
- `ADR 0021` - implemented. Task, memory, and artifact CLI surfaces exist.
- `ADR 0022` - implemented. Cross-operation agenda surface exists.
- `ADR 0023` - implemented. Stop-active-attached-agent-turn behavior exists.
- `ADR 0024` - implemented. Effective control-context CLI surface exists.
- `ADR 0025` - implemented. Project-profile init CLI surface exists.
- `ADR 0026` - implemented. Live one-operation dashboard surface exists.
- `ADR 0027` - implemented. Live fleet dashboard surface exists.
- `ADR 0028` `condensed-claude-session-log-view` - implemented in spirit but numbering is ambiguous.
- `ADR 0028` `explicit-answer-time-policy-promotion` - implemented in policy mutation flow but numbering is ambiguous.
- `ADR 0028` `policy-applicability-and-matching-semantics` - implemented but numbering is ambiguous; see also `ADR 0029`.
- `ADR 0029` - implemented. Policy applicability matching exists in domain/runtime/CLI coverage.
- `ADR 0030` `condensed-claude-session-log-view` - historical duplicate/provenance problem.
- `ADR 0030` `live-project-dashboard-cli-surface` - implemented but numbering is ambiguous.
- `ADR 0030` `policy-coverage-and-explainability` - implemented but numbering is ambiguous.
- `ADR 0031` `deterministic-policy-gap-guardrail` - implemented but numbering is ambiguous.
- `ADR 0031` `installed-cli-launch-mode-and-local-project-profile-discovery` - implemented but numbering is ambiguous.
- `ADR 0032` - partial. Goal-patching slice exists in design history but is not a strongly closed current public-product front.
- `ADR 0034` - implemented. Standard coding-agent tool capability framing matches current adapters.
- `ADR 0035` - implemented. Project profiles may carry default objective.
- `ADR 0036` - partial. Constraint-patching slice is not a contradicted design, but it is not one of the best-closed public surfaces either.
- `ADR 0037` - implemented. Stop-operation command slice exists.
- `ADR 0038` - implemented. CLI remains authority and TUI is supervisory over shared application/query paths.

### Runtime Recovery, ACP, And Permission ADRs

- `ADR 0039` - historical. Superseded by later wakeup/runtime-hosting ADRs.
- `ADR 0040` - historical/absorbed. Context-budget design intent was partially folded into current provider/prompting flow.
- `ADR 0041` - partial. Turn-summary behavior exists, but attached continuity closure is still open.
- `ADR 0042` - partial. Timeout/recovery behavior exists, but full attached-live closure remains open.
- `ADR 0043` - implemented. Claude ACP effort is exposed through environment/config behavior.
- `ADR 0044` - partial. Force-recovery surface exists, but larger attached-live closure remains open.
- `ADR 0045` - implemented. Claude ACP rate-limit cooldown behavior exists.
- `ADR 0046` - partial. Timed wakeups/auto-resume are real, but full repeated attached-live progression remains open.
- `ADR 0047` - historical. Superseded by later inline-wakeup attached semantics.
- `ADR 0048` - implemented. ACP substrate seam is operator-owned below runtime contracts.
- `ADR 0049` - implemented. Direct `claude_code` adapter is retired in favor of ACP-backed surfaces.
- `ADR 0050` - implemented. Shared ACP session runner exists beneath vendor adapters.
- `ADR 0051` - implemented. Shared ACP permission normalization exists.
- `ADR 0052` - implemented. Session/execution lifecycle authority is aligned with shared runner/runtime layering.
- `ADR 0053` - implemented. LLM-mediated ACP permission decisions exist with deterministic guardrails.
- `ADR 0054` - implemented. Recoverable ACP disconnects and session reattach behavior exist.
- `ADR 0055` - implemented. Background ACP progress snapshots and notification logging exist.
- `ADR 0056` - implemented. ACP SDK stdio reader-limit handling exists.
- `ADR 0057` - partial. Attached-mode inline wakeup auto-resume exists, but `ADR 0143` remains open.
- `ADR 0058` - implemented. Traceability brief completeness is materially present in query/traceability surfaces.
- `ADR 0059` - partial. Brain remains read-only on project filesystem, but associated promotion/document-update workflow depth is not fully closed.
- `ADR 0060` - partial. Project-scope memory exists, but broader end-to-end workflow verification remains lighter than newer operational surfaces.
- `ADR 0061` - partial. Operator-message context window semantics exist, but deserve stronger end-to-end evidence.
- `ADR 0062` - implemented. Feature-level task hierarchy exists.
- `ADR 0063` - implemented. Task-graph structural invariants exist in domain/runtime/projector logic.
- `ADR 0064` - partial. Memory-strata/scope model exists but is not one of the strongest closed workflow fronts.
- `ADR 0065` - implemented. Run-time stop conditions are explicit in lifecycle/runtime flow.
- `ADR 0066` - implemented. `stop_turn` addressing model exists.
- `ADR 0067` - implemented. Patch-command rejection model exists.
- `ADR 0068` - implemented. `NEEDS_HUMAN` operation status exists.

### Event-Sourcing, Command-Bus, And Canonical-Truth ADRs

- `ADR 0069` - implemented as building block. Event-store and checkpoint-store contracts exist.
- `ADR 0070` - implemented as building block. Fact store and fact translator contracts exist.
- `ADR 0071` - implemented as building block. Projector and reducer slices exist.
- `ADR 0072` - implemented. Process-manager policy/builder boundary exists.
- `ADR 0073` - partial. Command bus and planning triggers exist, but full live runtime truth is still mixed.
- `ADR 0074` - partial. Cleanup wave is directionally realized, but event-sourced-only closure is not complete.
- `ADR 0076` - partial. Command-file compatibility retirement is largely realized, but mixed live truth still leaks older-era behavior.
- `ADR 0077` - partial. Event-sourced cutover is real for birth/provenance, not yet for the entire live loop.
- `ADR 0078` - partial. Single-writer append boundary exists in services, but live loop still performs snapshot-shaped business writes.
- `ADR 0079` - partial. Replay/checkpoint authority exists, but not yet as sole live canonical truth.
- `ADR 0080` - partial. Shell extraction is materially advanced, not complete.
- `ADR 0081` - implemented. `AdapterRuntime` public protocol and transport ownership exist.
- `ADR 0082` - implemented. `AgentSessionRuntime` protocol and single-live-session invariant exist.
- `ADR 0083` - implemented. `OperationRuntime` coordination boundary exists, though adjacent shell thinning remains partial.
- `ADR 0084` - implemented. Async event-stream/cancellation semantics for runtime layers exist.
- `ADR 0085` - implemented. Operator-profile naming is retained for operation-scoped project configuration.
- `ADR 0086` - partial. Event-sourced operation birth exists, but snapshot-legacy retirement is not complete.
- `ADR 0087` - partial. Canonical operation loop and fact-to-domain append authority are directionally real, but mixed live persistence keeps this from full closure.
- `ADR 0088` - partial. Main entrypoint cutover happened, final shell boundary not yet complete.
- `ADR 0089` - implemented. Runtime-factory composition-root and AgentAdapter retirement direction are reflected in current bootstrap/runtime bindings.
- `ADR 0090` - implemented. Single-process async runtime hosting is current truth.
- `ADR 0091` - partial. Legacy cleanup/document supersession is incomplete while mixed live truth remains.
- `ADR 0092` - implemented. Policy, budget, and runtime hints are split.

### CLI Taxonomy, Public Surface, And Workflow ADRs

- `ADR 0093` - implemented. CLI taxonomy and default operator entry behavior exist.
- `ADR 0094` - implemented. `run` / `init` / `project create` workflow and project-profile lifecycle exist.
- `ADR 0095` - implemented. Operation reference resolution and command addressing exist.
- `ADR 0096` - implemented. One-operation control and summary surface exists.
- `ADR 0097` - implemented. Forensic log unification and debug-surface relocation exist.
- `ADR 0098` - implemented. History ledger and `history` contract exist.
- `ADR 0099` - partial. Workflow-authority extraction is materially advanced, not complete.
- `ADR 0100` - partial. Pluggable operator-policy boundary exists, but adjacent shell/runtime ownership is not fully closed.
- `ADR 0101` - partial. Ideal application organization is broadly visible, but not fully landed.
- `ADR 0102` - partial. Explicit lifecycle coordinator exists, but surrounding authority placement is not fully closed.
- `ADR 0103` - partial-to-implemented. Dishka composition root is real in bootstrap; remaining non-use in core constructors is deliberate.
- `ADR 0104` - partial. Top application/control-layer completion remains an active gap.
- `ADR 0105` - partial-to-implemented. Lint normalization wave is documented as complete, but this is a quality-wave/process ADR, not a central product gap.
- `ADR 0106` - implemented. Public docs and design corpus are properly separated.
- `ADR 0107` - implemented. Repository module hierarchy policy matches current package shape.
- `ADR 0108` - implemented with governance caveat. Legacy compatibility retirement fronts are directionally honored; ADR numbering duplication still harms provenance hygiene.
- `ADR 0109` - implemented-to-partial. Workbench-v2 direction is materially realized in current TUI.
- `ADR 0110` - implemented. TUI hierarchy and zoom contract exist.
- `ADR 0111` - implemented. TUI signal and attention propagation contract exists.
- `ADR 0112` - mostly implemented. Action parity and safety behavior are present, though not every path was re-opened in this audit.
- `ADR 0113` - implemented. TUI data substrate and refresh model exist.
- `ADR 0114` - implemented. CLI delivery substrate extraction exists before TUI refinement.
- `ADR 0115` - implemented. Fleet workbench projections and CLI/TUI parity substrate exist.
- `ADR 0116` - implemented. CLI parity gaps identified by that ADR are largely closed in current surface set.
- `ADR 0117` - implemented. Public session-scope CLI surface exists.
- `ADR 0118` - implemented-to-partial. Supervisory implementation tranche is materially live; later refinements remain open.
- `ADR 0119` - implemented. CLI main decomposition below 500 lines is reflected in current package split.
- `ADR 0120` - implemented. CLI submodule boundary rules match package reality.
- `ADR 0121` - implemented. Application submodule boundary rules match package reality.
- `ADR 0122` - implemented. Project operator-state clear command exists.
- `ADR 0123` - implemented. CLI package submodules and subpackage shape match current code.
- `ADR 0126` - implemented-to-partial. Shared supervisory activity summary is real; richer future signals remain open.
- `ADR 0127` - planned. Cross-level filtering/focus persistence is not yet fully implemented.
- `ADR 0128` - planned. Information-architecture-beyond-classic-zoom refinements remain future work.
- `ADR 0129` - planned. Pane authority and density modes remain future work.
- `ADR 0130` - partial. Blocking/non-blocking attention UX is real but broader family closure remains open.
- `ADR 0131` - planned. Cross-operation supervisory snapshot surface remains a future refinement.
- `ADR 0132` - partial. Workspace shell and lifecycle commands exist; help/output/docs family closure remains open.
- `ADR 0133` - partial. One-operation summary/control surface exists; wording/help/examples still need closure.
- `ADR 0134` - partial. One-operation live-follow surface exists; grammar/help/docs closure remains open.
- `ADR 0135` - partial. Session snapshot and live-follow surface is real but not fully closed.
- `ADR 0136` - implemented. Transcript, retrospective, and ledger surfaces exist.
- `ADR 0137` - implemented. Operation detail and inventory surfaces exist.
- `ADR 0138` - implemented. Project-profile inventory and inspection surfaces exist.
- `ADR 0139` - implemented. Project dashboard and entry surface exist.
- `ADR 0140` - implemented. Policy inventory and explainability surfaces exist.
- `ADR 0141` - implemented. Policy mutation and attention-promotion workflow exist.
- `ADR 0142` - implemented. Hidden debug/recovery/forensic inspection surfaces exist.
- `ADR 0143` - partial. Attached-live continuation and wakeup reconciliation are improved but not fully closed end-to-end.

## RFC And Supporting-Doc Notes

High-signal supporting docs whose status matters to current implementation truth:

- `RFC 0006` (`design/rfc/0006-event-model.md`) - active supporting spec. Current event taxonomy and event-sourcing helpers broadly align.
- `RFC 0007` (`design/rfc/0007-traceability-layer-model.md`) - active supporting spec. Traceability/query surfaces broadly align.
- `RFC 0008` (`design/rfc/0008-operator-workspace.md`) - active supporting spec. Workspace/project lifecycle direction is mostly implemented.
- `RFC 0009` (`design/rfc/0009-operation-event-sourced-state-model-and-runtime-architecture.md`) - partial and still the main open architecture front.
- `RFC 0010` (`design/rfc/0010-async-runtime-lifecycles-and-session-ownership.md`) - broadly aligned with current runtime boundaries.
- `RFC 0011` and `RFC 0012` - broadly aligned. Delivery package shape and migration tranche match current `cli/` organization.
- `RFC 0014` - active output-contract reference. Still relevant to the remaining closure work in `ADR 0132` through `ADR 0134`.

Supporting documents best treated as historical/process artifacts rather than current implementation contracts:

- critique rounds under `design/critique-*.md` and `design/rfc/critique-*.md`
- implementation plans once their wave is substantially landed
- brainstorm notes under `design/brainstorm/`
- forward-looking `design/VISION_v2.md`

## Duplicate ADR Numbers

Current corpus defect:

- `0028` is reused by:
  - `0028-condensed-claude-session-log-view.md`
  - `0028-explicit-answer-time-policy-promotion.md`
  - `0028-policy-applicability-and-matching-semantics.md`
- `0030` is reused by:
  - `0030-condensed-claude-session-log-view.md`
  - `0030-live-project-dashboard-cli-surface.md`
  - `0030-policy-coverage-and-explainability.md`
- `0031` is reused by:
  - `0031-deterministic-policy-gap-guardrail.md`
  - `0031-installed-cli-launch-mode-and-local-project-profile-discovery.md`

This does not block code execution, but it does block precise design provenance and should be
treated as real design debt.

## Highest-Value Next Slice

Make the live runtime event-sourced-only for `event_sourced` operations.

Why this is the best next slice:

- It closes the largest remaining mismatch between accepted architecture and running code.
- It removes the biggest source of ambiguity already recorded in `design/BACKLOG.md`.
- It unlocks more honest closure for `ADR 0077`, `ADR 0078`, `ADR 0079`, `ADR 0086`, `ADR 0087`,
  `ADR 0088`, and `ADR 0091`.
- It is higher leverage than more CLI/TUI polish because it fixes the canonical truth model under
  every surface.

Recommended tranche:

1. Route live command mutation through `EventSourcedCommandApplicationService`.
2. Remove snapshot-first `save_operation()` business writes from `OperationDriveService`.
3. Persist only event append plus checkpoint refresh as canonical live truth for `event_sourced`
   operations.
4. Add end-to-end tests proving `run` / `resume` / `recover` / `cancel` stay coherent without
   snapshot-canonical fallback.
