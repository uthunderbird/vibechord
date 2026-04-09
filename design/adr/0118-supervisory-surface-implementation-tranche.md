# ADR 0118: Supervisory Surface Implementation Tranche

## Status

Implemented

## Context

The repository now has a coherent design and ADR chain for the supervisory surface:

- `ADR 0115` — fleet workbench projection and CLI/TUI parity
- `ADR 0116` — parity gaps across fleet, operation, and session
- `ADR 0117` — public session-scope CLI surface

The repository also now has implementation-facing notes for each supervisory level:

- [fleet-cli-implementation-note-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/fleet-cli-implementation-note-2026-04-09.md)
- [operation-cli-implementation-note-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/operation-cli-implementation-note-2026-04-09.md)
- [session-cli-implementation-note-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/session-cli-implementation-note-2026-04-09.md)

What is still missing is an execution-anchor ADR that says, in one place:

- what the next implementation wave actually is
- what order the repository should execute it in
- which files are expected to move
- what counts as materially done for the tranche

Without that, the design corpus is coherent, but the implementation wave is still spread across
multiple documents.

## Decision

The next supervisory-surface implementation wave is a single staged tranche with three ordered
fronts:

1. `Fleet`
2. `Operation`
3. `Session`

This order is intentional.

### Why this order

#### 1. `Fleet` first

`Fleet` owns the most foundational shared projection gap.

Until the repository has a normalized fleet workbench projection, the TUI and CLI still diverge at
the top of the supervision model.

#### 2. `Operation` second

`Operation` already has the strongest raw substrate.

The main gap is the normalized `operation_brief` contract rather than missing deeper data.

#### 3. `Session` third

`Session` is the weakest public CLI surface, but it should be implemented after the operation-level
substrate is normalized so its shared payload can build on the same clarified patterns.

## Tranche scope

This tranche includes:

- normalized fleet workbench projection
- normalized `operation_brief`
- normalized `session_brief`
- public `operator session OP --task TASK` command
- CLI/TUI reuse of shared display-facing semantics

This tranche does not include:

- user-facing docs refresh before implementation lands
- arbitrary configurable layouts
- strong operator-load modeling
- full multi-agent grammar
- redesign of raw forensic surfaces

## Execution plan

### Front 1 — Fleet

Implement the `Fleet` tranche according to:

- [ADR 0115](/Users/thunderbird/Projects/operator/design/adr/0115-fleet-workbench-projection-and-cli-tui-parity.md)
- [fleet-cli-implementation-note-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/fleet-cli-implementation-note-2026-04-09.md)

Required outcome:

- one normalized fleet workbench projection used by:
  - TUI fleet rendering
  - CLI fleet snapshot
  - `fleet --json`

### Front 2 — Operation

Implement the `Operation` tranche according to:

- [ADR 0116](/Users/thunderbird/Projects/operator/design/adr/0116-cli-parity-gaps-for-fleet-operation-and-session-surfaces.md)
- [operation-cli-implementation-note-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/operation-cli-implementation-note-2026-04-09.md)

Required outcome:

- one normalized `operation_brief` block in the shared one-operation payload
- TUI `Operation View` consuming that block rather than reconstructing it locally

### Front 3 — Session

Implement the `Session` tranche according to:

- [ADR 0117](/Users/thunderbird/Projects/operator/design/adr/0117-public-session-scope-cli-surface.md)
- [session-cli-implementation-note-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/session-cli-implementation-note-2026-04-09.md)

Required outcome:

- one normalized `session_brief` block
- one public session-scoped CLI surface:
  - `operator session OP --task TASK`

## Shared file touch set

The tranche is expected to concentrate mostly in:

- [operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_projections.py)
- [operation_dashboard_queries.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_dashboard_queries.py)
- [main.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/main.py)
- [tui.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui.py)
- [agenda.py](/Users/thunderbird/Projects/operator/src/agent_operator/runtime/agenda.py)

and the corresponding tests:

- [test_operation_projections.py](/Users/thunderbird/Projects/operator/tests/test_operation_projections.py)
- [test_cli.py](/Users/thunderbird/Projects/operator/tests/test_cli.py)
- [test_tui.py](/Users/thunderbird/Projects/operator/tests/test_tui.py)

## Sequencing rule

The repository should avoid implementing these fronts in an interleaved ad hoc way.

Preferred sequence:

1. fleet projection and tests
2. fleet CLI/TUI wiring
3. operation brief projection and tests
4. operation TUI wiring
5. session brief projection and tests
6. public `session` CLI command
7. session TUI alignment
8. cross-surface polish

This sequencing is intended to reduce drift and prevent the session tranche from inventing a
parallel projection model while fleet and operation are still unstable.

## Verification gates

The tranche is not materially complete until all three gates pass.

### Gate 1 — Fleet gate

- normalized fleet workbench payload exists
- CLI and TUI both consume it
- old agenda-shaped fleet rendering assumptions are retired from the primary path

### Gate 2 — Operation gate

- normalized `operation_brief` exists
- TUI `Operation View` uses it
- selected-task detail remains separate and dominant

### Gate 3 — Session gate

- normalized `session_brief` exists
- `operator session OP --task TASK` exists
- session surface is task-addressed, not session-id-addressed
- session output is distinct from transcript and forensic output

## Documentation rule for this tranche

End-user docs and CLI reference updates should follow implementation, not lead it.

Until the tranche lands:

- design docs and ADRs remain the source of intended behavior
- user/reference docs should not overclaim the unimplemented surfaces

## Success condition

This ADR is satisfied when the repository can honestly claim:

- `Fleet`, `Operation`, and `Session` all have shared display-facing semantics
- CLI and TUI are aligned by scope and by projection truth
- the public CLI has a real `session`-scope surface rather than only operation and forensic
  approximations

## Verification Notes (2026-04-10)

The tranche described here is now implemented in repository truth.

Gate evidence:

- **Gate 1 — Fleet**
  - shared fleet workbench projection/query exists in
    [operation_fleet_workbench_queries.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_fleet_workbench_queries.py)
    and
    [operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_projections.py)
  - CLI and TUI both consume that projection through
    [workflows_views.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/workflows_views.py),
    [rendering_fleet.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/rendering_fleet.py),
    and
    [tui_models.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui_models.py)
- **Gate 2 — Operation**
  - normalized `operation_brief` is emitted by the shared one-operation payload in
    [operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_projections.py)
  - TUI `Operation View` renders that brief directly in
    [tui_rendering.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui_rendering.py)
- **Gate 3 — Session**
  - normalized `session_brief` and `session_views` are emitted by the shared dashboard payload in
    [operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_projections.py)
  - the public task-addressed session surface is implemented in
    [commands_operation_detail.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/commands_operation_detail.py)
  - TUI session and forensic drill-down consume the same shared semantics through
    [tui_models.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui_models.py),
    [tui_rendering.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui_rendering.py),
    and
    [tui_controller.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui_controller.py)

Focused verification already present in the repository includes:

- [test_operation_projections.py](/Users/thunderbird/Projects/operator/tests/test_operation_projections.py)
- [test_operation_dashboard_queries.py](/Users/thunderbird/Projects/operator/tests/test_operation_dashboard_queries.py)
- [test_cli.py](/Users/thunderbird/Projects/operator/tests/test_cli.py)
- [test_tui.py](/Users/thunderbird/Projects/operator/tests/test_tui.py)
- [test_tui_session_view.py](/Users/thunderbird/Projects/operator/tests/test_tui_session_view.py)

Documentation is now aligned with the implemented tranche in:

- [docs/reference/cli.md](/Users/thunderbird/Projects/operator/docs/reference/cli.md)
- [docs/tui-workbench.md](/Users/thunderbird/Projects/operator/docs/tui-workbench.md)
- [docs/tui-forensic-workflow.md](/Users/thunderbird/Projects/operator/docs/tui-forensic-workflow.md)
- [design/VISION.md](/Users/thunderbird/Projects/operator/design/VISION.md)
- [design/ARCHITECTURE.md](/Users/thunderbird/Projects/operator/design/ARCHITECTURE.md)
