# Critique: ARCHITECTURE.md — Round 1
<!-- Red Team output. Do not merge into ARCHITECTURE.md directly; use as a repair checklist. -->

## Summary Assessment

ARCHITECTURE.md is a well-structured reference document that mostly tracks VISION.md faithfully.
The majority of section pointers are accurate and the major invariants (event model, decision
split, protocol orientation) are consistent with VISION.md. However, four areas need repair before
the document can serve as a reliable normative complement to VISION.md:

1. One direct contradiction: the Artifact store section conflates operator-internal planning
   material with the VISION.md definition of artifacts as agent-session deliverables.
2. One inherited label inconsistency: `collaborative` involvement level appears in the attention
   section but is not a defined level in VISION.md's involvement model.
3. Six substantive concept gaps: operator messages, involvement level definitions, task graph
   invariants, `stop_turn` rejection, `patch_*` rejection conditions, and attention-during-drain
   behavior are all present in VISION.md but absent from ARCHITECTURE.md.
4. Five sections retain design-phase forward-tense language describing things that are implemented.

---

## Red Team Composition

| Role | Critique Focus |
|---|---|
| Normative Consistency Auditor | Contradictions between ARCHITECTURE.md claims and VISION.md normative content |
| Completeness Inspector | Concepts present in VISION.md that are absent from ARCHITECTURE.md |
| Temporal Language Analyst | Stale forward-tense language describing implemented things |
| Cross-Reference Validator | Section pointers — whether the named section exists at the right level in VISION.md |
| Conceptual Framing Critic | Terminology and conceptual framing alignment between the two documents |

---

## Critical Findings

### C-1 — Artifact framing contradicts VISION.md

**Location:** ARCHITECTURE.md, "Memory Layers → Artifact store" section.

ARCHITECTURE.md describes the artifact store as holding "research plans, design notes, findings,
and future ADR-like internal records." VISION.md (Operator Workspace section, final paragraph)
states explicitly:

> "Artifacts are user-facing deliverables — files, diffs, reports, or structured data returned
> as the concrete output of completed task work. They are distinct from `MemoryEntry` objects,
> which are operator-internal context used for planning and are not exposed as deliverables.
> The operator does not produce artifacts; only agent sessions do."

"Research plans" and "design notes" are operator-internal planning material — i.e. `MemoryEntry`
territory by VISION.md's definition, not artifacts. ARCHITECTURE.md's list conflates the two,
directly contradicting the VISION.md boundary.

**Impact:** A contributor implementing or testing the artifact store would use the wrong scope,
potentially storing operator-internal planning material as artifacts.

---

### C-2 — `collaborative` involvement label used but not defined in VISION.md

**Location:** ARCHITECTURE.md, "True Harness Direction → Attention and autonomy" section.

The phrase "at `collaborative` or higher involvement" appears in ARCHITECTURE.md's description of
when `policy_gap` and `novel_strategic_fork` block the operation. This label is inherited from
the same sentence in VISION.md's Attention requests section. However, VISION.md's Involvement
levels section (CLI Design → Tier 2 → Involvement levels) defines exactly two levels:
`unattended` and `interactive`. The label `collaborative` does not appear in the defined set.

This is a VISION.md internal inconsistency that ARCHITECTURE.md inherits without flagging it.
ARCHITECTURE.md also does not define what involvement levels exist, making the `collaborative`
reference a dangling label.

**Impact:** Implementers reading the attention section will encounter a level name that does not
map to any defined level in the normative reference.

---

### C-3 — Operator messages entirely absent from ARCHITECTURE.md

**Location:** No section in ARCHITECTURE.md.

VISION.md (User Interaction Model → Free-form operator messages) defines a distinct command
class — `message op-id "..."` — with its own semantics:

- free-form context injected into the brain's next planning decision
- operator message window (default 3 planning cycles), configurable per project or at run time
- `operator_message.dropped_from_context` domain event emitted on aging out
- visible in `watch` and `dashboard`
- distinct from typed commands in routing target, effect timing, and persistence

ARCHITECTURE.md mentions none of this. The application layer responsibility list, the domain
object list, the event model section, and the inspection surfaces section all omit operator
messages. The command `message` also appears in the CLI inspection surfaces list
(VISION.md Tier 1) but has no counterpart description in ARCHITECTURE.md.

**Impact:** A contributor working on the application layer or event model has no architectural
anchor for this feature.

---

## High-Priority Findings

### H-1 — Involvement levels not defined in ARCHITECTURE.md

**Location:** ARCHITECTURE.md, "True Harness Direction → Attention and autonomy" and ADR
reference 0017.

ARCHITECTURE.md refers to "involvement levels" and "autonomy policy" multiple times (ADR 0017,
policy filter description, attention section) but never defines what the levels are or what they
mean behaviorally. VISION.md (CLI Design → Tier 2 → Involvement levels) defines:

- `unattended`: brain proceeds without interrupting for routine decisions; policy gaps surface
  as attention but do not block non-affected tasks
- `interactive`: policy gaps and strategic forks block forward progress until answered

ARCHITECTURE.md should at minimum name and briefly describe these two levels, or clearly state
they are fully defined in VISION.md and give the exact section reference.

---

### H-2 — Task Graph section absent; `[BLOCKED]` display-alias rule not stated

**Location:** ARCHITECTURE.md, "Task Authority Model" section covers only the brain/runtime split.

VISION.md has a full "Task Graph" section with normatively specified content:

- Five canonical task states: `PENDING → READY → RUNNING → COMPLETED | FAILED | CANCELLED`
- `[BLOCKED]` is a **display grouping label** for `PENDING` tasks with unresolved dependencies —
  it is explicitly not a distinct lifecycle state
- Four graph invariants: DAG (cycle-detection), monotonicity (dependency removal requires
  non-empty `reason`), completion propagation (deterministic, no LLM call), no self-dependency

ARCHITECTURE.md's task authority model mentions brain vs runtime split but misses the invariants
and does not capture the `[BLOCKED]` display-alias rule. A contributor building the task view
or a cycle-detection check has no architectural guidance here.

---

### H-3 — "File tools" section pointer is imprecise (subsection, not top-level)

**Locations:** ARCHITECTURE.md lines in Memory Layers, Memory Correctness, and State Objects
sections — all reference "VISION.md File tools."

In VISION.md, the File tools content is a subsection nested under **Mental Model → Operator
brain → File tools** — it is not a top-level section. A reader following the pointer would look
for a top-level section called "File tools" and not find it at the expected level.

Correct pointer: "VISION.md Mental Model → Operator brain → File tools."

---

### H-4 — "Loop architecture" section pointer is imprecise (subsection, not top-level)

**Locations:** ARCHITECTURE.md "Operator Loop" and "Focus And Wait Semantics" sections reference
"VISION.md Loop architecture."

In VISION.md, "Loop architecture" is a subsection under **Event Model → Loop architecture** —
not a top-level section.

Correct pointer: "VISION.md Event Model → Loop architecture."

---

### H-5 — Operation/run distinction absent from ARCHITECTURE.md

**Location:** ARCHITECTURE.md, "Core Runtime Model" and "Preferred Runtime Surface" sections.

VISION.md (Why This Exists, lines 60–65) establishes a precise distinction:

> "A **run** is the execution of an operation — specifically, one `operator run` invocation.
> An operation may have multiple runs if it is interrupted and resumed; `operation` names the
> persistent entity, `run` names one execution attempt over it."

ARCHITECTURE.md uses "operation run" and "operation" interchangeably throughout without ever
defining this distinction. The Core Runtime Model section opens with "The main runtime unit is
an `operation run`" — which implies run = operation. A contributor encountering resumable mode
or multi-run operations has no architectural framing for why a single operation can span multiple
runs.

---

## Lower-Priority Findings

### L-1 — `patch_*` rejection conditions not documented

**Location:** ARCHITECTURE.md, "True Harness Direction → Live control."

VISION.md specifies three rejection conditions for `patch_*` commands: `operation_terminal`,
`invalid_payload`, and `concurrent_patch_conflict`. ARCHITECTURE.md lists the patch commands
as implemented but does not reference these rejection semantics.

---

### L-2 — Attention-during-drain semantics absent

**Location:** ARCHITECTURE.md, "Core Runtime Model → Terminal control decisions" and scheduler
state description.

VISION.md (Operation Lifecycle → Failure visibility) specifies: when a new attention request
arrives during a `draining` scheduler state, it is accepted and queued — except during a
cancel-drain, where new attentions are rejected with `operation_cancelling`. ARCHITECTURE.md
lists `draining` as a valid scheduler state but says nothing about this edge-case behavior.

---

### L-3 — `stop_turn` rejection semantics absent

**Location:** ARCHITECTURE.md, "Core Runtime Model" and attached-mode live control description.

VISION.md specifies that `stop_turn` targeting a task not in `RUNNING` state is rejected with
`stop_turn_invalid_state`, and the actual task state is included in the rejection message.
ARCHITECTURE.md does not document this behavior.

---

### L-4 — `OperationStore` section uses design-phase language

**Location:** ARCHITECTURE.md, `OperationStore` protocol section.

Phrases like "Expected responsibilities:", "Start with a file-backed implementation",
"will likely need to persist", and "Embedded assignment fields inside `Task` are sufficient for
the first long-lived version" describe planned, not implemented, design. Given the project's
current state, a file-backed store is already implemented. This section should be updated to
present-tense description of what is implemented.

---

### L-5 — `Composition and DI` section uses "Likely root responsibilities"

**Location:** ARCHITECTURE.md, "Composition And DI" section.

"Likely root responsibilities:" is forward-planning language. If `dishka` is already wiring the
system (stated fact in the same paragraph), the responsibilities are actual. Should read
"Root responsibilities:" or "Responsibilities of the composition root:".

---

### L-6 — `Repository Direction` section uses "likely source tree"

**Location:** ARCHITECTURE.md, "Repository Direction" section.

"The likely source tree looks roughly like this:" — given the actual source tree is established,
this should confirm the current tree or note where it diverges from the sketch. The qualifier
"likely" creates ambiguity about whether this is aspirational or actual.

---

### L-7 — `Concurrency` section uses "initial" framing

**Location:** ARCHITECTURE.md, "Concurrency" section.

"The initial system stays conservative" implies a design-start framing. If the system is built
and multi-session coordination is referenced as implemented, "initial" should be dropped.

---

### L-8 — `Delivery` section lists "future Python convenience APIs"

**Location:** ARCHITECTURE.md, "Delivery" section, examples list.

"future Python convenience APIs" is unqualified forward-tense. If not yet built, it should be
labeled `(planned)` or moved to a separate future-direction note. If the API is intentionally
out of scope for now, omitting it from the current layer description is cleaner.

---

## Recommendations

1. **Correct C-1 immediately**: rewrite the Artifact store description to match VISION.md's
   definition — artifacts are agent-session deliverables, not operator-internal planning notes.
   Move "research plans" and "design notes" to the `MemoryEntry` / Task memory / Objective memory
   descriptions where they belong.

2. **Fix C-2 and H-1 together**: add a brief "Involvement Levels" subsection defining
   `unattended` and `interactive` (with pointer to VISION.md CLI Design → Involvement levels),
   then replace `collaborative` in the attention section with the correct level reference and
   note that the VISION.md blocking-rule text contains an inconsistency (the word `collaborative`
   does not match the defined levels).

3. **Add operator messages (C-3)**: add at minimum a paragraph in the Application layer section
   and the Event model section acknowledging operator messages — their domain event
   (`operator_message.dropped_from_context`), the window mechanism, and visibility in `watch`/
   `dashboard`. Point to VISION.md User Interaction Model → Free-form operator messages.

4. **Add Task Graph section (H-2)**: create a "Task Graph" section (or expand the existing
   Task Authority Model section) to capture the five canonical states, `[BLOCKED]` as display
   alias, and the four runtime-enforced invariants. These are architectural constraints, not
   just application-layer details.

5. **Fix section pointers (H-3, H-4)**: update "VISION.md File tools" to "VISION.md Mental
   Model → Operator brain → File tools" and "VISION.md Loop architecture" to "VISION.md Event
   Model → Loop architecture."

6. **Add operation/run distinction (H-5)**: add a brief definition box or paragraph in Core
   Runtime Model clarifying that `operation` is the persistent entity, `run` is one execution
   attempt, and an operation may span multiple runs.

7. **Sweep stale forward-tense language (L-4 through L-8)**: update `OperationStore`,
   `Composition and DI`, `Repository Direction`, and `Concurrency` sections to present tense.
   Mark `future Python convenience APIs` as `(planned)` or remove from the current-state
   description.

8. **Add pointer coverage for rejection conditions (L-1, L-2, L-3)**: at minimum add a sentence
   in the live control section pointing to VISION.md User Interaction Model for `patch_*`
   rejection conditions, drain-time attention behavior, and `stop_turn` rejection semantics.

---

## Methodology

- Both documents read in full from the file system (no reasoning from memory).
- Five critic roles applied in a structured round-robin.
- All findings are grounded in direct text evidence from both documents with line-level citations.
- No claims are attributed to either document that are not present in the text.
- Round 1 scope: alignment with VISION.md only. Code correctness and issues purely internal to
  ARCHITECTURE.md are out of scope for this round.

---

## Ledger

**Target document:** `/Users/thunderbird/Projects/operator/design/ARCHITECTURE.md`

**Focus used:** Alignment with VISION.md — contradictions, missing concepts, stale forward-tense
language, and section pointer accuracy.

**Main findings:**
- 1 direct contradiction: artifact framing (C-1)
- 1 inherited label inconsistency: `collaborative` involvement level (C-2)
- 1 major missing concept class: operator messages entirely absent (C-3)
- 3 high-priority gaps: involvement level definitions, task graph invariants + `[BLOCKED]` alias,
  operation/run distinction
- 2 imprecise section pointers: "File tools" and "Loop architecture" are subsections, not top-level
- 3 missing edge-case semantics: `patch_*` rejection, drain-time attention, `stop_turn` rejection
- 5 stale forward-tense items: OperationStore, Composition and DI, Repository Direction,
  Concurrency, future Python convenience APIs

**Ordered fix list (for repair round):**

1. Rewrite Artifact store description to match VISION.md artifact definition (C-1)
2. Add Involvement Levels subsection defining `unattended` and `interactive`; fix `collaborative`
   label in attention section (C-2 + H-1)
3. Add operator messages to Application layer and Event model; cite domain event and window
   semantics (C-3)
4. Add Task Graph section: five states, `[BLOCKED]` display alias, four invariants (H-2)
5. Fix "VISION.md File tools" → "VISION.md Mental Model → Operator brain → File tools" (H-3)
6. Fix "VISION.md Loop architecture" → "VISION.md Event Model → Loop architecture" (H-4)
7. Add operation/run distinction to Core Runtime Model (H-5)
8. Add pointer to VISION.md for `patch_*` rejection, drain-time attention, `stop_turn`
   rejection conditions (L-1, L-2, L-3)
9. Sweep forward-tense language: OperationStore, Composition and DI, Repository Direction,
   Concurrency, Delivery (L-4 through L-8)
