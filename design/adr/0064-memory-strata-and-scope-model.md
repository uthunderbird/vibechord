# ADR 0064: Memory strata and scope model

## Status

Accepted

## Context

`ARCHITECTURE.md` (Memory Layers section) describes four named memory strata:

1. **Turn context** — immediate context for the current brain decision
2. **Session snapshot** — short summary of one agent session
3. **Task memory** — distilled memory for continuing one task independent of any vendor session
4. **Objective memory** — distilled memory for the overall long-lived goal

Plus a fifth cross-cutting concern: the **Artifact store** (agent-session outputs, not
operator-internal planning).

A reader familiar with the ARCHITECTURE.md strata model who then reads the domain code will find:

- `MemoryScope` with four values: `OBJECTIVE`, `TASK`, `SESSION`, `PROJECT`
- `MemoryEntry` with a single `scope: MemoryScope` field
- No type called `TurnContext`, `SessionSnapshot`, or `ObjectiveMemory`
- `FileProjectMemoryStore` persisting only `PROJECT`-scoped entries

The strata names in ARCHITECTURE.md do not map one-to-one to `MemoryScope` values. This document
records why, and what the actual mapping is.

## Decision

### The strata model is conceptual; the scope model is the implementation

The four strata in ARCHITECTURE.md are a **conceptual target model** — a description of the
different kinds of memory the system is designed to support. The `MemoryScope` enum is the
**implementation model**. They are not the same level of abstraction.

The conceptual strata are useful for understanding the design intent. The scope model is what
actually governs runtime behavior.

### Scope model

`MemoryScope` has four values, each with distinct runtime semantics:

**`OBJECTIVE`** — Memory scoped to the overall operation objective. Maps to ARCHITECTURE.md
"Objective memory." Used for cross-task, cross-session context about the long-lived goal: accepted
decisions, strategic constraints, unresolved blockers. Persisted in `OperationState.memory_entries`.
Freshness-tracked; may be superseded. Visible in `memory op-id` output.

**`TASK`** — Memory scoped to one task. Maps to ARCHITECTURE.md "Task memory." Used for
task-specific context that should survive across agent sessions assigned to the same task: source
references, intermediate findings, open sub-questions. Persisted in `OperationState.memory_entries`
alongside objective-scope entries. Identified by `scope_id = task_id`. Freshness-tracked.

**`SESSION`** — Memory scoped to one agent session. Maps to ARCHITECTURE.md "Session snapshot."
Used for session-internal context: current thread, latest terminal result, open local questions,
reusability assessment. Persisted in `OperationState.memory_entries`. Identified by
`scope_id = session_id`. Freshness-tracked.

**`PROJECT`** — Memory that persists across operations for the lifetime of the project. No direct
counterpart in the four-strata model — it is a cross-operation extension introduced in ADR 0060.
Persisted by `FileProjectMemoryStore` in `.operator/project_memory/<scope>/`. The brain reads all
active project-scope entries at the start of every planning cycle. Only writable via user-accepted
`document_update_proposal` attention; no project-scope write occurs without user action.

### Turn context is not a MemoryEntry scope

ARCHITECTURE.md "Turn context" — immediate context assembled for the current brain decision — is
not a `MemoryScope` value. It is not stored as a `MemoryEntry`. Turn context is ephemeral: it is
assembled at each planning cycle from the full operation state (tasks, sessions, open attentions,
operator messages, memory entries, policies) and passed directly to the brain call. Nothing
persists it independently because the full operation state from which it is assembled is itself
persisted.

Turn context is therefore not a memory layer in the storage sense — it is the *read path* across
all memory layers.

### Why four `MemoryScope` values rather than three strata

The three storage scopes (OBJECTIVE, TASK, SESSION) each correspond to one of the conceptual
strata. PROJECT is an additional cross-operation layer added to support context that outlives a
single operation (ADR 0060). The four-stratum model in ARCHITECTURE.md predates ADR 0060 and was
not updated to include PROJECT as a fifth stratum; it remained as the original design intent
description.

### Single `MemoryEntry` type across all scopes

All four scopes share one `MemoryEntry` model with a `scope: MemoryScope` discriminator. The
alternatives — a separate model per scope, or a union type — were rejected:

- **Separate models per scope:** The fields (summary, source_refs, freshness, superseded_by) are
  identical across scopes. Separate models would duplicate structure without buying type safety,
  since the meaningful behavioral differences are in the runtime (how entries are read, how they
  age, how they are persisted) — not in the field layout.
- **Union type:** Adds parsing complexity for no structural benefit given the above.

The scope discriminator in the single model is sufficient for all routing and display decisions.

### Artifact store is separate from MemoryEntry

Artifacts (normalized agent returns, structured data, files, diffs, reports surfaced as
deliverables) are not stored as `MemoryEntry` objects. They are agent-session outputs, not
operator-internal planning material. The distinction is:

- `MemoryEntry` — operator's own planning context; not user-facing as a deliverable.
- Artifact — concrete output produced by an agent session; user-facing, accessible via
  `artifacts op-id`.

Planning notes, research summaries, and file-read context belong in `MemoryEntry`. Structured task
deliverables belong in the artifact store.

## Consequences

- `MemoryScope` has four values: `OBJECTIVE`, `TASK`, `SESSION`, `PROJECT`.
- `MemoryEntry` is the single runtime type for all scopes; scope is the discriminator.
- Turn context is not a storage layer — it is the assembled read path across the operation state.
- `FileProjectMemoryStore` handles `PROJECT`-scope persistence across operations.
- OBJECTIVE, TASK, and SESSION entries are persisted in `OperationState.memory_entries`
  (in-operation, operation-local store).
- The ARCHITECTURE.md four-strata model remains accurate as a conceptual description of the design
  intent; this ADR provides the mapping from strata to implementation.
- A future fifth stratum ("workspace documents") would correspond to the Operator Workspace (RFC
  0008) if and when its activation criteria are met. It would not be a `MemoryScope` value — it
  would be a separate file-system-backed write layer.
