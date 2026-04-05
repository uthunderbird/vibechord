# RFC 0001 Critique Round 3

## Focus

Wording precision, consistency, internal coherence, and readability.

## Scope and evidence boundary

- Target only: `design/rfc/0001-acp-python-sdk-integration.md`
- Evidence boundary: the critique is grounded in the target document text itself.
- Constraint: this round does not revisit migration realism except where wording now creates
  inconsistency or readability drag.

## Critical findings

1. `verified issue`: the RFC now uses several near-overlapping labels for the same concept without
   settling on one primary term, which weakens precision and makes the document harder to follow.
   The text alternates among:
   - `operator-owned injected contract`
   - `operator-owned ACP substrate`
   - `per-adapter ACP substrate selection seam`
   - `substrate binding`
   - `selection and injection`
   Evidence:
   - `design/rfc/0001-acp-python-sdk-integration.md:42-71`
   - `design/rfc/0001-acp-python-sdk-integration.md:111-123`
   - `design/rfc/0001-acp-python-sdk-integration.md:214-227`
   - `design/rfc/0001-acp-python-sdk-integration.md:295-297`
   Why this matters:
   - The RFC is trying to make a boundary more explicit, but the terminology itself now shifts just
     enough that the reader has to keep re-normalizing what the document means.

2. `verified issue`: the document now mixes RFC content with round-specific repair metadata, which
   breaks internal coherence and weakens readability for a new contributor reading the RFC as a
   source-of-truth document.
   Evidence:
   - `## Repair Round 2 Ledger` appears inside the RFC at
     `design/rfc/0001-acp-python-sdk-integration.md:318-341`.
   Why this matters:
   - The ledger is useful during the review loop, but inside the RFC it reads as workflow residue
     rather than architecture content. It also creates a tone shift from proposal prose into
     process bookkeeping.

## Lower-priority findings

1. `bounded concern`: the coexistence mechanism is explained more than once in slightly different
   forms, which hurts readability even though the meaning is mostly stable.
   Evidence:
   - First explanation in the Decision section at
     `design/rfc/0001-acp-python-sdk-integration.md:59-71`
   - Repeated in dependencies at `design/rfc/0001-acp-python-sdk-integration.md:111-123`
   - Repeated again in Phase 1 and Phase 2 at
     `design/rfc/0001-acp-python-sdk-integration.md:214-227`
   Implication:
   - The RFC would read more cleanly if it defined the mechanism once in the Decision section, then
     referred back to that term consistently.

2. `bounded concern`: some phrasing is precise but heavier than necessary, making the migration plan
   harder to scan.
   Examples:
   - “That seam is what makes the mixed migration stage real rather than rhetorical” at
     `design/rfc/0001-acp-python-sdk-integration.md:67`
   - “The same caution applies to migration safety” at
     `design/rfc/0001-acp-python-sdk-integration.md:166`
   - “If a stage regresses runtime behavior, rollback should mean…” at
     `design/rfc/0001-acp-python-sdk-integration.md:295-297`
   Implication:
   - The RFC is now carrying some argument-by-emphasis wording that could be simplified without
     losing precision.

3. `bounded concern`: the verification and rollback language is internally coherent, but the same
   concepts recur with slightly different phrasing across Phase 2, Phase 3, Phase 4, Open
   Questions, and Success Criteria.
   Evidence:
   - Mixed-mode language at `design/rfc/0001-acp-python-sdk-integration.md:238-240`,
     `design/rfc/0001-acp-python-sdk-integration.md:250-253`,
     `design/rfc/0001-acp-python-sdk-integration.md:287-291`,
     `design/rfc/0001-acp-python-sdk-integration.md:313-315`
   Implication:
   - The reader gets the same message repeatedly, but not always in the same compact wording. This
     is a readability issue more than a correctness issue.

## Recommendations

1. Pick one primary term for the injected ACP layer and use it consistently.
   Suggested pattern:
   - primary term: `operator-owned ACP substrate`
   - secondary operational term only when needed: `selection seam`
   Avoid rotating among `binding`, `selection and injection`, and `injected contract` unless the
   distinction is real and defined.
2. Remove the repair ledger from the RFC and keep that bookkeeping in the critique artifacts rather
   than the target document.
3. Compress repeated mechanism prose.
   Define the coexistence mechanism once in the Decision section, then shorten later references to
   “the per-adapter ACP substrate seam” or similar.
4. Tighten a few rhetorical phrases into plainer architectural prose.
   Prefer direct statements of behavior over phrases like “real rather than rhetorical” or
   “the same caution applies.”
5. Normalize repeated mixed-mode and verification language so the same idea is phrased the same way
   across the migration phases and success criteria.

## Ledger

- target document: `design/rfc/0001-acp-python-sdk-integration.md`
- focus used: wording precision, consistency, internal coherence, and readability
- main findings:
  - the RFC now uses too many near-synonymous labels for the injected ACP layer and its selection
    mechanism
  - the embedded repair ledger weakens the RFC as a self-contained source-of-truth document
  - repeated mechanism and verification wording now creates readability drag even where the meaning
    is mostly correct
- exact ordered fix list for the repair round:
  1. Normalize terminology around the ACP layer and its coexistence mechanism so one primary term
     carries through the document.
  2. Remove the repair ledger from the RFC body.
  3. Compress repeated explanations of the coexistence mechanism so later sections refer back to the
     defined term instead of restating it.
  4. Simplify heavy rhetorical phrases into plainer architectural prose.
  5. Standardize repeated mixed-mode and verification language across the migration phases and
     success criteria.
