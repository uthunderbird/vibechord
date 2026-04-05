# ADR 0108: Legacy compatibility retirement fronts and parallel-truth policy

## Status

Implemented (prompt-compatibility wave and snapshot_legacy wave complete)

## Context

The repository does not currently show an obvious pile of completely dead Python modules under
`src/agent_operator/`.

The stronger cleanup signal is different: the codebase still contains live compatibility residue
from older architectural phases, and some of that residue is already at odds with the target
architecture.

This residue is not all the same.

Some code paths are explicit migration or compatibility seams that should disappear once the
repository fully closes the older model. Other code paths are still live but represent broader
parallel-truth debt that is not yet safe to remove without a separate architectural wave.

The distinction matters because blind "dead code cleanup" would be misleading:

- some suspicious surfaces are still exercised by tests and runtime paths
- some older language is still propagated through domain and traceability models
- some compatibility behavior has already been partially constrained by earlier ADRs, but not fully
  retired from the live codebase

This ADR builds on earlier event-sourcing cutover and retirement work, especially:

- `ADR 0077`: per-operation canonical persistence mode and legacy coexistence window
- `ADR 0086`: event-sourced operation birth and `snapshot_legacy` retirement policy

Those ADRs already reject long-lived dual live runtime authority. The repository now needs an
explicit cleanup policy for the remaining compatibility residue that still appears in code, tests,
and trace surfaces.

## Decision

The repository will treat remaining legacy residue in two explicit buckets rather than as one
undifferentiated cleanup problem.

### 1. Target-architecture retirement fronts

The following compatibility surfaces should be treated as code that is expected to disappear in the
target architecture:

- `CanonicalPersistenceMode.SNAPSHOT_LEGACY` — `implemented`
- hydration of missing canonical persistence mode to `snapshot_legacy` — `implemented`
- operation-status hydration from `"blocked"` to `"needs_human"` — `implemented`
- deprecated prompt-shaped goal-input compatibility — `implemented`
- `GoalInputMode.LEGACY_PROMPT` — `implemented`
- `GoalInputMode.LEGACY_MIXED_PROMPT` — `implemented`
- `legacy_ambiguity_reason` propagation, reporting, and legacy goal-summary decoration — `implemented`

These surfaces represent older conceptual models that currently coexist with the newer canonical
direction and should be retired rather than preserved indefinitely.

### 2. Still-live architectural debt

The following surfaces should be treated as architectural debt, but not as immediate safe-removal
candidates:

- `active_session` as a parallel surface alongside canonical `sessions`
- `sync_legacy_active_session`
- legacy rate-limit migration and cooldown-recovery heuristics

These remain behavior-bearing and have dense call-site and test coverage. They should not be
removed under a generic compatibility cleanup banner without a more specific replacement or
architectural decision.

### 3. Cleanup policy

Future cleanup work should start with the target-architecture retirement fronts, not with the
still-live architectural-debt bucket.

In particular:

- legacy compatibility code should not be described as stable repository truth merely because it is
  still exercised
- still-live architectural debt should not be mislabeled as dead code
- removal work should prefer collapsing old conceptual language rather than just moving it to new
  modules

### 4. Documentation and claim policy

Repository docs, ADRs, and implementation plans should distinguish:

- `implemented`: compatibility path still exists
- `verified`: compatibility path is still exercised by tests or runtime evidence
- `planned`: compatibility path is scheduled for retirement

They should not describe these surfaces as canonically desired just because they remain live during
the transition.

## Current evidence

The strongest current retirement-front evidence appears in:

- `domain/enums.py`
- `domain/operation.py`
- `domain/traceability.py`
- `application/operation_traceability.py`
- `providers/prompting.py`

The strongest current still-live architectural-debt evidence appears in:

- `domain/operation.py`
- `application/loaded_operation.py`
- `application/agent_results.py`
- `application/operation_entrypoints.py`
- `application/operation_runtime_reconciliation.py`
- `cli/main.py`

Existing tests still exercise parts of this residue, including:

- `tests/test_runtime.py` for missing canonical-mode upgrade behavior
- CLI and service tests that still observe or depend on `active_session`

## Alternatives Considered

### Option A: Treat all suspicious legacy code as dead code and remove it aggressively

Rejected.

The repository still has active call sites and tests for several of these paths. Calling them dead
code would overstate current freedom to delete them.

### Option B: Treat all currently live compatibility code as permanent repository truth

Rejected.

That would collapse the distinction between temporary coexistence and desired target architecture,
and would contradict earlier ADR direction around event-sourced cutover and snapshot-legacy
retirement.

### Option C: Track only `snapshot_legacy` retirement and ignore other old conceptual language

Rejected.

The current residue is broader than persistence mode alone. Prompt-shaped compatibility and legacy
ambiguity reporting also preserve older conceptual models that should not be normalized as enduring
truth.

### Option D: Treat `active_session` and legacy rate-limit migration as the same class of cleanup as prompt and snapshot compatibility

Rejected.

These surfaces still carry more live behavioral weight and need a separate architectural pass
rather than opportunistic deletion.

## Consequences

- `planned`: the next compatibility-retirement wave should begin with explicit legacy conceptual
  surfaces rather than with broad behavioral cleanup
- `planned`: prompt-compatibility and `snapshot_legacy` residue should be tracked as retirement
  fronts
- `planned`: `active_session` and legacy rate-limit recovery remain separate debt items that need a
  more specific decision before removal
- `partial`: some earlier ADR retirement direction is already reflected in code and tests, but the
  repository still carries substantial live compatibility residue
