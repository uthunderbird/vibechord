# Critique Round 1 — VISION.md
## Focus: Completeness, Internal Consistency, and Correctness

**Target document**: `/Users/thunderbird/Projects/operator/design/VISION.md`
**Cross-reference**: `/Users/thunderbird/Projects/operator/design/ARCHITECTURE.md`
**Round**: 1 of 3
**Method**: Swarm Red Team — full process (Phase 1–3, 4 iterations including sub-group)
**Date**: 2026-04-01

---

## Summary Assessment

VISION.md is a substantive and architecturally coherent document in its broad intent. It does a good job of establishing the operator loop as the center, articulating the LLM-first / deterministic-guardrails split, and describing a layered CLI. However, the document has:

- **Two critical structural contradictions** that would directly mislead an implementer.
- **Multiple high-priority coverage gaps** for concepts named but left undefined.
- **A foundational framing tension** ("minimalist") that the document does not fully resolve.
- **Missing user-centric success criteria** that are inconsistent with the stated Transparency principle.
- **Several ungrounded claims** in the positioning and success-criteria sections.

---

## Red Team Composition

| Role | Critique Focus |
|---|---|
| Internal Consistency Auditor | Contradictions, state machines, cross-section conflicts |
| Coverage / Completeness Analyst | Omissions, undefined terms, dangling references |
| Claims Grounding Specialist | Unsubstantiated assertions, unmeasurable criteria |
| Architectural Coherence Reviewer | Principle-to-content coherence, layer model |
| User / Stakeholder Perspective Skeptic | Audience definition, user-centric gaps, failure UX |

---

## Critical Findings

### C1 — Task state machine contradicts the user-facing CLI view

**Location**: Task Lifecycle (line 252) vs. User-Facing Task View (line 268)

The task lifecycle section defines exactly five states: `PENDING → READY → RUNNING → COMPLETED | FAILED | CANCELLED`. The CLI task view example displays a `[BLOCKED]` heading with tasks listed under it. `BLOCKED` is not defined in the state machine.

The text under the lifecycle section states "The transition from PENDING to READY is deterministic: when all dependency tasks are complete." This implies that a `PENDING` task with unresolved dependencies *is* the blocked state — but the document never reconciles this with the display label. A reader cannot determine whether:
- `BLOCKED` is a distinct state (contradicting the lifecycle definition), or
- `[BLOCKED]` is a display grouping for `PENDING` tasks whose dependencies are not yet met.

If the latter, the document should say so explicitly and confirm that `PENDING` is the canonical state. As written, the state machine is inconsistent with the UI model.

**Impact**: An implementer building the state machine and the CLI display will make contradictory choices. A user reading both sections will be confused about whether a task can be in a state not listed in the lifecycle.

---

### C2 — Operation lifecycle is missing reverse transition from NEEDS_HUMAN

**Location**: Operation Lifecycle (line 182–193)

The three macro-states are defined: `RUNNING`, `NEEDS_HUMAN`, `TERMINAL`. The text describes that in `NEEDS_HUMAN` "the operation may continue on non-blocking items but will not proceed past a blocking attention without an answer." However:

- No transition back from `NEEDS_HUMAN → RUNNING` is defined.
- It is unspecified whether the transition is triggered by the user's `answer` command, the next scheduler cycle, or automatic once all blocking attentions are resolved.
- It is unspecified whether an operation doing partial work in `NEEDS_HUMAN` mode (on non-blocking items) appears as `RUNNING` or `NEEDS_HUMAN` in the CLI.

`NEEDS_HUMAN` appears to be an overlay condition rather than a pure state, but the model does not say this. The lifecycle as stated is incomplete for any human-in-the-loop workflow.

**Impact**: The user's mental model of operation control flow is broken. A user who answers an attention request cannot tell from the document whether or when the operation will return to RUNNING.

---

## High-Priority Findings

### H1 — `patch_*` command referenced but not defined

**Location**: Multi-Session Coordination routing rules (line 319)

The routing table lists `patch_*` as routed to the operation inbox, alongside `message`, `answer`, `pause`, and `cancel`. `patch_*` is never explained. No section in VISION.md defines what patching an operation means, what fields can be patched, or what the wildcard `*` suffix covers.

Given that the document is otherwise careful to define typed commands, this omission leaves a significant surface area unexplained. (ARCHITECTURE.md references ADR 0032 "bounded live goal-patching" — but VISION.md should either define it or explicitly defer to an ADR reference.)

---

### H2 — `involvement` command has no definition of what autonomy levels exist

**Location**: CLI Tier 2 table (line 497)

`involvement op-id` is listed as "change the autonomy level for a running operation." The document does not define what autonomy levels exist, how they differ, or what behavior changes at each level. A user reading this command entry cannot know what values to pass or what effect to expect.

---

### H3 — Stop policy referenced but never defined

**Location**: Core Thesis (line 53, line 59)

The operator loop "repeats until the stop policy is satisfied." "Early Success Criteria" item 2 references "deterministic run policies around that loop." Neither section defines what a stop policy is, what policies are available by default, or how a user configures one. The closest the document comes is listing "hard stop conditions" as one example of deterministic guardrails — but this is illustrative, not definitive.

---

### H4 — "Minimalist" framing is irreconcilable with the described system

**Location**: Opening description (line 5) vs. "What Minimalism Means Here" (line 574)

The document opens: "`operator` is a minimalist Python library and CLI." The body of the document describes: a 4-level entity hierarchy (Objective → Feature → Task → Subtask), a typed command inbox with two command classes, multi-session parallel coordination, a 4-layer memory model, 3 operation macro-states with scheduler sub-states, 3 CLI tiers with ~25 named commands, policy memory and promotion workflows, attention taxonomy, and involvement levels.

The "What Minimalism Means Here" section (line 574) attempts reconciliation but is buried after most of the complexity has been introduced, and it cannot retroactively undo the opening claim. The section redefines minimalism as "a small number of central abstractions" and "explicit boundaries" — a reasonable definition, but not what "minimalist" means to a reader encountering the opening description.

**Impact**: The opening positioning sets incorrect expectations. Readers who associate "minimalist" with low complexity will feel misled.

---

### H5 — "Limited read-only access" claim is unquantified

**Location**: Mental Model / Operator brain (line 149) vs. Operator File Tools (line 350)

The Mental Model section says the operator brain has "limited read-only access to the project file system." The Operator File Tools section describes `read_file`, `list_dir`, and `search_text` — three full capabilities. No limit is defined anywhere in either section. The word "limited" is used without content.

---

### H6 — Failure model is entirely absent from VISION.md

**Location**: No section exists

ARCHITECTURE.md has an explicit "Failure Model" section listing brain provider failure, adapter startup failure, stall, malformed output, timeout, budget exhaustion, and user cancellation. VISION.md — which defines Transparency as a product requirement (Principle 5, line 122) — does not address how failures surface to users at any level. There is no mention of what a user sees when an operation fails, what the `TERMINAL` state communicates about failure cause, or what recovery options exist.

This is a direct gap against the stated Transparency principle.

---

### H7 — File reads produce memory side effects, contradicting the "no side effects" claim

**Location**: Mental Model / Operator brain (line 152) vs. Operator File Tools (line 361)

The Mental Model section states: "These reads inform planning decisions and are recorded as memory entries — they never produce side effects."

The Operator File Tools section states: "Results of operator file reads either inform the immediate brain decision or are persisted as `MemoryEntry` with freshness tracking."

Persisting a `MemoryEntry` is a side effect on the memory store. The "no side effects" claim applies only to the project file system (i.e., the brain cannot write files), but the framing in the Mental Model section implies broader purity that is not accurate.

---

### H8 — Target audience is never defined

**Location**: Entire document

VISION.md never states who `operator` is for. Developers building agent-based pipelines? Platform engineers? End users of agent-assisted tooling? The CLI First and Why This Exists sections hint at developers and engineers, but without explicit definition, the vision cannot be evaluated for completeness against audience needs, and the Early Success Criteria section has no basis for determining what counts as "usable."

---

## Medium-Priority Findings

### M1 — `BLOCKED` as task state undermines the invariant claim

The Task Graph Invariants section (line 259) states that these are "enforced by the runtime, not by the brain." The BLOCKED display state (if it is a state) is not included in the listed invariants. If BLOCKED is a display grouping, the invariants section should confirm this. The omission creates an impression that the invariant list is incomplete.

---

### M2 — "The third adapter easier than the first" is an unmeasurable success criterion

**Location**: Early Success Criteria, item 6 (line 611)

"An architecture that makes the third adapter easier than the first" is qualitative and subjective. No metric, comparison method, or acceptance test is provided. It is not a criterion that can be verified by inspection.

---

### M3 — Single decision serializer claim lacks a mechanism description

**Location**: Multi-Session Coordination (line 307)

"The operator brain remains the single decision serializer." In parallel multi-session execution, sessions complete asynchronously. If the brain processes events from multiple concurrent sessions, serial decision-making either requires a queue (not described) or the claim is aspirational. No mechanism is named, and no ordering guarantee is stated.

---

### M4 — Vendor-specific CLI commands conflict with Protocol-orientation principle

**Location**: Principle 3 (line 99) vs. Tier 3 CLI commands (lines 501–502)

Principle 3 states all external components should be accessed through `typing.Protocol` interfaces, keeping the core independent from any one agent vendor. The CLI directly exposes `claude-log` and `codex-log` as named vendor commands. This is an acknowledged exception in ARCHITECTURE.md but is not acknowledged in VISION.md. The principle and the CLI design are not reconciled.

---

### M5 — Operation vs. run terminology is not distinguished

Multiple sections use "operation" and "run" interchangeably or without differentiation. "operator run" is the CLI command; "operation run" appears in ARCHITECTURE.md. VISION.md does not define whether an operation can have multiple runs (e.g., after resume) or whether they are synonymous.

---

### M6 — Context window for operator messages is undefined

**Location**: Free-form operator messages (line 211)

The document states that when a message "ages out of the context window, an `operator_message.dropped_from_context` event is emitted." The context window is never defined: who sets its size, what the unit is (tokens, turns, time), or whether it is configurable. For a document that treats this transparency mechanism as a product requirement, the absence of the underlying concept is a gap.

---

### M7 — Early Success Criteria split is implicit and unexplained

**Location**: Early Success Criteria (line 604)

Items 1–6 and 7–10 are separated by "Subsequent milestones add:" without naming the release boundary, version gate, or milestone identity. Readers cannot determine which set represents a first release vs. a follow-on.

---

### M8 — `daemon` command has no description

**Location**: Tier 3 CLI table (line 509)

`daemon` is listed as "background resumption mode" — one phrase, no elaboration. In a CLI-first document, a command that runs persistently in the background is significant enough to warrant at least a one-sentence description of when to use it and what it does.

---

### M9 — Feature authority (brain vs. user) is ambiguous

**Location**: Long-Lived Objective Hierarchy (line 329–344)

The hierarchy table says "brain proposes" only for Tasks (line 331). Features have acceptance criteria and a review lifecycle, but the document does not say whether the brain creates Features or only the user does. This is a consequential design gap for any long-lived workflow implementation.

---

### M10 — "Existing agent tools" claim is ungrounded

**Location**: Why This Exists (line 28)

"Existing agent tools are usually optimized for one agent in one surface" is stated as motivating fact with no named examples, citations, or evidence. The document then lists four patterns but does not match them to real tools. The competitive rationale is asserted, not demonstrated.

---

## Recommendations

1. **Fix C1**: Either add `BLOCKED` to the task state machine as a formal state with a defined transition (PENDING[unresolved dependencies] → BLOCKED, BLOCKED → READY when dependencies clear), or explicitly document that `[BLOCKED]` in the CLI view is a display grouping for PENDING tasks with outstanding dependencies. Ensure the CLI display section references the state machine definition.

2. **Fix C2**: Add the reverse transition `NEEDS_HUMAN → RUNNING` to the Operation Lifecycle section. Specify the trigger (all blocking attentions answered + next scheduler cycle). Clarify whether partial work in NEEDS_HUMAN mode is displayed as RUNNING or NEEDS_HUMAN to the user.

3. **Fix H1**: Define `patch_*` in the User Interaction Model section. List what fields can be patched and what the wildcard suffix represents. Reference the relevant ADR if the full definition lives there.

4. **Fix H2**: Add a sub-section or note under `involvement op-id` (or in the User Interaction Model) that defines the available autonomy levels and their behavioral differences.

5. **Fix H3**: Add a "Stop Policy" or "Run Constraints" section defining the default stop policy, available policies (iteration limit, budget limit, time limit, explicit success signal), and how a user configures them.

6. **Fix H4**: Either retitle the project as "structured" or "composable" instead of "minimalist," or move and expand the "What Minimalism Means Here" section to immediately follow the opening description, so readers are calibrated before encountering the full complexity.

7. **Fix H5**: Replace "limited" with a concrete qualifier ("read-only, no network, project root–scoped" or similar), or remove the word "limited" and allow the File Tools section to stand as the authoritative description.

8. **Fix H6**: Add a brief failure-visibility section to VISION.md (parallel to ARCHITECTURE.md's Failure Model), describing how failures appear to the user: what the TERMINAL state communicates about failure cause and how the user distinguishes completed/failed/cancelled.

9. **Fix H7**: In the Mental Model / Operator brain section, change "they never produce side effects" to "they never produce side effects on the project file system" (or equivalent accurate scoping).

10. **Fix H8**: Add a single paragraph to the opening "Project" section or "Why This Exists" section identifying the primary audience (e.g., developers building multi-agent workflows, engineers supervising autonomous agent runs).

11. **Fix M3**: Add a note to the Multi-Session Coordination section describing the mechanism that enforces single-brain serialization (event queue, mutex, or similar) so the guarantee is not merely claimed but grounded.

12. **Fix M4**: Acknowledge in Principle 3 (or in the "Claude ACP And Codex" section) that vendor-named CLI commands (`claude-log`, `codex-log`) are a deliberate exception to protocol orientation, kept in the forensic tier to preserve full upstream transparency.

---

## Methodology

This critique was produced via the Swarm Red Team process: Phase 1 (target definition), Phase 2 (5-role Red Team assembly), Phase 3 with 3 substantive iterations (round-robin discussion, sub-group deep dive on C1/C2, checkpoint). All findings are grounded in specific sections and line numbers of the target document. ARCHITECTURE.md was used as a cross-reference for detecting gaps and contradictions but was not itself the subject of critique in this round. No claims are attributed to the document beyond what the text states.

---

## Compact Ledger

**Target document**: `/Users/thunderbird/Projects/operator/design/VISION.md`

**Focus used**: Completeness, internal consistency, and correctness — contradictions between sections, coverage gaps, ungrounded claims, sections that undermine each other.

**Main findings**:
- C1: Task state machine lacks `BLOCKED`; CLI view contradicts the defined lifecycle
- C2: Operation lifecycle missing `NEEDS_HUMAN → RUNNING` reverse transition and trigger
- H1: `patch_*` command referenced but never defined
- H2: `involvement` command autonomy levels not defined
- H3: Stop policy referenced but never defined
- H4: "Minimalist" framing irreconcilable with actual system complexity without restructuring
- H5: "Limited" file access claim is empty — no limit is specified
- H6: Failure model absent from VISION.md despite Transparency being a stated principle
- H7: "No side effects" claim is inaccurate — file reads produce MemoryEntry side effects
- H8: Target audience never defined

**Ordered fix list for the repair round**:

1. Add `BLOCKED` to the task state machine or document it as a display alias for PENDING-with-unresolved-dependencies (fixes C1)
2. Add `NEEDS_HUMAN → RUNNING` transition with trigger condition to Operation Lifecycle (fixes C2)
3. Define `patch_*` commands in User Interaction Model (fixes H1)
4. Define autonomy levels for the `involvement` command (fixes H2)
5. Add a Stop Policy section with default policy and available options (fixes H3)
6. Move / restructure "What Minimalism Means Here" to immediately follow the opening description, or revise the opening label (fixes H4)
7. Replace "limited read-only access" with accurate scoping qualifier (fixes H5)
8. Add a failure-visibility paragraph to VISION.md (fixes H6)
9. Narrow the "no side effects" claim to file-system scope only (fixes H7)
10. Add a primary audience statement to the opening section (fixes H8)
11. Describe the single-brain serialization mechanism in Multi-Session Coordination (fixes M3)
12. Acknowledge vendor-named CLI commands as a deliberate forensic-tier exception to Principle 3 (fixes M4)
