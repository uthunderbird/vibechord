# TUI Workbench Status Against Vision and Architecture (2026-04-10)

## Scope

This status note compares current repository truth against:

- [TUI-UX-VISION.md](/Users/thunderbird/Projects/operator/design/TUI-UX-VISION.md)
- [VISION.md](/Users/thunderbird/Projects/operator/design/VISION.md)
- [ARCHITECTURE.md](/Users/thunderbird/Projects/operator/design/ARCHITECTURE.md)

It is a status artifact, not a new design authority.

## Conclusion

No comparable first-priority TUI/workbench implementation gap remains that is both:

- still open against the current design corpus, and
- small enough to truthfully land as the next narrow slice without mixing into unrelated in-flight
  work already present in the tree.

The current workbench truth is therefore best represented by a status assessment rather than a new
implementation claim.

Since this note was first added, two previously in-flight fronts have landed and no longer act as
blocking overlap:

- `ADR 0121` application package reorganization is now implemented in repository truth.
- forensic `q` now behaves as back-navigation to session level rather than quitting the whole
  workbench.

## Vision/Architecture Matrix

| Area | Status | Notes |
|---|---|---|
| Fleet -> operation -> session -> forensic drill-down | implemented | Implemented in `agent_operator.cli.tui` controller/rendering stack; also described in [README.md](/Users/thunderbird/Projects/operator/README.md) and [docs/tui-workbench.md](/Users/thunderbird/Projects/operator/docs/tui-workbench.md). |
| Left-pane anchored zoom model | implemented | Current TUI keeps navigation/detail split across all levels. |
| Fleet-level attention triage | implemented | Blocking and non-blocking attention answer flows, picker, and fleet-scope action routing are present. |
| Blocking badge propagation and oldest-first attention ordering | implemented | Present in projection/model/controller behavior and already called out in `ADR 0111`. |
| Operation view task board with grouped lanes and dependency/session cue lines | implemented | `RUNNING`, `READY`, `BLOCKED`, `COMPLETED`, `FAILED`, `CANCELLED` rendering is present and documented. |
| Session brief + timeline + selected-event detail | implemented | Shared `session_brief` payload and session drill-down are in repository truth. |
| Forensic drill-down without requiring raw transcript presence | implemented | Forensic view opens with explicit empty-state messaging when transcript text is absent, and `q` now returns to session level. |
| CLI/TUI command parity for pause, unpause, interrupt, answer, cancel | implemented | Behavior is implemented; ADR status lag remains on `ADR 0112` only. |
| Shared delivery substrate and shared projections | implemented | `ARCHITECTURE.md`, `ADR 0113` to `0118`, and landed `ADR 0121` package organization now match current query/runtime/application shape. |
| Human-first fleet/operation/session briefs | implemented | Shared `fleet` / `operation_brief` / `session_brief` payloads exist and are used by CLI/TUI surfaces. |
| Full multi-pane attention-management surface | partial | Current inline answer flow and attention picker are sufficient for parity, but not yet a richer dedicated management surface. |
| Adapter-specific forensic formatting richness | partial | Current docs already call out that per-adapter forensic formatting remains limited. |
| Nested sub-operator (`operator_acp`) hierarchy in the workbench | blocked | Vision path exists, but no implemented nested sub-operator workbench hierarchy was found in current repository truth. |

## Source-by-Source Assessment

### TUI-UX-VISION.md

- `implemented`: the four-level hierarchy and supervision-first navigation model.
- `implemented`: fleet-level answer flow without forced deep drill-down.
- `implemented`: help overlays, filtering, task board grouping, and forensic escalation path.
- `implemented`: forensic `q` now acts as exit from Level 3 back to the parent session view.
- `partial`: the vision still describes some stronger presentational ambitions than current terminal
  tables provide; this is presentation debt, not a missing first-priority capability slice.
- `blocked`: explicit nested sub-operator hierarchy support remains future-facing.

### VISION.md

- `implemented`: TUI/workbench behavior remains supervisory over persisted runtime truth rather than
  a second runtime authority.
- `implemented`: deterministic guardrails remain outside TUI; TUI actions route through the same
  lifecycle/control semantics as CLI.
- `implemented`: transparency-by-default requirement is materially satisfied for fleet, operation,
  session, and forensic inspection.
- `partial`: transparency is strong for normalized summaries and forensic raw text, but still not a
  richer adapter-specific forensic analysis surface.

### ARCHITECTURE.md

- `implemented`: delivery-layer statement that CLI is authoritative and TUI is a supervisory driving
  adapter over the same application-facing contracts.
- `implemented`: documented partial package migration under `ADR 0123`; current TUI package lives
  under `agent_operator.cli.tui` with compatibility shims.
- `implemented`: shared projection/query path for fleet, operation, and session surfaces.
- `implemented`: `ADR 0121` is no longer an in-flight blocker to further TUI closure work.
- `partial`: broader delivery package cleanup outside the TUI family remains intentionally deferred
  and is not a TUI slice blocker.

## ADR >= 0101 Acceptance-Feasibility Assessment

### Application architecture ADRs

| ADR | Status in ADR | Feasibility assessment | Notes |
|---|---|---|---|
| 0101 | Accepted | feasible, partially realized | `ARCHITECTURE.md` already marks the intended shell / loaded-operation / policy / workflow-capability shape as repository direction with partial completion. |
| 0102 | Accepted | feasible, not yet complete | Lifecycle coordination remains an explicitly planned authority above `LoadedOperation`. No evidence in this pass justifies upgrading it to implemented. |
| 0103 | Accepted | feasible, partially realized | `STACK.md` and `ARCHITECTURE.md` both describe `dishka` migration as partial current truth. |
| 0104 | Accepted | feasible, not yet complete | The remaining top-layer control/lifecycle boundary work is still documented as planned/partial rather than complete. |

### TUI/workbench ADRs

| ADR | Status in ADR | Feasibility assessment | Notes |
|---|---|---|---|
| 0109 | Implemented | accepted and feasible | Repository truth matches the CLI-authoritative / TUI-supervisory split. |
| 0110 | Implemented | accepted and feasible | Current zoom contract and back-navigation behavior are in place. |
| 0111 | Implemented | accepted and feasible | Badge and oldest-first attention semantics are in current behavior and tests. |
| 0112 | Accepted | effectively implemented; ADR status update appears feasible | Current controller/docs/tests reflect the accepted parity and safety contract even though the ADR header still says `Accepted`. |
| 0113 | Implemented | accepted and feasible | Shared query/projection substrate is in place. |
| 0114 | Implemented | accepted and feasible | Delivery-substrate extraction has landed enough for the current TUI family. |
| 0115 | Implemented | accepted and feasible | Normalized fleet workbench projection exists. |
| 0116 | Implemented | accepted and feasible | Fleet/operation/session parity tranche claims are consistent with current docs/tests. |
| 0117 | Implemented | accepted and feasible | Public task-addressed session surface exists. |
| 0118 | Implemented | accepted and feasible | The tranche success condition is materially met. |
| 0121 | Accepted + Implemented | accepted and feasible | Application command/query/runtime families now live in canonical subpackages and no longer block TUI read-surface follow-up work. |

## Verified Evidence Used For This Pass

- Design authority:
  - [design/TUI-UX-VISION.md](/Users/thunderbird/Projects/operator/design/TUI-UX-VISION.md)
  - [design/VISION.md](/Users/thunderbird/Projects/operator/design/VISION.md)
  - [design/ARCHITECTURE.md](/Users/thunderbird/Projects/operator/design/ARCHITECTURE.md)
- Current user/docs surfaces:
  - [README.md](/Users/thunderbird/Projects/operator/README.md)
  - [docs/tui-workbench.md](/Users/thunderbird/Projects/operator/docs/tui-workbench.md)
- Current implementation/test surfaces inspected:
  - [src/agent_operator/application/queries/operation_status_queries.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/queries/operation_status_queries.py)
  - [src/agent_operator/cli/tui/controller.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui/controller.py)
  - [src/agent_operator/cli/tui/rendering.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui/rendering.py)
  - [src/agent_operator/cli/tui/models.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui/models.py)
  - [tests/test_application_structure.py](/Users/thunderbird/Projects/operator/tests/test_application_structure.py)
  - [tests/test_tui.py](/Users/thunderbird/Projects/operator/tests/test_tui.py)
  - [tests/test_tui_session_view.py](/Users/thunderbird/Projects/operator/tests/test_tui_session_view.py)

## Remaining Work

- `blocked`: nested sub-operator workbench hierarchy described in the TUI UX vision.
- `partial`: richer adapter-specific forensic presentation.
- `partial`: the TUI UX vision still describes stronger presentation ambition than the current
  terminal tables and text panels provide, even though the core supervision workflow is now in
  place.
- `partial`: if desired, a future cleanup pass can update `ADR 0112` from `Accepted` to
  `Implemented` once the repository wants the ADR header to match current behavior explicitly.
