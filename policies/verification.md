# Verification Policy

## Verification Hygiene

- For nontrivial behavioral claims, prefer at least one concrete verification path:
  - automated test
  - direct local run
  - persisted artifact inspection
  - trace or log confirmation
- If verification was not performed, say `not verified`.
- If a bug fix changes runtime semantics, prefer adding or updating a regression test in the same
  task.
- If an ADR changes the expected behavior of implemented functionality, update the affected tests to
  the new contract before changing the implementation.

## Computed Outputs

For computation- or script-derived outputs, be explicit about whether the result is:

- computed
- inferred
- copied from an external source

## Local Verification Workflow

`implemented`: pre-commit runs `ruff` and `mypy` on changed Python files plus the full `pytest -q`
suite.

`planned`: full repository-wide `mypy` coverage.
