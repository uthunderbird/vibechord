# ADR 0030: Expose A Condensed Claude Session Log View

## Status

Accepted

## Context

`operator` already treats `claude_acp` as the canonical Claude adapter and already persists the
runtime truth needed to reach the underlying Claude log:

- `OperationState` stores the Claude session handle
- the Claude headless adapter persists a stable `log_path`
- `trace` and `dashboard` already point users toward raw-log-backed inspection

That still leaves a product gap relative to the accepted operator workbench story.

Codex-backed runs already have an operation-keyed condensed transcript drill-down via
`operator codex-log <operation-id>`.
Claude-backed runs still require opening the raw `.operator/claude/*.log` file directly and
understanding vendor-shaped stream-json events.

That asymmetry weakens the multi-adapter product story even though the persisted truth is already
available.

## Decision

Add a dedicated Claude drill-down surface:

- `operator claude-log <operation-id>`

The command will:

- resolve the attached `claude_acp` session from persisted `OperationState`
- read the authoritative headless stream-json log using the persisted `log_path`
- condense only the high-value event classes
- render a human-readable view by default

The command also supports:

- `--follow` for tail-like live viewing
- `--limit` for bounded history
- `--json` for machine-readable output

The condensed view remains a projection over the authoritative Claude log rather than a copied
transcript store.

## Alternatives Considered

- Option A: rely only on the raw Claude stream-json log file
- Option B: copy the full Claude transcript into operator-owned trace storage
- Option C: expose a condensed Claude log view keyed by operation id

Option A was rejected because it keeps the product asymmetric and forces users to inspect
vendor-shaped raw logs directly.

Option B was rejected because it duplicates upstream evidence and expands operator-owned state
without improving the core product contract.

Option C was accepted because it closes the user-visible parity gap with the smallest honest
surface over already persisted truth.

## Consequences

- Claude-backed runs gain the same style of operation-centric transcript drill-down already
  available for Codex-backed runs.
- The full Claude ACP log remains the evidence source of truth.
- Claude-specific transcript parsing stays localized to runtime/CLI code.
- The CLI surface grows slightly and now depends on a stable enough subset of Claude headless
  event shapes.
