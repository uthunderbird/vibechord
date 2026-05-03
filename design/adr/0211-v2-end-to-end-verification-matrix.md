# ADR 0211: v2 End-to-End Verification Matrix

- Date: 2026-04-23

## Decision Status

Accepted

## Implementation Status

Partial

Implementation grounding on 2026-04-28:

- `implemented`: the repository already exposes the core verification surfaces this ADR depends on:
  `operator run --v2`, `operator status --json`, `operator watch --once --json`,
  `operator log --json`, `operator attention --json`, `operator answer --text`,
  `operator debug inspect --json --full`, and `operator debug event append`
- `partial`: this ADR now records a minimal manual verification matrix and bounded procedures for
  one fresh operator-on-operator smoke in this repository and one fresh external-project smoke in
  `../erdosreshala/problems/625`
- `verified`: the repository-wide baseline row was rerun on 2026-05-03 with
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest` (`1100 passed, 11 skipped`) and recorded in
  `design/internal/v2-verification-evidence-2026-05-03-full-suite.md`
- `blocked`: the live Codex ACP preflight row was attempted on 2026-05-03 and failed before ACP
  initialize with `AcpProtocolError: ACP subprocess closed before completing all pending requests`;
  direct `npx @zed-industries/codex-acp --help` diagnostics also failed with npm registry DNS
  resolution (`ENOTFOUND registry.npmjs.org`). Evidence:
  `design/internal/v2-verification-evidence-2026-05-03-live-codex-acp-preflight.md`
- `implemented`: the live Codex ACP pytest row now performs a bounded readiness check before
  opening the ACP JSON-RPC session, so unavailable ACP executables are reported as explicit skips
  instead of late protocol failures. Evidence:
  `tests/test_live_codex_acp.py`,
  `tests/test_live_codex_acp_preflight.py`
- `blocked`: this evidence wave did not run a fresh operator-on-operator v2 smoke
- `blocked`: this evidence wave did not run a fresh external-project v2 smoke against
  `../erdosreshala/problems/625`
- `noted`: `../erdosreshala/problems/625` exists locally and already contains `.operator/`,
  including `.operator/runs/`; that existing directory is not itself proof of v2 dependency, so
  the no-`.operator/runs` matrix row still requires outcome-based verification rather than simple
  filesystem inspection
- `noted`: the current `operator` worktree is clean (`git status --short` returned no entries), so
  the remaining blockers in this wave are live-evidence gaps rather than repository-state hygiene

Acceptance grounding on 2026-04-26:

- `implemented`: the repository now has one canonical in-repo verification procedure document at
  `docs/reference/v2-verification.md` that names the matrix rows, preflight, live commands, and
  promotion rules for this ADR rather than leaving them implicit.
- `implemented`: the procedure's referenced evidence artifact now exists at
  `design/internal/v2-verification-evidence-template.md`, so the recorded-evidence workflow is a
  real repository artifact rather than a broken reference.
- `implemented`: smoke-goal and live-smoke entrypoints already exist in code for the documented
  local and live rows. Evidence: `src/agent_operator/smoke.py`,
  `tests/test_smoke_goal.py`, `tests/test_live_codex_acp.py`,
  `tests/test_live_codex_continuation.py`, and
  `tests/test_live_mixed_code_agent_selection.py`.
- `verified`: a static regression now fails if the procedure references a missing evidence
  template. Evidence: `tests/test_v2_verification_docs.py`.
- `implemented`: the published procedure now explicitly enumerates the previously implicit
  `targeted query/read-model tests`, `stream/TUI visibility smoke`, and `restart/resume smoke`
  rows, so the document matches this ADR's required matrix more closely instead of leaving those
  rows buried only in later prose sections.
- `verified`: static regressions now fail if the procedure drops those required row names or the
  canonical `status` / `watch --once` / `debug inspect --full` visibility commands. Evidence:
  `tests/test_v2_verification_docs.py`.
- `blocked`: this ADR still lacks the fresh operator-on-operator and external-project live
  evidence required for `Verified`, so implementation status remains `Partial`.

## Context

Targeted tests can prove slices, but full v2 confidence requires end-to-end evidence that the
operator can operate itself and operate a real external project. ADR 0202 already exposed this:
local tests can pass while the external `../erdosreshala/problems/625` smoke remains the missing
verification gate.

Current repository truth also shows that parts of the live verification workflow already exist:

- ADR 0202 records targeted permission-path coverage and leaves the external
  `../erdosreshala/problems/625` smoke as an explicit remaining blocker
- ADR 0205 records repository test coverage for the canonical v2 control plane
- ADR 0212 records a debug-only repair surface for canonical event-stream repair when normal CLI
  lifecycle control is insufficient during verification or incident response

What is still missing is a single in-repo procedure that says exactly how to run the bounded live
checks, what evidence to capture, and what currently blocks closure.

Current repository truth also includes one newly observed verification blocker: replay-backed public
surfaces are not yet schema-stable for all canonical v2 event payloads. During this wave,
`operator status`, `operator answer`, and operation-resolution paths were observed failing in replay
with projector validation errors while materializing `operation.created`. That failure belongs to
the ADR 0206 closure scope, but it must also be recorded here because it blocks honest end-to-end
verification.

## Decision

v2 acceptance requires a verification matrix that combines repository tests with real
operator-on-operator and external-project e2e runs.

The required external e2e target is:

```text
../erdosreshala/problems/625
```

This ADR does not mark v2 as verified. It defines the minimum manual procedure and evidence bar
needed to do so later without guessing.

## Required Matrix

| Matrix row | Required evidence | Current state on 2026-04-28 |
| --- | --- | --- |
| full `uv run pytest` | one recorded green repository-wide run tied to the repo state under review | recorded on 2026-05-03: `1100 passed, 11 skipped` |
| targeted command/control tests | explicit green commands for the touched v2 control-plane tests | grounded by ADR 0205, not rerun here |
| targeted query/read-model tests | explicit green commands for read-model/query tests | grounded by existing ADR/test references, not rerun here |
| restart/resume smoke | one fresh v2 operation survives restart/resume path or records the blocker | not verified in this slice |
| permission approve/reject/escalate/needs_human smoke | one fresh run records the permission path and resulting operator behavior without external ACP UI selection | not verified in this slice |
| stream/TUI visibility smoke | status/watch/debug inspect evidence reflects the live/canonical result | procedure documented; not run here |
| live Codex ACP roundtrip | narrow ACP transport preflight before larger live smokes | blocked on 2026-05-03 before ACP initialize; see recorded evidence note |
| operator-on-operator v2 smoke | one fresh run in this repository with persisted evidence artifacts | procedure documented; not run here |
| external project smoke against `../erdosreshala/problems/625` | one fresh run in that target with persisted evidence artifacts | procedure documented; not run here |
| no `.operator/runs` dependency for v2 operation success | live result proves success does not depend on legacy `.operator/runs` semantics | not verified in this slice |

## Required Properties

- each ADR claiming `Verified` names the matrix subset that verifies it
- skipped live tests are not counted as e2e verification
- e2e evidence records command, date, repository state, operation id, result, and known
  environmental assumptions
- failures produce an autopsy and either a fix or a named blocker
- replay/query crashes on canonical persisted events are blocker evidence and must be recorded as
  failed verification rows until fixed
- existing `.operator/` artifacts in the target workspace do not count as positive verification
  unless the recorded run proves the required property

## Prerequisites

Run live verification only when all of the following are true:

1. the repository state under test is intentionally pinned and reviewable
2. local dependencies are installed with:

   ```sh
   UV_CACHE_DIR=/tmp/uv-cache uv sync --extra dev
   ```

3. Codex ACP is launched through the explicit command override required by this repository:

   ```sh
   env OPERATOR_CODEX_ACP__COMMAND='npx @zed-industries/codex-acp --' \
       OPERATOR_CODEX_ACP__MODEL='gpt-5.4' \
       OPERATOR_CODEX_ACP__EFFORT='low' \
       UV_CACHE_DIR=/tmp/uv-cache \
       uv run operator run --mode attached --agent codex_acp --max-iterations 100 "<objective>"
   ```

4. the workspace being verified has a committed or explicit project profile; initialize one when
   needed with:

   ```sh
   UV_CACHE_DIR=/tmp/uv-cache uv run operator init
   ```

5. if the target workspace already has prior `.operator/` state, the verifier either:
   - records that reused state is intentional, or
   - clears it explicitly before the run through a separately authorized destructive step

## Manual Procedure

### A. Operator-on-operator smoke in this repository

From `/Users/thunderbird/Projects/operator`:

1. initialize the workspace profile if needed:

   ```sh
   UV_CACHE_DIR=/tmp/uv-cache uv run operator init
   ```

2. start one fresh v2 attached run:

   ```sh
   env OPERATOR_CODEX_ACP__COMMAND='npx @zed-industries/codex-acp --' \
       OPERATOR_CODEX_ACP__MODEL='gpt-5.4' \
       OPERATOR_CODEX_ACP__EFFORT='low' \
       UV_CACHE_DIR=/tmp/uv-cache \
       uv run operator run --v2 --mode attached --agent codex_acp --max-iterations 100 \
       "Inspect this repository and summarize the main architectural boundaries. Use only read-only commands. If a permission request is rejected, continue through operator follow-up rather than external ACP UI selection."
   ```

3. capture the resulting canonical status:

   ```sh
   UV_CACHE_DIR=/tmp/uv-cache uv run operator status last --json
   ```

4. capture the one-shot live view:

   ```sh
   UV_CACHE_DIR=/tmp/uv-cache uv run operator watch last --once --json
   ```

5. capture the full forensic/canonical payload:

   ```sh
   UV_CACHE_DIR=/tmp/uv-cache uv run operator debug inspect last --json --full
   ```

6. capture the transcript/log view when a Codex session exists:

   ```sh
   UV_CACHE_DIR=/tmp/uv-cache uv run operator log last --agent codex --json --limit 50
   ```

7. if the run reaches `needs_human`, capture the blocking request before answering:

   ```sh
   UV_CACHE_DIR=/tmp/uv-cache uv run operator attention last --json
   ```

8. if a human answer is required, answer explicitly through the operator surface rather than ACP UI:

   ```sh
   UV_CACHE_DIR=/tmp/uv-cache uv run operator answer last <attention-id> --text "<answer>"
   ```

### B. External-project smoke in `../erdosreshala/problems/625`

From `/Users/thunderbird/Projects/operator`, switch to the target workspace:

```sh
cd ../erdosreshala/problems/625
```

1. initialize the target workspace profile if needed:

   ```sh
   UV_CACHE_DIR=/tmp/uv-cache uv run operator init
   ```

2. start one fresh v2 attached run scoped to the external target:

   ```sh
   env OPERATOR_CODEX_ACP__COMMAND='npx @zed-industries/codex-acp --' \
       OPERATOR_CODEX_ACP__MODEL='gpt-5.4' \
       OPERATOR_CODEX_ACP__EFFORT='low' \
       UV_CACHE_DIR=/tmp/uv-cache \
       uv run operator run --v2 --mode attached --agent codex_acp --max-iterations 100 \
       "Work only inside this problem workspace. Complete a bounded inspection or implementation step for problem 625, and if a permission request appears, resolve it through operator policy or operator attention handling rather than external ACP UI selection."
   ```

3. capture the canonical status:

   ```sh
   UV_CACHE_DIR=/tmp/uv-cache uv run operator status last --json
   ```

4. capture the one-shot live view:

   ```sh
   UV_CACHE_DIR=/tmp/uv-cache uv run operator watch last --once --json
   ```

5. capture the full forensic/canonical payload:

   ```sh
   UV_CACHE_DIR=/tmp/uv-cache uv run operator debug inspect last --json --full
   ```

6. capture Codex transcript evidence when present:

   ```sh
   UV_CACHE_DIR=/tmp/uv-cache uv run operator log last --agent codex --json --limit 50
   ```

7. if the run reaches `needs_human`, capture and answer through the operator CLI:

   ```sh
   UV_CACHE_DIR=/tmp/uv-cache uv run operator attention last --json
   UV_CACHE_DIR=/tmp/uv-cache uv run operator answer last <attention-id> --text "<answer>"
   ```

## Expected Evidence

For each live smoke, preserve at least:

- the exact run command
- the date
- the repository state under test (`git rev-parse HEAD` in `operator`, plus the target workspace
  revision when applicable)
- the resolved operation id from `status` or `debug inspect`
- terminal or blocking outcome from `status --json`
- permission-path evidence from `debug inspect --json --full`, including whether the run approved,
  rejected with follow-up, or escalated to `needs_human`
- transcript or log evidence from `operator log ... --json` when a Codex session exists
- any error text or repair requirement if the normal lifecycle path fails

Expected positive signals include:

- `status --json` resolves the v2 operation without legacy resolution failure
- `watch --once --json` and `debug inspect --json --full` describe the same operation outcome
- permission events, attention state, or follow-up-required state are visible in canonical
  inspection payloads when that path was exercised
- the run completes without requiring an external ACP approval UI choice

## Current Blockers

- No fresh operator-on-operator run has been recorded for this ADR wave.
- No fresh `../erdosreshala/problems/625` run has been recorded for this ADR wave.
- The external target already contains `.operator/` state, including `.operator/runs/`; a future
  run must distinguish reused legacy artifacts from actual v2 runtime requirements.
- If normal CLI lifecycle control fails during a verification run, record the blocker first. Use
  `operator debug event append ...` only as a separately justified repair action, not as silent
  verification scaffolding.

## Verification Plan

This ADR remains unverified in the current slice.

It can move to `Verified` only when:

- the documented manual procedure or a matrix runner is actually executed
- at least one fresh operator-on-operator v2 run is captured with the evidence above
- at least one fresh external-project v2 run against `../erdosreshala/problems/625` is captured
  with the evidence above
- the recorded evidence shows whether the permission path was approve, reject-with-follow-up, or
  escalate-to-attention
- the no-`.operator/runs` dependency claim is established by recorded behavior rather than assumed
  from repository layout

## Related

- ADR 0194
- ADR 0202
- ADR 0203
- ADR 0204
- ADR 0205
- ADR 0206
- ADR 0207
- ADR 0208
- ADR 0209
- ADR 0210
- ADR 0212
