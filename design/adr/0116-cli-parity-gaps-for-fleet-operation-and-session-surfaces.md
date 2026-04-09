# ADR 0116: CLI Parity Gaps For Fleet, Operation, And Session Surfaces

## Status

Implemented

## Context

The current ADR chain already establishes the intended product model:

- `status` is the canonical shell-native one-operation summary surface
- the TUI workbench is the preferred interactive live supervision surface
- CLI and TUI should remain thin driving adapters over shared persisted truth and shared
  application-facing command/query contracts

That direction is established in:

- `ADR 0109`
- `ADR 0110`
- `ADR 0111`
- `ADR 0112`
- `ADR 0113`
- `ADR 0114`
- `ADR 0115`

The TUI design corpus has now converged on a display family with distinct level roles:

- `Fleet`: calm-summary hybrid
- `Operation View`: task board + compact operation brief + selected-task panel
- `Session View`: split hybrid with recent timeline + compact session brief + selected event detail

However, the repository does not yet have full CLI parity for that display family.

The parity gap is not uniform.

### Fleet

The current fleet substrate still depends on the older agenda/dashboard-oriented payload shape:

- `AgendaItem`
- `AgendaSnapshot`
- `build_fleet_payload()`

This is not yet the same thing as the normalized fleet workbench projection required by the current
`Fleet` contract.

`ADR 0115` already captures this as a dedicated fleet tranche.

### Operation View

The current one-operation dashboard payload is much stronger than fleet and already exposes most of
the required truth:

- tasks
- attention
- decision memos
- memory entries
- sessions
- recent events
- timeline events

But the current shared payload still lacks a dedicated normalized `operation_brief` block matching
the new `Operation View` contract.

### Session View

This is the weakest parity area.

The repository has session-related building blocks:

- session-related data inside the one-operation dashboard payload
- transcript-oriented output via `log`
- forensic event data via `trace`

But it does not yet expose a public CLI surface corresponding cleanly to the new `Session View`
contract:

- compact session brief
- recent session timeline
- selected-event detail
- explicit transcript escalation path

### Public CLI visibility gap

Some of the richer inspection surfaces that currently help approximate parity are still hidden:

- `inspect`
- `context`
- `trace`

This means the repository can appear closer to parity in source code than it is in public CLI
practice.

## Decision

The repository must treat CLI parity for the TUI display family as a real staged architecture task,
not as incidental future polish.

This parity work is split into three fronts:

1. **Fleet parity**
   - remains governed by `ADR 0115`
   - requires a dedicated fleet workbench projection shared by CLI and TUI

2. **Operation parity**
   - requires a normalized `operation_brief` display block within the shared one-operation query
     path
   - does not require a wholly separate operation query service in the first tranche

3. **Session parity**
   - requires an explicit public CLI story for the `Session View` contract
   - requires a normalized `session_brief` display block
   - must not be treated as satisfied merely because transcript or forensic commands exist

### Shared rule

Parity means:

- shared projection truth
- public CLI access to the meaningful level semantics
- multiple renderers over the same normalized data

Parity does **not** mean:

- identical terminal formatting
- forcing every TUI level to become a one-command CLI screen immediately
- treating hidden forensic commands as sufficient public parity

## Consequences

### 1. Fleet parity remains a dedicated tranche

No change to the decision in `ADR 0115`.

`Fleet` still needs:

- normalized fleet rows
- normalized fleet brief
- one shared fleet workbench projection for CLI and TUI

### 2. Operation parity becomes an explicit shared-display-contract requirement

The one-operation dashboard/query substrate may remain the main shared query path for now.

But it must grow a normalized display-facing `operation_brief` block with semantics aligned to the
`Operation View` contract:

- `Now`
- `Wait`
- `Progress`
- `Attention`
- `Recent`

This allows:

- TUI `Operation View`
- CLI one-operation rich snapshot surfaces

to render the same higher-level semantics without ad hoc assembly.

### 3. Session parity becomes a first-class missing surface

The repository must stop implicitly treating:

- `dashboard`
- `log`
- hidden `trace`
- hidden `inspect`

as equivalent to a public `Session View` parity story.

Instead, the design must explicitly define:

- what the public CLI equivalent of `Session View` is
- whether it is a dedicated command, a mode of an existing command, or a snapshot sub-surface
- how transcript escalation is represented without collapsing Level 2 into Level 3

### 4. Hidden commands must not silently carry the public parity story

If a surface is part of the intended human CLI parity model, it should not remain hidden forever.

This does not force immediate un-hiding of:

- `inspect`
- `context`
- `trace`

But it does require the repository to decide whether each command is:

- a public product surface
- a debug / forensic surface
- or an implementation aid that should not be cited as parity support

## Explicit non-goals

This ADR does not require:

- redesigning `status`
- replacing the current operation dashboard query service immediately
- removing hidden forensic commands
- implementing arbitrary configurable screen or CLI layouts
- implementing full operator-load or multi-agent modeling before stronger substrate exists

## First implementation tranche

### P0

1. Complete fleet parity through `ADR 0115`.
2. Add a normalized `operation_brief` display block to the shared one-operation payload.
3. Add a normalized `session_brief` display block to the shared one-operation payload or a
   dedicated session-facing query path.
4. Define a public CLI parity story for `Session View`.
5. Separate public parity surfaces from hidden forensic/debug surfaces in docs and implementation
   notes.

### P1

1. Add a textual CLI snapshot surface per level where it materially improves parity:
   - fleet snapshot
   - operation snapshot
   - session snapshot
2. Reassess whether `inspect`, `context`, and `trace` should remain hidden once public parity shape
   is clearer.

## Implementation checklist

1. **Finish the fleet tranche from `ADR 0115`**
   - dedicated fleet workbench projection
   - CLI/TUI shared fleet rendering truth

2. **Normalize operation-level display semantics**
   - add `operation_brief` to the shared one-operation payload
   - keep deeper task/session/event payloads in the same query path for now

3. **Normalize session-level display semantics**
   - add `session_brief`
   - make session timeline / selected-event semantics explicit in shared payload shape

4. **Define the public CLI Level 2 story**
   - choose whether `Session View` parity is delivered via:
     - new command
     - new mode / flag on an existing command
     - or another explicit public surface

5. **Audit command visibility**
   - decide whether current hidden commands are:
     - public parity surfaces
     - debug-only surfaces
     - or transitional implementation aids

6. **Update documentation only after the parity story is explicit**
   - avoid citing hidden commands as if they were normal public workflow surfaces

## Verification criteria

This ADR is materially satisfied only when all of the following are true:

1. `Fleet` has one shared normalized projection used by CLI and TUI.
2. `Operation View` semantics can be rendered from a normalized shared `operation_brief` block.
3. `Session View` semantics can be rendered from a normalized shared `session_brief` block.
4. There is an explicit public CLI path for Level 2 session supervision.
5. Repository docs no longer overstate parity by relying on hidden commands or compositional
   workarounds.

## Verification Notes (2026-04-10)

Repository evidence for parity closure now exists in three layers:

- `Fleet` parity through the shared fleet workbench projection from `ADR 0115`
- normalized `operation_brief` and `session_brief` payload blocks in the shared one-operation
  dashboard/query path
- a public task-addressed `operator session OP --task TASK` surface documented in
  [docs/reference/cli.md](/Users/thunderbird/Projects/operator/docs/reference/cli.md)

Focused tests now cover:

- operation-brief payload semantics
- public session command snapshot/json/follow behavior
- TUI consumption of normalized operation/session semantics
