# 2026-04-11 Design Corpus Inventory Status

## Scope

This is a lightweight, evidence-based inventory pass requested from the repository root. It covers:

1. `AGENTS.md` requirements that directly affect execution of this slice
2. the committed design corpus inventory in `design/`
3. the most relevant current code, test, and public-doc touchpoints for each design-corpus family
4. immediately verifiable gaps observed from the tree on 2026-04-11

This note does not attempt claim-by-claim implementation validation for every ADR.

## Execution Requirements From `AGENTS.md`

The following repository rules materially constrained how this pass was executed:

- Start with the canonical reading path:
  - `README.md`
  - `policies/README.md`
  - `design/VISION.md`
  - `design/ARCHITECTURE.md`
  - `STACK.md`
  - relevant `design/adr/`
- Keep the operator loop central when interpreting architecture and code placement.
- Prefer small, explicit abstractions and protocol-oriented boundaries over framework-heavy readings.
- Treat vendor-specific behavior as adapter-local.
- Distinguish `implemented`, `verified`, `partial`, `planned`, and `blocked`; do not overclaim.
- Keep public docs aligned with repository truth and treat policy files as canonical for engineering, documentation, architecture, and verification rules.
- Put repository-operational status material under `design/` or `policies/`, not `docs/`.
- If a nearby real issue cannot be fixed quickly, record it in `design/BACKLOG.md`.

## Corpus Inventory

### Design Corpus Counts

- `design/` markdown files total: `237`
- `design/` root markdown files: `25`
- `design/adr/` markdown files: `144`
- `design/rfc/` markdown files: `21`
- `design/brainstorm/` markdown files: `19`
- `design/internal/` markdown files: `28`

### Root Design Files

```text
design/AGENT-INTEGRATION-VISION.md
design/ARCHITECTURE.md
design/BACKLOG.md
design/CLI-UX-VISION.md
design/CONFIG_UX_VISION.md
design/DOCS-UX-VISION.md
design/NL-UX-VISION.md
design/README.md
design/RFC-ADR-ROADMAP.md
design/TUI-UX-VISION.md
design/VISION.md
design/VISION_v2.md
design/WORKFLOW-UX-VISION.md
design/adr-0104-implementation-plan.md
design/adr-0105-implementation-plan.md
design/agent-turn-summary-implementation-plan.md
design/attached-turn-recovery-implementation-plan.md
design/critique-arch-round-1.md
design/critique-arch-round-2.md
design/critique-arch-round-3.md
design/critique-round-1.md
design/critique-round-2.md
design/critique-round-3.md
design/resident-reconciler-implementation-plan.md
design/user-stories-and-surface-model.md
```

### ADR Files

```text
design/adr/0001-agent-adapter-lifecycle.md
design/adr/0002-agent-result-and-progress-shape.md
design/adr/0003-brain-decision-shape.md
design/adr/0004-adopt-acp-for-codex.md
design/adr/0005-long-lived-objectives-and-memory-model.md
design/adr/0006-memory-entry-freshness-and-invalidations.md
design/adr/0007-event-wakeup-and-wait-semantics.md
design/adr/0008-attached-run-as-primary-runtime-mode.md
design/adr/0009-explicit-failure-action-for-operator-brain.md
design/adr/0010-expose-codex-acp-execution-policy.md
design/adr/0011-expose-condensed-codex-session-log-view.md
design/adr/0012-separate-objective-from-harness-instructions.md
design/adr/0013-operation-command-inbox-and-command-envelope.md
design/adr/0014-deterministic-command-reducer-vs-brain-mediated-replanning.md
design/adr/0015-scheduler-state-and-pause-semantics-for-attached-runs.md
design/adr/0016-attention-request-taxonomy-and-answer-routing.md
design/adr/0017-involvement-levels-and-autonomy-policy.md
design/adr/0018-project-profile-schema-and-override-model.md
design/adr/0019-policy-memory-and-promotion-workflow.md
design/adr/0020-live-attached-transparency-surface.md
design/adr/0021-expose-task-memory-and-artifact-cli-surfaces.md
design/adr/0022-cross-operation-agenda-cli-surface.md
design/adr/0023-stop-active-attached-agent-turn.md
design/adr/0024-effective-control-context-cli-surface.md
design/adr/0025-project-profile-init-cli-surface.md
design/adr/0026-live-operation-dashboard-cli-surface.md
design/adr/0027-live-fleet-dashboard-cli-surface.md
design/adr/0028-condensed-claude-session-log-view.md
design/adr/0028-explicit-answer-time-policy-promotion.md
design/adr/0028-policy-applicability-and-matching-semantics.md
design/adr/0029-policy-applicability-matching.md
design/adr/0030-condensed-claude-session-log-view.md
design/adr/0030-live-project-dashboard-cli-surface.md
design/adr/0030-policy-coverage-and-explainability.md
design/adr/0031-deterministic-policy-gap-guardrail.md
design/adr/0031-installed-cli-launch-mode-and-local-project-profile-discovery.md
design/adr/0032-live-goal-patching-command-slice.md
design/adr/0034-standard-coding-agent-tool-capabilities.md
design/adr/0035-project-profiles-may-carry-a-default-objective.md
design/adr/0036-live-constraint-patching-command-slice.md
design/adr/0037-stop-operation-command-slice.md
design/adr/0038-cli-authority-and-tui-supervisory-workbench.md
design/adr/0039-resident-reconciler-for-resumable-runtime.md
design/adr/0040-brain-context-budgets-before-provider-caching.md
design/adr/0041-agent-turn-summaries-and-full-latest-result-for-brain-history.md
design/adr/0042-attached-turn-timeouts-and-recovery-replanning.md
design/adr/0043-claude-acp-effort-via-thinking-token-env.md
design/adr/0044-force-recovery-command-for-stuck-runs.md
design/adr/0045-claude-acp-rate-limit-cooldown.md
design/adr/0046-timed-wakeups-and-daemon-auto-resume.md
design/adr/0047-attached-background-turns-owned-by-the-live-run.md
design/adr/0048-operator-owned-acp-substrate-and-per-adapter-sdk-migration.md
design/adr/0049-remove-direct-claude-code-adapter.md
design/adr/0050-shared-acp-session-runner-beneath-vendor-adapters.md
design/adr/0051-shared-acp-permission-policy-and-normalized-request-model.md
design/adr/0052-session-execution-migration-order-and-single-writer-lifecycle-authority.md
design/adr/0053-llm-mediated-acp-permission-decisions.md
design/adr/0054-recoverable-acp-disconnects-and-session-reattach.md
design/adr/0055-background-acp-progress-snapshots-and-sdk-notification-logging.md
design/adr/0056-acp-sdk-stdio-reader-limit.md
design/adr/0057-attached-mode-inline-wakeup-auto-resume.md
design/adr/0058-traceability-brief-layer-completeness.md
design/adr/0059-brain-project-file-system-boundary.md
design/adr/0060-project-scope-memory-entry.md
design/adr/0061-operator-messages-context-injection-and-window-semantics.md
design/adr/0062-feature-level-in-task-hierarchy.md
design/adr/0063-task-graph-structural-invariants.md
design/adr/0064-memory-strata-and-scope-model.md
design/adr/0065-operation-runtime-stop-conditions.md
design/adr/0066-stop-turn-task-addressing-model.md
design/adr/0067-patch-command-rejection-model.md
design/adr/0068-needs-human-operation-status.md
design/adr/0069-operation-event-store-and-checkpoint-store-contracts.md
design/adr/0070-fact-store-and-fact-translator-contracts.md
design/adr/0071-operation-projector-and-reducer-slices.md
design/adr/0072-process-manager-policy-boundary-and-builder-assembly.md
design/adr/0073-command-bus-and-planning-trigger-semantics.md
design/adr/0074-bridge-slice-cleanup-after-process-manager-and-planning-trigger-integration.md
design/adr/0076-remove-command-file-compatibility-layer-after-control-intent-migration.md
design/adr/0077-event-sourced-operation-cutover-and-legacy-coexistence-policy.md
design/adr/0078-command-application-and-single-writer-domain-event-append-boundary.md
design/adr/0079-live-replay-and-checkpoint-materialization-authority.md
design/adr/0080-operator-service-shell-extraction-and-runtime-ownership-after-event-sourced-cutover.md
design/adr/0081-adapter-runtime-public-protocol-and-transport-ownership.md
design/adr/0082-agent-session-runtime-public-protocol-and-single-live-session-invariant.md
design/adr/0083-operation-runtime-coordination-boundary-and-relationship-to-operator-service.md
design/adr/0084-async-event-stream-and-cancellation-semantics-for-runtime-layers.md
design/adr/0085-retain-operator-profile-naming-for-operation-scoped-project-configuration.md
design/adr/0086-event-sourced-operation-birth-and-snapshot-legacy-retirement-policy.md
design/adr/0087-canonical-operation-loop-and-fact-to-domain-append-authority.md
design/adr/0088-main-entrypoint-cutover-and-final-operator-service-shell-boundary.md
design/adr/0089-runtime-factory-composition-root-and-agentadapter-retirement.md
design/adr/0090-single-process-async-runtime-hosting-and-background-worker-removal.md
design/adr/0091-legacy-runtime-cleanup-and-document-supersession-after-cutover.md
design/adr/0092-split-operationconstraints-into-policy-budget-and-runtime-hints.md
design/adr/0093-cli-command-taxonomy-visibility-tiers-and-default-operator-entry-behavior.md
design/adr/0094-run-init-project-create-workflow-and-project-profile-lifecycle.md
design/adr/0095-operation-reference-resolution-and-command-addressing-contract.md
design/adr/0096-one-operation-control-and-summary-surface.md
design/adr/0097-forensic-log-unification-and-debug-surface-relocation.md
design/adr/0098-history-ledger-and-history-command-contract.md
design/adr/0099-operator-service-shell-completion-through-workflow-authority-extraction.md
design/adr/0100-pluggable-operator-policy-boundary-above-loaded-operation-runtime.md
design/adr/0101-ideal-application-organization-shell-loaded-operation-policy-and-workflow-capabilities.md
design/adr/0102-explicit-operation-lifecycle-coordinator-above-loaded-operation.md
design/adr/0103-dishka-composition-root-migration.md
design/adr/0104-top-application-control-layer-boundary-completion-after-shell-thinning.md
design/adr/0105-repository-wide-lint-normalization-as-a-separate-quality-wave.md
design/adr/0106-public-documentation-surface-and-committed-design-corpus-separation.md
design/adr/0107-repository-module-hierarchy-policy-and-low-ambiguity-application-tightening.md
design/adr/0108-legacy-compatibility-retirement-fronts-and-parallel-truth-policy.md
design/adr/0109-cli-authority-and-tui-workbench-v2.md
design/adr/0110-tui-view-hierarchy-and-zoom-contract.md
design/adr/0111-tui-signal-and-attention-propagation-contract.md
design/adr/0112-tui-cli-action-parity-and-safety.md
design/adr/0113-tui-data-substrate-and-refresh-model.md
design/adr/0114-cli-delivery-substrate-extraction-before-tui.md
design/adr/0115-fleet-workbench-projection-and-cli-tui-parity.md
design/adr/0116-cli-parity-gaps-for-fleet-operation-and-session-surfaces.md
design/adr/0117-public-session-scope-cli-surface.md
design/adr/0118-supervisory-surface-implementation-tranche.md
design/adr/0119-cli-main-module-decomposition-below-500-lines.md
design/adr/0120-cli-submodule-organization-and-boundary-rules.md
design/adr/0121-application-submodule-organization-and-boundary-rules.md
design/adr/0122-project-operator-state-clear-command.md
design/adr/0123-cli-package-submodules-and-subpackage-shape.md
design/adr/0126-supervisory-activity-summary-contract.md
design/adr/0127-cross-level-filtering-search-and-focus-persistence.md
design/adr/0128-tui-information-architecture-beyond-classic-zoom.md
design/adr/0129-tui-pane-authority-and-density-modes.md
design/adr/0130-attention-and-intervention-ux-for-blocking-and-non-blocking-work.md
design/adr/0131-cross-operation-supervisory-snapshot-surface.md
design/adr/0132-workspace-shell-and-lifecycle-commands.md
design/adr/0133-one-operation-summary-and-control-surface.md
design/adr/0134-one-operation-live-follow-surface.md
design/adr/0135-session-snapshot-and-live-follow-surface.md
design/adr/0136-transcript-retrospective-and-ledger-surfaces.md
design/adr/0137-operation-detail-and-inventory-surfaces.md
design/adr/0138-project-profile-inventory-and-inspection-surfaces.md
design/adr/0139-project-dashboard-and-entry-surface.md
design/adr/0140-policy-inventory-and-explainability-surfaces.md
design/adr/0141-policy-mutation-and-attention-promotion-workflow.md
design/adr/0142-hidden-debug-recovery-and-forensic-inspection-surfaces.md
design/adr/0143-attached-live-wakeup-reconciliation-contract.md
```

### RFC Files

```text
design/rfc/0001-acp-python-sdk-integration.md
design/rfc/0001-acp-python-sdk-integration.round1-critique.md
design/rfc/0001-acp-python-sdk-integration.round2-critique.md
design/rfc/0001-acp-python-sdk-integration.round3-critique.md
design/rfc/0002-peer-systems-study-and-acp-boundary.md
design/rfc/0003-shared-acp-session-runner-for-vendor-adapters.md
design/rfc/0004-unused-acp-sdk-capabilities-and-integration-priorities.md
design/rfc/0005-data-directory-layout-and-profile-storage.md
design/rfc/0005-session-execution-data-model.md
design/rfc/0006-event-model.md
design/rfc/0007-traceability-layer-model.md
design/rfc/0008-operator-workspace.md
design/rfc/0009-event-storming.md
design/rfc/0009-operation-event-sourced-state-model-and-runtime-architecture.md
design/rfc/0010-async-runtime-lifecycles-and-session-ownership.md
design/rfc/0011-delivery-package-boundary-for-cli-and-tui.md
design/rfc/0012-delivery-package-migration-tranche.md
design/rfc/0014-cli-output-contract-and-example-corpus.md
design/rfc/critique-0006-round-1.md
design/rfc/critique-0006-round-2.md
design/rfc/critique-0006-round-3.md
```

### Brainstorm Files

```text
design/brainstorm/attention-request-model-and-answer-routing-brainstorm-ideas.md
design/brainstorm/deterministic-vs-brain-mediated-live-command-handling-brainstorm-ideas.md
design/brainstorm/involvement-levels-and-policy-learning-brainstorm-ideas.md
design/brainstorm/involvement-policy-and-autonomy-brainstorm-ideas.md
design/brainstorm/operation-command-inbox-and-live-human-command-model-brainstorm-ideas.md
design/brainstorm/operator-involvement-and-policy-learning-brainstorm-ideas.md
design/brainstorm/operator-project-profiles-and-launch-ergonomics-brainstorm-ideas.md
design/brainstorm/operator-realtime-tui-and-intervention-brainstorm-ideas.md
design/brainstorm/operator-runtime-and-true-harness-brainstorm-ideas.md
design/brainstorm/operator-vision-consolidation-brainstorm-ideas.md
design/brainstorm/pause-semantics-during-active-attached-turns-brainstorm-ideas.md
design/brainstorm/project-profiles-and-launch-ergonomics-brainstorm-ideas.md
design/brainstorm/realtime-tui-and-control-brainstorm-ideas.md
design/brainstorm/realtime-tui-and-human-control-brainstorm-ideas.md
design/brainstorm/realtime-tui-and-monitoring-brainstorm-ideas.md
design/brainstorm/true-harness-adr-tranche-implementation-roadmap-brainstorm-ideas.md
design/brainstorm/true-harness-control-plane-consolidation-brainstorm-ideas.md
design/brainstorm/true-harness-runtime-brainstorm-ideas.md
design/brainstorm/user-involvement-and-policy-learning-brainstorm-ideas.md
```

### Internal Design Files

```text
design/internal/2026-04-05-architecture-status-note.md
design/internal/2026-04-10-repo-truth-vs-design-corpus-status-note.md
design/internal/2026-04-11-bounded-baseline-design-inventory.md
design/internal/adr-repo-truth-status-2026-04-11.md
design/internal/application-submodule-decomposition-implementation-note-2026-04-09.md
design/internal/clear-command-implementation-note-2026-04-09.md
design/internal/cli-main-decomposition-implementation-note-2026-04-09.md
design/internal/cli-parity-and-gaps-red-team-2026-04-09.md
design/internal/cli-tui-extraction-tranche-outcome-2026-04-09.md
design/internal/cli-tui-extraction-tranche-plan.md
design/internal/fleet-cli-implementation-note-2026-04-09.md
design/internal/fleet-default-and-modes-decision-2026-04-09.md
design/internal/fleet-ui-contract-2026-04-09.md
design/internal/fleet-window-candidates-2026-04-09.md
design/internal/operation-cli-implementation-note-2026-04-09.md
design/internal/operation-view-candidates-2026-04-09.md
design/internal/operation-view-default-and-modes-decision-2026-04-09.md
design/internal/operation-view-ui-contract-2026-04-09.md
design/internal/session-cli-implementation-note-2026-04-09.md
design/internal/session-view-candidates-2026-04-09.md
design/internal/session-view-default-and-modes-decision-2026-04-09.md
design/internal/session-view-ui-contract-2026-04-09.md
design/internal/strategy-draft.md
design/internal/tui-cli-red-team.md
design/internal/tui-display-family-red-team-2026-04-09.md
design/internal/tui-workbench-head-status-2026-04-11.md
design/internal/tui-workbench-status-2026-04-10.md
design/internal/workflow-nl-agent-red-team.md
```

## Current Repo Touchpoints By Design Family

This section maps the design-corpus families to the most relevant current code, test, and public-doc locations that are directly visible from the repository tree.

### Core Authority: `VISION.md`, `ARCHITECTURE.md`, `STACK.md`

- Code:
  - `src/agent_operator/application/`
  - `src/agent_operator/application/runtime/`
  - `src/agent_operator/application/drive/`
  - `src/agent_operator/application/event_sourcing/`
  - `src/agent_operator/domain/`
  - `src/agent_operator/protocols/`
  - `src/agent_operator/bootstrap.py`
- Tests:
  - `tests/test_attached_turn_service.py`
  - `tests/test_event_sourced_birth.py`
  - `tests/test_operation_projections.py`
  - `tests/test_operation_project_dashboard_queries.py`
- Public docs:
  - `README.md`
  - `docs/quickstart.md`
  - `docs/reference/cli.md`
  - `docs/reference/config.md`

Evidence:

- `design/ARCHITECTURE.md` explicitly names `LoadedOperation`, `OperatorService`, `application/drive/`, `application/event_sourcing/`, `application/commands/`, `application/queries/`, and `application/runtime/`.
- `STACK.md` explicitly names `dishka`, and `src/agent_operator/bootstrap.py` exists as the composition root.

### ADR Family: `design/adr/`

- Most relevant code:
  - `src/agent_operator/domain/`
  - `src/agent_operator/application/`
  - `src/agent_operator/adapters/`
  - `src/agent_operator/acp/`
  - `src/agent_operator/cli/commands/`
  - `src/agent_operator/cli/rendering/`
  - `src/agent_operator/cli/tui/`
  - `src/agent_operator/projectors/`
  - `src/agent_operator/providers/`
- Most relevant tests:
  - `tests/test_attached_turn_service.py`
  - `tests/test_codex_acp_adapter.py`
  - `tests/test_cli_rendering_imports.py`
  - `tests/test_event_sourced_birth.py`
  - `tests/test_operation_projections.py`
  - `tests/test_operation_project_dashboard_queries.py`
- Most relevant public docs:
  - `docs/reference/cli.md`
  - `docs/reference/config.md`
  - `docs/integrations.md`
  - `docs/tui-workbench.md`
  - `docs/tui-forensic-workflow.md`

Why this is the best lightweight mapping:

- The ADR corpus spans application loop, event sourcing, policy, adapters, CLI, TUI, and forensic surfaces.
- Current package layout mirrors those families directly: `application/*`, `domain`, `adapters`, `acp`, `cli/*`, `projectors`, and `providers`.

### RFC Family: `design/rfc/`

- Most relevant code:
  - `src/agent_operator/acp/`
  - `src/agent_operator/adapters/`
  - `src/agent_operator/application/event_sourcing/`
  - `src/agent_operator/cli/rendering/`
  - `src/agent_operator/cli/tui/`
- Most relevant tests:
  - `tests/test_codex_acp_adapter.py`
  - `tests/test_event_sourced_birth.py`
  - `tests/test_cli_rendering_imports.py`
- Most relevant public docs:
  - `docs/integrations.md`
  - `docs/reference/cli.md`
  - `docs/tui-workbench.md`

Evidence:

- `design/ARCHITECTURE.md` directly points to `RFC 0011` and `RFC 0012` for delivery boundaries.
- The RFC topics present in the tree cluster around ACP integration, event model/state model, and CLI/TUI delivery output.

### Brainstorm Family: `design/brainstorm/`

- Most relevant code:
  - `src/agent_operator/application/`
  - `src/agent_operator/cli/tui/`
  - `src/agent_operator/cli/workflows/`
- Most relevant tests:
  - `tests/test_attached_turn_service.py`
  - `tests/test_operation_projections.py`
- Most relevant public docs:
  - `docs/reference/cli.md`
  - `docs/tui-workbench.md`

Notes:

- These are exploratory artifacts rather than authority documents.
- The strongest current overlap is with attention handling, intervention, pause/resume behavior, and TUI/workbench supervision.

### Internal Design Family: `design/internal/`

- Most relevant code:
  - `src/agent_operator/application/`
  - `src/agent_operator/cli/commands/`
  - `src/agent_operator/cli/rendering/`
  - `src/agent_operator/cli/tui/`
- Most relevant tests:
  - `tests/test_cli_rendering_imports.py`
  - `tests/test_operation_project_dashboard_queries.py`
  - `tests/test_operation_projections.py`
- Most relevant public docs:
  - `docs/reference/cli.md`
  - `docs/tui-workbench.md`
  - `docs/tui-forensic-workflow.md`

Notes:

- The current internal-note set is heavily skewed toward the April 2026 CLI/TUI extraction tranche and related supervision surfaces.

### UX Vision Files

Files:

- `design/CLI-UX-VISION.md`
- `design/CONFIG_UX_VISION.md`
- `design/DOCS-UX-VISION.md`
- `design/NL-UX-VISION.md`
- `design/TUI-UX-VISION.md`
- `design/WORKFLOW-UX-VISION.md`

Most relevant paths:

- Code:
  - `src/agent_operator/cli/commands/`
  - `src/agent_operator/cli/rendering/`
  - `src/agent_operator/cli/tui/`
  - `src/agent_operator/cli/workflows/`
- Tests:
  - `tests/test_cli_rendering_imports.py`
  - `tests/test_operation_project_dashboard_queries.py`
- Public docs:
  - `docs/reference/cli.md`
  - `docs/quickstart.md`
  - `docs/tui-workbench.md`
  - `docs/tui-forensic-workflow.md`

### Integration-Vision and Implementation-Plan Files

Files:

- `design/AGENT-INTEGRATION-VISION.md`
- `design/adr-0104-implementation-plan.md`
- `design/adr-0105-implementation-plan.md`
- `design/agent-turn-summary-implementation-plan.md`
- `design/attached-turn-recovery-implementation-plan.md`
- `design/resident-reconciler-implementation-plan.md`

Most relevant paths:

- Code:
  - `src/agent_operator/adapters/`
  - `src/agent_operator/acp/`
  - `src/agent_operator/application/runtime/`
  - `src/agent_operator/providers/`
- Tests:
  - `tests/test_codex_acp_adapter.py`
  - `tests/test_attached_turn_service.py`
- Public docs:
  - `docs/integrations.md`
  - `docs/reference/config.md`

## Immediately Verifiable Gaps

These are repo-observable gaps or friction points, not speculative architecture critiques.

### 1. ADR numeric identifiers are not unique

Observed directly from `design/adr/`:

- `0028` is used by three files:
  - `design/adr/0028-condensed-claude-session-log-view.md`
  - `design/adr/0028-explicit-answer-time-policy-promotion.md`
  - `design/adr/0028-policy-applicability-and-matching-semantics.md`
- `0030` is used by three files:
  - `design/adr/0030-condensed-claude-session-log-view.md`
  - `design/adr/0030-live-project-dashboard-cli-surface.md`
  - `design/adr/0030-policy-coverage-and-explainability.md`
- `0031` is used by two files:
  - `design/adr/0031-deterministic-policy-gap-guardrail.md`
  - `design/adr/0031-installed-cli-launch-mode-and-local-project-profile-discovery.md`

Impact:

- Any tooling or human workflow that assumes one ADR number maps to one decision document is currently unsafe.

Recommended follow-up:

- Record and resolve the ADR-number collision policy in `design/BACKLOG.md` or through a dedicated cleanup pass.

### 2. The design corpus has no committed single-source index beyond directory listing

Observed directly from the tree:

- `design/README.md` explains the corpus families and contributor reading order.
- There is no committed generated inventory file or ADR index in `design/` that normalizes counts, duplicate identifiers, or topic-to-code touchpoints.

Impact:

- Corpus discovery currently depends on directory traversal rather than a maintained inventory artifact.

Status:

- This note partially fills that gap for the current date, but it is still a point-in-time status document rather than a maintained index system.

## Evidence Notes

This pass was based on direct reads of:

- `README.md`
- `policies/README.md`
- `design/README.md`
- `design/VISION.md`
- `design/ARCHITECTURE.md`
- `STACK.md`

And direct repository enumeration of:

- `design/**/*.md`
- `src/agent_operator/**`
- `tests/**`
- `docs/**`

No claim in this note should be read as full implementation verification of every ADR or RFC.
