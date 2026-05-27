# Plan 0004: Release Readiness

Status: `complete`

## Goal

Prepare `vibechord` for its first public pre-release.

## Scope

- Public docs.
- CLI reference.
- REST API reference.
- TUI guide.
- Verification matrix.
- Known limitations.
- Packaging and distribution.

## Dependencies

- Plan 0001 and Plan 0002 exit gates.
- Plan 0003 only for whichever real adapters are claimed in the release.
- All ADR implementation statuses updated to match evidence.

## Work Items

1. Write public quickstart.
2. Generate or hand-maintain CLI reference.
3. Write REST API reference with schemas.
4. Write TUI workbench guide.
5. Publish verification matrix tied to `TESTING-RAILS.md`.
6. Record known limitations and planned follow-up work.
7. Run full local verification and E2E fake harness.

## Verification

- VS-012 architecture fitness scenarios.
- VS-013 release verification scenarios.
- Full local verification command.
- E2E fake harness artifacts.
- Red-team pass on release docs.

## Exit Gate

The release may only describe behavior as implemented when the verification
matrix links each claim to tests, E2E artifacts, or an explicit manual
verification note.
