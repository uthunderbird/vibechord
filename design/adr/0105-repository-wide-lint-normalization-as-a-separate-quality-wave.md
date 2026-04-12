# ADR 0105: Repository-wide lint normalization as a separate quality wave

## Status

Accepted

## Context

The repository now has a meaningful `ruff` baseline, but it is not yet repo-wide green.

Current truth at decision time:

- `implemented`: touched-file lint cleanup is already part of active refactor work when it is
  low-risk and local
- `verified`: current architecture and DI slices can be kept clean at the file level
- `verified`: a full repository `ruff` run still reported substantial legacy debt outside the most
  recently touched files

This means the repository currently has two different lint realities:

- newer or recently refactored files can often be kept clean
- older files still carry accumulated style, import, and line-length debt

That split is manageable for local work, but it has real costs:

- contributors cannot use repo-wide lint as a strict always-green signal
- unrelated lint debt creates noise during otherwise narrow changes
- cleanup pressure gets mixed into architecture and behavior refactors
- style normalization remains vulnerable to endless deferral

The architectural and process question is therefore:

- should full lint normalization remain opportunistic and piggyback on feature/refactor work
- or should it be treated as a separate repository-quality wave with its own scope and acceptance
  criteria

## Decision

Repository-wide lint normalization should be treated as a separate quality wave.

It should not be smuggled into unrelated architectural or behavior changes as background cleanup.

### Scope of the quality wave

The lint-normalization wave should aim to make:

- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests`

an always-green repository gate.

The wave may be delivered incrementally, but the target is repo-wide normalization rather than
perpetual touched-file-only cleanup.

### What this wave should include

- import sorting and removal of dead imports
- line-length normalization where it improves maintainability
- mechanical style fixes that do not change behavior
- small safe simplifications when directly suggested by lint and behavior-preserving

### What this wave should not include

- semantic refactors disguised as lint cleanup
- architecture changes that happen to be motivated by lint
- behavior changes without matching tests
- repo-wide automated rewrites without review of risky sites

### Execution rule

Until the repository is repo-wide lint clean:

- contributors should continue keeping touched files clean where practical
- but repo-wide normalization should be tracked and executed as its own workstream

This preserves both:

- local hygiene for new work
- and honest recognition that the repository still has a broader quality backlog

## Alternatives Considered

### Keep lint cleanup purely opportunistic

Rejected.

That preserves local progress but does not create a real closure path for repo-wide debt.

It leaves the repository in a long-lived mixed state where:

- some files are clean
- some files are not
- and no one owns the closure of the whole baseline

### Enforce repo-wide green lint immediately on every change

Rejected as the immediate default.

The current repository still carries enough legacy lint debt that immediate hard enforcement would
turn unrelated changes into broad cleanup obligations.

That would create avoidable churn and distract from behavioral or architectural work already in
flight.

### Ignore lint debt outside changed files indefinitely

Rejected.

That would normalize drift between local hygiene expectations and repo-wide quality truth.

## Consequences

- The repository gets a clear quality workstream for repo-wide lint closure.
- Architectural and behavior refactors can stay narrower and easier to reason about.
- Repo-wide lint debt becomes visible and schedulable instead of ambient background noise.
- The repository can continue requiring touched-file cleanliness without pretending that the whole
  baseline is already normalized.
- `implemented`: the repository-wide lint normalization wave is now complete.
- `verified`: `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests` is green.
- `verified`: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` remains green after the cleanup.

## Implementation Status

Implemented

Skim-safe current truth on 2026-04-12:

- `implemented`: `ruff` is configured and enforced in pre-commit hooks
- `implemented`: `uv run ruff check src/` reports zero errors as of 2026-04-12
- `verified`: all checks pass — legacy import and style debt cleared
