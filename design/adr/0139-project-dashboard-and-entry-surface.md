# ADR 0139: Project dashboard and entry surface

- Date: 2026-04-10

## Status

Accepted

## Implementation Status

Implemented

Skim-safe current truth on 2026-04-10:

- `implemented`: `operator project create` and `operator project dashboard` already exist as the
  active-entry commands of the project subgroup
- `implemented`: `project create` remains explicit profile mutation that writes profile defaults and
  returns the written profile path
- `implemented`: `project dashboard` remains a project-scoped supervisory entry surface with
  snapshot/live workflow support rather than a profile editor or run replacement
- `verified`: focused CLI coverage for `project create` and the `project dashboard` command
  entrypoint now exists in `tests/test_project_cli.py`
- `verified`: dashboard payload assembly remains covered in
  `tests/test_operation_project_dashboard_queries.py`
- `partial`: RFC 0014 remains draft, so broader family-example closure beyond this landed slice is
  still incomplete

## Commands Covered

- `operator project create`
- `operator project dashboard`

## Not Covered Here

- project read-side inspection commands
- top-level `operator init`
- top-level `operator run`

## Context

The project subgroup now contains two commands with very different jobs:

- author or update a named profile
- supervise a project-scoped workbench

Older ADRs cover the profile lifecycle and the live project dashboard separately, but RFC 0014 now
puts both in one visible project subgroup and requires the product relationship between them to be
clear.

## Decision

The CLI should treat `project create` and `project dashboard` as the two active-entry commands of
the project subgroup.

### `project create`

`project create` remains the explicit named-profile authoring or update command.

It is a mutation surface, not a first-run shell replacement and not a dashboard entry.

### `project dashboard`

`project dashboard` remains the live project-scoped workbench.

It should aggregate project-scoped truth without becoming:

- a second fleet
- a second run command
- or a profile editor

## Relationship Rule

The accepted user story is:

- use `project create` to define a reusable project entry
- use `project dashboard` to supervise project-scoped current state

These commands belong to the same subgroup, but they do not form one uniform output class.

## Consequences

Positive:

- the visible project subgroup gets cleaner internal structure
- RFC 0014 examples for `project create` and `project dashboard` gain one ADR owner

Tradeoffs:

- mutation and dashboard commands share a subgroup but remain behaviorally different

## Verification

Current evidence for the landed slice:

- `verified`: `project create` remains explicit profile mutation
- `verified`: `project dashboard` remains project-scoped supervision/workbench output
- `verified`: neither command silently absorbs the job of `init`, `run`, or `project resolve`

The repository should preserve these conditions:

- `project create` remains explicit profile mutation
- `project dashboard` remains project-scoped supervision/workbench output
- neither command silently absorbs the job of `init`, `run`, or `project resolve`

## Related

- [ADR 0030](./0030-live-project-dashboard-cli-surface.md)
- [ADR 0094](./0094-run-init-project-create-workflow-and-project-profile-lifecycle.md)
- [RFC 0014](../rfc/0014-cli-output-contract-and-example-corpus.md)
