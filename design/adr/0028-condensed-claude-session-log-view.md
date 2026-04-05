# ADR 0028: Expose A Condensed Claude Session Log View

## Status

Accepted

## Context

The repo already exposes strong operation-centric control surfaces:

- `watch` for live attached-state follow
- `dashboard` for a one-operation workbench
- and `codex-log` for Codex-specific transcript drill-down

That still leaves an asymmetry in the product story.

Claude is a first-class adapter target in the vision, but Claude-backed ACP runs still
require the user to find and inspect raw Claude log files directly when they need
more detail than the normal operation summaries provide.

That weakens the CLI-first transparency story exactly where the product is supposed to make
heterogeneous agents feel equally operator-friendly.

## Decision

`operator` will expose a first-class `claude-log` CLI command for `claude_acp` sessions.

The command will:

- start from an `operation_id`
- resolve the persisted `claude_acp` session and its recorded log path
- parse a condensed subset of the Claude headless stream-json log
- and render a human-readable drill-down by default

Initial scope:

- one operation at a time
- `--limit` for bounded history
- `--follow` for tail-like live viewing
- `--json` for machine-readable output

The command remains a thin drill-down over the authoritative upstream Claude ACP log.
It does not copy the full transcript into operator-owned persistence.

## Alternatives Considered

- Option A: keep using the raw `.operator/claude/*.log` file directly
- Option B: copy the full Claude transcript into operator-owned trace state
- Option C: add a condensed operation-keyed Claude log view

Option A was rejected because it makes Claude-backed runs materially less inspectable than
Codex-backed runs from the CLI.

Option B was rejected because it duplicates a large upstream log and weakens the boundary between
operator truth and adapter-owned evidence.

Option C was accepted because it improves transparency parity while preserving the thin-projection
rule already used elsewhere in the runtime.

## Consequences

- Claude-backed ACP runs gain an operation-keyed drill-down surface that matches the existing CLI-first
  control-plane story more closely.
- The product becomes more honest about heterogeneous agent support instead of making deep
  inspection feel Codex-only.
- Claude-specific log parsing remains localized to runtime/CLI code.
- This ADR does not yet define equivalent drill-down surfaces for every adapter or a generic
  session-log abstraction across adapters with incompatible upstream evidence shapes.
