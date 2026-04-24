# ADR 0207: Delivery Surface Parity Contract

- Date: 2026-04-23

## Decision Status

Proposed

## Implementation Status

Planned

## Context

`operator` exposes overlapping capabilities through CLI, TUI, MCP, and Python SDK. Without a
delivery parity contract, each surface can implement its own resolver, command path, error shape,
and read projection. That creates drift and hides v2 bugs in one surface while another works.

## Decision

CLI, TUI, MCP, and Python SDK are delivery adapters over shared application command/query
contracts.

The parity matrix covers:

- run
- status
- list
- answer
- cancel
- interrupt
- stream/watch
- session/log
- attention/task inspection

## Required Properties

- One operation resolver contract.
- One command application contract.
- One query/read-model contract.
- Surface-specific rendering is allowed; surface-specific authority is not.
- Error codes and JSON schema fields are stable and documented for machine-facing surfaces.

## Verification Plan

- cross-surface contract tests for operation id resolution.
- cross-surface command tests for answer/cancel/interrupt.
- MCP and SDK tests use v2-only operation fixtures.
- CLI/TUI/MCP/SDK status outputs agree on status, attention, session, and permission facts.
- public docs list parity guarantees and intentional gaps.

## Related

- ADR 0145
- ADR 0146
- ADR 0161
- ADR 0204
- ADR 0205
- ADR 0206
