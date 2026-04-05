# ADR 0030: Add A Live Project Dashboard CLI Surface

## Status

Accepted

## Context

`operator` now has strong operation-centric and fleet-centric product surfaces:

- `run --project ...` for project-scoped launch
- `project inspect` and `project resolve` for declarative project defaults
- `fleet --project ...` for project-filtered operation triage
- and `policy list --project ...` for explicit project-local policy memory

Those pieces are individually useful, but they still leave a product-level gap.

For normal day-to-day use, there is still no single project-scoped workbench that answers:

- what this project's resolved run defaults are
- which active reusable policies currently shape work in this project
- what work is running or needs attention now
- and which next operator commands are most relevant

That weakens the "project profile as real entrypoint" story from ADR 0018 and leaves the product
feeling more like a bag of adjacent commands than a coherent harness.

The architecture already rejects hidden dashboard-only state, so any project-level workbench must
remain a thin projection over persisted truth that already exists.

## Decision

`operator` will expose a first-class `project dashboard` CLI command.

The command is a live project-scoped workbench built from existing persisted truth:

- the project profile YAML
- the resolved run configuration derived from that profile
- active project-local policy entries
- and the existing agenda / fleet projection filtered to the target project

Initial scope:

- one project profile at a time
- one-shot rich rendering or a live polling view
- JSON snapshot output for tooling
- and suggested commands that point back to existing run, project, policy, fleet, and operation
  surfaces

The command does not introduce:

- a new store
- hidden project-dashboard state
- or a second cross-operation classification path separate from `agenda` / `fleet`

## Alternatives Considered

- Option A: keep composing `project inspect`, `project resolve`, `fleet --project`, and
  `policy list` manually
- Option B: add a broader TUI shell next
- Option C: add a thin live project dashboard over existing truth

Option A was rejected because it preserves the current product fragmentation at the exact point
where project profiles are supposed to become a practical entrypoint.

Option B was rejected because it is a larger delivery slice than needed and would increase surface
area before the thinner project-level read model is proven.

Option C was accepted because it closes the project-entrypoint gap with minimal architectural risk.

## Consequences

- Project profiles become a more credible product entrypoint instead of only a config container.
- The CLI gains a coherent project-scoped workbench without changing runtime semantics.
- Future TUI work can reuse the same project payload rather than inventing a dashboard-only model.
- This ADR does not define project creation wizards, project-only control semantics, or a generic
  home screen across multiple projects.
