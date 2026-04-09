# TUI Workbench Status Against Vision and Architecture (2026-04-10)

## Scope

This status note compares current repository truth against:

- [TUI-UX-VISION.md](/Users/thunderbird/Projects/operator/design/TUI-UX-VISION.md)
- [VISION.md](/Users/thunderbird/Projects/operator/design/VISION.md)
- [ARCHITECTURE.md](/Users/thunderbird/Projects/operator/design/ARCHITECTURE.md)

It is a status artifact, not a new design authority.

## Conclusion

The current repository truth is close enough to the TUI/workbench design corpus that a final
closeout/status pass is warranted.

The implemented supervisory workbench path is materially in place:

- fleet -> operation -> session -> forensic drill-down exists
- attention triage and current-scope answering exist across the supported levels
- shared CLI/TUI query and command routing is in place
- the package-submodule reorganization needed to make the current delivery shape legible is present
  in repository truth

The remaining gaps are not hidden blockers to truthful closeout. They are bounded follow-up work:

- nested sub-operator hierarchy from the TUI UX vision remains unimplemented
- adapter-specific forensic richness remains intentionally limited
- the UX vision still aims at a stronger presentation language than the current table/panel
  rendering provides

That means the workbench can be documented as implemented with explicit partial/blocked edges
rather than as an unfinished tranche waiting on another prerequisite repair.

## Vision/Architecture Matrix

| Area | Implemented | Verified | Notes |
|---|---|---|---|
| Fleet -> operation -> session -> forensic drill-down | yes | yes | Present in `agent_operator.cli.tui`; covered by [tests/test_tui.py](/Users/thunderbird/Projects/operator/tests/test_tui.py) and [tests/test_tui_session_view.py](/Users/thunderbird/Projects/operator/tests/test_tui_session_view.py). |
| Left-pane anchored zoom model | yes | yes | Rendering keeps a stable left selection pane and right detail pane across view levels. |
| Fleet-level attention triage | yes | yes | Blocking `a`, non-blocking `n`, and current-scope picker `A` are implemented and exercised in tests. |
| Blocking badge propagation and oldest-first attention ordering | yes | yes | Current model/controller behavior matches the stated signal contract. |
| Operation view task board with grouped lanes and dependency/session cue lines | yes | yes | Grouped lane rendering plus compact dependency/session continuation lines are present and tested. |
| Session brief + timeline + selected-event detail | yes | yes | Current TUI renders the shared session brief and selected-event detail path. |
| Forensic drill-down without requiring raw transcript presence | yes | yes | Empty-transcript fallback and forensic back-navigation to session are exercised in tests. |
| CLI/TUI command parity for pause, unpause, interrupt, answer, cancel | yes | partial | Code/docs/tests show the behavior; `ADR 0112` itself still remains `Accepted`, so the ADR corpus has status lag rather than a product gap. |
| Shared delivery substrate and shared projections | yes | partial | Repository structure and imports show the delivery-family split; this pass verified shape/evidence, not the whole CLI/TUI surface end-to-end. |
| Human-first fleet/operation/session briefs | yes | partial | The brief payloads are present and used, though the richer visual ambition in the UX vision remains above current presentation fidelity. |
| Full multi-pane attention-management surface | no | n/a | Inline answer flow and the compact picker are shipped; a richer dedicated management surface is still absent. |
| Adapter-specific forensic formatting richness | no | n/a | Current forensic output remains intentionally normalized and limited. |
| Nested sub-operator (`operator_acp`) hierarchy in the workbench | no | n/a | No nested sub-operator hierarchy was found in the current controller/model/rendering path. |

## Truth Matrix

| Category | Items |
|---|---|
| implemented | four-level workbench drill-down; left/right supervision layout; fleet/operation/session/forensic filtering; pause/unpause/interrupt/cancel command routing; oldest-first blocking and non-blocking answer flow; current-scope attention picker; grouped task-board lanes; forensic fallback with no raw transcript payload; forensic `q` back-navigation |
| verified | design/source review against [design/TUI-UX-VISION.md](/Users/thunderbird/Projects/operator/design/TUI-UX-VISION.md), [design/VISION.md](/Users/thunderbird/Projects/operator/design/VISION.md), [design/ARCHITECTURE.md](/Users/thunderbird/Projects/operator/design/ARCHITECTURE.md); behavior evidence in [tests/test_tui.py](/Users/thunderbird/Projects/operator/tests/test_tui.py) and [tests/test_tui_session_view.py](/Users/thunderbird/Projects/operator/tests/test_tui_session_view.py); user-facing docs checked in [README.md](/Users/thunderbird/Projects/operator/README.md), [docs/tui-workbench.md](/Users/thunderbird/Projects/operator/docs/tui-workbench.md), and [docs/tui-forensic-workflow.md](/Users/thunderbird/Projects/operator/docs/tui-forensic-workflow.md) |
| partial | stronger UX-vision presentation ambition than current table/panel rendering; broad delivery-substrate closure beyond the current TUI slice; ADR-header/doc synchronization where ADR text lags shipped behavior |
| blocked | nested sub-operator hierarchy from the TUI UX vision; richer adapter-specific forensic formatting |

## Source-by-Source Assessment

### TUI-UX-VISION.md

- `implemented`: the four-level hierarchy and supervision-first navigation model.
- `implemented`: fleet-level answer flow without forced deep drill-down.
- `implemented`: help overlays, filtering, task board grouping, and forensic escalation path.
- `implemented`: forensic `q` now acts as exit from Level 3 back to the parent session view.
- `partial`: the vision still describes a stronger visual/presentational language than the current
  Rich table/panel rendering provides.
- `blocked`: explicit nested sub-operator hierarchy support remains future-facing.

### VISION.md

- `implemented`: TUI/workbench behavior remains supervisory over persisted runtime truth rather than
  a second runtime authority.
- `implemented`: deterministic guardrails remain outside TUI; TUI actions route through the same
  lifecycle/control semantics as CLI.
- `implemented`: transparency-by-default requirement is materially satisfied for fleet, operation,
  session, and forensic inspection.
- `partial`: transparency is strong for normalized summaries and raw transcript/detail text, but
  still not a richer adapter-specific forensic analysis surface.

### ARCHITECTURE.md

- `implemented`: delivery-layer statement that CLI is authoritative and TUI is a supervisory driving
  adapter over the same application-facing contracts.
- `implemented`: the current repository truth now includes the family subpackages under
  `agent_operator.cli.commands`, `agent_operator.cli.rendering`, `agent_operator.cli.tui`,
  `agent_operator.cli.workflows`, and `agent_operator.cli.helpers`.
- `implemented`: shared projection/query path for fleet, operation, and session surfaces.
- `implemented`: `ADR 0121` no longer acts as a feasibility blocker for truthful TUI closeout.
- `partial`: broader delivery-package cleanup and final architectural tightening outside the TUI
  family remain intentionally deferred and are not blockers to the workbench status claim.

## ADR >= 0101 Acceptance-Feasibility Assessment

### Application architecture ADRs

| ADR | ADR status | Acceptance-feasibility | Notes |
|---|---|---|---|
| 0101 | Accepted | feasible, partially realized | `ARCHITECTURE.md` explicitly documents this shape as the intended current direction with partial completion. |
| 0102 | Accepted | feasible, not yet complete | Lifecycle coordination remains a named future authority above `LoadedOperation`. |
| 0103 | Accepted | feasible, partially realized | `dishka` is partially landed at the composition root; the repository truth does not justify calling this complete. |
| 0104 | Accepted | feasible, not yet complete | The remaining top-layer lifecycle/control-state/runtime-gating boundary work is still openly deferred. |

### TUI/workbench ADRs

| ADR | ADR status | Acceptance-feasibility | Notes |
|---|---|---|---|
| 0109 | Implemented | accepted and feasible | Repository truth matches the CLI-authoritative / TUI-supervisory split. |
| 0110 | Implemented | accepted and feasible | Current zoom contract and back-navigation behavior are in place. |
| 0111 | Implemented | accepted and feasible | Badge and oldest-first attention semantics are in current behavior and tests. |
| 0112 | Accepted | accepted, feasible, and materially implemented in repo truth | Current controller/docs/tests reflect the contract even though the ADR header still says `Accepted`. |
| 0113 | Implemented | accepted and feasible | Shared query/projection substrate is in place. |
| 0114 | Implemented | accepted and feasible | Delivery-substrate extraction has landed enough for the current TUI family. |
| 0115 | Implemented | accepted and feasible | Normalized fleet workbench projection exists. |
| 0116 | Implemented | accepted and feasible | Fleet/operation/session parity tranche claims are consistent with current docs/tests. |
| 0117 | Implemented | accepted and feasible | Public task-addressed session surface exists. |
| 0118 | Implemented | accepted and feasible | The tranche success condition is materially met. |
| 0121 | Accepted; implementation status says Implemented | accepted and feasible | Application command/query/runtime families now live in canonical subpackages and no longer block this TUI closeout/status pass. |

## Verified Evidence Used For This Pass

- Design authority:
  - [design/TUI-UX-VISION.md](/Users/thunderbird/Projects/operator/design/TUI-UX-VISION.md)
  - [design/VISION.md](/Users/thunderbird/Projects/operator/design/VISION.md)
  - [design/ARCHITECTURE.md](/Users/thunderbird/Projects/operator/design/ARCHITECTURE.md)
- Current user/docs surfaces:
  - [README.md](/Users/thunderbird/Projects/operator/README.md)
  - [docs/tui-workbench.md](/Users/thunderbird/Projects/operator/docs/tui-workbench.md)
  - [docs/tui-forensic-workflow.md](/Users/thunderbird/Projects/operator/docs/tui-forensic-workflow.md)
- Current implementation/test surfaces inspected:
  - [src/agent_operator/cli/tui/controller.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui/controller.py)
  - [src/agent_operator/cli/tui/rendering.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui/rendering.py)
  - [src/agent_operator/cli/tui/models.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui/models.py)
  - [tests/test_tui.py](/Users/thunderbird/Projects/operator/tests/test_tui.py)
  - [tests/test_tui_session_view.py](/Users/thunderbird/Projects/operator/tests/test_tui_session_view.py)

## Remaining Work

- `blocked`: nested sub-operator workbench hierarchy described in the TUI UX vision.
- `partial`: richer adapter-specific forensic presentation.
- `partial`: the TUI UX vision still describes stronger presentation ambition than the current
  terminal tables and text panels provide, even though the core supervision workflow is in place.
- `partial`: if the repository wants the ADR corpus to read as closed, a later doc-only pass can
  reconcile `ADR 0112` header status with shipped behavior without changing implementation truth.
