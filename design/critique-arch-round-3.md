# Critique: ARCHITECTURE.md — Round 3
**Focus**: Wording precision, VISION.md pointer completeness, structural finish, aspirational
language, readability.
**Round**: 3 of 3
**Assessed file**: `design/ARCHITECTURE.md`
**Assessment date**: 2026-04-02

---

## Summary Assessment

ARCHITECTURE.md is in good shape overall. The prose is mostly tight, the layer model is coherent,
and earlier rounds have clearly sharpened the document. Round 3 finds no structural collapse or
factual errors, but it does surface a cluster of issues that would leave a careful contributor
uncertain: several vague qualifiers, a small set of future-tense sentences embedded without
labeling in present-tense sections, a few VISION.md pointer paths whose precision is
questionable, and four or five structural seams where sections end without connecting forward.
The overall fix list is tractable and editorial in nature.

**Strengths**:
- Deliberate distinction between implemented and future state in most sections.
- ADR references are precise and well-placed.
- The domain/application/integration/delivery layer split is described consistently.
- The authority model (brain vs deterministic runtime) is stated clearly and never confused.
- Known technical debt is explicitly labeled.

**Weaknesses**:
- "Mostly", "compact", "small number", "mostly framework-free" — imprecise qualifiers that give
  contributors no actionable signal.
- Three `will/should` sentences inside protocol/store sections are not labeled as roadmap items.
- Several sections end without a forward pointer, leaving the narrative thread broken.
- `§ Protocols` intro sentence is content-free.
- `§ Agent Adapters` "Expected shape" heading implies the adapters are not yet implemented.

---

## Red Team Composition

| Role | Focus |
|---|---|
| Technical Editor (precision) | Vague/ambiguous sentences; "will/should/may" audit |
| Cross-reference auditor | VISION.md pointer paths and naming consistency |
| Structural completeness reviewer | Abrupt endings, orphaned bullets, heading levels |
| Contributor-experience advocate | What leaves a new contributor guessing |
| Copy editor / consistency checker | Inconsistent terminology, mixed tense, duplication |

---

## Critical Findings

### C-1: Aspirational sentences embedded without labeling in `OperationStore`

**Location**: § `OperationStore`, lines ~657–665.

Three sentences in this section are future-tense or conditional but appear inside a
present-tense protocol description with no visual distinction:

> "As long-lived work grows, the store will need to persist: objective state, task state,
> memory entries, active and historical sessions, and durable artifacts."

> "A separate assignment entity should only be introduced when that simpler shape stops
> carrying the runtime cleanly."

A contributor implementing or testing the store today cannot tell which obligations are current
and which are roadmap items. The "will need to" block could be mistaken for unimplemented
protocol requirements.

**Fix**: Wrap the "will need to" list in a labeled block (e.g., `> **Roadmap:** ...`) or move
it to a separate subsection titled "Not yet implemented" or "Future obligations". Change
"should only be introduced" to a conditionally framed design note: "A separate assignment
entity is warranted only when..." — present-tense guidance, not future obligation.

---

### C-2: "Expected shape" headings in `Agent Adapters` imply unimplemented state

**Location**: § Agent Adapters → Claude ACP adapter and Codex ACP adapter, lines ~757 and ~769.

Both sub-sections are headed "Expected shape:". The word "expected" implies these adapters
are designed but not yet present. The repository contains active adapter source files
(`src/agent_operator/adapters/claude_acp.py`, `src/agent_operator/adapters/codex_acp.py`).
Using "Expected shape" for implemented code misleads contributors.

Additionally, the Claude ACP adapter description includes:

> "ACP Python SDK-backed substrate by default once direct runtime evidence is established"

This sentence is opaque: "direct runtime evidence" is undefined, no criteria are given, and the
contributor does not know whether this is a pending milestone or an indefinite condition.

**Fix**: Rename both subsection headings to "Architecture" or "Design notes" (matching the rest
of the document's style). Clarify or remove the "once direct runtime evidence is established"
clause — either state the concrete criterion or note it as a deferred decision with an ADR
reference.

---

### C-3: `§ Protocols` intro sentence is content-free

**Location**: § Protocols, line ~619.

> "The first implementation keeps the protocol surface compact."

This is the entire content of the `§ Protocols` section before the sub-sections begin.
"Compact" is undefined; "the first implementation" implies a future second implementation
without explaining the difference. A contributor landing on this section has no orientation
to what protocols are in this system, how they relate to layers, or why this section exists
as a grouping.

**Fix**: Either replace with a one-sentence orienting statement ("Protocols define the seams
between layers. Each is a `typing.Protocol` with a narrow, testable surface.") or remove the
sentence entirely if the sub-sections are self-explanatory.

---

## High-Priority Findings

### H-1: "Mostly framework-free" / "favors dataclasses" contradicts the next sentence

**Location**: § Domain, lines ~35–36.

> "This layer stays mostly framework-free and favors dataclasses and enums.
> The current implementation uses `pydantic` models for domain objects..."

"Mostly framework-free" + "favors dataclasses" is immediately contradicted by "uses pydantic
models." The two sentences together leave a contributor unsure whether to write new domain
objects as dataclasses, pydantic models, or something else.

**Fix**: Remove "stays mostly framework-free and favors dataclasses and enums." Keep only the
factual second sentence and add the intent: "Domain objects use `pydantic` models with a bias
toward small explicit types and minimal framework leakage."

---

### H-2: "If the implementation needs task priority" — orphaned conditional

**Location**: § Task Authority Model, lines ~582–583.

> "If the implementation needs task priority, it distinguishes between a brain-level proposed
> priority and a deterministic effective runnable priority."

This conditional sentence is appended to a definitive authority-split list with no transition.
It is unclear whether task priority is implemented, planned, or hypothetical. The conditional
framing ("if...") treats an architectural invariant as a contingency.

**Fix**: Either (a) state whether task priority is currently implemented ("Task priority is not
yet implemented; when added, it will distinguish…") or (b) if it is implemented, rewrite as a
present-tense invariant and move it into the appropriate bullet ("the deterministic runtime
enforces: ... effective runnable priority distinct from brain-proposed priority").

---

### H-3: Duplicate sentences in `§ Memory Correctness`

**Location**: § Memory Correctness, lines ~496–498.

These two consecutive sentences say substantially the same thing:

> "The freshness, supersession, and two-scope semantics are now normatively specified in
> VISION.md (Mental Model → Operator brain → File tools). The original minimum semantics were
> captured in ADR 0006."

> "The two-scope model and freshness tracking are implemented. See VISION.md Mental Model →
> Operator brain → File tools for the normative specification."

The second sentence adds nothing beyond a repeat of the same VISION.md pointer already given
one sentence earlier.

**Fix**: Cut the second sentence entirely. The ADR 0006 reference in the first block is
sufficient history; the VISION.md pointer is already given.

---

### H-4: "May produce trace events" — ambiguous guarantee in `§ Failure Model`

**Location**: § Failure Model, lines ~829–830.

> "Failures that do not yet terminate the operation may produce trace events for forensic
> inspection."

"May produce" is ambiguous: does the runtime guarantee trace events for non-terminal failures,
or is it a best-effort possibility? A contributor implementing failure handling does not know
whether to rely on these trace events.

**Fix**: Clarify: either "produce best-effort trace events" (explicit about the non-guarantee)
or "produce trace events" (if the guarantee exists). Remove "may" if the behavior is
deterministic; keep it only with a qualifier if it is genuinely conditional.

---

### H-5: `§ Protocols → "The protocol is kept narrow"` — undefined constraint

**Location**: § `OperationStore`, line ~654.

> "The protocol is kept narrow."

"Narrow" is not defined. Does this mean three methods? One method per responsibility? A
contributor implementing a second `OperationStore` backend does not know what "narrow" means
for their implementation surface.

**Fix**: Replace with a concrete statement: "The protocol exposes the minimum surface needed
for the application loop: create, append, load. It does not expose query or aggregation
operations." (Adjust to match actual interface — the architectural principle should be
expressible concretely.)

---

### H-6: VISION.md pointer `Why This Exists` is an unusual section name

**Location**: § Core Runtime Model, line ~136.

> "See VISION.md Why This Exists for the canonical statement."

"Why This Exists" reads like a FAQ or motivation section heading, not a formal architecture
section name. This pointer is more likely to be broken or to lead a contributor to scan
VISION.md looking for a section that may be titled differently.

**Fix**: Confirm the exact VISION.md section heading and update the pointer to the exact name.
If no section by that name exists, either remove the pointer or point to the nearest accurate
section.

---

### H-7: `§ Concurrency` ends without explaining multi-session routing relevance

**Location**: § Concurrency, lines ~808–810.

> "Multi-session parallel coordination within a single operation is supported — see VISION.md
> Multi-Session Coordination for the routing rules and serialization model."

The section describes a conservative default, then ends with a forward pointer to a feature
with no architectural context. A contributor reading the concurrency model does not understand
how multi-session coordination relates to the "one active operator loop per run" default stated
two sentences earlier.

**Fix**: Add one sentence bridging the default and the multi-session capability: "When policy
allows parallel sessions, the operator loop uses the routing rules in VISION.md
Multi-Session Coordination to schedule and serialize them."

---

## Lower-Priority Findings

### L-1: "Python convenience APIs (planned)" in a feature list

**Location**: § Delivery, line ~122.

The word "(planned)" appears inline in an example list alongside two implemented surfaces
(CLI commands, machine-readable console output). There is no visual distinction between
implemented and planned items in this list.

**Fix**: Either remove the planned item until it is implemented, or move it to a separate
"Planned surfaces" note below the list. Do not mix implementation states in a flat example list.

---

### L-2: `§ Repository Direction` ends abruptly

**Location**: § Repository Direction, line ~928.

The section ends with:
> "This is a directional sketch, not a frozen filesystem contract."

This is a sensible caveat but provides no forward guidance. A contributor who has just read the
tree sketch does not know where to start navigating, whether there is a module map, or which
layers map to which directories.

**Fix**: Add one sentence pointing to the relevant layer sections: "The `domain/`, `application/`,
`protocols/`, and `adapters/` directories correspond to the Architectural Layers described above."

---

### L-3: `§ Standing Architectural Policy` ends the document without a closing bridge

**Location**: § Standing Architectural Policy, lines ~930–939 (end of document).

The document ends with a comma-separated principles list with no closing sentence. A contributor
reaching the end has no signal that the document is complete, no pointer to related materials,
and no guidance on how to raise questions or propose changes.

**Fix**: Add a brief closing note: "Deviations from these principles should be captured in an
ADR. For decisions already made, see `design/adr/`."

---

### L-4: `§ Testability` ends without pointing to the `testing/` module

**Location**: § Testability, line ~902.

> "The system is testable with fake brains and fake adapters."

This sentence states a fact but does not point a contributor to the `testing/fakes.py` module
visible in the repository tree. The section is the natural place to anchor this.

**Fix**: Append: "Fake implementations live in `testing/fakes.py` (see Repository Direction)."

---

### L-5: `§ Operator Loop` has no pointer to `§ Failure Model`

**Location**: § Operator Loop, line ~526.

The loop description ends with a forward reference to `§ Decision Split` but has no pointer to
`§ Failure Model` for abnormal termination. A contributor reading the loop description does not
know where error handling is specified.

**Fix**: Append to the loop description: "For failure handling and abnormal loop termination,
see Failure Model below."

---

### L-6: Repeated VISION.md pointer within one paragraph

**Location**: § Memory Layers → Artifact store, lines ~459–467; § Memory Correctness,
lines ~496–498.

`Mental Model → Operator brain → File tools` is cited four times in a small span (including two
consecutive sentences in § Memory Correctness — see H-3 above). Even after removing the
duplicate per H-3, the pointer appears three times in close proximity. The first occurrence
carries informational value; subsequent ones add visual noise without navigation benefit.

**Fix**: Retain the pointer once per section. Remove the repeat in § Memory Correctness per H-3.
Consider merging the two `MemoryEntry` scope descriptions (in § Memory Layers and § State
Objects) into one location with a pointer from the other.

---

### L-7: Inconsistent involvement-level heading pointer depth

**Location**: § Involvement levels, line ~312.

> "See VISION.md CLI Design → Tier 2 → Involvement levels for the full behavioral specification."

This is the deepest nested VISION.md pointer in the document (three levels). Other pointers in
the same document use one- or two-level paths. The three-level path is unusually specific; if
VISION.md's heading structure does not match exactly, the pointer is silently broken.

**Fix**: Verify the exact heading path in VISION.md. If "Tier 2" is not a formal sub-heading,
shorten to "CLI Design → Involvement levels" or whatever the actual heading path is.

---

### L-8: "A small number of active agent sessions" — not a constraint

**Location**: § Concurrency, line ~805.

> "one or a small number of active agent sessions at a time"

"A small number" is not an architectural constraint. It tells a contributor nothing about actual
limits or when concurrency is permitted.

**Fix**: Replace with a concrete statement of the actual default or limit, or frame it as a
policy question: "Concurrency is governed by the involvement level and operation configuration."

---

## Recommendations

1. **Create an implementation-status convention** for the document. The current mix of
   present-tense implemented facts, future-tense roadmap items, and conditional design notes
   creates unnecessary ambiguity. A simple inline convention (`> **Roadmap:**` blocks, or a
   footnote-style `[not yet implemented]` tag) would make the status of any statement
   immediately clear to contributors.

2. **Audit all VISION.md section pointers against the actual VISION.md heading tree.** The
   cross-reference auditor identified twelve distinct VISION.md section names cited in
   ARCHITECTURE.md. A one-pass verification against the actual heading list would catch broken
   pointers before contributors encounter them.

3. **Add a one-paragraph "how to navigate this document" note to § Purpose.** The document is
   long and non-linear. A brief reading-order hint would reduce time-to-productivity for new
   contributors.

4. **Consolidate `MemoryEntry` scope descriptions.** The two-scope model is described in
   § Memory Layers → Artifact store AND in § State Objects. Pick one canonical location; point
   from the other.

5. **Unify `Agent Adapter` sub-section format.** Both adapter sub-sections use a plain bullet
   list under "Expected shape:". Replace with consistent headings and a cross-reference to the
   adapter-addition guide (or ADR) when one exists.

---

## Methodology

- Target document read once in full (940 lines).
- VISION.md not re-read per Round 3 instructions; VISION.md pointer findings are based on the
  pointer paths in ARCHITECTURE.md only. Verification of whether the named sections exist
  under those exact headings requires a separate pass against VISION.md and is noted as a
  limitation of this round.
- No claims are attributed to the author beyond what appears verbatim in the document.

---

## Compact Ledger

**Target document**: `design/ARCHITECTURE.md`

**Focus**: Wording precision, VISION.md pointer completeness, structural finish, aspirational
language, readability.

**Main findings**:
- Three future/conditional sentences in `OperationStore` are unlabeled roadmap items embedded
  in present-tense protocol description.
- "Expected shape" headings in Agent Adapters misrepresent implemented adapters as aspirational.
- `§ Protocols` intro sentence is content-free; `§ Repository Direction` and
  `§ Standing Architectural Policy` end abruptly without forward connections.
- "Mostly framework-free / favors dataclasses" directly contradicts the next sentence.
- Duplicate VISION.md pointer sentences in `§ Memory Correctness`.
- VISION.md pointer `Why This Exists` is an unusual name likely to break navigation.
- "May produce trace events" leaves failure-model guarantees ambiguous.
- Six vague qualifiers ("mostly", "compact", "narrow", "small number", "expected") give
  contributors no actionable signal.

**Exact ordered fix list for the repair round**:

1. **`OperationStore` — "will need to persist" block**: wrap in `> **Roadmap:**` or move to
   a labeled "Future obligations" subsection.
2. **`OperationStore` — "should only be introduced"**: rewrite as present-tense conditional
   design note.
3. **Agent Adapters — "Expected shape:" headings**: rename to "Architecture" or "Design notes".
4. **Claude ACP adapter — "once direct runtime evidence is established"**: state the concrete
   criterion or note as deferred with an ADR reference.
5. **`§ Protocols` intro sentence**: replace with an orienting statement or remove.
6. **Domain layer — "mostly framework-free / favors dataclasses"**: remove and consolidate into
   the factual pydantic sentence.
7. **Task Authority Model — orphaned conditional**: resolve whether task priority is implemented
   and rewrite accordingly.
8. **`§ Memory Correctness` — duplicate sentences**: cut the second VISION.md pointer sentence.
9. **`§ Failure Model` — "may produce trace events"**: clarify guarantee vs best-effort.
10. **`OperationStore` — "The protocol is kept narrow"**: replace with a concrete statement of
    the actual protocol surface.
11. **`§ Core Runtime Model` — VISION.md pointer "Why This Exists"**: verify exact section name
    in VISION.md; update pointer.
12. **`§ Concurrency` — "a small number"**: replace with a concrete constraint or policy
    reference.
13. **`§ Concurrency` — abrupt ending**: add one bridging sentence before the VISION.md pointer.
14. **`§ Delivery` — "(planned)" inline**: move planned item out of the example list.
15. **`§ Repository Direction` — abrupt ending**: add directory-to-layer mapping sentence.
16. **`§ Standing Architectural Policy` — abrupt document ending**: add ADR deviation note.
17. **`§ Testability` — no module pointer**: append reference to `testing/fakes.py`.
18. **`§ Operator Loop` — no failure pointer**: append pointer to `§ Failure Model`.
19. **VISION.md pointer `CLI Design → Tier 2 → Involvement levels`**: verify exact heading path;
    shorten if "Tier 2" is not a formal heading.
20. **`MemoryEntry` scope description duplication** (§ Memory Layers vs § State Objects):
    consolidate into one canonical location; add pointer from the other.
