# Critique Round 3 — Structure, Readability, and Redundancy
## Target: `design/VISION.md`

---

## Summary Assessment

VISION.md is technically accurate and internally coherent as a specification. However, by Round 3 the document has accumulated structural habits that work against a reader navigating top-to-bottom: the same design ideas are stated two or three times in different sections, a few sections exist only to summarize content already present, and several explanatory inserts appear in the wrong place for a first-time reader. The fixes are almost entirely organizational — no content needs to be invented, only consolidated and reordered.

**Strengths:**
- Drill-down model and CLI tier tables are well-structured and earn their format.
- The Mental Model three-actor breakdown is clear and appropriately placed.
- Code blocks are used sparingly and correctly.
- The normative intent is consistent, even if the preamble that declares it is misplaced.

**Weaknesses (summary):**
- Three sections revisit the operator loop concept without adding new material.
- The `[BLOCKED]` display-alias explanation appears verbatim three times.
- Two sections (`Architectural Direction`, `CLI First`) can be removed or folded without loss.
- Four items of definitional content are embedded in table cells or mid-paragraph prose where they cannot be found on a second read.
- The normative preamble is the first thing a reader encounters, before they know what the document is about.

---

## Red Team Composition

| Expert | Focus |
|---|---|
| Information Architect | Section ordering, reader journey top-to-bottom, misplaced information |
| Redundancy Detector | Repeated ideas, duplicated content, restatements with no added value |
| Plain Language Editor | Sentence-level readability, list vs. prose choices, dense constructions |
| Table Critic | Tables and lists that add visual weight without adding clarity |
| Document Surgeon | Sections whose removal would leave the document more coherent |

---

## Critical Findings

### C1 — `[BLOCKED]` label explained three times (lines 354–356, 369–371, 375–377)

The same point — "`[BLOCKED]` is a CLI display alias for a subset of `PENDING` tasks, not a distinct state" — appears three times in three consecutive sub-sections of the Task Graph section. Lines 369-371 open a paragraph with a near-verbatim restatement of lines 354-356. Lines 375-377 repeat it a third time as the preamble to the code block.

**Impact:** Signals either that the author did not trust the earlier statement, or that the sub-sections were written independently and never reconciled. Either way, a reader who reads all three notices the repetition and loses confidence in the document's economy.

**Fix:** Keep the explanation once in "Task lifecycle" (lines 354-356). In "Task graph invariants," replace the repeated statement with a cross-reference: "The `[BLOCKED]` CLI label is a presentation alias — see Task lifecycle above." In "User-facing task view," remove the two-sentence preamble entirely; the code block is self-explanatory.

---

### C2 — Operator loop described three times (Project, Core Thesis, Design Principles § 1)

The operator loop concept — decompose goal into task graph, choose agent, execute, evaluate, iterate — is described in:
- **Project section** (lines 14-20): bullet list of what the system can do.
- **Core Thesis** (lines 79-87): 5-step numbered list of the loop's responsibilities.
- **Design Principles § 1** (lines 115-121): 5-item bullet list that restates decomposition, agent selection, result interpretation, and iteration.

By the time the reader reaches the Mental Model section, they have read the loop described three times. The Core Thesis is the clearest and most purposeful statement. Principle 1 could be reduced to "The operator drives all orchestration decisions through its own LLM brain" with a forward reference to Core Thesis rather than restating the loop steps.

---

### C3 — Deterministic guardrails repeated twice, stop conditions listed twice

Stop conditions appear fully in "Run Constraints and Stop Policy" (lines 98-109) with a 6-item list. The same concept appears in "Design Principles § 2" (lines 125-142) with a 10-item example list that is a superset of the first. The "Project" section also states "stop conditions, iteration limits, budget caps" at line 27.

**Impact:** A reader following up on stop conditions encounters two authoritative-looking lists and must determine whether they are the same or different. The lists are not identical (§ 2 adds retry policies, event recording, adapter capability checks, etc.), which is confusing — are these "stop conditions" or "deterministic guardrails"? The terminological conflation across sections is a readability problem as much as a redundancy problem.

**Fix:** "Run Constraints and Stop Policy" owns the stop conditions list. Principle 2 should name the broader category (deterministic control plane) and reference that section rather than restating a longer, differently-ordered list.

---

## High-Priority Findings

### H1 — "Architectural Direction" is a pure recap of Design Principles (lines 749–765)

The final section maps bullet-for-bullet to named design principles:
- "clean but not layered to excess" = Principle 4
- "protocol-oriented" = Principle 3
- "eventful and transparent" = Principle 5
- "LLM-first in planning and evaluation" = Principle 1
- "deterministic in execution policy" = Principle 2
- "adapter-driven at the edges" = Principle 3

The second list (lines 759-764) restates Core Thesis. No sentence in this section adds information not already present.

**Fix:** Remove the section entirely. A closing summary does not belong in a specification; it belongs in an essay. If a forward-looking "what to preserve under pressure" note is wanted, add one sentence to Design Principles or Core Thesis.

---

### H2 — Normative preamble is the first thing a reader encounters

The RFC-style `must`/`should`/`may` paragraph (lines 3-4) appears before any project description. A first-time reader has no context for what document they are reading conventions for. The preamble is also 65 words for a concept expressible in one sentence.

**Fix:** Move after the "Project" section introduction. Shorten to: "> **Normative language:** **must** is a binding requirement; **should** is a strong recommendation; **may** is permitted but not required. Prose stating behavior as fact (e.g., "commands are organised in three tiers") is also normative."

---

### H3 — "CLI First" section should be merged into "CLI Design"

"CLI First" (lines 556-575) is six lines of rationale followed by a 9-item wish list. "CLI Design" (lines 577+) follows immediately with mechanics. The separation creates a heading that delivers less than it promises and interrupts the read between rationale and design. The rationale paragraph and the wish list fit naturally as the opening of "CLI Design."

---

### H4 — "Interfaces" section restates Design Principles § 3

The "Interfaces" section (lines 486-499) lists six protocol names and states "the important point is not the names." This is the same point made by Principle 3, which already says the core should depend on capabilities, not concrete SDKs. The six names are illustrative and could be appended to Principle 3 as a brief example list.

---

### H5 — "Operator File Tools" section is misplaced

The section (lines 472-484) sits between "Multi-Session Coordination" and "Interfaces," breaking an architectural arc. File tools are a brain capability. They belong as a sub-section of the "Operator brain" description in the Mental Model section, or immediately after the Mental Model section.

---

## Medium-Priority Findings

### M1 — NEEDS_HUMAN paragraph is too dense

Lines 239-251 pack four distinct points into one paragraph: definition of NEEDS_HUMAN, behavior of non-blocking tasks, automatic reversion to RUNNING, and the overlay-condition concept. The overlay concept is easy to miss in this format.

**Fix:** Break into a short bullet list for the first three points, then state the overlay concept in a sentence that follows the list.

---

### M2 — "Attention during drain" edge case is placed too early

Lines 251-252 describe a drain/cancel interaction before the reader has a full model of the scheduler states or the drain mechanism. This is a narrow edge case that should appear after the basic lifecycle is fully described, or in a "notes" callout at the bottom of the section.

---

### M3 — harness_instructions definition is buried mid-paragraph

The first substantive definition of `harness_instructions` (lines 288-289) appears in the middle of the goal-patching sub-section, without a heading. This is the canonical definition of a key term but it is formatted as inline prose. Readers looking for this term later cannot find it by scanning headings.

**Fix:** Give it a `#### harness_instructions` heading or promote it to a callout block before the goal-patching description.

---

### M4 — Policy gap definition interrupts the involvement levels section

Lines 631 define "policy gap" and "novel strategic choice" in the body of the "Involvement levels" sub-section. These definitions are longer than the two involvement level descriptions combined. The definitions should be placed either before the involvement levels description or in a dedicated callout, not inline.

---

### M5 — operation/run distinction defined once but re-explained elsewhere

The `operation` vs. `run` distinction is clearly defined at lines 69-74. It is restated parenthetically in the Tier 1 command table for `run` (acceptable — a brief reminder) and effectively re-explained in Early Success Criteria item 1. The Success Criteria restatement adds length without clarity for a reader who has already encountered the definition.

---

## Lower-Priority Findings

### L1 — patch_* rejection table adds weight for thin content

The three-row rejection table (lines 295-299) could be stated in two plain sentences without loss of precision. Tables signal tabular structure; three rows mapping one field to one reason is not tabular in a meaningful sense.

---

### L2 — wakeup definition belongs outside a table cell

Line 649: the "wakeups" entry in the Tier 3 table contains a 22-word parenthetical defining "wakeup" — the first definition of the term in the document. Definitions should not be introduced inside table cells. A brief inline definition before the table, or a footnote, would be appropriate.

---

### L3 — Tier 1 table run cell parenthetical is too long for a table cell

The `run` entry in the Tier 1 table (lines 592-593) contains a ~25-word parenthetical. This breaks the visual scanning rhythm of the table. Move to a prose note immediately after the table or to a dedicated "run vs operation" callout.

---

### L4 — Operator File Tools table is under-sized for the format

The three-row file tools table (lines 473-479) would read equivalently as a one-sentence enumeration: "`read_file`, `list_dir`, and `search_text` — read only, no writes." The table signals more structure than it contains.

---

### L5 — message vs. typed command comparison table row labels are unclear

The four-row comparison table (lines 317-324) has row labels "Direction" and "Apply point" that are not obviously distinct. "Direction" means the routing target (user → brain vs. user → state machine); "Apply point" means when the effect takes effect. These labels should be renamed: "Routing target" and "When it takes effect" would be unambiguous.

---

## Recommendations

1. **Consolidate the three operator loop descriptions.** Keep Core Thesis as the authoritative statement. Reduce the Project bullet list to one sentence ("The core mechanism is an iterative operator loop — see Core Thesis below"). Reduce Principle 1 to a one-sentence statement + forward reference.

2. **Remove the `[BLOCKED]` repetition.** One statement in Task lifecycle, a cross-reference in Task graph invariants, and no preamble in User-facing task view.

3. **Remove "Architectural Direction."** No content is lost.

4. **Merge "CLI First" into "CLI Design"** as the opening paragraph.

5. **Fold "Interfaces" into Design Principles § 3** as a brief example list.

6. **Move "Operator File Tools"** to a sub-section of Mental Model → Operator brain.

7. **Shorten and relocate the normative preamble** to after the Project section opener; reduce to 2–3 lines.

8. **Break NEEDS_HUMAN paragraph** into a list + overlay-concept sentence.

9. **Move "Attention during drain" callout** to the end of Operation Lifecycle, after the main model is established.

10. **Give `harness_instructions` a visible heading** before its definition block.

11. **Move policy gap definition** to a callout before the involvement levels, not inline within them.

12. **Replace patch_* rejection table** with two plain sentences.

13. **Move the `wakeup` definition** out of the Tier 3 table cell (inline before the table or as a brief callout).

14. **Move the `run` parenthetical** out of the Tier 1 table cell (prose note after the table).

---

## Compact Ledger

**Target document:** `/Users/thunderbird/Projects/operator/design/VISION.md`

**Focus used:** Structure, readability, and redundancy — sections that repeat the same idea, information in the wrong place for a top-to-bottom reader, prose harder to read than necessary, tables or lists that obscure rather than clarify, sections whose removal would improve coherence.

**Main findings:**
- `[BLOCKED]` display-alias explanation repeated verbatim three times (lines 354, 369, 375)
- Operator loop described three times across Project, Core Thesis, and Principle 1
- Stop conditions listed twice in separate sections with different (confusing) scopes
- "Architectural Direction" final section is a full recap of Design Principles with no new content
- "CLI First" and "CLI Design" are one section split into two
- "Interfaces" section restates Principle 3 as a list with no new content
- "Operator File Tools" is misplaced between multi-session and interfaces sections
- Normative preamble is the first thing a reader encounters, before project context
- Four definitions buried in table cells or mid-paragraph prose (harness_instructions, wakeup, run parenthetical, policy gap)
- NEEDS_HUMAN paragraph and "attention during drain" callout are dense and early-placed

**Ordered fix list for the repair round:**

1. Remove "Architectural Direction" section entirely (no content loss)
2. Merge "CLI First" into "CLI Design" as its opening paragraph
3. Consolidate `[BLOCKED]` explanation to one occurrence in Task lifecycle; replace other two with a one-line cross-reference and remove the User-facing task view preamble
4. Reduce operator loop restatements: trim Project bullet list, reduce Principle 1 to a one-sentence + forward-reference form
5. Refactor stop conditions: "Run Constraints" owns the list; Principle 2 references it rather than restating a second, longer list
6. Fold "Interfaces" protocol list into Design Principles § 3 as example lines; remove the standalone section
7. Move "Operator File Tools" to a sub-section under Mental Model → Operator brain
8. Shorten normative preamble to 2-3 lines and relocate it to after the Project section opener
9. Break NEEDS_HUMAN paragraph into bullet list + overlay sentence
10. Move "Attention during drain" callout to the end of Operation Lifecycle
11. Give `harness_instructions` a `####` heading before its definition
12. Move policy gap definition to a callout block before the involvement levels description
13. Replace patch_* rejection table with two prose sentences
14. Move `wakeup` definition out of the Tier 3 table cell
15. Move `run` parenthetical out of the Tier 1 table cell
