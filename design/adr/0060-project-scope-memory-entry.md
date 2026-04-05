# ADR 0060: Project-scope MemoryEntry

## Status

Accepted

## Context

### Preceding design

ADR 0005 established stratified memory: operation-scope `MemoryEntry` objects carry context
built during a single operation — freshness-tracked per file path, superseded when the same path
is re-read. This was sufficient for single-operation work but left a gap for long-lived objectives
that span multiple operations.

### The multi-operation context problem

When an operation is interrupted and later resumed — or when a new operation is started to
continue work begun by an earlier one — the operator brain starts with no memory of what the
prior operation learned. Context about the project structure, key decisions, discovered
constraints, or working hypotheses must be rediscovered from scratch every time.

The alternative of reading project files at the start of each operation is partial: it captures
what is written down in user-authored documents but not the brain's own synthesised understanding.
The brain's reasoning about those documents — which parts matter for the current objective, what
it concluded from them — is lost between operations.

### Why not write context to project files directly?

Writing the brain's synthesised context directly to a project file would strip provenance
(which sources produced it, when it was last verified, whether it has since been superseded) and
make it indistinguishable from user-authored content. See ADR 0059 for the full rationale for
the brain-project file system boundary.

## Decision

`MemoryEntry` supports two scopes, distinguished by `scope: MemoryScope`:

**`MemoryScope.OBJECTIVE` / `MemoryScope.TASK` / `MemoryScope.SESSION`** (existing) — operation-
scoped context. Freshness-tracked per file path within one operation. Visible in `memory op-id`
output. Not persisted across operations.

**Project-scope** (`scope_id = "project"` or a dedicated `MemoryScope.PROJECT` value) — cross-
operation context. Persists for the lifetime of the project, or until the user explicitly expires
it. Surfaced in `memory op-id` output with a `[project]` scope label.

### Read semantics

The brain reads all active project-scope entries at the start of every planning cycle, before
the first brain call of that cycle. This ensures that cross-operation context is available to
every planning decision without requiring the brain to request it explicitly.

"Active" means `freshness = CURRENT` — entries that have been explicitly expired or superseded
are excluded. The load happens unconditionally; the brain does not choose whether to load
project-scope entries.

### Write semantics

No project-scope write occurs without user action. The only write path is:

1. The brain emits a `document_update_proposal` attention request carrying the proposed entry
   content and rationale.
2. The user accepts the proposal (via `operator answer att-id`).
3. The operator service creates or updates the project-scope `MemoryEntry`.

This keeps project-scope memory under the same provenance-bearing, user-gated model as ADR 0059
describes for all brain-to-project-file writes.

### Expiry and supersession

Project-scope entries follow the same freshness model as operation-scope entries (ADR 0006):

- `CURRENT` — active and loaded at each planning cycle
- `STALE` — flagged as potentially outdated; still loaded but annotated
- `SUPERSEDED` — replaced by a newer entry for the same subject; excluded from loads

The user can explicitly expire a project-scope entry via the `memory expire` CLI surface. The
brain may propose supersession as part of a new `document_update_proposal` that covers the same
subject as an existing entry.

### Rationale for a scope extension rather than a separate store

Project-scope entries are `MemoryEntry` objects — the same type, the same provenance fields
(`source_refs`, `freshness`, `superseded_by`), the same CLI surface. A separate store would
duplicate the freshness and provenance model without adding capability. The scope field is
sufficient to distinguish operation-local from cross-operation context.

## Consequences

- `MemoryScope.PROJECT` value added to `domain/enums.py`
- `ProjectMemoryStore` protocol in `protocols/runtime.py` — `save`, `load`, `list_active`, `expire`
- `FileProjectMemoryStore` in `runtime/project_memory.py` — stores entries as JSON under
  `.operator/project_memory/<scope>/`
- `OperatorService._refresh_project_memory_context()` — loads active project-scope entries into
  `state.memory_entries` before each brain call; replaces any stale project-scope entries from
  prior cycles; no-ops if `project_memory_store` is not configured or scope is absent
- `OperatorService._auto_create_project_memory_entry()` — called from
  `_finalize_pending_attention_resolutions` when a `document_update_proposal` is accepted;
  reads `proposed_content` and `target_file_path` from attention metadata; supersedes any
  existing active entry for the same `target_file_path` scope_id
- `build_service()` in `bootstrap.py` wires in `FileProjectMemoryStore` at
  `.operator/project_memory/`
- `memory op-id` CLI output surfaces project-scope entries with `[project]` label — pending
  CLI implementation (see prompt injection ADR 0061 for context injection surface)
