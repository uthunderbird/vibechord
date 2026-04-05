# ADR 0024: Effective Control Context CLI Surface

## Status

Accepted

## Context

Recent slices made project profiles, policy memory, involvement levels, `watch`, `agenda`, and
durable work-state surfaces first-class parts of the operator control plane.

Those pieces are individually inspectable, but the answer to:

- which profile defaults launched this operation
- which policy scope applies
- which active policy entries currently steer it
- and what runtime control state is in effect now

still requires hopping across multiple commands such as `project resolve`, `policy list`,
`inspect`, and `report`.

That fragmentation weakens the vision requirement that operator behavior remain transparent and
inspectable from the CLI.

## Decision

`operator` will expose a first-class `context` command for one operation.

The command is an operation-centric effective control-plane view built from persisted operation
truth. It will surface:

- objective and harness context that steer orchestration
- current runtime control state such as run mode, scheduler state, focus, and involvement level
- the persisted project profile name and resolved profile config used at launch when available
- the resolved policy scope
- and the currently active policy entries carried on operation state

The command complements rather than replaces:

- `inspect` for mixed operational summary plus forensic links
- `report` for narrative handoff
- `trace` for forensic detail
- `project resolve` for standalone profile resolution
- and `policy list` / `policy inspect` for direct policy inventory

## Alternatives Considered

### Option A: Keep reconstructing context from existing commands

Rejected because it keeps the effective control basis fragmented and harder to inspect quickly.

### Option B: Expand `inspect` again instead of adding a dedicated surface

Rejected because `inspect` already spans brief, report, commands, and optional forensic detail.
Adding another dense block there would blur its purpose rather than creating a clean default view.

### Option C: Add a dedicated `context` surface

Accepted because it keeps the inspection model operation-centric while making the active control
basis explicit and easy to consume in either human-readable or JSON form.

## Consequences

- Users get one concise view of the profile, policy, and runtime control truth steering an
  operation.
- Future TUI or dashboard work can reuse the same effective-context projection instead of
  recomputing it ad hoc.
- The command deliberately reports persisted resolved profile context used by the operation rather
  than silently re-resolving current on-disk profile files.
- This ADR does not define richer policy applicability matching, profile authoring, or policy
  supersession UX.
