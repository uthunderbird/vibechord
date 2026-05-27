# Verification Policy

## Verification Hygiene

- For nontrivial behavioral claims, prefer at least one concrete verification
  path:
  - automated test;
  - direct local run;
  - persisted artifact inspection;
  - trace or log confirmation.
- If verification was not performed, say `not verified`.
- If a bug fix changes runtime semantics, prefer a regression test in the same
  work wave.
- If an ADR changes expected behavior of implemented functionality, update the
  affected tests before changing the implementation.

## Computed Outputs

For computation- or script-derived outputs, state whether the result is:

- computed;
- inferred;
- copied from an external source.

## Local Verification Workflow

Planned baseline once implementation begins:

- `ruff`
- `mypy`
- full test suite

The fuller planned verification architecture lives in
[`../design/TESTING-RAILS.md`](../design/TESTING-RAILS.md).

Until code exists, verification for design work means checking the artifact
corpus for internal consistency, placement, status labels, and red-team
coverage.
