# ADR 0208: Runtime, Session, Permission, and Process-Manager v2 Canonicalization

- Date: 2026-04-23

## Decision Status

Proposed

## Implementation Status

Planned

## Context

The runtime layer produces session facts, permission requests, process signals, wakeups, supervisor
state, and crash recovery observations. v2 correctness depends on these facts reaching canonical
events and read models quickly enough for CLI/TUI/MCP/SDK consumers and the brain.

## Decision

Runtime coordination facts that affect operation behavior become event/projector-backed v2
contracts.

Covered facts:

- session created/started/waiting/terminal
- execution registered/linked/observed state
- permission observed/decided/escalated/followup-required
- supervisor background task state
- wakeups and orphan recovery
- process signals and cancellation requests

## Required Properties

- Brain decisions see relevant runtime facts through replay-derived state.
- TUI/live surfaces receive session and permission events promptly.
- Restart/crash recovery is event-driven where behavior depends on the fact.
- Codex rejection or escalation wakes replacement-instruction flow when required.
- Runtime caches remain ephemeral unless explicitly materialized as domain events.

## Verification Plan

- restart/crash recovery tests with v2-only fixtures.
- permission approve/reject/escalate/needs_human tests.
- Codex post-denial follow-up regression.
- TUI session timeline receives permission/session events.
- orphan detection produces replayable state transitions.

## Related

- ADR 0082
- ADR 0084
- ADR 0196
- ADR 0200
- ADR 0201
- ADR 0202
