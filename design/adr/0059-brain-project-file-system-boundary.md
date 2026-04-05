# ADR 0059: Brain — project file system boundary

## Status

Accepted

## Historical note

This ADR is still active, but references to `AgentAdapter` in the consequences section are
historical wording. The current runtime-contract surface is defined by ADR 0081, ADR 0082,
ADR 0083, ADR 0089, and ADR 0091.

**Implementation notes:**
- `AttentionType.DOCUMENT_UPDATE_PROPOSAL` is present in `domain/enums.py`
- `_attention_should_block` in `service.py` returns `False` unconditionally for this type,
  enforcing non-blocking semantics regardless of involvement level or `APPROVAL_HEAVY` mode
- `_attention_title_from_decision` carries the default title "Document update proposed"
- Proposal payload (`target_file_path`, `proposed_content`, `rationale`) is carried in
  `AttentionRequest.metadata` — no dedicated fields needed, as this is an informational
  proposal, not a structured decision gate
- **Brain file read tools:** `read_file`, `list_dir`, and `search_text` are implemented via:
  - `FileContextProvider` protocol in `protocols/providers.py` — optional extension for
    providers that support a tool-use loop during `decide_next_action`
  - `OpenAIResponsesStructuredOutputProvider.decide_with_file_context()` — sends one LLM
    round-trip with file tool definitions; returns `FileToolCallStep` or `DecisionStep`
  - `OperatorService._decide_next_action_with_file_context()` — manages the read loop
    (max 10 reads), executes file reads against the operation CWD, emits
    `operator.context_read` trace events, and upserts `MemoryEntry` (operation-scope)
    after each read
  - Path traversal is rejected by security invariant in `_execute_file_tool`
  - Providers that do not implement `FileContextProvider` fall back to the existing
    `decide_next_action` path unchanged

## Context

The operator brain has an LLM client and read-only access to the project file system
(`read_file`, `list_dir`, `search_text`). A natural question arises: why is the brain's file
access strictly read-only, even at high involvement levels or in unattended mode? And what is the
correct path for the brain to contribute to user-authored planning documents?

Without an explicit decision record, these three aspects are likely to be questioned independently:

1. Why can't the brain write files when `involvement = unattended`?
2. Why does `document_update_proposal` exist as a non-blocking attention type rather than a
   direct write?
3. Why does `MemoryEntry` have a `project` scope rather than just writing context to a file?

All three stem from the same boundary decision.

## Decision

### Invariant: brain is read-only with respect to all project files

The operator brain has no write authority over any file in the project file system, regardless of
involvement level, scheduler state, or operation duration.

**Rationale:** Write authority over project files is a user trust boundary, not a capability
boundary. The brain's involvement level (`unattended` / `interactive`) controls how much it
interrupts the user during orchestration — it does not change who is the author of record for
project artifacts. A brain that can write files unilaterally at `unattended` level is
indistinguishable to downstream consumers (git history, reviewers, auditors) from a human author.
This conflation is the failure mode to avoid.

The alternative — "write when unattended, propose when interactive" — was rejected because it
makes the write-authority boundary a function of a runtime parameter rather than an explicit
architectural invariant. Any involvement-level change would silently change whether the brain
becomes an author.

### `document_update_proposal` — the only write path, non-blocking

When the brain's planning reasoning should inform an update to a user-authored document (strategy
note, research journal entry, backlog item), it emits a `document_update_proposal` attention
request. This carries the target file path, proposed content, and a brief rationale.

The user is the author of record. Accepting a proposal means the user edits the file themselves
or delegates the edit to an agent task. The brain never writes project files under any path or
any involvement level.

**Why non-blocking:** `document_update_proposal` is deliberately non-blocking by default. Making
it blocking would mean the operation halts every time the brain identifies a document to update —
which could happen multiple times per planning cycle in long-lived work. The proposal queue is
intended for asynchronous user review, not for synchronous approval gates. The user is free to
ignore proposals; the operation continues regardless.

This distinguishes `document_update_proposal` from `approval_request` (which gates a specific
agent action) and from `policy_gap` / `novel_strategic_fork` (which gate forward progress at
`interactive` involvement).

### Project-scope `MemoryEntry` — provenance-bearing cross-operation context

`MemoryEntry` supports two scopes:

- **Operation-scope** (default): context built during a single operation, freshness-tracked per
  file path. Superseded when the same path is re-read.
- **Project-scope**: persists across operations. The brain reads all active project-scope entries
  at the start of every planning cycle. Entries are writable only via user-accepted
  `document_update_proposal` attention — no project-scope write occurs without user action.

**Why MemoryEntry rather than direct file writes:** Project-scope context that the brain
assembles during an operation (what it learned from reading source files, what decisions it
recorded) carries provenance — which sources produced it, when it was last verified, whether it
has been superseded. Writing this directly to a project file would strip the provenance and make
it indistinguishable from human-authored content. `MemoryEntry` preserves the provenance chain
and keeps the content in the operator's data directory (`.operator/`), not in the project tree.

### Relation to Operator Workspace (future direction)

The read-only invariant may be lifted in a future evolution where the brain holds write authority
over a dedicated operator workspace directory (`.operator/workspace/`). The criteria for that
promotion are documented in VISION.md (Operator Workspace section) and RFC 0008 (Status:
Deferred). Until all four criteria are met, this ADR's invariant holds.

`document_update_proposal` is not a shortcut toward the workspace. It is a permanent mechanism
for brain-to-user proposal regardless of whether the workspace is ever built.

## Consequences

- The `AgentAdapter` contract, brain protocols, and all provider implementations must not expose
  file-write tools to the brain
- `document_update_proposal` remains a distinct `AttentionType` in `domain/enums.py`
- Project-scope `MemoryEntry` writes are gated on user-accepted proposals — no code path in the
  operator service creates a project-scope entry without first resolving an attention request
- Future involvement levels or autonomy extensions must explicitly justify any deviation from the
  read-only invariant against the criteria in RFC 0008 before implementing write access
