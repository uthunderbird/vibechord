# RFC 0008: Operator Workspace

## Status

Deferred — Activation criteria not yet met

## Context

The current architecture keeps the operator brain strictly read-only with respect to the project
file system. Planning documents — strategy, roadmap, research journal, backlog — are user-authored
and user-maintained. The brain reads them via its `read_file` / `list_dir` / `search_text` file
tools; it may propose additions via `document_update_proposal` attention requests; it does not
write.

This model is correct for the current maturity level of the system. The `document_update_proposal`
pathway preserves user authorship authority while giving the brain a mechanism to surface relevant
additions. The user reviews and decides; the brain proposes and informs.

However, there is a foreseeable evolution point at which this model becomes a bottleneck rather
than a safety guarantee:

- The brain's planning documents (strategy notes, running journals, roadmap drafts, backlog items)
  are operationally distinct from user-authored project documents. The user has clear intent
  authority over the project; the brain has clear operational authority over its own planning layer.
- If `document_update_proposal` proposals accumulate faster than the user can review them, or the
  user routinely accepts them without meaningful review, the review step has become de facto
  delegation without governance infrastructure — the worst of both worlds.

This RFC formalises the deferral of the Operator Workspace concept with explicit activation
criteria, so the decision is not relitigated from scratch when conditions change.

## What the Operator Workspace Is

A dedicated **operator workspace** is a scoped directory (`.operator/workspace/`) where the brain
holds write authority over its own planning documents — strategy notes, a running journal, a
roadmap draft, a backlog. In this model the brain is not merely a reader and proposer; it is the
author of its own planning layer, under a defined governance contract.

The workspace is not a promotion of the brain to general write authority over the project. It is a
bounded sandbox: the workspace boundary is `.operator/workspace/`, and the read-only invariant
remains in force for everything outside that directory.

**Relationship to `document_update_proposal`:** The workspace is a promotion, not a replacement.
Under the current model the brain is a proposer; under the workspace model the brain is an author
within the workspace boundary. The `document_update_proposal` pathway remains available for
proposing changes to user-authored project documents outside the workspace. The two pathways are
complementary, not competing.

**Relationship to `MemoryEntry`:** `MemoryEntry` objects (operation-scope and project-scope) are
operator-internal context used for planning. They are not exposed as user-readable documents and do
not live in the workspace. The workspace is for human-readable planning documents that the brain
authors and the user can read, search, and optionally commit to version control.

## Activation Criteria

All four criteria must be met before this RFC moves to Accepted:

**Criterion 1 — Proposal bottleneck observed in practice**

The `document_update_proposal` attention queue has become a user-review bottleneck: proposals
accumulate faster than the user can review them, or the user routinely accepts them without
meaningful review. This is an empirical threshold, not a design decision — it must be observed in
actual usage before it can be cited as a justification.

*Leading indicator:* a pattern of proposals being batch-accepted without review within a session,
or a pattern of proposals going unaddressed across multiple operations.

**Criterion 2 — Workspace involvement level defined**

A new involvement level is defined that explicitly grants the brain write authority over the
workspace directory. This level must:
- have a clear name and user-facing description,
- be documented in the involvement-levels ADR (currently ADR 0017),
- state the precise boundary: write authority over `.operator/workspace/` only; read-only
  everywhere else in the project file system,
- and be activatable via the `involvement` command at run time.

Without a named involvement level, workspace write authority has no governance envelope.

**Criterion 3 — Write governance machinery exists**

Before the brain can write to the workspace, the following infrastructure must exist:

- `workspace.document.written` domain event — emitted on every workspace file write, carrying
  the relative path within `.operator/workspace/`, the write mode (`create` | `update`), and
  the size in bytes
- `workspace.document.updated` domain event — emitted on partial updates (appends, patches)
- Both events visible in `trace` output without additional flags
- `workspace revert <op-id> <path>` command — reverts a workspace file to its state before the
  most recent operation, using the event log as the audit trail
- `dashboard` includes a workspace activity section showing recent writes without requiring the
  user to open the files directly

Without this machinery, workspace writes are invisible side effects — indistinguishable from
file-system corruption from the user's perspective.

**Criterion 4 — Workspace directory is gitignored by default**

The workspace directory (`.operator/workspace/`) must be gitignored by default, following the
same pattern as `.operator/` itself. The user must explicitly opt in to committing workspace
documents to version control.

This prevents workspace drafts and running journals from polluting the repository history unless
the user has made an intentional decision to treat them as versioned artifacts.

## What This RFC Does Not Decide

The following questions are explicitly deferred until the activation criteria are met:

- **File format and schema for workspace documents.** Strategy notes, journals, roadmap drafts, and
  backlog items may have different structures. Deciding these prematurely risks over-specifying
  a schema before the brain's actual planning needs are understood from usage data.

- **Workspace synchronization across operations.** If two concurrent operations both write to the
  workspace, conflict resolution semantics are needed. This is a complex problem that should not be
  pre-solved before the single-operation workspace case is validated.

- **Read-model for workspace content.** Whether workspace documents should be indexed for semantic
  search, exposed via new CLI surfaces, or fed back into the brain context at operation start are
  all open questions. The base case (brain writes, user reads files directly) is sufficient for the
  first implementation.

- **Workspace promotion path for `MemoryEntry`.** Project-scope `MemoryEntry` objects could
  eventually be migrated into workspace documents if the workspace model proves out. This migration
  path is not part of the initial workspace design.

## Relationship to Read-Only Invariant

The read-only invariant (ADR 0059) holds until all four activation criteria are met. The workspace
is not a shortcut around the review step — it is a promotion of the brain from proposer to author,
which requires explicit governance infrastructure before it is safe to enable.

When all four criteria are met, ADR 0059 should be updated to note the bounded exception: the
brain holds write authority within `.operator/workspace/` under the workspace involvement level,
and the invariant remains in force everywhere else.

## Consequences

Until all four criteria are met:
- The read-only invariant holds unconditionally.
- `document_update_proposal` is the only write-adjacent pathway available to the brain.
- No code changes are required or permitted in the direction of workspace write authority.

When all four criteria are met and this RFC moves to Accepted:
- A workspace involvement level is added to `InvolvementLevel`.
- `FileContextProvider` or an equivalent protocol gains workspace write methods.
- `workspace.document.written` and `workspace.document.updated` are added to the domain event
  catalog (RFC 0006).
- `workspace revert` is added as a Tier 3 forensic command.
- ADR 0059 is updated to note the bounded exception.
- This RFC's status changes to Accepted — Implemented.
