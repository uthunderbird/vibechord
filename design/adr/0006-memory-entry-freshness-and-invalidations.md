# ADR 0006: Memory Entry Freshness And Invalidation

## Status

Accepted

## Context

ADR 0005 established that long-lived work in `operator` should rely on stratified memory rather than transcript replay.

That direction is necessary, but not sufficient.

Without explicit freshness and invalidation semantics, a `MemoryEntry` can become:

- well-structured,
- portable across sessions,
- and still wrong.

The main failure mode is stale continuity:

- an earlier artifact or transcript is summarized into memory,
- later work supersedes or contradicts that state,
- the operator continues from the old summary,
- and the system behaves coherently on top of obsolete information.

This ADR defines the minimum semantics required for `MemoryEntry` so that memory can be reused across long-lived work without pretending all summaries are equally trustworthy forever.

## Decision

`MemoryEntry` is a derived, provenance-backed state object with explicit freshness and invalidation semantics.

It is not a freeform note and not a canonical source of truth on its own.

### 1. Memory entries are derived state

A memory entry must be understood as a compact derivative of one or more sources, not as a primary authority.

Primary authorities remain:

- artifacts,
- explicit decisions,
- source documents,
- and raw transcripts where needed for audit.

Memory exists to support continuity, not to replace the need for traceability.

### 2. Every memory entry must carry provenance

At minimum, a memory entry must reference the sources from which it was derived.

The model should support one or more source references such as:

- artifact ids,
- run ids,
- iteration ids,
- session ids,
- or other durable source handles.

If a memory entry cannot answer "what evidence produced this?", it should not be treated as durable orchestration memory.

### 3. Every memory entry must carry freshness state

Freshness is explicit, not inferred.

The minimum accepted freshness states are:

- `current`
- `stale`
- `superseded`

Interpretation:

- `current`
  The best known distilled state for its intended scope.
- `stale`
  Potentially outdated due to later work, but not yet replaced by a newer entry.
- `superseded`
  Explicitly replaced or invalidated by a later entry or artifact and should not drive new decisions.

### 4. Supersession must be explicit

The system should be able to represent that one memory entry was replaced by another memory entry or invalidated by a later artifact or decision.

The minimal model should support:

- `superseded_by`
- and an optional reason or cause

The operator should not be forced to infer supersession only from timestamps.

### 5. Scope is part of meaning

Freshness is only meaningful relative to scope.

A memory entry should be scoped to one of:

- objective-level memory
- task-level memory
- session-level snapshot memory

The system should not treat one global memory pool as if all entries compete for the same freshness status.

### 6. Memory reuse rule

Only `current` memory entries should be treated as normal reusable context for future orchestration.

`stale` memory may still be shown for audit or recovery, but should not be injected as trusted current context without revalidation.

`superseded` memory should be excluded from normal continuation context.

## Non-Goals

This ADR does not define:

- exact storage schema,
- exact database or file layout,
- compaction algorithms,
- summarization prompts,
- or event-driven invalidation triggers.

Those may vary by implementation as long as they preserve the semantic contract here.

## Alternatives Considered

### Option A: Treat memory entries as lightweight notes with no formal freshness model

Rejected because:

- it allows silent reuse of obsolete summaries,
- weakens auditability,
- and makes long-lived continuity unreliable.

### Option B: Use timestamps only and infer freshness implicitly

Rejected because:

- latest is not always authoritative,
- timestamps do not encode contradiction or replacement,
- and the operator needs to know whether a memory entry is merely old or actually invalidated.

### Option C: Require provenance, explicit freshness state, and supersession links

Accepted because:

- it is the smallest mechanism set that makes memory auditable and reusable,
- it supports compaction without pretending summaries are permanent truth,
- and it fits both file-backed and richer future persistence layers.

## Consequences

### Positive

- Long-lived memory becomes auditable instead of purely narrative.
- Reuse of stale summaries becomes a visible state problem rather than a hidden prompt problem.
- Future memory compaction and task continuation can share one minimal semantic contract.

### Negative

- `MemoryEntry` becomes more structured and less casual.
- Implementations must track source references and status transitions explicitly.
- Simple append-only note-taking is no longer enough for durable orchestration memory.

### Follow-Up Implications

- `design/ARCHITECTURE.md` should reference this ADR from the memory section.
- Future event and wakeup semantics should define when entries become `stale` or `superseded`.
- Any future memory implementation should expose enough metadata for debugging and inspection in the CLI.
