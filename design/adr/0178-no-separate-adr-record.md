# ADR 0178: No Separate ADR Record

## Decision Status

Rejected

## Implementation Status

N/A

Skim-safe status on 2026-04-15:

- `implemented`: the repository does not contain a standalone `design/adr/0178-*.md` file before
  this bookkeeping record
- `verified`: the repository does not contain any references to `ADR 0178` in code, tests, docs,
  or design records
- `current repository truth`: no repo-internal evidence identifies a separate missing
  architectural authority that should be reconstructed under this number

## Context

An audit request on 2026-04-15 asked for line-by-line verification of `ADR 0178` against current
repository code and tests.

Current repository truth at the start of that audit:

- there was no `design/adr/0178-*.md` file
- there were no repository references to `ADR 0178`
- there was no git-history evidence of a prior tracked path under `design/adr/*0178*`
- there was no repo-internal evidence identifying a displaced or superseding authority for this ADR
  number

Creating a new normative architectural decision without repository evidence for its intended topic
would invent design history rather than clarify repository truth.

## Decision

Do not create a new normative architecture decision under ADR 0178.

`ADR 0178` is reserved as a bookkeeping record only:

- to state that no separate ADR existed at current repository truth
- to prevent future readers from assuming a missing-but-normative decision record
- to record that no repo-grounded displaced authority could be identified for this number

Future work should cite the actual ADR or status artifact that carries the relevant authority
rather than using `ADR 0178` as a behavioral reference.

## Repository Evidence

- ADR directory listing showed a numbering gap between `0177` and `0180` before this file:
  [design/adr](/Users/thunderbird/Projects/operator/design/adr)
- Repository text search for `ADR 0178` / `0178` across design, docs, source, and tests produced
  no relevant matches:
  [design](/Users/thunderbird/Projects/operator/design),
  [docs](/Users/thunderbird/Projects/operator/docs),
  [src](/Users/thunderbird/Projects/operator/src),
  [tests](/Users/thunderbird/Projects/operator/tests)
- Git history inspection for `design/adr/*0178*` and commit messages mentioning `ADR 0178`
  produced no prior tracked ADR under that number

## Verification

Evidence inspected during this audit:

- `find design/adr -maxdepth 1 -type f | sort | tail -n 40` -> numbering gap confirmed before this
  record was added
- `rg -n "ADR 0178|0178|178" design docs src tests` -> no ADR-0178 repository references
- `git log --all --name-status -- 'design/adr/*0178*'` -> no tracked ADR-0178 history
- `git log --all --grep='ADR 0178' --oneline` -> no commit history naming ADR 0178
- full repository verification for this slice is `uv run pytest`

## Consequences

- Future requests for `ADR 0178` should not assume a hidden authoritative document exists in this
  repository.
- If a real intended authority is identified later from external evidence, it should be recorded
  explicitly and linked from this bookkeeping record rather than inferred retroactively.
