# Critique of RFC 0006: Event Model — Round 3
**Focus**: Wording precision, consistency, and internal coherence
**Date**: 2026-04-02
**Critique method**: Swarm Red Team (5 critics: Normative Language Auditor, Table–Prose Consistency Checker, Undefined Terms Detective, Contradiction Hunter, Redundancy/Duplication Auditor; 1 sub-group iteration)

---

## Summary Assessment

RFC 0006 is a technically thorough specification with detailed invariants, failure contracts, and
implementation guidance. The core architecture is coherent and the event catalog is largely
complete. However, the document has three critical coherence defects that will cause implementer
confusion or divergent implementations without correction, plus a significant cluster of undefined
terms that force readers to guess at types, semantics, and field ownership.

**Strengths**:
- Failure direction A/B contract is precise and actionable
- Loop invariants are numbered and explicit
- Async conversion call sites are enumerated with line numbers
- Tech debt is explicitly registered rather than buried

**Weaknesses**:
- The "Category" column in the taxonomy table and the `category` field use the same word for
  different concepts, causing direct contradictions with the data model table
- `session.cooldown_expired` is simultaneously classified as `domain` and as `kind=WAKEUP`,
  which violates the RFC's own kind/category rule
- Backwards-compatibility rule silently downgrades pre-existing domain events to trace
- Eleven terms used without definition; several payload fields specified by name only

---

## Red Team Composition

| Critic | Focus |
|---|---|
| Normative Language Auditor | RFC 2119 precision, imperative vs normative register, under-specified defaults |
| Table–Prose Consistency Checker | Table-to-prose mismatches, missing table rows, column content anomalies |
| Undefined Terms Detective | Terms used before definition, semantic drift, unresolved type references |
| Contradiction Hunter | Cross-section logical contradictions, rule-then-exception without reconciliation |
| Redundancy/Duplication Auditor | Near-verbatim duplication, content repeated with divergent wording |

---

## Critical Findings

### C1 — Taxonomy table "Category" column conflicts with `category` field values

**Location**: Section 1, taxonomy table (rows: `domain`, `trace`, `wakeup`) vs. Data model changes
table (`category: Literal["domain", "trace"] | None`).

**Problem**: The taxonomy table uses "Category" as its column header and lists `wakeup` as a
valid row. The very next table defines the `category` field with only two non-None values:
`"domain"` and `"trace"`. `"wakeup"` never appears as a `category` field value. A reader
mapping the taxonomy table onto the field table concludes `wakeup` is a valid `category` value —
which directly contradicts the field definition and the kind/category relationship table.

**Root cause**: The taxonomy table's "Category" column is a conceptual label (event bucket), not
the `category` field value. These two uses of the word "category" are never disambiguated in the
text.

**Impact**: Implementers may attempt to pass `category="wakeup"` to `_emit()`, which should
be a type error but the ambiguity makes it plausible. The Literal type annotation will catch it
at runtime, but the document creates the confusion.

**Fix**: Rename the taxonomy table's first column from "Category" to "Event bucket" (or
"Conceptual type") and add a sentence after the table stating: "The `category` field on
`RunEvent` uses only the values `"domain"` and `"trace"`; `"wakeup"` is a conceptual bucket
only, not a field value."

---

### C2 — `session.cooldown_expired` is domain in the catalog but kind=WAKEUP in the model

**Location**: Section 2A reclassification table (marks `session.cooldown_expired` as `domain`);
Section 5 Session events table (State effect column); Section 1 kind/category relationship table.

**Problem**: Section 1 establishes unambiguously: `kind="wakeup"`, `category=None`. The Session
events table's State effect cell for `session.cooldown_expired` states the event is emitted with
`kind=WAKEUP` and that "the `domain` category applies to the intent." But under the RFC's own
rule, a `kind=WAKEUP` event must have `category=None` and "is not an observability record." The
event therefore cannot be both `domain` (per Section 2A and 5) and `kind=WAKEUP, category=None`
(per Section 1's rule) without contradiction.

The cell acknowledges this as "acknowledged tech debt" but does not resolve the normative
contradiction: is the event domain or not? What should a conformant implementation do today?

**Impact**: An implementer who follows Section 1 rules will emit this event with
`kind=WAKEUP, category=None`, making it non-domain. An implementer who follows Section 2A/5
will attempt `kind=WAKEUP, category="domain"`, which the Pydantic validator should reject (since
wakeup events are exempt from category assignment). The document gives no actionable resolution
beyond "tech debt."

**Fix**: Add a normative resolution sentence to the tech debt note for this event. Either:
(a) "For now, emit with `kind=WAKEUP, category=None`; the domain record is sacrificed until the
tech debt is resolved"; or (b) "Emit two events: a `kind=WAKEUP` signal for delivery and a
separate `kind=TRACE, category='domain'` record for observability." Choose one and state it
normatively.

---

### C3 — Backwards-compatibility rule silently downgrades pre-existing domain events

**Location**: "No migration needed" section, last paragraph.

**Problem**: The backwards-compat rule states: "readers should treat absent `category` as
`'trace'` for backwards compatibility." But `operation.started`, `command.applied`,
`command.accepted_pending_replan`, `command.rejected`, `session.force_recovered`,
`session.cooldown_expired`, and `background_run.cancelled` are all classified as `domain` in
this RFC's own Section 2A table — and they were already being emitted before this RFC. Their
existing `events.jsonl` records have no `category` field. Under the backwards-compat rule, these
historical domain events will be read as `trace`. The claim "no migration needed" is accurate
for schema compatibility but false for semantic correctness: the historical domain event record
is degraded.

**Impact**: Any reader that uses the domain event log to reconstruct operation state from
existing files will silently omit pre-existing domain events (treating them as trace). The
event-sourcing guarantee stated in Section 1 ("reconstruct state from domain events alone") is
violated for historical logs.

**Fix**: Add a qualification: "Note: pre-existing domain events in historical `events.jsonl`
files will be read as `trace` by backwards-compat readers. Readers that reconstruct operation
state must also process events with `event_type` matching any domain event listed in Section 2A
regardless of the absent `category` field, using `event_type` as the discriminator." Alternatively,
change the backwards-compat default to `"domain"` for known domain event_type values.

---

## High-Priority Findings

### H1 — "should be a type error" uses weak normative strength for a hard enforcement requirement

**Location**: Section 1, Data model changes prose: "constructing a `RunEvent` with `kind='trace'`
and no `category` should be a type error in new code — enforced via a Pydantic validator or
`__init__` guard."

**Problem**: "Should be" is SHOULD in RFC terms (optional/recommended). "Type error" is a hard
enforcement concept. The document means this MUST be enforced; "should" allows an implementer
to skip the validator without violating the RFC.

**Fix**: Replace "should be a type error" with "must be a type error."

---

### H2 — `policy.evaluated` is listed as a required new domain event but absent from Section 5

**Location**: Section 2B required events table lists `policy.evaluated` (priority: Medium).
Section 5 domain event detail tables contain no entry for `policy.evaluated`.

**Problem**: All other events in Section 2B have corresponding Section 5 detail entries.
`policy.evaluated` has none. There is no explanation for the omission — no note saying
"deferred" or "detail TBD."

**Fix**: Add a `policy.evaluated` row to an appropriate Section 5 table (or a new "Policy
events" sub-table), or add a note in Section 2B explaining that the detail entry is deferred
and why.

---

### H3 — `msg.dropped_from_context` field used without definition

**Location**: Section 5 Session events table, State effect for `operator_message.dropped`:
"`msg.dropped_from_context = True`".

**Problem**: `dropped_from_context` is used as a field name without defining: its owner model
(`OperatorMessage`?), type (`bool`?), semantics (does it affect routing? context building?), or
whether it is a new field introduced by this RFC or pre-existing.

**Fix**: Add a definition sentence, e.g.: "The `dropped_from_context: bool` field on
`OperatorMessage` (defaulting `False`) is set to `True` when the message is evicted from the
active context window."

---

### H4 — `reason` payload field in `operation.status.changed` is undefined

**Location**: Section 5 Operation aggregate events table, State effect column for
`operation.status.changed`: "payload carries `previous_status`, `new_status`, `reason`."

**Problem**: `reason` is named but not specified: type (string? enum?), required vs optional,
valid values or format. The document provides detailed payload specs for some events but leaves
this one to imagination.

**Fix**: Specify `reason: str | None` (or an enum) and whether it is required.

---

### H5 — "replan triggered" vs. "replan queued" — same concept, two formulations

**Location**: Section 5, `attention.request.answered` State effect ("replan triggered") and
`operator_message.received` State effect ("replan queued").

**Problem**: These appear to describe the same mechanism (schedule a brain re-evaluation) but
use different verbs. "Triggered" implies immediate execution; "queued" implies deferred. If
semantically distinct, explain the difference. If the same, use one term consistently.

**Fix**: Standardize to one term (recommend "replan queued" if it goes through the command
inbox; "triggered" if it causes an immediate loop re-entry) and add a one-line definition.

---

### H6 — WakeupWatcher "synchronous scan" uses misleading terminology in async context

**Location**: WakeupWatcher spec, Startup initial scan: "must perform a synchronous scan of the
wakeup directory."

**Problem**: In asyncio, "synchronous" means blocking the event loop. The spec's goal is to
perform an initial scan before entering the watch loop — a sequential, not concurrent, operation.
But calling it "synchronous" may cause an implementer to block the event loop doing the initial
file scan.

**Fix**: Replace "synchronous scan" with "an initial blocking-tolerant scan" or "a startup
scan performed before entering the watch loop." Add: "This scan may use blocking I/O only if
wrapped in `anyio.to_thread.run_sync` or equivalent."

---

## Lower-Priority Findings

### L1 — "WakeupInbox" and "FileWakeupInbox" used interchangeably without definition

**Location**: Section 3. "file-based `WakeupInbox`" (first paragraph), then "FileWakeupInbox
uses a flat directory" and "defined by FileWakeupInbox" in WakeupWatcher spec.

**Problem**: It is unclear whether these are the same type, an interface/implementation pair,
or aliases. The spec delegates the filename convention to `FileWakeupInbox` but never says what
`FileWakeupInbox` is.

**Fix**: At first use, add: "`FileWakeupInbox` is the concrete implementation of `WakeupInbox`
backed by a filesystem directory."

---

### L2 — "run context" used without definition

**Location**: WakeupWatcher spec, Creation and supervision context and Cancellation contract.

**Problem**: "Run context" is referenced as an object ("stored on the run context," "run context
is torn down") but never defined — its type, scope, and lifecycle are not described in this RFC.

**Fix**: Add a parenthetical on first use, e.g.: "run context (the per-operation object
allocated by `run()` that holds the `asyncio.Event` and `WakeupWatcher` task)."

---

### L3 — `RunEventKind` type is referenced but not defined in the RFC

**Location**: Section 1 Data model changes table, `kind` field: type listed as
`RunEventKind ("trace" | "wakeup")`.

**Problem**: `RunEventKind` is presented as a type annotation without saying whether it is an
`enum.Enum`, a `Literal`, or a `TypeAlias`. As a standalone RFC, readers need to know its
definition or a reference to where it is defined.

**Fix**: Add: "`RunEventKind` is defined in `domain/enums.py` as a `str`-based enum with
members `TRACE` and `WAKEUP`." (or the actual definition location).

---

### L4 — `not_before` and `dedupe_key` parameters in `_emit()` signature are undefined

**Location**: Section 1, `_emit()` signature listing.

**Problem**: The RFC states the signature shows "all parameters, not only the new one." But
`not_before: datetime | None` and `dedupe_key: str | None` are listed without explanation. A
reader of this RFC cannot determine their semantics without consulting the existing code.

**Fix**: Add a table note or footnote: "`not_before` — earliest allowed emit time (scheduling
deferred events); `dedupe_key` — idempotency key to suppress duplicate emits. Both pre-existing;
see [source reference]."

---

### L5 — "fan-out broadcast" term used in Context but not defined or referenced later

**Location**: Context section: "conflating permanence with ephemerality and fan-out broadcast
with single-consumer delivery."

**Problem**: "Fan-out broadcast" implies a multi-consumer publish mechanism. No such mechanism
is defined in this RFC. Section 5 lists "Future projections" as a consumer, but the delivery
mechanism is never specified. The term is used once and never revisited.

**Fix**: Either define "fan-out broadcast" (e.g., "all consumers reading the append-only JSONL
log") or replace with a precise description ("all consumers via the append-only event log").

---

### L6 — Trace events absent from Section 5 with no explanatory note

**Location**: Section 5 heading and all sub-tables cover only domain events.

**Problem**: Section 2A lists 10 trace events. Section 5 says it covers "domain event details."
There is no explicit statement that trace events are intentionally excluded from Section 5 or
a pointer to where their details live.

**Fix**: Add a one-line note at the start of Section 5: "This section covers domain events
only. Trace events are not given detail entries; their payloads are documented inline at their
emit sites."

---

### L7 — Scheduler state values in wrong table column

**Location**: Section 5, `scheduler.state.changed` row in Operation aggregate events table,
Consumers column: "valid values: ACTIVE, PAUSE_REQUESTED, PAUSED, DRAINING."

**Problem**: Valid state values are enumerated inside the Consumers column, which is meant to
list event consumers (EventSink, CLI/Watch, etc.). This content belongs either in the State
effect column or in a separate scheduler FSM section, not in Consumers.

**Fix**: Move the valid values enumeration to the State effect column or to the scheduler state
transition rules block immediately below the table.

---

### L8 — Three near-identical "no test/fake files" notes are boilerplate candidates

**Location**: Immediate Changes Required section, async conversion notes for
`_apply_task_mutations`, `_open_attention_request`, `_append_operator_message`.

**Problem**: Each async conversion note ends with: "No test or fake files call [method]
directly; no changes required outside `service.py` for this conversion." This sentence is
repeated verbatim three times. While not incorrect, it could be consolidated into a single
note or a table.

**Fix**: Add one shared note: "For all async conversions listed above, no test or fake files
call these methods directly; changes are confined to `service.py`." Remove the three
repetitions.

---

### L9 — `operator_message.dropped` cardinality rule appears only in Immediate Changes Required

**Location**: Immediate Changes Required: "Exactly one `operator_message.dropped` event must be
emitted per dropped message."

**Problem**: This cardinality rule is normative and belongs in Section 5's event detail for
`operator_message.dropped`. A reader referencing Section 5 as the authoritative catalog will
not find it. The Section 5 State effect says "Oldest messages removed" which could be read as
batch removal with a single event.

**Fix**: Move or duplicate the cardinality rule to the Section 5 `operator_message.dropped`
State effect column.

---

### L10 — `TOCTOU` jargon used without expansion

**Location**: WakeupWatcher spec, Startup initial scan: "This closes the TOCTOU window."

**Problem**: Inconsistent with the document's general prose register. Most readers in this
codebase's context will understand it, but the RFC does not expand it elsewhere.

**Fix**: Expand on first use: "TOCTOU (time-of-check/time-of-use) window."

---

### L11 — "Do not add this path" uses imperative without RFC 2119 normative force

**Location**: Task status transitions note: "Do not add this path when implementing this RFC."

**Problem**: All other prohibitions in the document use "must not." This isolated "Do not"
is weaker in register and inconsistent.

**Fix**: Replace "Do not add this path" with "Implementers must not add this path."

---

### L12 — Section 2B `policy.evaluated` trigger has embedded implementation note that should be in Immediate Changes Required

**Location**: Section 2B, `policy.evaluated` row, Trigger column: "(change-detected, not on
every call); requires adding a diff step to `_refresh_policy_context`."

**Problem**: Implementation instruction ("requires adding a diff step") is embedded inside an
event catalog table's Trigger column, which is an unusual place for implementation guidance. The
Immediate Changes Required section does not mention `policy.evaluated` at all.

**Fix**: Remove the implementation note from the Trigger column. Add a corresponding entry
to Immediate Changes Required.

---

## Recommendations

1. **Rename the taxonomy table column** from "Category" to "Event bucket" (C1 — critical).
2. **Add a normative resolution for `session.cooldown_expired`** — specify exactly what
   implementation should do today, even if imperfect (C2 — critical).
3. **Qualify the "no migration needed" claim** with the silent downgrade caveat for historical
   domain events (C3 — critical).
4. **Upgrade "should be a type error" to "must be a type error"** (H1).
5. **Add Section 5 detail entry for `policy.evaluated`** or note it as deferred (H2).
6. **Define `dropped_from_context` field** (H3) and `reason` payload field (H4).
7. **Standardize "replan triggered/queued"** to one term with a definition (H5).
8. **Replace "synchronous scan" with precise async-safe phrasing** (H6).
9. Address lower-priority findings L1–L12 as time permits; L7 (wrong column for scheduler
   values), L9 (cardinality rule placement), and L12 (policy.evaluated missing from Immediate
   Changes Required) are the most impactful of the lower group.

---

## Methodology

- Document read in full before critiquing; no source code files were read.
- Five critic roles applied in one round-robin iteration followed by one targeted sub-group
  on the taxonomy/kind-category coherence cluster.
- All findings are grounded in specific document text; no claims are attributed to the author
  beyond what is written.
- ACP integration events: the document contains no dedicated ACP section. The focus brief
  mentioned ACP. This critique notes the absence but cannot determine whether it is an
  intentional scope exclusion or a gap, as the RFC is silent on the question. No finding
  is raised for this absence.

---

## Compact Ledger

**Target document**: `/Users/thunderbird/Projects/operator/design/rfc/0006-event-model.md`

**Focus used**: Wording precision, consistency, and internal coherence — ambiguous normative
language, contradictions between sections, undefined terms, table/prose inconsistencies,
duplicate content, implementation gaps.

**Main findings**:
- C1: "Category" column naming collision between taxonomy table (3 rows) and `category` field
  (2 values), creating wakeup-as-category confusion
- C2: `session.cooldown_expired` simultaneously domain (Sections 2A, 5) and kind=WAKEUP,
  category=None (Section 1 rules) — irreconcilable contradiction without a normative resolution
- C3: Backwards-compat rule "treat absent category as trace" silently downgrades pre-RFC
  domain events, breaking the event-sourcing guarantee for historical logs
- H1: "should be a type error" too weak for a hard enforcement requirement
- H2: `policy.evaluated` listed as required domain event but absent from Section 5 detail tables
- H3–H4: `dropped_from_context` and `reason` fields unnamed/untyped in payload specs
- H5: "replan triggered" vs "replan queued" — inconsistent terms for same mechanism
- H6: "synchronous scan" misleading in async context
- L1–L12: Undefined terms (WakeupInbox/FileWakeupInbox, run context, RunEventKind,
  not_before/dedupe_key, fan-out broadcast), trace events absence unexplained, scheduler values
  in wrong column, cardinality rule misplaced, boilerplate repetition

**Exact ordered fix list for the repair round**:

1. Rename taxonomy table "Category" column → "Event bucket"; add disambiguation sentence (C1)
2. Add normative resolution for `session.cooldown_expired` today-behavior in tech debt note (C2)
3. Qualify "No migration needed" with silent-downgrade caveat and discriminator-by-event_type
   guidance (C3)
4. Change "should be a type error" → "must be a type error" in Data model changes prose (H1)
5. Add `policy.evaluated` detail entry to Section 5, or add explicit "deferred, detail TBD"
   note in Section 2B (H2)
6. Add `_append_operator_message` cardinality rule to Section 5 `operator_message.dropped`
   State effect column (L9 — feeds H3 fix)
7. Define `dropped_from_context: bool` field (owner, type, semantics) in Section 5 (H3)
8. Specify `reason` payload field type and required/optional status in Section 5 (H4)
9. Standardize "replan triggered" → "replan queued" (or vice versa) and add one-line definition
   (H5)
10. Replace "synchronous scan" with "startup scan … wrapped in anyio.to_thread.run_sync" (H6)
11. Move scheduler valid-values enumeration from Consumers column to State effect column (L7)
12. Add note at start of Section 5 explaining trace events are intentionally excluded (L6)
13. Add `policy.evaluated` entry to Immediate Changes Required list (L12)
14. Consolidate three "no test/fake files" async notes into one shared note (L8)
15. Standardize "Do not add this path" → "Implementers must not add this path" (L11)
16. Define WakeupInbox/FileWakeupInbox relationship at first use (L1)
17. Define "run context" parenthetically at first use (L2)
18. Add footnote for `not_before` and `dedupe_key` parameters in `_emit()` signature (L4)
19. Expand TOCTOU on first use (L10)
20. Replace "fan-out broadcast" with precise delivery description (L5)
21. Add `RunEventKind` definition or source reference at first use (L3)
