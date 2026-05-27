# ADR 0002: Shared Delivery Surface Contracts

- Date: 2026-05-23

## Decision Status

Accepted

## Implementation Status

Verified

Scope: CLI, REST, SDK, MCP tools/resources/prompts, and pure-TUI first slice.

## Context

`vibechord` needs CLI, TUI, REST, SDK, and MCP surfaces. If each surface
resolves operations, applies commands, and builds status independently,
behavior will drift.

## Decision

CLI, TUI, REST, SDK, and MCP are delivery adapters over shared application
command/query contracts.

Surface-specific rendering is allowed. Surface-specific business authority is
not.

## Required Properties

- One operation resolver.
- One command application path.
- One projection/read path through `ProjectionService`.
- One fleet read-model contract.
- One live-feed envelope family.
- Stable machine-facing error codes for CLI JSON and REST.

## Consequences

### Positive

- REST becomes a remote programmatic surface rather than a second runtime.
- TUI actions can be tested through the same command semantics as CLI.
- Cross-surface parity tests can catch drift early.

### Negative

- Surface implementation must wait for shared payloads and command contracts.
- Some UI-specific shortcuts are disallowed if they bypass the application
  layer.

## Verification Plan

- Scenario coverage: VS-005, VS-006, VS-007, and VS-008 in
  [VERIFICATION-SCENARIOS.md](../VERIFICATION-SCENARIOS.md).
- Delivery parity tests for operation resolution.
- CLI/TUI/REST/SDK/MCP command routing tests.
- Shared fleet/status payload tests.
- REST endpoint tests that assert application command/query delegation.
