# ADR 0215: Public Python API v2 Canonicalization And v1 Shell Retirement

- Date: 2026-04-24

## Decision Status

Accepted

## Implementation Status

Verified

Implementation grounding on 2026-04-26:

- `implemented`: the package-root public API now exports only `OperatorClient`, so the documented
  SDK surface is also the only root-level stable embedding surface. Evidence:
  `src/agent_operator/__init__.py`.
- `implemented`: the public Python SDK reference now names `agent_operator.OperatorClient` as the
  stable entrypoint and uses the package-root import in its example. Evidence:
  `docs/reference/python-sdk.md`.
- `implemented`: `OperatorService` remains available only by internal or advanced import paths such
  as `agent_operator.application.service`; it is no longer kept public accidentally through package
  root exports.
- `verified`: package-root export coverage now asserts that `agent_operator.__all__` contains only
  `OperatorClient` and that `OperatorService` and `build_service` are absent from the package root.
  Evidence: `tests/test_client.py::test_agent_operator_package_root_exports_only_operator_client`.
- `verified`: existing SDK regressions continue to prove that the canonical public surface controls
  and queries v2-only operations. Evidence:
  `tests/test_client.py::test_operator_client_resolves_v2_only_operation_reference`,
  `tests/test_client.py::test_operator_client_stream_events_reads_canonical_v2_operation_events`,
  and the full repository suite at the repository state closing this ADR.

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
   - external Python callers use `agent_operator.OperatorClient`
   - `OperatorClient` is the stable machine-facing facade for run, query, control, and stream
     operations

2. **Retired v1 shell surface**
   - `OperatorService` is not a package-root public export
   - it may remain importable by internal or advanced module path while repository internals still
     use it, but it is not part of the stable public package-root contract

3. **Top-level export policy**
   - `agent_operator.__init__` exports only `OperatorClient`
   - composition helpers such as `build_service` and shell types such as `OperatorService` are
     non-public at package root even if importable by path

4. **Surface boundary**
   - `OperatorClient` is the machine-facing SDK boundary
   - bootstrap assembly and service shells remain internal composition surfaces rather than stable
     package-root API

## Required Properties

- Public docs name one canonical Python entrypoint family for v2.
- Top-level exports do not keep v1 shell semantics alive by accident.
- Public examples and tests use the declared canonical surface.
- Python API cutover is coordinated with CLI/MCP parity claims from ADR 0207 and legacy-removal
  rules from ADR 0209.

## Verification Plan

Recorded local verification on 2026-04-26:

- `uv run pytest tests/test_client.py -k "package_root_exports_only_operator_client or resolves_v2_only_operation_reference or stream_events_reads_canonical_v2_operation_events"`
- `uv run pytest`

## Related

- ADR 0194
- ADR 0204
- ADR 0207
- ADR 0209
