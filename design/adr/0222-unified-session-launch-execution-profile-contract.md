# ADR 0222: Unified Session Launch Execution Profile Contract

- Date: 2026-05-04

## Decision Status

Accepted

## Implementation Status

Verified

Implementation grounding on 2026-05-04:

- `implemented`: execution-profile request/stamp mapping now has a shared domain helper instead of
  being owned only by `LoadedOperation`. Evidence:
  `src/agent_operator/domain/execution_profiles.py`.
- `implemented`: `LoadedOperation.effective_execution_profile_stamp()`,
  `LoadedOperation.execution_profile_request_metadata()`, and session handle stamp extraction now
  delegate to the shared helper, reducing the v1 path to a compatibility shell for this mapping.
  Evidence: `src/agent_operator/application/loaded_operation.py`.
- `implemented`: v2 `PolicyExecutor` real session launch adds shared execution-profile metadata to
  `AgentRunRequest.metadata` before starting the session. Evidence:
  `src/agent_operator/application/drive/policy_executor.py`.
- `implemented`: `SessionState` derives an `execution_profile_stamp` from handle metadata when a
  `session.created` payload contains a stamped handle but no explicit stamp field. Evidence:
  `src/agent_operator/domain/operation.py`.
- `verified-focused`: v2 launch regression proves Codex `model`, `reasoning_effort`,
  `approval_policy`, and `sandbox_mode` reach request metadata, `session.created` handle metadata,
  and `SessionState.execution_profile_stamp`. Evidence: `tests/test_drive_service_v2.py`.
- `verified-suite`: full suite passed on 2026-05-04:
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest` (`1113 passed, 12 skipped`). Focused type check
  passed for the changed source files:
  `UV_CACHE_DIR=/tmp/uv-cache uv run mypy src/agent_operator/domain/execution_profiles.py src/agent_operator/application/loaded_operation.py src/agent_operator/domain/operation.py src/agent_operator/application/drive/policy_executor.py`.
- `verified-review`: separate post-commit review on 2026-05-04 confirmed that
  `LoadedOperation` delegates execution-profile request/stamp mapping to the shared helper, v2
  `PolicyExecutor` uses that helper before session launch, and remaining
  `execution_profile_*` references are consumers, tests, command validation, projection/display
  code, or operation overlay state rather than competing request-metadata authorities.

## Context

A v2 operator-on-operator run exposed a split-brain session launch bug:

1. A Codex ACP session requested approval during an attached turn.
2. The human answer was accepted and the attention request was resolved.
3. The next `tick` attempted to continue the same session.
4. Continuation failed because the session had no observed execution profile, while the operation's
   desired contract required `codex_acp` on `gpt-5.4`.

The failure message was:

```text
Session 019def75-99fa-71f1-80a6-23b5f3d507ee cannot continue because it has no observed execution profile, but adapter 'codex_acp' requires gpt-5.4.
```

This was not an approval-handling failure. The answer command was accepted, the attention request
was answered, and the attention was resolved. The failure happened after that, at the session
continuation guard.

The continuation guard itself is correct. ADR 0190 and ADR 0218 require continuation, reuse, and
resume to compare the desired execution profile with the observed session profile. Continuing an
unstamped Codex session would silently weaken the operation's runtime contract, especially for
`approval_policy` and `sandbox_mode`.

The root cause is that session launch metadata is split across two launch paths:

- the v1 attached path builds request metadata through
  `LoadedOperation.execution_profile_request_metadata()` via
  `OperationTurnExecutionService._background_request_metadata()`;
- the v2 `PolicyExecutor` real session launch constructs `AgentRunRequest.metadata` directly with
  only `operation_id` and `adapter_key`.

Therefore the v2 path can start a real ACP session under effective adapter settings while the
returned `AgentSessionHandle.metadata` lacks the `execution_profile_*` fields required to stamp
the session record.

## Decision

All real session launch paths must use one canonical execution-profile request metadata contract.

For every real attached or background launch, the request metadata sent to the session manager must
include the effective execution profile for the target adapter when the operation has one.

For `codex_acp`, the execution-profile metadata includes:

- `execution_profile_model`
- `execution_profile_reasoning_effort`
- `execution_profile_approval_policy`, when configured
- `execution_profile_sandbox_mode`, when configured

For `claude_acp`, the execution-profile metadata includes:

- `execution_profile_model`
- `execution_profile_effort`, when configured

Session handles, session records, event-sourced `session.created` events, checkpoints, and read
models derive observed execution-profile truth from that launch metadata. They must not infer a
missing observed profile from the desired profile at continuation time.

## Non-Goals

This ADR does not change the compatibility rule from ADR 0190 and ADR 0218:

- an unstamped session does not match a desired execution profile;
- a mismatched session must not be reused silently;
- approval answers do not override execution-profile compatibility.

This ADR also does not remove all v1 operation-drive code immediately. It records the cleanup path
needed to avoid carrying two authorities for execution-profile launch metadata.

## Required Implementation

### 1. Introduce a shared execution-profile metadata helper

Create one application/domain helper that can derive request metadata from operation truth without
depending on `LoadedOperation`.

Inputs should be limited to:

- operation goal metadata,
- operation-local execution-profile overrides,
- adapter key.

The helper should be usable from both:

- `LoadedOperation.execution_profile_request_metadata()`
- v2 `PolicyExecutor`

The helper is the single source of truth for mapping effective profile fields into
`execution_profile_*` request metadata.

### 2. Wire v2 `PolicyExecutor` session launch through the helper

The real session launch path in `src/agent_operator/application/drive/policy_executor.py` must add
the shared execution-profile metadata to `AgentRunRequest.metadata`.

The final metadata should still include operation-local trace fields such as `operation_id` and
`adapter_key`, but those fields must not replace the execution-profile contract.

### 3. Preserve the strict continuation guard

`LoadedOperation.session_matches_execution_profile()` and
`LoadedOperation.execution_profile_mismatch_summary()` should keep rejecting unstamped or
mismatched sessions when a desired profile exists.

If a legacy or corrupted operation contains an unstamped active session, the operator should fail,
re-escalate, or start a fresh compatible session through an explicit path. It must not silently
pretend the session was launched under the desired profile.

### 4. Add regression coverage for the missing v2 slice

Tests must cover:

- v2 `PolicyExecutor` real session launch includes execution-profile metadata in the returned
  `session.created` handle payload;
- the aggregate/checkpoint session state receives an observed `ExecutionProfileStamp`;
- continuation after an answered attention or waiting-input interruption can proceed when the
  session stamp matches;
- continuation still rejects an unstamped or mismatched session when a desired profile exists.

At least one regression should include Codex policy fields (`approval_policy` and `sandbox_mode`)
because those are the fields whose loss makes this bug materially unsafe.

### 5. Clean up v1 duplication after the v2 helper lands

Once the shared helper is used by v2 and covered by tests, v1-side execution-profile mapping should
be reduced to a thin call into the same helper.

The cleanup target is:

- no independent field mapping in `LoadedOperation.execution_profile_request_metadata()`;
- no second execution-profile metadata builder in turn execution services;
- no v1-only semantics for Codex `approval_policy` / `sandbox_mode`;
- no tests that pass only because v1 and v2 launch paths diverge.

The v1 code may remain as a compatibility shell while the broader v1 removal ADRs are still partial,
but it must stop being a separate authority for execution-profile request metadata.

## Consequences

### Positive

- v2 launched sessions can be continued after approval/resume without failing due to missing
  observed profile stamps.
- The continuation guard remains strict and continues to prevent unsafe silent reuse.
- Codex `approval_policy` and `sandbox_mode` become part of one launch contract instead of
  depending on which drive path started the session.
- v1 cleanup has a concrete seam: delete duplicated metadata mapping after both paths call the
  shared helper.

### Negative

- The shared helper adds one more explicit application-level contract before v1 removal is complete.
- Existing tests that assume v1-only metadata construction will need to be rewritten around the
  shared helper.

## Relationship To Existing ADRs

- ADR 0190 defines dynamic execution-profile overlays and reuse compatibility.
- ADR 0191 requires execution-profile transparency in status and timeline surfaces.
- ADR 0218 requires continuation/reuse/resume to compare desired and observed execution contracts.
- ADR 0209 and ADR 0213 track broader legacy removal gates.

This ADR narrows the implementation gap those ADRs exposed: the desired-versus-observed
continuation contract already exists, but v2 launch metadata does not yet feed the observed side of
that contract consistently.

## Verification Plan

Implementation should not be marked `Implemented` until focused tests prove the v2 `PolicyExecutor`
launch path stamps sessions with the effective execution profile.

Implementation should not be marked `Verified` until:

- the focused v2 launch/continuation regressions pass;
- the existing execution-profile reuse tests pass;
- the full suite passes at the final tree;
- a focused review confirms no remaining independent execution-profile request metadata builder is
  load-bearing outside the shared helper.

## Next Working Point

The nearest safe working point is:

1. add the shared helper;
2. change `LoadedOperation.execution_profile_request_metadata()` to delegate to it;
3. change v2 `PolicyExecutor` real session launch to use it;
4. add focused v2 regression coverage;
5. run focused tests for policy executor, attached-turn reuse, event-sourced replay/projection, and
   operation status.

This working point is reachable without removing v1 drive code and without weakening the strict
continuation guard.
