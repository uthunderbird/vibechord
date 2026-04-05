# Red Team: TUI-UX-VISION.md + CLI-UX-VISION.md

**Date:** 2026-04-03
**Target documents:** `docs/TUI-UX-VISION.md`, `docs/CLI-UX-VISION.md`
**Evaluated as:** Paired UX specification — coherence, completeness, naming consistency, vision alignment, implementability
**Cross-reference:** `design/VISION.md` (normative)

---

## Summary Assessment

Both documents are well-structured and cover their respective surfaces with unusual depth. The CLI spec is more rigorous internally than the TUI spec. The primary failure mode is **drift between the two documents** — they were designed in sequence and the later document (CLI-UX-VISION.md) introduced changes (rename of `stop_turn` → `interrupt`, `log` unification) that are not reflected in the earlier document (TUI-UX-VISION.md). There is also one unacknowledged conflict with the normative VISION.md.

**Strengths:**
- CLI-UX-VISION.md's "Naming Changes" and "Relationship to Existing CLI Commands" tables are thorough and actionable
- TUI's badge propagation model (`[!!N]`/`[!N]`) is coherent and well-specified
- CLI ↔ TUI relationship table provides a useful bridge
- Both documents share a consistent mental model (fleet/operation/session levels)

**Weaknesses:**
- TUI-UX-VISION.md uses stale command names (`stop_turn`, old `answer` syntax) that contradict CLI-UX-VISION.md
- One normative VISION.md exception is overridden silently without acknowledgment
- TUI terminal states (`FAILED`, `CANCELLED`) are under-specified
- Several CLI commands appear in a disposition table but not in any command list
- TUI confirmation behavior for destructive actions is unspecified

---

## Red Team Composition

| Expert | Role | Critique focus |
|--------|------|----------------|
| Erin | UX Coherence Critic | Cross-surface consistency; user confusion points |
| Dmitri | Completeness & Coverage Auditor | Missing states, edge cases, absent workflows |
| Priya | Naming & Convention Skeptic | Terminology drift, command name conflicts |
| Lars | Vision Alignment Critic | Conflicts with VISION.md principles |
| Natasha | Implementability Skeptic | Ambiguities that would cause divergent implementations |

---

## Critical Findings

### C1 — `stop_turn` / `interrupt` naming inconsistency across documents

**Location:** TUI-UX-VISION.md (3 locations)
**Severity:** Critical

CLI-UX-VISION.md renames `stop_turn` → `interrupt` throughout. TUI-UX-VISION.md was not updated and still uses `stop_turn` in:

1. **Level 1 Operation View key bindings table:** `s | stop_turn for selected task`
2. **Consolidated Key Binding Map:** `s | — | stop_turn for task | —`
3. **Relationship to Existing CLI Commands table:** `stop_turn op-id | s key at Level 1`

**Fix required:** Replace all three occurrences with `interrupt`. Canonical form: `s | interrupt current agent turn for selected task`.

---

### C2 — VISION.md deliberate exception overridden without acknowledgment

**Location:** CLI-UX-VISION.md §Naming Changes (`codex-log`/`claude-log` → `log`)
**Severity:** Critical

VISION.md §Protocol-oriented integration contains an explicitly argued deliberate exception:

> *The CLI exposes `claude-log` and `codex-log` as vendor-named commands in the forensic tier. This is an intentional exception. Raw upstream transcripts are vendor-specific artifacts; giving them vendor-named commands in the forensic tier preserves full upstream transparency without polluting the operator core.*

CLI-UX-VISION.md unifies these into `operator log OP [--agent claude|codex|auto]`. This overrides the VISION.md exception without acknowledging the conflict or arguing for the override.

**Fix required:** Add to CLI-UX-VISION.md §Naming Changes, under the `log` unification row:

> *Note: This unification overrides the deliberate exception in VISION.md §Protocol-oriented integration. Rationale: `--agent` makes the vendor explicit when required (`operator log --agent claude`), preserving transparency on demand; unified `log` is more consistent with P5 (hyphen-case) and P2 (progressive disclosure); auto-detect is unambiguous in the common case (one agent session per operation); the TUI already uses `log OP --follow` rather than vendor-named commands, making two vendor-named alternatives alongside a unified one redundant. VISION.md §Protocol-oriented integration deliberate exception is superseded by this document for the CLI surface.*

---

## High Findings

### H1 — `p`/`u` (pause/unpause) missing from Operation View key binding table

**Location:** TUI-UX-VISION.md §Level 1 — Operation View key bindings
**Severity:** High

The Level 1 Operation View key binding table lists: `↑↓`, `Enter`, `Tab`, `a`, `s`, `d`, `t`, `m`, `Esc`, `?`, `q`. `p`/`u` are absent.

The Consolidated Key Binding Map (same document, later section) includes: `p / u | Fleet: pause/unpause | **Operation: pause/unpause** | —`

These two tables directly contradict each other. The Consolidated Map is likely correct — pause is useful at Level 1 where the operation is already selected.

**Fix required:** Add `p / u | pause / unpause operation` to the Level 1 Operation View key binding table.

---

### H2 — FAILED and CANCELLED terminal states under-specified in TUI

**Location:** TUI-UX-VISION.md throughout
**Severity:** High

The glyph table defines `✗` for `failed` and notes running states and `✓` for completed. But:

- **No example** shows a failed operation in any fleet view example or right-pane detail
- **CANCELLED** state has no glyph at all — the domain has `completed`, `failed`, `cancelled` as distinct terminal states; TUI defines glyphs for only two
- Right-pane content for failed/cancelled operations is unspecified

**Fix required:**
1. Add a `CANCELLED` glyph to the status glyph table. Recommendation: `⊘` (distinct from `✗`) to preserve the distinction between "stopped by the system/user on purpose" vs "stopped due to error."
2. Add an example of a failed operation in the fleet view left pane
3. Specify right-pane content for terminal-state operations (failed/cancelled): should show outcome summary, stop_reason, and final iteration count

---

### H3 — `attention` and `report` commands absent from command lists

**Location:** CLI-UX-VISION.md §Relationship to Existing CLI Commands vs §Command Structure
**Severity:** High

The disposition table says:
- `attention` → "Merged into `status` output; retained as secondary for detail"
- `report` → "Retained as secondary; `status` covers the summary"

Neither `attention` nor `report` appears in the Secondary commands list. They are neither in primary, secondary, nor hidden/debug sections. They are effectively dropped without being explicitly removed.

**Fix required:** Either add both to the Secondary commands section, or change their disposition to "Removed — functionality covered by `status`."

---

### H4 — TUI answer syntax example is stale

**Location:** TUI-UX-VISION.md §Level 0 Fleet View, right pane example
**Severity:** High

The right pane example shows:
```
→ operator answer att-7f2a "use a branch"
```

This is wrong in two ways: (1) missing the operation ID argument, (2) uses positional text argument instead of `--text` flag.

Per CLI-UX-VISION.md: `operator answer OP [ATT] [--text TEXT]`

**Fix required:**
```
→ operator answer op-arch-3 att-7f2a --text "use a branch"
```

---

### H5 — TUI confirmation behavior for destructive actions unspecified

**Location:** TUI-UX-VISION.md (no section)
**Severity:** High

CLI-UX-VISION.md specifies that `cancel` prompts for confirmation unless `--yes` is passed. The TUI has a `c` key at fleet level mapped to "cancel op."

The TUI spec has no confirmation dialogs defined anywhere. Does pressing `c` immediately cancel? Show an inline confirmation? Open a modal? The absence is a design gap that will produce inconsistent behavior between CLI and TUI — one requires explicit confirmation, the other is unspecified.

**Fix required:** Add a note in TUI §Level 0 key bindings: *Confirmation: pressing `c` opens an inline confirmation bar at the bottom of the screen — "Cancel op-abc123? [y/n]" — requiring explicit `y` keystroke. Pressing any other key aborts.* This is consistent with CLI P7 (destructive commands confirm).

---

## Medium Findings

### M1 — DecisionMemo has no CLI equivalent

**Location:** CLI-UX-VISION.md §CLI ↔ TUI Relationship table
**Severity:** Medium

The TUI `d` key at Level 1 shows the latest DecisionMemo — "the brain's reasoning for the most recent planning cycle." This is a key transparency feature per VISION.md Principle 5. The CLI ↔ TUI table does not include this mapping. `debug inspect` contains DecisionMemos in its full forensic dump, but there is no user-facing `operator decision-memo OP` or equivalent.

**Fix required:** Either add `operator decision-memo OP [--json]` as a secondary command (showing the latest brain decision for an operation), or note explicitly in the CLI ↔ TUI table that DecisionMemo is TUI-only at this stage.

---

### M2 — `[BLOCKED]` task alias vs `NEEDS_HUMAN` operation status — disambiguation absent

**Location:** TUI-UX-VISION.md §Level 1 — Operation View left pane
**Severity:** Medium

The TUI spec says: *"`[BLOCKED]` is a display alias for `PENDING` tasks that have at least one dependency not yet completed — it is a presentation grouping, not a distinct lifecycle state."*

This is correct. But `NEEDS_HUMAN` is the *operation*-level status for blocking attention (previously named `BLOCKED` in the domain enum). The document doesn't clarify that task-level `[BLOCKED]` (dependency blocking) and operation-level `NEEDS_HUMAN` (human attention blocking) are distinct concepts. An implementer might conflate them.

**Fix required:** Add a parenthetical to the `[BLOCKED]` definition: *"Note: `[BLOCKED]` refers to task dependency blocking, distinct from `OperationStatus.NEEDS_HUMAN` (operation-level blocking attention awaiting human response)."*

---

### M3 — TUI does not distinguish implemented vs. roadmap features

**Location:** TUI-UX-VISION.md throughout
**Severity:** Medium

VISION.md uses `> **Roadmap:**` blocks to mark unimplemented future items. CLI-UX-VISION.md has a "Known Open Items" section. TUI-UX-VISION.md makes no such distinction. The `operator_acp` hierarchy extension (sub-operators in the fleet view, badge propagation through operator hierarchies) is described as a fully designed feature, but it depends on `operator_acp` which does not yet exist.

**Fix required:** Add a "Known Open Items" or "Roadmap" section to TUI-UX-VISION.md, at minimum noting: *"`operator_acp` hierarchy (sub-operators nested in fleet view, cross-hierarchy badge propagation) depends on the `operator_acp` architecture not yet designed."*

---

### M4 — `agenda` command disposition is ambiguous

**Location:** CLI-UX-VISION.md §Relationship to Existing CLI Commands
**Severity:** Medium

The disposition table says: *"`agenda` — Merged into `fleet` output; may be removed."*

"May be removed" is not a design decision. It's a deferred decision. For a spec document, this is insufficient — it means an implementer doesn't know whether to remove the command or retain it.

**Fix required:** Decide and commit. Either: "Removed — functionality covered by `fleet`" or "Retained as hidden/debug; accessible as `operator debug agenda`."

---

### M5 — Empty fleet state not specified in TUI

**Location:** TUI-UX-VISION.md §Level 0 — Fleet View
**Severity:** Medium

The fleet view spec describes the layout for a fleet with operations, but does not define the empty state (no operations at all, or all operations completed/cancelled). CLI-UX-VISION.md specifies: *"Falls back to `--help` when no operations exist and no TTY is attached."*

The TUI doesn't have a `--help` fallback concept. What does the TUI show when the fleet is empty?

**Fix required:** Add an empty state to the TUI Fleet View spec. Recommendation: *"When no operations are active, the fleet view shows: left pane — empty message 'No active operations. Run `operator run [goal]` to start.'; right pane — blank. The breadcrumb shows `fleet`. `q` quits."*

---

### M6 — Attention auto-selection ordering undefined

**Location:** CLI-UX-VISION.md §`operator answer`; TUI-UX-VISION.md §Level 0 key `a`
**Severity:** Medium

Both documents say `answer` (or `a` key) auto-selects "the first blocking attention" without defining what "first" means. Oldest by creation time? Most recently opened? Highest blocking severity? If an operation has two blocking attentions of different types, the auto-selection is indeterminate.

**Fix required:** Define ordering explicitly. Recommended: *"Auto-selection follows creation time ascending (oldest blocking attention first). If multiple blocking attentions exist and ATT is omitted, the oldest is selected and its question is displayed; the user is shown the count of remaining attentions after answering."*

---

## Recommendations

1. **Immediate (before any TUI implementation work):** Fix C1 (three `stop_turn` → `interrupt` replacements in TUI), H4 (stale answer syntax). These are pure text fixes that take minutes.

2. **Before publishing CLI-UX-VISION.md externally:** Add the VISION.md override argument (C2) and resolve the `attention`/`report` command list gap (H3). Both are documentation-only changes.

3. **During TUI design review:** Add confirmation behavior (H5), terminal state specs (H2), `p`/`u` at Level 1 (H1), and empty state (M5). These require small design decisions but no implementation.

4. **Deferred but tracked:** DecisionMemo CLI equivalent (M1), TUI roadmap section (M3), `agenda` decision (M4), attention ordering (M6), `[BLOCKED]` disambiguation (M2).

---

## Links to Assessed Materials

- `docs/TUI-UX-VISION.md`
- `docs/CLI-UX-VISION.md`
- `design/VISION.md` (§Protocol-oriented integration, §Design Principles §5 Transparency by default)
