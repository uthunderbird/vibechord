# ADR 0105 Implementation Plan

## Summary

Implement `ADR 0105` as a dedicated repository-quality wave.

Goal:

- make `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests` an always-green gate
- keep the work mechanical and low-risk
- avoid mixing style cleanup with architecture or runtime behavior changes

Current closure:

- `implemented`: all planned subtree phases were completed
- `implemented`: remaining repo-wide lint tail outside the original phase buckets was also closed
- `verified`: `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests` is green
- `verified`: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` is green

## Principles

### 1. Treat lint normalization as mechanical work

Allowed:

- import sorting
- dead import removal
- line wrapping
- trivial simplifications suggested by `ruff`

Not allowed by default:

- behavior changes
- opportunistic architectural refactors
- semantic rewrites hidden as lint cleanup

### 2. Work in bounded slices

Do not try to clean the whole repo in one pass.

Preferred slices:

1. `tests/`
2. `application/`
3. `runtime/`
4. `adapters/`
5. `acp/`

Each slice should end with:

- slice-local `ruff` green
- targeted tests green
- no behavior drift

### 3. Keep verification proportional

For pure import/formatting cleanup:

- targeted tests for touched modules

For cleanup that touches control flow:

- broader targeted suite
- full suite before merge of each major slice

## Recommended Order

### Phase 1: Fast mechanical cleanup in `tests/`

Scope:

- unused imports
- import sorting
- line-length fixes
- unused locals
- similar low-risk issues

Why first:

- high fix volume
- low architecture risk
- good signal that the quality wave is moving

Verification:

- `ruff check tests`
- targeted pytest for changed test files
- full suite if the slice is broad

### Phase 2: `application/` subtree normalization

Scope:

- import cleanup
- formatting
- safe simplifications only where obviously behavior-preserving

Special care:

- files around operator loop, lifecycle, and command handling should be reviewed manually after
  auto-fix

Verification:

- `ruff check src/agent_operator/application`
- service-heavy targeted tests
- full suite

### Phase 3: `runtime/` subtree normalization

Scope:

- store/inbox/event/history modules
- supervisor-related files
- background inspection and persistence helpers

Special care:

- anything around file I/O and async state transitions

Verification:

- `ruff check src/agent_operator/runtime`
- runtime/cancellation/reconciliation tests
- full suite

### Phase 4: `adapters/` subtree normalization

Scope:

- ACP adapters
- runtime bindings
- permission-related glue

Special care:

- keep vendor behavior unchanged
- review any auto-simplification around permission and prompt handling

Verification:

- `ruff check src/agent_operator/adapters`
- adapter/runtime-binding tests
- smoke or CLI tests where relevant

### Phase 5: `acp/` subtree normalization

Scope:

- SDK client
- session runner
- transport/runtime helpers

Why last:

- highest density of long lines and potential risky rewrites
- easiest place for “mechanical” changes to accidentally obscure protocol behavior

Verification:

- `ruff check src/agent_operator/acp`
- ACP/session tests
- full suite

## Execution Tactics

### Use auto-fix first, then hand-fix the tail

For each slice:

1. run `ruff check --fix` on the slice
2. inspect remaining errors
3. hand-fix line-length or small local issues
4. run tests

### Prefer narrow commits or checkpoints

Each slice should be understandable independently:

- `tests lint normalization`
- `application lint normalization`
- etc.

### Watch-list areas

These should get extra manual review after auto-fix:

- `session_runner.py`
- `sdk_client.py`
- drive/lifecycle/reconciliation files
- permission-handling code
- event-sourced loop code

## Test Plan

### Slice-local gate

For each slice:

- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check <slice>`
- relevant `pytest` subset

### Major-slice gate

After each broad subtree:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q`

### Final acceptance gate

- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q`

## Acceptance Criteria

- repo-wide `ruff check src tests` is green
- full pytest suite is green
- no behavioral claims changed without tests
- no architecture refactors were smuggled into the lint wave
- touched-file cleanliness becomes repository-wide cleanliness

## Outcome

- `implemented`: `tests/`, `application/`, `runtime/`, `adapters/`, and `acp/` were normalized
- `implemented`: repo-wide tail closure in `cli/`, `domain/`, `dtos/`, `protocols/`,
  `providers/`, and `testing/`
- `verified`: final gate
  `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests`
- `verified`: final gate
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q`

## Risks

- accidental behavior changes during “mechanical” cleanup
- oversized slices that become hard to review
- mixing lint normalization with unrelated refactors
- auto-fix obscuring subtle protocol logic in ACP/runtime files

## Defaults

- prefer many small slices over one big cleanup
- prefer auto-fix plus review over manual editing everything
- prefer targeted tests after each slice
- use full suite after each major subtree and at final closure
