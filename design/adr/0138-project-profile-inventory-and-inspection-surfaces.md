# ADR 0138: Project profile inventory and inspection surfaces

- Date: 2026-04-10

## Status

Accepted

## Implementation Status

Implemented

Skim-safe current truth on 2026-04-10:

- `implemented`: `operator project list`, `operator project inspect`, and
  `operator project resolve` already exist as the project-profile read-side CLI family
- `implemented`: all three commands default to human-readable output and expose machine-readable
  payloads only under `--json`
- `implemented`: current CLI docs already describe this family in `docs/reference/cli.md`
- `verified`: focused CLI coverage for inventory vs inspect vs resolve now exists in
  `tests/test_project_cli.py`
- `partial`: RFC 0014 remains draft, so broader family-example closure beyond this landed slice is
  still incomplete

## Commands Covered

- `operator project list`
- `operator project inspect`
- `operator project resolve`

## Not Covered Here

- `operator project create`
- `operator project dashboard`
- top-level `operator init`

## Context

The repository already has older ADR authority for project profiles and profile authoring, but RFC
0014 exposes a narrower current gap:

- project-profile read surfaces need one clear public CLI owner
- they must produce human-readable output by default
- they must remain meaningfully distinct from each other

Without a dedicated ADR here, `project list`, `project inspect`, and `project resolve` risk
remaining implementation-shaped rather than product-shaped.

## Decision

The CLI should treat project-profile inventory and inspection as one coherent read-side family.

### `project list`

`project list` remains the inventory surface for available profiles.

### `project inspect`

`project inspect` remains the human-readable inspection surface for one profile's declared content.

### `project resolve`

`project resolve` remains the human-readable inspection surface for effective resolved run defaults.

It is not the same as raw profile inspection.

## Distinction Rule

These commands should remain clearly separable:

- `list`: available profile inventory
- `inspect`: declared profile content
- `resolve`: effective run defaults after resolution/precedence

All three should be human-readable by default and machine-readable only under `--json`.

## Consequences

Positive:

- profile read surfaces become easier to explain and test as a family
- RFC 0014 project-read examples gain an explicit ADR owner

Tradeoffs:

- the CLI must preserve the inspect-vs-resolve distinction even when output fields overlap

## Verification

Current evidence for the landed slice:

- `verified`: `project list` remains inventory-shaped in both default and `--json` modes
- `verified`: `project inspect` defaults to human-readable declared-profile inspection
- `verified`: `project resolve` defaults to human-readable effective-default inspection rather than
  raw profile serialization

The repository should preserve these conditions:

- `project inspect` and `project resolve` do not default to raw JSON
- `project resolve` clearly represents effective defaults rather than literal YAML content
- `project list` remains inventory-shaped

## Related

- [ADR 0018](./0018-project-profile-schema-and-override-model.md)
- [ADR 0025](./0025-project-profile-init-cli-surface.md)
- [ADR 0094](./0094-run-init-project-create-workflow-and-project-profile-lifecycle.md)
- [RFC 0014](../rfc/0014-cli-output-contract-and-example-corpus.md)
