# Critique: ARCHITECTURE.md — Round 2 of 3

**Target document**: `/Users/thunderbird/Projects/operator/design/ARCHITECTURE.md`
**Focus**: Internal coherence — cross-section conflicts, duplication, tonal inconsistencies,
structural gaps, VISION.md pointer accuracy against local claims
**Round**: 2 of 3
**Method**: Swarm Red Team (5 critics: Technical Editor, Information Architect, Logic Auditor,
Cross-Reference Inspector, Reader Advocate)
**Limitation**: VISION.md was not re-read in full; the one VISION.md inconsistency surfaced here
(the `collaborative` term) is already called out within ARCHITECTURE.md itself and required no
external lookup.

---

## Summary Assessment

ARCHITECTURE.md is functionally useful and covers its declared scope. The coherence problems are
not catastrophic but they accumulate into a document that:

- defines the same concepts in two places with slightly different framing,
- introduces state objects in lists but elaborates only some of them, leaving the rest as dead
  entries,
- uses three tonal registers when it declares one, and
- has several VISION.md pointers where the local surrounding text conflicts with or fails to
  resolve what the pointer points to.

The most structurally damaging single issue is the duplication of the event-category taxonomy
across `EventSink` and `Event Model`. The most navigation-harming gap is `task_short_id` defined
in a state-objects list instead of in the `Task Graph` section where a contributor would look for
it.

---

## Critical Findings

### C1. Event categories defined twice with divergent framing

The three event categories (domain events, trace events, wakeup signals) are defined in full,
with nearly identical bullet points, in two separate sections:

- **`EventSink` section** (around line 652): presents them as what the `EventSink` records,
  implying the taxonomy is local to the sink.
- **`Event Model` section** (around line 727): presents them as the normative system-wide
  taxonomy.

The framing divergence is the critical problem. A reader of `EventSink` may reasonably conclude
the three categories are a storage concern rather than a system-wide classification. A reader of
`Event Model` encounters the same definitions again without knowing they were already established.
More practically: a future editor updating one section has no textual signal that the other
section exists.

**The `EventSink` section should not re-define the taxonomy.** It should reference `Event Model`
for the category definitions and state only what is specific to the sink (e.g. that one run may
write to multiple sinks).

### C2. `AgentSelectionPolicy` introduced but never elaborated

`AgentSelectionPolicy` appears in the `State Objects → Inputs` list alongside `OperationGoal`,
`OperationConstraints`, and `RunOptions`. `OperationGoal` receives a dedicated sub-section
distinguishing objective / harness instructions / success criteria. `AgentSelectionPolicy`
receives no elaboration anywhere in the document — not in `Decision Split`, not in `Task Authority
Model`, not in the `AgentAdapter` section.

This creates a specific coherence problem: the `Task Authority Model` section says the brain may
propose "assignment choices," and `Decision Split → Deliberative control` includes "which agent
is most suitable." `AgentSelectionPolicy` appears to be the input object governing this area, but
the document never connects the two. A contributor reading the task authority model has no path
to the policy object that constrains it.

Either elaborate `AgentSelectionPolicy` (what it contains, how it constrains brain assignment
proposals, its relationship to `run --project` profile resolution) or remove it from the inputs
list and note that assignment policy is embedded in profile configuration.

### C3. `task_short_id` defined in the wrong section

`task_short_id` (the user-facing 8-character hex display alias used in commands and operator
messages) is defined in `State Objects → Runtime`, not in the `Task Graph` section. A contributor
reading `Task Graph` — the natural and complete description of task lifecycle and invariants —
will not learn how tasks are referenced in CLI commands. The `Inspection Surfaces` section also
does not mention it. The placement causes the user-facing reference mechanism for tasks to be
invisible in the sections where it matters most.

Move or mirror the `task_short_id` description into `Task Graph`, specifically after the task
lifecycle states.

---

## Lower-Priority Findings

### L1. "The brain proposes; the deterministic runtime enforces" stated twice

This sentence appears as a standalone at the end of the `Operator Loop` section and again as the
framing principle of the `Decision Split` section. The first instance is a preview-style
repetition that adds no structural information. It makes `Operator Loop` appear to summarize
`Decision Split` before `Decision Split` has been read, creating a mild redundancy that dilutes
the impact of the dedicated section.

Remove or replace the standalone sentence in `Operator Loop` with a forward reference:
"See Decision Split below for the authority model."

### L2. Section numbering artifact (5a / 5b)

The document uses no section numbering anywhere except for `5a. Runtime Modes` and
`5b. ADR References`, both nested under `Preferred Runtime Surface`. These numbered labels are
an artifact from an earlier outlining pass and contradict the unnumbered style of every other
section. They create the misleading impression that the document has a partial numbering scheme.

Remove the `5a` / `5b` prefixes; use plain subsection headers.

### L3. `Current Bias` section is design-memo register, not reference register

The document's `Purpose` section declares it is "a structural reference for contributors." The
`Current Bias` section reads as a directive from the original author to future implementers:
"Until contradicted by implementation evidence, prefer: …" This is design-memo language — the
author reasoning aloud about current posture. It does not belong in a structural reference without
framing that contextualizes it as standing policy rather than personal preference.

Either reframe as "Standing architectural policy" or move its content into a dedicated ADR.

### L4. `Long-Lived Objectives` contains changelog text

The note "earlier versions of this document described a three-level hierarchy (Objective → Task →
Subtask). The Feature level was added to VISION.md as a bounded deliverable…" is changelog
content embedded in reference content. In a structural reference, a reader encountering this note
may infer that the document is still catching up to VISION.md, undermining confidence in the
rest of the section.

Remove the historical note. If the migration context matters, it belongs in a changelog entry or
the relevant ADR, not in the body of the reference section.

### L5. `Focus And Wait Semantics` section partially duplicates `Operator Loop`

The `Focus And Wait Semantics` section re-describes `asyncio.Event`, `WakeupWatcher`, and the
wakeup delivery model — the same content that appears in the `Operator Loop` section (line 515).
The section then adds one sentence ("One run may write to multiple sinks: CLI renderer, JSONL
trace, test capture") that is unrelated to focus and wait semantics and belongs in `EventSink`.

Consolidate: keep wakeup delivery in `Operator Loop`, remove the `Focus And Wait Semantics`
section or reduce it to a cross-reference, and move the multi-sink sentence to `EventSink`.

### L6. `SessionRecord` and `RunOptions` listed without description

Both appear in the `State Objects` lists alongside objects that receive at least some description
or connection to other sections. `SessionRecord` has no definition anywhere in the document
despite being a runtime state object. `RunOptions` has no description of its contents or its
relationship to `OperationConstraints`. These are lower-severity than `AgentSelectionPolicy`
because they are less connected to authoritatively described concepts elsewhere, but they remain
dead list entries.

Add one-line descriptions or forward references for each.

### L7. Session policy (one-shot / prefer-reuse / require-reuse) introduced without resolution

The `AgentAdapter` protocol section mentions "Session lifecycle carries session policy: one-shot,
prefer-reuse, require-reuse." This is the only mention of session policy in the document. Who sets
it? How does it interact with the task graph, the concurrency model, or agent adapter
configuration? The concept is introduced as a fact and left structurally unconnected.

Add a sentence connecting session policy to its owner (profile configuration? brain decision?
adapter-local default?) or add a pointer to the relevant ADR or VISION.md section.

### L8. `Failure Model` disconnected from event model and task states

The `Failure Model` section lists seven failure classes but does not connect them to the domain
event taxonomy, the task lifecycle states, or the `StopReason` domain type. A new contributor
reading the section knows the system tolerates these failures but does not know which produce
domain events, which produce trace events, which result in `FAILED` task state, or which trigger
`user-blocking clarification` stop reasons. The section is structurally isolated.

Add cross-references to the event taxonomy and task lifecycle states, or add one sentence per
failure class noting its downstream structural effect.

### L9. Three-tier CLI model introduced only as a footnote, not connected to `Delivery` section

The three-tier CLI model (Everyday / Situational / Forensic) is mentioned once, at the end of
`Inspection Surfaces`, as a pointer to VISION.md. The `Delivery` section earlier describes the
delivery layer without naming the tiers or referencing this structure. A reader of `Delivery` will
not know the CLI has a tier model. The concept is orphaned in a footnote position.

Add a forward reference in `Delivery` to the three-tier CLI structure and the `Inspection
Surfaces` section.

---

## VISION.md Pointer-Specific Findings

### V1. `collaborative` term noted but unresolved at source

Lines 355–357 contain a note that VISION.md's Attention requests section uses the word
`collaborative` in a blocking-rule sentence, but no defined involvement level carries that name.
The note correctly tells readers to treat the defined levels as normative. However, this is a
documented cross-document inconsistency that has not been resolved in VISION.md. The note is
coherent within ARCHITECTURE.md but represents deferred correction.

### V2. `document_update_proposal` pointer creates ambiguity

`document_update_proposal` is listed as an attention type in `Attention and autonomy` and
described in `Long-Lived Objectives` as the mechanism for planning document contributions. The
section "Operator Workspace (Future Direction)" points to VISION.md for criteria under which the
brain may be granted write authority over a workspace. A reader may not know whether
`document_update_proposal` is the gating mechanism for workspace write authority or a separate
attention pathway for planning documents specifically. The local text treats them as separate
without explaining the boundary.

### V3. "Conceptual overview" label on implementation-specific content

The `Operator Loop` section is labeled "Conceptual overview — for the normative loop architecture
and invariants, see VISION.md Event Model → Loop architecture." The section then describes
implementation-specific facts: `WakeupInbox`, `asyncio.Event`, `WakeupWatcher`. "Conceptual
overview" is an inaccurate label for content that mixes architecture with implementation.

Change the label to "Implementation summary" or split: keep the seven-step conceptual list
labeled as overview, and label the wakeup delivery paragraph as an implementation note.

---

## Recommendations

1. **Establish one section as the authoritative home for the event taxonomy** (`Event Model`) and
   reduce `EventSink` to a reference + sink-specific facts. Eliminate the duplication.

2. **Audit every entry in the `State Objects` lists**: for each object, either add a description
   or pointer to where it is described, or remove it from the list. No silent dead entries.

3. **Move `task_short_id` to `Task Graph`**, after the task lifecycle states, as part of the
   task identity model — not in a generic state-objects inventory.

4. **Remove the `5a`/`5b` numbering artifacts** from section headers.

5. **Reframe or relocate `Current Bias`** as standing architectural policy (not design-memo
   directive) or move it to a dedicated ADR.

6. **Remove the changelog note** from `Long-Lived Objectives` (the three-level → four-level
   history note).

7. **Add one cross-reference from `Delivery` to the three-tier CLI model** so the structure is
   discoverable from the natural entry point.

8. **Add one sentence connecting session policy** (one-shot / prefer-reuse / require-reuse) to
   its owner and any governing ADR.

9. **Correct the "conceptual overview" label** on `Operator Loop` to reflect the mixed
   conceptual/implementation content actually present.

10. **Resolve the `collaborative` term in VISION.md** (out of scope for this document, but flagged
    here for the repair pass — the note in ARCHITECTURE.md is a symptom, not the fix).

---

## Compact Ledger

**Target document**: `/Users/thunderbird/Projects/operator/design/ARCHITECTURE.md`

**Focus used**: Internal coherence — cross-section conflicts, duplication, tonal inconsistencies,
structural gaps where concepts are introduced but not resolved, VISION.md pointer accuracy against
local claims

**Main findings**:
- Event-category taxonomy duplicated across `EventSink` and `Event Model` with divergent framing
- `AgentSelectionPolicy` in inputs list is unelaborated and unconnected to `Task Authority Model`
- `task_short_id` defined in state-objects list, invisible to readers of `Task Graph`
- Three tonal registers in a document that declares itself a single-register structural reference
- `Current Bias` and the changelog note in `Long-Lived Objectives` are design-memo content
- `5a`/`5b` numbering is an isolated artifact contradicting the document's unnumbered style
- `Focus And Wait Semantics` partially duplicates `Operator Loop`; multi-sink sentence is
  misplaced
- `SessionRecord`, `RunOptions` are dead list entries
- Session policy (one-shot/prefer-reuse/require-reuse) introduced without structural connection
- `Failure Model` disconnected from event taxonomy and task states
- Three-tier CLI model visible only as a footnote, not connected to `Delivery` section
- `collaborative` term in VISION.md called out locally but unresolved at source
- `document_update_proposal` pointer leaves workspace write authority vs. planning attention
  boundary ambiguous
- "Conceptual overview" label on content that is partly implementation-specific

**Exact ordered fix list for the repair round**:

1. Eliminate event-category duplication: make `Event Model` the canonical definition, reduce
   `EventSink` to a reference.
2. Audit `State Objects` lists — add descriptions or pointers for `AgentSelectionPolicy`,
   `SessionRecord`, `RunOptions`, `RunSummary`, or remove dead entries.
3. Move `task_short_id` description into `Task Graph` (after task lifecycle states).
4. Remove `5a`/`5b` numbering from subsection headers.
5. Reframe `Current Bias` as standing policy or move to ADR.
6. Remove changelog note from `Long-Lived Objectives`.
7. Remove or replace redundant "brain proposes; runtime enforces" sentence at end of `Operator
   Loop`.
8. Consolidate `Focus And Wait Semantics` into `Operator Loop`; relocate multi-sink sentence to
   `EventSink`.
9. Add one sentence connecting session policy to its owner and a governing ADR.
10. Add forward reference in `Delivery` section to the three-tier CLI model.
11. Correct "Conceptual overview" label on `Operator Loop`.
12. Add cross-references from `Failure Model` to event taxonomy and task lifecycle states.
13. Clarify the `document_update_proposal` boundary (planning attention vs. workspace write
    authority gating).
14. (VISION.md action) Resolve the `collaborative` term in VISION.md Attention requests section.
