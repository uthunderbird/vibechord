# ADR 0223: V2 Continue-Agent Must Target A Compatible Existing Session

- Date: 2026-05-04

## Decision Status

Accepted

## Implementation Status

Verified

Implementation grounding on 2026-05-04:

- `implemented`: v2 `PolicyExecutor` now distinguishes `CONTINUE_AGENT` from `START_AGENT` and
  sends the follow-up through the existing session manager session instead of always starting a new
  session. Evidence: `src/agent_operator/application/drive/policy_executor.py`.
- `implemented`: v2 continuation now rejects missing, wrong-adapter, unstamped, or execution-profile
  mismatched sessions instead of guessing or silently weakening the session contract. Evidence:
  `src/agent_operator/application/drive/policy_executor.py`.
- `verified`: focused regressions prove v2 continuation reuses a stamped Codex session and rejects
  an unstamped session when the desired execution profile exists. Evidence:
  `tests/test_drive_service_v2.py`.
- `verified`: local focused regression suite passed on 2026-05-04:
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_drive_service_v2.py -k 'continue_agent or execution_profile'`
  (`3 passed`).
- `verified`: focused source type check passed on 2026-05-04:
  `UV_CACHE_DIR=/tmp/uv-cache uv run mypy src/agent_operator/application/drive/policy_executor.py`.
- `verified`: full repository suite passed on 2026-05-04:
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` (`1116 passed, 12 skipped`).
- `verified-review`: red-team self-check rejected an earlier fallback that guessed the latest
  adapter session when `session_id` was omitted; the final implementation requires an explicit
  reusable target session instead.

## Context

ADR 0222 closed the execution-profile stamping gap for real v2 session launches, but repository
truth after that ADR still had a runtime contract hole:

- `START_AGENT` and `CONTINUE_AGENT` both followed the same fresh-launch path in v2
  `PolicyExecutor`;
- a brain decision to continue an existing session could therefore start a new session instead of
  sending a follow-up through the previously stamped one;
- this weakened parity with the attached/v1 continuation contract and made the execution-profile
  guard less meaningful in the v2 drive path.

This was a real runtime behavior gap, not just missing paperwork. The v2 path already had the
strict desired-versus-observed execution-profile contract from ADR 0222, but it still needed to
honor the semantic difference between “start a new session” and “continue this session.”

## Decision

V2 `CONTINUE_AGENT` must target an explicit existing session and must not guess.

The contract is:

1. `START_AGENT` starts a new session.
2. `CONTINUE_AGENT` requires an explicitly identified reusable session.
3. The target session must belong to the requested adapter.
4. If a desired execution profile exists, the observed session profile must match it exactly.
5. If any of those checks fail, v2 must fail explicitly rather than silently starting or reusing a
   different session.

## Consequences

### Positive

- V2 continuation now preserves the semantic difference between new launch and follow-up.
- The execution-profile guard from ADR 0222 becomes load-bearing for actual continuation.
- The drive path avoids ambiguous session guessing and keeps operator behavior deterministic.

### Negative

- Brain decisions that emit `CONTINUE_AGENT` without `session_id` now fail instead of recovering by
  heuristic reuse.
- Additional v2 continuation slices may still be needed later for richer task/session targeting,
  but those can build on an explicit contract instead of hidden inference.

## Relationship To Existing ADRs

- ADR 0222 defines the unified launch-time execution-profile stamping contract.
- ADR 0218 defines strict desired-versus-observed execution-profile compatibility.
- This ADR closes the next practical runtime gap after ADR 0222 by applying those contracts to the
  v2 continue-agent path rather than only to fresh launch.
