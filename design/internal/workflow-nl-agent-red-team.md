# Red Team: WORKFLOW-UX-VISION.md + NL-UX-VISION.md + AGENT-INTEGRATION-VISION.md

**Date:** 2026-04-03
**Target documents:** `docs/WORKFLOW-UX-VISION.md`, `docs/NL-UX-VISION.md`, `docs/AGENT-INTEGRATION-VISION.md`
**Evaluated as:** Companion UX specification suite — coherence, completeness, naming consistency, vision alignment, implementability
**Cross-reference:** `design/VISION.md` (normative), `docs/CLI-UX-VISION.md`, `docs/TUI-UX-VISION.md`, `design/internal/tui-cli-red-team.md` (prior red team)

---

## Summary Assessment

All three documents are well-structured and address their respective surfaces with appropriate depth. The primary failure modes are: (1) cross-document naming drift that compounds the TUI/CLI red team's C1/C2 findings, (2) a new UX concept (`[~N]` ambient attention) with no grounding in the existing domain model, and (3) a referenced schema document (`docs/AGENT-API.md`) that is cited as the authoritative schema source but does not yet exist.

**Strengths:**
- WORKFLOW-UX-VISION.md's committed vs. internal artifact table is clear and actionable
- AGENT-INTEGRATION-VISION.md's priority table with explicit rationale is strong specification practice
- NL-UX-VISION.md's read/write/dangerous confirmation taxonomy is rigorous and well-motivated
- Python SDK design is thin and coherent; correctly defers to existing service layer
- MCP tool LLM descriptions are well-written for the intended audience

**Weaknesses:**
- Three documents collectively introduce commands (`operator converse`, `operator ask`, `operator mcp`) that are absent from CLI-UX-VISION.md's Known Open Items
- `operator profile create` (WORKFLOW) conflicts with `operator project create` (CLI spec) — code-confirmed three-way naming split
- Ambient attention `[~N]` has no corresponding `AttentionType` in the domain model — architecturally ungrounded
- `AGENT-API.md` is referenced as the schema authority but is itself listed as a Known Open Item in the same document
- MCP `attached` mode, `OperationBrief` return structure, and event stream termination contract are all undefined

---

## Red Team Composition

| Expert | Role | Critique focus |
|--------|------|----------------|
| Vera | Cross-Document Coherence Critic | Naming drift, command inconsistencies, mental model conflicts across all five UX docs |
| Mikael | Completeness & Edge Case Auditor | Missing states, incomplete workflows, absent error conditions |
| Yuki | Vision Alignment Critic | Conflicts with VISION.md principles; normative violations |
| Ramon | Implementability Skeptic | Ambiguities that would cause divergent implementations; interface contracts |
| Sasha | Integration Surface Critic | Agent integration priorities, MCP design gaps, SDK interface quality |

---

## Critical Findings

### C1 — `operator converse` / `operator ask` / `operator mcp` absent from CLI-UX-VISION.md Known Open Items

**Location:** NL-UX-VISION.md §Relationship to CLI and TUI; AGENT-INTEGRATION-VISION.md §Interaction with CLI-UX-VISION.md
**Severity:** Critical

NL-UX-VISION.md introduces `operator converse [OP]` and `operator ask OP "..."` as new primary commands. AGENT-INTEGRATION-VISION.md introduces `operator mcp` as a secondary-visible command. CLI-UX-VISION.md's §Known Open Items does not include any of these. An implementer working from CLI-UX-VISION.md alone would not know these commands need to be added.

AGENT-INTEGRATION-VISION.md §Interaction with CLI-UX-VISION.md includes a table listing `operator mcp` as a required addition to CLI's secondary commands section — this is the correct cross-reference pattern. NL-UX-VISION.md has no equivalent table. Its §What Changes in the Existing CLI section mentions the commands should appear in primary `--help` but does not produce a formal addendum to CLI-UX-VISION.md.

**Fix required:**
1. Add to NL-UX-VISION.md a §Interaction with CLI-UX-VISION.md table (mirroring AGENT-INTEGRATION's pattern) with the following additions:

| Addition | Section in CLI-UX-VISION.md |
|----------|-----------------------------|
| `operator converse [OP]` as a primary command | Primary commands |
| `operator ask OP "..."` as a primary command | Primary commands |
| Ambient attention `[~N]` tier in output format conventions | Output Format Conventions |

2. Add to CLI-UX-VISION.md §Known Open Items:
   - `operator converse [OP]` — NL REPL session
   - `operator ask OP "..."` — single-shot NL query

---

### C2 — Three-way naming conflict: `project init` / `project create` / `profile create`

**Location:** CLI-UX-VISION.md §`project` Subgroup; WORKFLOW-UX-VISION.md §Known Open Items
**Severity:** Critical

**Verified via code search**: the current CLI has `operator project init` (not `project create`).

CLI-UX-VISION.md renames this to `operator project create` for named profile management (with `operator init` as the top-level first-run command). WORKFLOW-UX-VISION.md §Known Open Items uses `operator profile create [--local]` — a different command name that uses `profile` as the subgroup rather than `project`.

This is a three-way split:
- Current implementation: `operator project init`
- CLI-UX-VISION.md: `operator project create`
- WORKFLOW-UX-VISION.md: `operator profile create [--local]`

**Fix required:** Reconcile to one canonical name. The CLI spec's `operator project create` is the more consistent choice (keeps `project` as the subgroup, consistent with `operator project list/inspect/resolve/dashboard`). WORKFLOW-UX-VISION.md §Known Open Items must be updated from `operator profile create [--local]` to `operator project create [--local]`.

---

### C3 — Ambient attention `[~N]` has no domain type; architecturally ungrounded

**Location:** NL-UX-VISION.md §Three-Tier Attention Model
**Severity:** Critical

**Verified via code search**: `AttentionType` enum has two values: `POLICY_GAP` and `DOCUMENT_UPDATE_PROPOSAL`. There is no `AMBIENT` type.

NL-UX-VISION.md introduces `[~N]` as a "third tier" alongside `[!!N]` (blocking) and `[!N]` (non-blocking). The document says: "An ambient attention is a brain observation that meets all three criteria…" — it uses the word "attention" as if ambient observations are instances of the existing `AttentionRequest` domain type. But:

1. The domain's `AttentionRequest` model has an `attention_type: AttentionType` field
2. There is no `AttentionType.AMBIENT` (or equivalent) in the codebase
3. Ambient observations "do not need to be answered" and "do not interrupt the flow" — semantically different from the existing attention request model, which always represents a request for user action

The document conflates two distinct concepts: typed attention requests (user-action-required) and brain observations (informational). Using "attention" for both causes implementers to either (a) add a new attention type (expanding the domain model) or (b) build a separate observation subsystem, with no guidance on which.

Additionally, `VISION.md §Mental Model` specifies that project-scope memory writes require `document_update_proposal` attention requests. The relationship between these typed requests and the ambient `[~N]` tier is never specified. A `document_update_proposal` should arguably display as `[!N]` (non-blocking, user sees it) not `[~N]` (ambient, only visible at operation level) — but the document doesn't address this.

**Fix required:**
1. Rename `[~N]` throughout NL-UX-VISION.md from "ambient attention" to "ambient observation" to distinguish from typed `AttentionRequest`
2. Add a clarifying note: *"Ambient observations are a separate concept from `AttentionRequest` instances. They do not have an `AttentionType` and are not stored as `AttentionRequest` records. They are brain-generated informational entries visible in the TUI at operation level. Implementation note: ambient observations require a new domain model distinct from the existing attention system."*
3. Specify how `document_update_proposal` attention requests display in the badge system (they are `[!N]` non-blocking, not `[~N]` ambient)

---

### C4 — `AGENT-API.md` cited as schema authority but doesn't exist

**Location:** AGENT-INTEGRATION-VISION.md §Schema Stability Contract; §MCP §Error Handling
**Severity:** Critical

AGENT-INTEGRATION-VISION.md §Schema Stability Contract says: *"The full schema is documented in `docs/AGENT-API.md`."* The MCP section lists "`docs/AGENT-API.md`: JSON schema documentation for all `--json` output surfaces and event file format" in its §Open Items for Implementation.

The document simultaneously cites `AGENT-API.md` as the authoritative schema reference AND lists it as a future deliverable in the same document. Any implementer reading the schema stability contract would assume `AGENT-API.md` exists and defines the schema. It does not.

**Fix required:** In §Schema Stability Contract, change:
> *"The full schema is documented in `docs/AGENT-API.md`."*

To:
> *"The full schema will be documented in `docs/AGENT-API.md` (pending — see Open Items). Until that document exists, the `--json` output of each command serves as the de facto schema; adding new optional fields is non-breaking; all other changes require a deprecation cycle."*

---

## High Findings

### H1 — `operator ask` fleet form absent; OP required

**Location:** NL-UX-VISION.md §`operator ask`
**Severity:** High

`operator converse [OP]` accepts `OP` as optional — without it, fleet-level context loads. `operator ask OP "QUESTION"` requires `OP`. There is no `operator ask --fleet "question"` or `operator ask "question"` (no OP) for fleet-level single-shot queries. This asymmetry limits `ask`'s scripting utility compared to `converse`.

**Fix required:** Either make `OP` optional in `operator ask` (consistent with `converse`), or explicitly note the asymmetry: *"Unlike `operator converse`, `operator ask` requires a specific operation context. Fleet-level queries are only supported via `operator converse` (interactive) or `operator status` / `operator fleet` (structured output)."*

---

### H2 — TUI disambiguation for NL numbered list undefined

**Location:** NL-UX-VISION.md §Ambiguous NL
**Severity:** High

The ambiguous NL protocol shows a numbered list: `1. operator interrupt ...  2. operator interrupt ...` with `[1/2/cancel]` prompt. In the CLI REPL, this is typed input. In the TUI inline conversation panel (`n` key), the key binding summary shows only `y` and `N` for confirmation. How does a TUI user select `1` or `2` from a numbered disambiguation list?

**Fix required:** Add to NL-UX-VISION.md §TUI: `n` key: *"Numbered disambiguation lists in the TUI panel accept digit keys (`1`, `2`, …) for selection. The key binding bar shows `[1–N: select] [Esc: cancel]` when a disambiguation list is active."*

---

### H3 — `step-by-step` compound command mode missing from TUI key bindings

**Location:** NL-UX-VISION.md §Compound NL Commands; §Key Binding Summary
**Severity:** High

The compound command example shows `[y/N/step-by-step]` as a CLI REPL confirmation option. The Key Binding Summary table shows only `y` and `N` for TUI conversation confirmation. `step-by-step` does not appear in TUI at all.

**Fix required:** Either add `step-by-step` to the TUI Key Binding Summary as a third option (`t` or `s` key), or add a note: *"`step-by-step` mode is available only in `operator converse` (CLI REPL). The TUI conversation panel supports only `y` (execute all) and `N` (cancel all) for compound commands."*

---

### H4 — MCP `attached` mode behavior undefined

**Location:** AGENT-INTEGRATION-VISION.md §MCP §Tool Set
**Severity:** High

`run_operation` has `mode?: "attached"|"background"`. The CLI `--mode attached` blocks the terminal and follows the operation live. In MCP over stdio, a blocking tool call is valid but the document never defines what `attached` means: does it block until terminal state? Does it time out? The recommended workflow uses fire-and-poll (not attached mode), making `attached` redundant and confusing.

**Fix required:** Either remove `mode` from the MCP `run_operation` tool (fire-and-poll is the recommended pattern; `attached` adds no value in MCP context), or add: *"When `mode=\"attached\"`, the tool call blocks until the operation reaches a terminal state or a blocking attention opens (returns `status=needs_human`). Timeout is governed by the MCP client's tool timeout configuration. Operations expected to run longer than the client timeout should use `mode=\"background\"` (default) with the fire-and-poll pattern."*

---

### H5 — MCP `get_status` return structure undefined; bridges to non-existent `AGENT-API.md`

**Location:** AGENT-INTEGRATION-VISION.md §MCP §Tool Set
**Severity:** High

`get_status` returns `OperationBrief + attention summary` per the tool table, but `OperationBrief`'s JSON structure is not defined in this document. The reference is to `docs/AGENT-API.md` which doesn't exist. An LLM calling `get_status` receives an undefined JSON blob. The MCP interface is unusable without the schema.

**Fix required:** Inline the `get_status` JSON return structure directly in AGENT-INTEGRATION-VISION.md as a provisional schema, explicitly labeled pending `AGENT-API.md`. Minimum fields to specify:

```json
{
  "operation_id": "op-abc123",
  "status": "running|needs_human|completed|failed|cancelled",
  "iteration": 14,
  "max_iterations": 100,
  "task_summary": {"running": 2, "queued": 3, "blocked": 1},
  "attention_requests": [
    {"attention_id": "att-7f2a", "blocking": true, "question": "..."}
  ]
}
```

---

### H6 — No bridge between MCP control surface and file-based event streaming

**Location:** AGENT-INTEGRATION-VISION.md §Surface 2; §Surface 3
**Severity:** High

An agent using `run_operation` via MCP gets back `{operation_id, status}` but not the `data_dir` needed to construct the event file path. Surfaces 2 and 3 are described in isolation. An agent that wants to combine them (MCP for control, file streaming for real-time events) has no documented path to do so.

**Fix required:** Add to the MCP §Configuration for Claude Code section: *"To use file-based event streaming alongside MCP, the agent needs the event file path: `<OPERATOR_DATA_DIR>/events/<operation_id>.jsonl`. The `OPERATOR_DATA_DIR` environment variable is set in the MCP server configuration. When using the recommended Claude Code config above, the agent should read `OPERATOR_DATA_DIR` from its environment to construct the event file path."* Alternatively, add a `get_data_dir` tool or return `event_file` in the `run_operation` response.

---

### H7 — `stream_events` termination contract unspecified

**Location:** AGENT-INTEGRATION-VISION.md §Surface 4 (Python SDK)
**Severity:** High

`stream_events` is described as "reads from `.operator/events/<op-id>.jsonl` with async file tail." The termination contract is unspecified: does the iterator return when a terminal event is received? Does it continue tailing? What happens if the file write process closes before a terminal event appears? The Python example shows `elif event.kind in ("operation_completed", "operation_failed"): break` — but this is user code, not the SDK contract.

**Fix required:** Define explicitly: *"The `stream_events` iterator yields events as they are written to the event file. It terminates automatically when an `operation_completed`, `operation_failed`, or `operation_cancelled` event is received and no more writes follow within a configurable drain window (default: 1 second). Callers may also break out of the iterator at any time. The iterator does not raise if the operation is already terminal when called — it drains the existing file and returns."*

---

### H8 — PM reporting has no retry mechanism; `reported: false` on failure is silent

**Location:** WORKFLOW-UX-VISION.md §Result Reporting
**Severity:** High

The `ExternalTicketLink.reported: bool` field prevents duplicate posts on resume. But if the GitHub API is unavailable when the operation reaches terminal state, `reported` stays `false`. No retry mechanism is specified, no manual retry command exists (existing `report` command does operation summaries, not PM posting), and the user has no way to know the report failed except by checking the ticket.

**Fix required:** Either (a) add a brief note: *"If result reporting fails, a non-blocking attention (`[!N]`) is created with the failure reason and the text of the intended report. The user can manually post or dismiss."* Or (b) add `operator report OP --ticket` as an explicit secondary command for manual PM reporting with a clear distinction from the existing `report` command (rename existing to `operator summary OP`).

---

## Medium Findings

### M1 — Profile precedence merge semantics absent

**Location:** WORKFLOW-UX-VISION.md §Profile Precedence
**Severity:** Medium

The precedence ladder is specified for scalar fields. List fields like `default_agents` (a list of adapter names) have ambiguous merge behavior: does `--agent claude_acp` on the CLI *replace* the profile's `default_agents` list or *append* to it? Repeatable flags (`--agent ADAPTER` is repeatable per CLI spec) imply replace semantics, but this is never stated.

**Fix required:** Add: *"CLI flag precedence for list fields (`--agent`, `--success-criterion`) is replacement semantics: specifying any value replaces the profile's list entirely. To combine profile defaults with CLI additions, the profile list must be re-specified explicitly."*

---

### M2 — History ledger JSONL example missing populated `ticket` field

**Location:** WORKFLOW-UX-VISION.md §Operator History Ledger
**Severity:** Medium

The JSONL example shows two records, neither with a `ticket` field. The spec says the field is optional, but an example with a ticket-sourced operation would be useful and would define the concrete serialized form. The word "summary" in the field description is ambiguous — does the full `ExternalTicketLink` object serialize into the ledger, or a subset?

**Fix required:** Add a third example record showing a ticket-sourced operation:

```jsonl
{"op_id": "op-ghi789", "goal": "Fix: auth tokens expire silently", "profile": "default", "started": "2026-04-03T15:00:00Z", "ended": "2026-04-03T16:12:00Z", "status": "completed", "stop_reason": "explicit_success", "ticket": {"provider": "github_issues", "project_key": "my-org/my-repo", "ticket_id": "234", "url": "https://github.com/my-org/my-repo/issues/234", "title": "Fix: auth tokens expire silently"}}
```

Note: `reported` field is excluded from the ledger — it's an operational field, not a historical record field.

---

### M3 — Ambient observation vs Transparency Principle (VISION.md §5)

**Location:** NL-UX-VISION.md §Who Initiates
**Severity:** Medium

VISION.md §Transparency by default requires that users can see "what the operator decided" and "why the next step was chosen." Ambient observations are specifically designed *not* to propagate to the fleet level — they are only visible at operation level in the TUI. This creates a category of brain communication that users monitoring at fleet level will miss. The document doesn't acknowledge this tension with Principle 5.

**Fix required:** Add a note in §Who Initiates: *"Ambient observations intentionally do not propagate to the fleet level — they are visible only in Operation View. This is a deliberate trade-off: high-volume ambient observations at fleet level would produce noise that degrades the clarity of the fleet signal. Users who want full transparency can monitor at operation level or use `operator ask` to query the brain directly. This trade-off is acknowledged as a partial relaxation of VISION.md §Transparency Principle 5 for the ambient tier specifically."*

---

### M4 — A2A forward note may be stale (ACP exists in codebase)

**Location:** AGENT-INTEGRATION-VISION.md §Surface 7
**Severity:** Medium

The A2A forward note says: *"When `operator_acp` is designed, evaluate whether A2A is the right protocol."* But the git status at session start shows `src/agent_operator/acp/` already exists in the codebase (modified files: `acp/__init__.py`, `acp/client.py`). The premise that `operator_acp` is "not yet designed" is potentially stale.

**Fix required:** Verify the current status of `operator_acp` architecture and update the A2A note accordingly. If ACP is implemented, the A2A evaluation is not a future task but an immediate one.

---

### M5 — ACP omission undocumented within AGENT-INTEGRATION-VISION.md

**Location:** AGENT-INTEGRATION-VISION.md (no section)
**Severity:** Medium

The user's original request explicitly included ACP as a surface to consider. The document covers CLI, file streaming, MCP, Python SDK, REST, JSON-RPC, and A2A but has no ACP section, not even a deferred forward note. An implementer would not know that ACP was considered and deferred.

**Fix required:** Add to the priority table and as a brief note:

| # | Surface | Status | Rationale |
|---|---------|--------|-----------|
| 8 | **ACP** | Deferred — separate document | ACP serves operator-as-server (other operators connecting to this operator), not agent-as-client. The right scope is a dedicated `operator_acp` architecture document. See `src/agent_operator/acp/` for current implementation. |

---

### M6 — NL/PM write boundary unspecified

**Location:** NL-UX-VISION.md §Where NL Goes Far Enough; WORKFLOW-UX-VISION.md §Design Principles
**Severity:** Medium

WORKFLOW-UX-VISION.md Design Principle 1 says: "operator does not write back to the PM system mid-operation." NL-UX-VISION.md §Where NL Stops lists commands that require structured confirmation but does not explicitly exclude PM-write NL expressions. If a user types "update the Linear ticket to say we're making progress," the NL system would need to either refuse (WORKFLOW principle) or support it (as a mid-operation write). This boundary is not drawn.

**Fix required:** Add to NL-UX-VISION.md §Where NL Stops: *"PM system writes (mid-operation ticket updates) are not supported via natural language. Per WORKFLOW-UX-VISION.md Design Principle 1, operator writes to PM systems only on terminal state. Natural language requests to update tickets mid-operation should be declined with an explanation."*

---

### M7 — Python SDK `cancel` has no confirmation parameter

**Location:** AGENT-INTEGRATION-VISION.md §Surface 4 (Python SDK)
**Severity:** Medium

CLI `operator cancel OP` prompts for confirmation unless `--yes` is passed (CLI-UX-VISION.md §P7). Python SDK `async def cancel(self, operation_id: str) -> None` has no confirmation parameter. The SDK bypasses the CLI's safety confirmation without documentation.

**Fix required:** Either document this explicitly — *"The Python SDK does not prompt for confirmation; `cancel()` executes immediately. SDK callers are responsible for confirming with the user before calling `cancel()`."* — or add a `confirmed: bool = False` parameter that raises if `False`.

---

### M8 — `comment_and_close` auto-closes ticket without user confirmation

**Location:** WORKFLOW-UX-VISION.md §Result Reporting
**Severity:** Medium

`on_success: comment_and_close` automatically closes a GitHub Issue when the operation completes. This is a consequential external action (closing an issue that may have further context, ongoing discussion, or a PR linked to it) that happens without user confirmation. CLI-UX-VISION.md §P7 says destructive commands confirm. Closing a ticket is at least as consequential.

**Fix required:** Add: *"When `on_success: comment_and_close` is configured, operator creates a non-blocking attention `[!N]` with the intended comment text before posting. The operation auto-proceeds after 1 planning cycle if not dismissed. To require explicit confirmation, set `on_success: confirm_and_close` (prompts the user via attention request before executing)."* Or at minimum note: *"Automatic ticket close on success is irreversible from operator's side; users should configure this setting deliberately."*

---

## Recommendations

1. **Immediate (before any NL or MCP implementation):** Fix C3 (ambient observation naming and domain model gap), C4 (AGENT-API.md citation while it doesn't exist), C2 (profile create naming conflict). These are structural issues that will propagate into code if not resolved first.

2. **Before any CLI implementation work:** Add `operator converse`, `operator ask`, `operator mcp` to CLI-UX-VISION.md §Known Open Items (C1). The CLI spec is the implementation reference; it must reflect all planned commands.

3. **During MCP design review:** Resolve H4 (attached mode), H5 (OperationBrief structure), H6 (data_dir bridge). These are design decisions, not just documentation fixes.

4. **During PM integration design:** Address H8 (reporting retry), M8 (auto-close confirmation), M6 (NL/PM write boundary). These touch the same surface area.

5. **Deferred but tracked:** M4 (A2A/ACP staleness), M5 (ACP omission), M7 (SDK cancel confirmation), M1 (merge semantics), H7 (stream_events termination).

---

## Links to Assessed Materials

- `docs/WORKFLOW-UX-VISION.md`
- `docs/NL-UX-VISION.md`
- `docs/AGENT-INTEGRATION-VISION.md`
- `design/VISION.md` (§Protocol-oriented integration, §Transparency by default, §Mental Model, §Operation Lifecycle)
- `docs/CLI-UX-VISION.md` (§Known Open Items, §Design Principles P7, §project Subgroup)
- `design/internal/tui-cli-red-team.md` (prior red team; C1=stop_turn, C2=log unification)
- `src/agent_operator/domain/enums.py` (AttentionType — verified AMBIENT not present)
- `src/agent_operator/cli/main.py` (project commands — verified `project init`, no `project create`)
