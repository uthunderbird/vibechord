# Implementation-Ready Design Red Team

Status: `complete`

Target artifacts:

- `design/VISION.md`
- `design/ARCHITECTURE.md`
- `design/CLI-VISION.md`
- `design/TUI-VISION.md`
- `design/REST-API-VISION.md`
- `design/adr/0001` through `0006`
- `design/plans/0001` through `0004`

## Method

This pass checked whether a developer could start implementation without
guessing the owner of canonical state, the command/query boundary, delivery
surface behavior, REST safety defaults, or verification gates.

## Findings

### P0: Superseded Architecture Draft Created Dual Authority

`ARCHITECTURE.md` is now the implementation authority, but the repository still
contained `ARCHITECTURE-DRAFT.md` with old design text. That created a direct
risk of implementers following stale choices.

Resolution: `ARCHITECTURE-DRAFT.md` now explicitly points to
`ARCHITECTURE.md` and is marked `superseded`.

### P1: Vision Understated REST as a First-Class Surface

The product vision still emphasized CLI/TUI/future SDK and did not make REST
part of the parity target.

Resolution: `VISION.md` now names CLI, TUI, and REST as shared-contract
surfaces and adds first implementation targets.

### P1: REST Vision Needed Versioning, Error, Cursor, and Local-Only Rules

The REST vision named endpoint families but left out enough contract detail to
invite implementation drift.

Resolution: REST now starts under `/v1`, requires idempotency for mutating
calls, maps errors from shared application errors, uses sequence cursors for
events, and binds locally by default until exposure safety exists.

### P1: CLI and TUI Visions Needed Acceptance Gates

The CLI and TUI visions described capabilities but did not state enough
verification gates for first implementation.

Resolution: CLI now has initial exit-code and JSON error contracts. TUI now has
an initial key model, first slice, and reducer/render/command-dispatch
acceptance gates.

### P1: REST Deserved Its Own ADR

ADR 0002 covers shared delivery surfaces, but REST is new and externally
exposed enough to need its own durable decision record.

Resolution: ADR 0006 records REST as a versioned delivery adapter with
idempotency, cursor, error, live-feed, and local-binding requirements.

## Residual Risk

The documents are ready to guide implementation, but runtime claims remain
`planned` until code and tests exist. Authentication strategy, exact CLI command
names for verification rails, and machine-readable E2E summary schema remain
tracked in backlog.
