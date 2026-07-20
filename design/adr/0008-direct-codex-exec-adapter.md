# ADR 0008: Direct Codex Exec Adapter

- Date: 2026-07-20

## Decision Status

Accepted

## Implementation Status

Verified

## Context

Some supervised operations need one fresh Codex turn but do not need ACP
sessions, a second LLM brain, provider-neutral continuation, or adapter-owned
process-group authority. Configuring the generic process adapter with a Codex
command would hide vendor-specific JSONL, final-message, sandbox, and failure
semantics inside an opaque argv string.

## Decision

Provide a dedicated `CodexExecAdapter` behind the existing synchronous
`AgentAdapter` protocol and a deterministic `SingleAgentBrain`.

The adapter:

- receives immutable launcher-validated paths, environment, model, and network
  policy;
- invokes one absolute Codex executable with `exec --ephemeral --json`;
- explicitly disables ambient user configuration and optional features;
- inherits its enclosing process group rather than creating a new one;
- drains stdout and stderr concurrently;
- validates and bounds JSONL, stderr, and final-message artifacts;
- exposes terminal execution facts without claiming that the operation's
  domain goal was achieved; and
- never retries, resumes, detaches, or falls back to another adapter.

The deterministic brain invokes the configured agent exactly once and maps one
successful result to operation completion. Whole-operation cancellation,
timeouts, descendant cleanup, executable attestation, and higher-level semantic
postconditions remain responsibilities of the enclosing supervisor.

## Consequences

### Positive

- One-turn Codex execution does not require ACP or another LLM decision.
- Vendor-specific evidence and failure rules stay out of the core loop.
- Existing operation events and budgets remain the execution ledger.
- The adapter cannot silently select ambient executables or configuration.

### Negative

- The first implementation has terminal, not live typed, adapter updates.
- Independent mid-turn cancellation is unavailable; cancellation is by the
  enclosing process supervisor.
- The adapter is intentionally unsuitable for session continuation and
  concurrent multi-agent orchestration.

## Verification

`tests/test_core.py` covers the deterministic one-call policy, valid JSONL and
final-message handling, malformed JSONL rejection, terminal receipts, and an
end-to-end operation loop using a fake Codex executable. A real provider smoke
test remains an integrator-owned release check because it requires credentials
and network access.
