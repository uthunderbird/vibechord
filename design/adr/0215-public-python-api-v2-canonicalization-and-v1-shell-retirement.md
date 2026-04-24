# ADR 0215: Public Python API v2 Canonicalization And v1 Shell Retirement

- Date: 2026-04-24

## Decision Status

Proposed

## Implementation Status

Planned

## Context

The repository is not only a CLI application. It is also a Python package with public embedding
surfaces, including top-level exports and the documented SDK.

The v2 ADR tranche already covers command/query parity and delivery surfaces, but it does not yet
fully answer the Python API cutover question:

- should `OperatorService` remain public
- should `OperatorServiceV2` become the canonical public service shell
- should callers prefer `OperatorClient` or another higher-level API
- which top-level exports remain stable after v1 retirement

Without an explicit ADR, the repository can delete large parts of legacy CLI/runtime behavior while
still keeping v1 shell concepts load-bearing through imports and embedding examples.

## Decision

The repository adopts one canonical public Python API for v2 and retires v1 shell exposure.

The final v2 Python API contract must define:

1. **Canonical embedding surface**
   - which public API is recommended for external Python callers
   - whether that surface is `OperatorClient`, `OperatorServiceV2`, or another named facade

2. **Retired v1 shell surface**
   - whether `OperatorService` is removed, hidden from top-level exports, or retained only as a
     migration alias with a named retirement condition

3. **Top-level export policy**
   - which symbols remain exported from `agent_operator.__init__`
   - which symbols are explicitly non-public even if importable by path

4. **Surface boundary**
   - the difference between machine-facing SDK/query APIs and internal composition/service shells

## Required Properties

- Public docs name one canonical Python entrypoint family for v2.
- Top-level exports do not keep v1 shell semantics alive by accident.
- Public examples and tests use the declared canonical surface.
- Any retained compatibility alias has an explicit retirement condition and is not load-bearing for
  normal v2 usage.
- Python API cutover is coordinated with CLI/MCP parity claims from ADR 0207 and legacy-removal
  rules from ADR 0209.

## Verification Plan

- public import/export tests for the accepted API surface
- docs and examples search showing they use the canonical v2 Python surface
- regression tests proving v2-only operations can be controlled and queried through the declared
  public Python contract
- one explicit check that removed or retired v1 shell exports are no longer documented as stable

## Related

- ADR 0194
- ADR 0204
- ADR 0207
- ADR 0209
