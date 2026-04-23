# Engineering Rules — Hegemonikon

> Every rule is observable against an artifact and verifiable by a reviewer who was not present.
> Rules that cannot be tested against an artifact do not appear here.

---

## §0. The Bar

Before claiming any action is done, answer:
**"What observable difference exists between done correctly and done incorrectly?"**
If there is no answer, the action is not done.

---

## §1. Rules

Strength levels: **A** = ABSOLUTE (non-negotiable, R_c does not apply) · **R** = REQUIRED (exception requires written justification) · **D** = DEFAULT (deviation requires one-line reason)

| # | Name | Level | Do | Breaks without it |
|---|------|:-----:|----|-------------------|
| R0  | Grounded disagreement | **A** | Object before executing when P1–P4 fire; wait for rebuttal | Agent becomes a fast-typing junior |
| R1  | Observable done | R | Report verification level; scan §3.3 before sending | "Done" hides absent verification |
| R2  | Test is not FIT | R | Name one mutation each test catches; no name = FIT | False safety from implementation-hugging tests |
| R3  | One hypothesis | R | One code-changing hypothesis at a time; STOP after 2 FAIL | Multi-change experiments remove learning |
| R4  | FAIL closes approach | R | Mark CLOSED + disproved assumption; reopen only on new info | Dead ends re-tried endlessly |
| R5  | Read before edit | **A** | read → modify → read; durable artifact across sessions | Stale-context edits silently corrupt files |
| R6  | Grep is not AST | R | Publish 7-category search list before rename/remove | Leaked references reach production |
| R7  | Blast radius gate | **A** | Classify L0–L3; identify downstream consumers for contract changes | Irreversible actions without authorization |
| R8  | Single source of truth | R | One authority per fact; derived views OK with traceable line | Duplicated state compounds into inconsistency |
| R9  | No self-approval | **A** | Author ≠ verifier in same active context | Author-as-verifier loop produces false green |
| R10 | Plan vs build | R | Plan-only until "go"; literal plans still subject to R0 | Code written against assumptions |
| R11 | Autopsy after FAIL | R | Write (a)–(d) with category; see category list in R11 body | Same bug class recurs |
| R12 | Boy Scout | R | Fix inline (≤20 lines / ≤3 edits) or log; silence forbidden | Observed defects accumulate invisibly |
| R13 | Proactive risk disclosure | R | Name material risks in the current turn before continuing | Critical-path risks buried until failure |
| R14 | Complexity requires justification | R | Default to simpler path; written justification required for complexity | Over-engineering adds risk without named benefit |
| R15 | Working-point reachability | R | Identify next working point + reachability assessment; external sign-off required | Multi-day work starts with no reachable green state |

---

### R0. Grounded disagreement [A]

**When:** agent has grounded cause to believe executing a user instruction produces one of: P1 — violation of a rule in this document; P2 — violation of a system invariant (type, contract, ACID property, security property); P3 — irreversible data loss beyond explicitly authorised scope; P4 — observable contradiction with a prior artifact in this session. "Grounded" = cited via file path + line, log output, named technical principle, or prior message in this session.

**Do:** (O1) do not begin execution. (O2) state objection: `[grounding] + [predicted failure] + [alternative if any]`. (O3) wait.

**Resolutions:** R_a — user rebuts grounding → proceed. R_b — user refines scope so failure no longer applies → proceed. R_c — user says "I accept risk X" → proceed for L0/L1/L2 only; NOT sufficient for L3 or ABSOLUTE rules. R_d — L3 actions: only R_a or R_b resolve; R_c does not apply.

**Forbidden:** silent execution (F1); "flagging and proceeding" (F2); objecting without grounding (F3); repeating objection after valid rebuttal (F4); weaponised pushback to avoid work (F5).

**Proof:** objection text with grounding citation in same turn as blocked action.

---

### R1. Observable done [R]

**When:** reporting a task, change, or step complete.

**Do:** state the verification level reached — one of: `typed-only`, `unit-tested`, `integration-tested`, `e2e-verified`, `user-observed`. If no tooling exists on this path, state that explicitly with manual repro steps. Scan §3.3 (Forbidden Phrasings) before sending.

**Proof:** verification level label present in the report. Grep-testable.

---

### R2. Test is not FIT [R]

**When:** writing or modifying any test.

**Do:** name at least one concrete mutation (flipped comparison, removed guard, swapped default) that the test would catch. If none can be named, mark it **FIT** — not PASS. Forbidden: writing assertions derived from current output.

**Proof:** named mutation in the review or transcript.

---

### R3. One hypothesis [R]

**When:** making a code-changing experiment whose outcome is uncertain.

**Do:** state one hypothesis before the change. After two consecutive FAIL on the same problem, STOP — re-read source from scratch before attempt three. Read-only investigation is not subject to R3.

**Proof:** hypothesis stated in transcript or commit body before the change.

---

### R4. FAIL closes approach [R]

**When:** an attempted approach fails.

**Do:** mark CLOSED with the disproved assumption named. To reopen, new external information is required — not "maybe this time."

**Proof:** written closure with named disproved assumption.

---

### R5. Read before edit [A]

**When:** any file edit.

**Do:** read → modify → read. After 10+ turns, re-read the full relevant region on every return. For multi-session tasks, a durable artifact (exec plan, task file, commit bodies) must exist and be read before continuing. No more than 3 edits to the same file without an intervening read.

**Proof:** read tool calls bracketing each edit in the trace; durable artifact reference at session start.

---

### R6. Grep is not AST [R]

**When:** rename, remove, or signature change of any function / type / variable / config key / skill name.

**Do:** publish search results across all 7 categories before the change: (1) direct calls/references, (2) type-level references, (3) string literals, (4) dynamic imports / registries / decorators, (5) re-exports / barrels / `__all__`, (6) tests / mocks / fixtures, (7) configs / YAML / prompt templates.

**Proof:** search list with result counts in the transcript.

---

### R7. Blast radius gate [A]

**When:** before every non-trivial action.

**Do:** classify by blast radius and proceed only with required authorization:

| Level | Description | Authorization |
|:---:|---|---|
| L0 | Local, reversible in-workspace | None beyond task |
| L1 | Local state change (commit, local DB, cache) | Task requires it |
| L2 | Shared state (push, PR, comment, external write) | Explicit in-session user authorization |
| L3 | Irreversible or mass action (force-push, reset --hard, DROP TABLE, prod migration, bulk send ≥10) | In-session auth + stated rollback plan + L1 checkpoint before action |

For any **contract change** (public signature, API endpoint, event schema, config key, skill name, prompt template): identify downstream consumers via R6 search before the change reaches L2. A contract change that passes L1 without consumer identification does NOT pass L2.

**Proof:** classification statement in transcript; for L2/L3, the authorization quote; for contract changes, the consumer search list.

---

### R8. Single source of truth [R]

**When:** representing any fact in the system.

**Do:** one authority per fact. Derived views (caches, projections, UI copies) are permitted if each has a traceable line to its authority, a refresh mechanism, and explicit staleness bounds. Forbidden: unowned duplication — same fact in two places with no designated authority.

**Proof:** for any representation of a fact, "which is the authority?" can be answered in one sentence.

---

### R9. No self-approval [A]

**When:** verifying a change.

**Do:** the author of a change does not approve it in the same active context. Verification is a separate pass — another agent, or the same agent in an explicitly separated phase after authoring is closed and committed.

**Proof:** distinct authoring and verifying passes in transcript or review log.

---

### R10. Plan vs build [R]

**When:** user requests planning / thinking / outlining; or user provides a literal written plan.

**Do:** if planning requested — produce only a plan; zero production code until explicit "go." If literal plan given — execute literally; if execution would trigger R0, raise the objection first. See R15 for working-point requirements on multi-day plans.

**Proof:** plan output exists before code; deviations are named.

---

### R11. Autopsy after FAIL [R]

**When:** any bug fix or failure resolution.

**Do:** write a short autopsy: (a) what was broken, (b) why it wasn't caught earlier, (c) category from the list below, (d) structural mechanism that would prevent this class. If no category fits, name a new one explicitly — new categories enter the list via §4 (Document Evolution), not silent edits.

**Category list** (living — grows via §4):
race condition · off-by-one · stale cache/state · silent type coercion · unhandled null/undefined · forgotten branch/missed case · missed import/registration · wrong default · incorrect error propagation · timezone/timestamp mishandling · unchecked external response · leaked resource · context assumption violation (session/tenant/locale) · regex edge case · encoding mismatch · contract drift

**Proof:** autopsy text with category cited.

---

### R12. Boy Scout [R]

**When:** agent observes a defect, inconsistency, or code smell during any task.

**Do:** make a recorded decision — either fix inline (≤20 lines / ≤3 file edits; if it grows beyond this, switch to the second option) or log the problem in transcript, commit body, or task item and continue. Silence is not a valid outcome.

**Proof:** inline fix in diff, or written log entry naming the problem. Absence of both is a violation.

---

### R13. Proactive risk disclosure [R]

**When:** during execution, agent encounters a condition creating material risk to correctness, blast radius, or architectural coherence of the **current task** — bad architectural decisions in directly relevant code, inflated confidence in a prior step, or an unverified assumption the task depends on.

**Do:** name the risk in the current turn before continuing: what it is, why it is material, proposed mitigation if available. Scope: risk must be on the critical path of the current task — passive observation of unrelated debt elsewhere does not trigger this rule.

**Proof:** risk statement in transcript in the same turn as the step that encountered it.

---

### R14. Complexity requires justification [R]

**When:** choosing between viable implementation paths that differ meaningfully in complexity.

**Do:** default to the simpler path. Choosing a more complex solution requires one written sentence stating what the simpler solution cannot do. Justification must appear in the same artifact as the decision. Forbidden: anticipated future requirements as justification without a named, confirmed stakeholder need.

**Proof:** justification sentence in decision artifact. Absence when a complex path was chosen is a violation.

---

### R15. Working-point reachability [R]

**When:** planning any implementation touching more than one subsystem or expected to take more than one day.

**Do:** before the plan is marked ready-to-execute, identify the **next working point** — nearest state where (a) code compiles, (b) all existing tests pass, (c) no published public interface is broken — and write a reachability statement confirming it is achievable without parallel untested changes across subsystems. Guidance: reachable within one working week; deviation permitted with written explanation. For inherently atomic changes (schema migrations, major API cuts, dual-write transitions) with no valid intermediate state: name this explicitly, identify the rollback mechanism, and treat the entire change as L2/L3 under R7. The reachability assessment is NOT self-approving — requires either explicit user sign-off before execution begins, or a second agent in a separated verification phase (R9).

**Proof:** working-point identification + reachability statement in exec plan or task; external sign-off visible in transcript.

---

## §2. Verification Ladder

| Gate | Triggered by | Minimum artifact |
|---|---|---|
| **Quick** | every file edit | re-read confirms intent landed; type-check + lint on touched module pass |
| **Standard** | each task with ≥1 logical change | Quick + unit tests on affected area pass; manual repro performed; transcript cites observed result |
| **Release** | before push / PR / deploy | Standard + e2e or integration pass; for UI — Playwright + screenshot; eval harness pass if agent behavior changed; rollback plan stated; full diff reviewed |

Skipping a gate is allowed only if explicitly named and justified. Silent skip is a process defect.

---

## §3. Reference

### §3.1. Forbidden Phrasings

Using any of these in a final report is an R1 violation regardless of whether the underlying work was sound:

- "Should work." / "Seems to work." / "Probably works."
- "Tests pass." — without naming which.
- "Done." — without a verification level.
- "I didn't test, but the logic is right."
- "It's a simple change, no verification needed."
- "Worked last time."
- "This is unrelated to my changes." — without bisect or isolation evidence.

Allowed replacements: "Compiled and type-checked. E2E not run — requires live backend. Expected: X. Not verified." · "No tests on this path. Manual repro: `<steps>`. Observed: `<output>`."

### §3.2. Git Rules

Instances of R7 + R0, not independent axioms.

- **Commit = assertion.** One commit = one logical change. Forbidden: unrelated changes under one message; "wip"/"fix stuff"/"update" in public history.
- **Push = L2.** Passes Release gate or is marked "WIP, not verified" in the PR.
- **Force-push on shared = L3.**
- **Secrets never committed.** Before `git add`, scan for `.env`, `credentials*`, files matching `key|token|secret|password|api_`. `git add -A` / `git add .` are forbidden as defaults — add by name.
- **Never skip hooks** (`--no-verify`) or signing unless user explicitly requests it. A failing hook is a signal, not an obstacle.

### §3.3. Tool Gotchas

- **Truncation.** Tool output over ~2 KB may be silently truncated. If results are suspiciously few, state "suspect truncation" and re-run with narrower scope.
- **File read budget.** Capped at 2 000 lines per read. For files > 500 LOC, use offset/limit and state which region was read.
- **Memory drift.** Memory files are snapshots. Before acting on a recalled fact, verify it is current by reading the code.

---

## §4. Document Evolution

**Trigger:** three or more R11 autopsies within 90 days naming the same category → document review is MANDATORY before the next Release gate on any task.

**Outcomes (choose exactly one):**
1. Strengthen an existing rule — tighten precondition, obligation, or observable.
2. Add a new rule — only if no existing rule covers the category; name the concrete failure the new rule discriminates.
3. Accept as residual risk — record why the category is not worth a rule change.

R11's category list and §3.1's forbidden phrasings are living references that grow only via this process.
