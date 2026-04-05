# VISION.md — Round 2 Critique: Specificity and Actionability

**Target document:** `/Users/thunderbird/Projects/operator/design/VISION.md`
**Critique round:** 2 of 3
**Focus:** Specificity and actionability — vague promises, weasel words, abstract behavior descriptions, missing boundary conditions
**Date:** 2026-04-01

---

## Red Team Composition

| Role | Critique focus |
|---|---|
| Implementer / Practitioner | Gap between stated behavior and what an engineer needs to build or test it |
| Product Clarity Skeptic | Weasel words, hedges, qualifier stacks that dilute normative force |
| Boundary Conditions Auditor | Missing limits, error cases, edge cases, and scope edges |
| Testability Analyst | Claims with no observable acceptance criterion |
| Terminology Precision Critic | Undefined, overloaded, or inconsistently used terms |

---

## Summary Assessment

The document is above average for a vision document. Its strongest passages — the stop-policy enumeration, the NEEDS_HUMAN lifecycle description, the operation/run disambiguation, the task lifecycle state machine, and the `operator` / `run` command routing table — are precise enough to implement directly. These set the bar the rest of the document should reach but does not.

The primary failure mode is not dishonesty but incompleteness: the document frequently names a concept, lists examples, and moves on, leaving the boundary, the mandatory set, and the failure behavior unstated. Several critical concepts (`harness_instructions`, `policy gap`, `artifacts`, `involvement` routing rule) are introduced but not defined, and at least one key architectural mechanism (the adapter contract) is described as a brainstorm list rather than a contract.

---

## Critical Findings

### C1 — Agent adapter contract is illustrative, not binding

**Location:** "Interfaces → Agent adapter contract"

> "At minimum, the contract should support concepts like: start a run, continue or respond to an active run, observe status, collect output and artifacts, stop or cancel, expose capabilities and limits."

"Concepts like" signals the list is illustrative. "At minimum" combined with "should support" makes the entire statement advisory. An implementer cannot derive a `typing.Protocol` definition, a test suite, or a conformance checklist from this passage. The document's Principle 3 promises "stable operator-facing contracts" — this section does not deliver one.

**What is missing:** A normative list of required methods or capabilities with their signatures, semantics, and the behavior when a capability is not supported (e.g., an adapter that cannot `stop` a turn).

---

### C2 — Involvement levels have no routing rule

**Location:** "CLI Design → Involvement levels"

The document defines two poles (`unattended`, `interactive`) and distinguishes "routine decisions" (surface-but-don't-block) from "policy gaps and novel strategic choices" (block). But the rule by which the brain classifies a decision as routine vs. strategic is never stated.

Without this rule, `involvement` is unimplementable. The brain cannot apply a level it cannot evaluate. The watch UI example (`"Should I commit directly to main?"`) illustrates the concept but does not generalize to a classification criterion.

**What is missing:** A definition of what constitutes a "policy gap" or "novel strategic choice" — even if that definition is "any question for which no answer exists in `harness_instructions` or prior answers."

---

### C3 — "harness_instructions" is undefined

**Location:** "Goal-patching commands" (`patch_harness_instructions`), "Long-Lived Objective Hierarchy" ("injected into `harness_instructions`")

The term "harness" and the entity "harness_instructions" appear twice in the document but are never defined. No section explains what a harness is, what it contains, how it differs from the `objective` text, or what "execution policy for the operator and agent path" means operationally.

**What is missing:** A definition of `harness_instructions` as a domain concept — what data it holds, who reads it (brain only? adapters?), and how it interacts with `objective` and `success_criteria`.

---

### C4 — "partly deterministic" safety qualifier is unexplained

**Location:** "Project" section

> "Safety, observability, and execution constraints remain explicit and partly deterministic."

"Partly deterministic" applied to safety is a significant qualifier with no explanation. The rest of the document describes a binary model: stop conditions are deterministic and not subject to LLM override. If some safety logic is non-deterministic, the document must say which part, and why.

**What is missing:** Explicit identification of which safety/execution constraints are deterministic and which are not, and the rationale for the non-deterministic ones.

---

## High-Priority Findings

### H1 — patch_* rejection conditions are not enumerated

**Location:** "User Interaction Model → Goal-patching commands"

> "Commands are acknowledged by the operation (accepted or rejected-with-reason) and applied deterministically at the next decision point."

"Accepted or rejected-with-reason" promises determinism but enumerates no rejection conditions. An implementer cannot write the acceptance logic. A user cannot predict when a patch will fail.

**What is missing:** The conditions under which each `patch_*` command is rejected (e.g., operation in `TERMINAL` state, malformed payload, conflicting concurrent patch).

---

### H2 — Success criteria items 1–5 and 7–10 have no acceptance test

**Location:** "Early Success Criteria"

Item 6 ("adding a third adapter should require no changes to the operator core") is the only falsifiable criterion in the list — it is binary. All others are not:

- Item 1: "a stable operator loop" — "stable" is undefined.
- Item 3: "one clean headless adapter" — "clean" is aesthetic.
- Item 5: "a usable CLI with transparent event output" — "usable" and "transparent" are subjective.
- Items 7–10 (Phase 2): no sequencing, dependencies, or done-criteria. "Multi-session parallel coordination" (item 8) could mean passing one test or passing a full suite.

**What is missing:** For each item, a behavioral description precise enough to verify pass/fail. Even a sentence per item would suffice (e.g., "all six stop conditions fire deterministically in the test harness").

---

### H3 — "Policy gap" is undefined

**Location:** "CLI Design → Involvement levels," `watch` UI example

The term "policy gap" is used as if self-evident but is never defined. The watch UI shows a concrete example (`"Should I commit directly to main?"`), but the document does not generalize this to a definition. The involvement section also refers to "novel strategic choices" as a separate category from policy gaps, without distinguishing the two.

**What is missing:** A one-sentence definition of "policy gap" as a domain term, and clarification of whether "novel strategic choice" is a subset or a distinct category.

---

### H4 — Monotonicity invariant: actor and mechanism undefined

**Location:** "Task Graph → Task graph invariants"

> "Monotonicity: dependencies are added, not silently removed. Removal requires explicit justification."

This is stated as a runtime invariant but does not specify:
- Who provides the justification (brain, user, or both)?
- In what form (a logged string, a mandatory command parameter)?
- Whether the runtime enforces this by rejecting removal without justification, or merely by logging it.

The Q&A round confirmed the ambiguity: "explicit justification" could mean unconditional rejection, a logged reason string, or a CLI flag. All three have different implementation consequences.

---

### H5 — "should" vs. "must" normative force is inconsistent throughout

The document uses "should," "must," and "will" without a declared convention. Examples:

- "The operator must be inspectable from the CLI." (Principle 5 — treated as a requirement)
- "The architecture should stay clean without becoming ceremonious." (Principle 4 — advisory)
- "Every external component should be accessed through `typing.Protocol` interfaces." (Principle 3 — unclear)
- "Commands are organised in three tiers." (statement of fact)

An implementer reading this cannot distinguish enforced invariants from design preferences. RFC 2119 or equivalent should be declared if the document is to serve as a specification.

---

## Medium-Priority Findings

### M1 — "Minimalist" is defined qualitatively, not quantitatively

**Location:** "What 'minimalist' means here"

> "a small number of central abstractions," "little accidental framework code," "no extra architectural layers unless they buy clear leverage"

"Small number," "little," and "clear leverage" have no reference point. A reader enforcing minimalism has no criterion to evaluate a proposed new abstraction against.

---

### M2 — Principle 4 ("Minimal layers") has no criterion

**Location:** "Design Principles → 4. Minimal layers"

> "The architecture should stay clean without becoming ceremonious."

"Clean" and "ceremonious" are aesthetic judgments. The principle lists four layers as the desired structure, which is useful, but does not state what violation looks like (e.g., "a layer with no direct callers is not justified").

---

### M3 — MemoryEntry freshness: "same file" is ambiguous

**Location:** "Operator File Tools"

> "If the same file is read again, the new entry supersedes the prior one."

"Same file" is not defined. Does identity mean: same path? Same content hash? Same inode? This matters for symlinks, renames, and files that change between reads. The deduplication behavior is unspecified.

---

### M4 — Operator message window has no default

**Location:** "User Interaction Model → Free-form operator messages"

> "Operator messages persist in the brain's context for a configurable number of planning cycles (the operator message window, set per project or at run time)."

No default value, no minimum, no maximum, and no behavior when the window is set to 0 or a very large value are specified. A new user who does not configure this value has no defined behavior.

---

### M5 — "Artifacts" domain entity is undefined

**Location:** Tier 3 CLI table (`artifacts op-id`), adapter contract ("collect output and artifacts")

"Artifacts" appears as a first-class concept in two sections but is never defined as a domain entity. What distinguishes an artifact from a memory entry or a plain file write? What schema does it carry? Is it agent-produced only, or can the operator produce artifacts?

---

### M6 — stop_turn on non-RUNNING task: error behavior undefined

**Location:** "User Interaction Model → Active turn control"

The command syntax is specified, but if `stop_turn` targets a task that is not in `RUNNING` state (e.g., already `COMPLETED`, or `READY` but not yet started), the error response is not described.

---

### M7 — NEEDS_HUMAN edge case during drain is undocumented

**Location:** "Operation Lifecycle"

The transition from `NEEDS_HUMAN` back to `RUNNING` when all blocking attentions are cleared is documented. The reverse edge — a new attention request arriving while the scheduler is draining — is not addressed. Is the incoming attention accepted and queued? Rejected? The document is silent.

---

## Lower-Priority Findings

### L1 — "At least initially" in Non-Goals weakens the boundary without a trigger condition

**Location:** "Non-Goals"

> "At least initially, `operator` should not try to be: a generic workflow orchestration platform…"

"At least initially" implies the boundary may change, but provides no condition under which it would change. This is fine for a living document but should be acknowledged explicitly if the boundaries are genuinely time-bounded.

---

### L2 — operation/run naming inversion in CLI table is unacknowledged

**Location:** Tier 1 command table

The document carefully disambiguates `operation` (persistent entity) from `run` (execution attempt). The Tier 1 command is named `run` but described as "start a new operation." The inversion is intentional but is never explained, which may confuse readers who have just read the disambiguation.

---

### L3 — "Wakeup" is unexplained for new readers

**Location:** Tier 3 CLI table (`wakeups op-id`)

"Wakeup" appears in the CLI table without any prior definition. A new reader has no context for what a wakeup is, when it is created, or why they would need to inspect it.

---

## Recommendations

1. **Declare normative conventions.** Add a one-paragraph note at the top of the document stating the meaning of "must," "should," "will," and "may" (RFC 2119 or equivalent). This resolves H5 across the entire document without rewriting every sentence.

2. **Replace "concepts like" in the adapter contract with a normative list.** State which methods/capabilities are required, which are optional, and what the behavior is when an optional capability is absent. Even a minimal table with required/optional columns would suffice.

3. **Define "policy gap" and the involvement routing rule.** A two-sentence definition of policy gap and the routing rule ("if no answer exists in `harness_instructions` or prior answers, the decision is a policy gap") would close C2 and H3 simultaneously.

4. **Define "harness_instructions" as a first-class domain concept.** Add a row to the Mental Model section or a dedicated paragraph explaining what harness instructions contain and how they differ from objective text.

5. **Add acceptance tests to success criteria.** For each of the 10 early success criteria, add one sentence describing what "done" looks like in the test harness or in observable behavior.

6. **Enumerate patch_* rejection conditions.** A brief table (condition → rejection reason string) would make the "accepted or rejected-with-reason" promise actionable.

7. **Define "same file" for MemoryEntry deduplication.** State whether identity is by path, content hash, or both. Note symlink behavior.

8. **State the operator message window default.** Add a default value and state behavior at the boundary (window = 0, window = very large).

9. **Clarify the Monotonicity invariant.** State whether dependency removal is unconditionally rejected, or accepted with a mandatory reason parameter, and who supplies the reason.

10. **Define "Artifacts" as a domain entity.** Add a paragraph or table entry alongside MemoryEntry explaining what an artifact is, who produces it, and how it is distinguished from other persisted outputs.

---

## Compact Ledger

**Target document:** `/Users/thunderbird/Projects/operator/design/VISION.md`

**Focus used:** Specificity and actionability — vague promises, weasel words, abstract behavior descriptions, missing boundary conditions

**Main findings:**

| ID | Finding | Severity |
|---|---|---|
| C1 | Adapter contract uses "concepts like" — illustrative, not binding | Critical |
| C2 | Involvement levels lack the routing rule to classify routine vs. strategic decisions | Critical |
| C3 | "harness_instructions" introduced but never defined | Critical |
| C4 | "partly deterministic" safety qualifier unexplained | Critical |
| H1 | patch_* rejection conditions not enumerated | High |
| H2 | Success criteria items 1–5, 7–10 have no acceptance test | High |
| H3 | "Policy gap" is undefined | High |
| H4 | Monotonicity invariant: actor and mechanism of justification undefined | High |
| H5 | "should" / "must" normative force inconsistent throughout | High |
| M1 | "Minimalist" defined qualitatively with no reference criterion | Medium |
| M2 | Principle 4 "Minimal layers" has no violation criterion | Medium |
| M3 | MemoryEntry "same file" identity is ambiguous | Medium |
| M4 | Operator message window has no default value or boundary behavior | Medium |
| M5 | "Artifacts" domain entity is undefined | Medium |
| M6 | stop_turn on non-RUNNING task: error behavior undefined | Medium |
| M7 | NEEDS_HUMAN + new attention during drain: edge case undocumented | Medium |
| L1 | "At least initially" in Non-Goals has no trigger condition | Low |
| L2 | operation/run naming inversion in CLI table unacknowledged | Low |
| L3 | "Wakeup" unexplained for new readers | Low |

**Ordered fix list for repair round:**

1. Declare normative conventions ("must" / "should" / "may") at document top — resolves H5 globally.
2. Replace "concepts like" in adapter contract with a required/optional capability table — resolves C1.
3. Define "policy gap" and the involvement routing rule — resolves C2 and H3.
4. Define "harness_instructions" as a named domain concept — resolves C3.
5. Clarify "partly deterministic" — identify which safety constraints are non-deterministic and why — resolves C4.
6. Enumerate patch_* rejection conditions — resolves H1.
7. Add acceptance tests (one sentence each) to all 10 success criteria items — resolves H2.
8. Specify Monotonicity invariant: actor, mechanism, and rejection vs. annotation behavior — resolves H4.
9. Define "same file" for MemoryEntry deduplication — resolves M3.
10. State operator message window default and boundary behavior — resolves M4.
11. Define "Artifacts" as a domain entity — resolves M5.
12. Document stop_turn error behavior on non-RUNNING task — resolves M6.
13. Document NEEDS_HUMAN edge case during drain — resolves M7.
14. Add trigger condition or remove "at least initially" qualifier from Non-Goals — resolves L1.
15. Add a note acknowledging the operation/run naming inversion in the CLI table — resolves L2.
16. Add a one-sentence definition of "wakeup" in Tier 3 — resolves L3.
