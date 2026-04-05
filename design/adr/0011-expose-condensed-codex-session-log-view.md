# ADR 0011: Expose A Condensed Codex Session Log View

## Status

Accepted

## Context

`operator` already persists its own briefs, reports, trace records, and raw log references.
For Codex-backed work, the most detailed live execution record still lives in the upstream
Codex session transcript under `~/.codex/sessions/...jsonl`.

That transcript is valuable, but it is too noisy to serve directly as the normal inspection
surface for an `operator` run:

- it mixes full prompts, tool payloads, token counters, and low-level protocol items,
- it is keyed by Codex session id rather than `operator` operation id,
- and it is difficult to skim during a live run.

We need a repository-local way to follow the important events from that transcript by starting
from an `operator` operation id.

## Decision

Add a dedicated CLI drill-down surface:

- `operator codex-log <operation-id>`

This command will:

- resolve the attached `codex_acp` session from the persisted `OperationState`,
- locate the matching transcript file under `~/.codex/sessions/...`,
- parse only a condensed subset of important events,
- and render them in a human-readable form by default.

The command will also support:

- `--follow` for tail-like live viewing,
- `--limit` for bounded history,
- `--json` for machine-readable output,
- and `--codex-home` for tests or non-default Codex homes.

The condensed view is intentionally not a replacement for the full Codex transcript.
It is a curated operator-facing drill-down surface over the authoritative upstream log.

## Alternatives Considered

### Option A: Keep using only the raw `~/.codex/...jsonl` file

Rejected.

This keeps the system simpler, but it forces users to know the Codex session id, the transcript
path shape, and the low-level event schema.

### Option B: Copy the full Codex transcript into the operator trace store

Rejected.

This would duplicate a large vendor-owned log, widen storage costs, and blur the distinction
between operator traceability and upstream evidence.

### Option C: Expose a condensed Codex log view keyed by operation id

Accepted.

This preserves the upstream transcript as the evidence source while giving `operator` a practical
inspection surface that is aligned with its own operation-centric UX.

## Consequences

- `operator` gains a more useful live drill-down tool for Codex-backed runs.
- The full Codex transcript remains the underlying evidence source.
- Codex-specific transcript parsing remains localized to runtime/CLI code rather than leaking into
  the operator core.
- The CLI surface grows slightly and now depends on the stable enough subset of Codex transcript
  event shapes that we condense.
