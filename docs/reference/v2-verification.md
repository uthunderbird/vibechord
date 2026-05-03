# v2 Verification Procedure

This document is the canonical procedure for the v2 verification matrix referenced by
`ADR 0211`.

It is intentionally procedure-first rather than runner-first. Current repository truth already has
the relevant execution surfaces:

- local regression tests through `pytest`
- live operator-on-operator smokes in `tests/test_live_*.py`
- direct CLI execution through `operator run --v2`

The authority for each matrix row is the existing test or CLI command, not a second wrapper layer.

## Scope

This procedure is the current reproducible path for:

- local repository verification needed by `ADR 0205`
- operator-on-operator v2 smoke verification
- external-project v2 smoke verification against `../erdosreshala/problems/625`
- evidence capture for future promotion of `ADR 0202`, `ADR 0205`, and `ADR 0211`

## Evidence Rules

Every matrix run must record:

- date
- repository `HEAD`
- whether the worktree was clean
- exact command
- operation id when a live run creates one
- result: `passed`, `failed`, `skipped`, or `blocked`
- known environment assumptions
- blocker or failure notes when the row does not pass

Use `design/internal/v2-verification-evidence-template.md` as the recording format.

Committed evidence notes live under `design/internal/` and use the
`v2-verification-evidence-<date>-<row>.md` naming pattern. Current recorded notes:

- `design/internal/v2-verification-evidence-2026-05-03-full-suite.md`
- `design/internal/v2-verification-evidence-2026-05-03-live-codex-acp-preflight.md`
- `design/internal/v2-verification-evidence-2026-05-03-operator-on-operator-smoke.md`

## Preflight

Run these checks before any live row:

```sh
git rev-parse HEAD
git status --short
command -v uv
command -v npx
command -v claude
python3 - <<'PY'
import importlib.util
print(importlib.util.find_spec("oauth_cli_kit") is not None)
PY
ls -ld ../erdosreshala/problems/625
```

If the worktree is dirty, record that fact in the evidence note. A dirty worktree does not block
verification, but it does weaken commit-anchored closure claims.

## Matrix

| Row | Purpose | Canonical command |
| --- | --- | --- |
| full suite | repository-wide regression baseline | `UV_CACHE_DIR=/tmp/uv-cache uv run pytest` |
| targeted control plane | prove `ADR 0205` local command/control behavior | `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_event_sourced_command_application.py tests/test_operator_service_v2.py` |
| targeted query/read-model tests | prove replay-backed status, resolution, and projector surfaces still hold | `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_operation_status_queries.py tests/test_operation_resolution.py tests/test_operation_projector.py` |
| targeted smoke shape | verify smoke-goal definitions still match the intended live surfaces | `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_smoke_goal.py` |
| live Codex ACP roundtrip | narrow ACP transport preflight before larger smokes | `OPERATOR_RUN_CODEX_ACP_LIVE=1 UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q -rs tests/test_live_codex_acp.py` |
| stream/TUI visibility smoke | prove the same live operation exposes coherent status/watch/inspect evidence | see `Stream / Visibility Capture` below |
| restart/resume smoke | prove one live v2 operation completes, resumes, or cancels through the approved follow-up path | see `Restart / Resume / Cancel Follow-up` below |
| operator-on-operator continuation smoke | fresh v2 run that reuses the same Codex session | `OPERATOR_RUN_CODEX_CONTINUATION_SMOKE=1 UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q -rs tests/test_live_codex_continuation.py` |
| operator-on-operator mixed-code smoke | fresh v2 run that chooses a real coding agent for this repo | `OPERATOR_RUN_MIXED_CODE_AGENT_SMOKE=1 UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q -rs tests/test_live_mixed_code_agent_selection.py` |
| external project baseline | prove `operator run --v2` works against problem `625` | see `External Project Baseline` below |
| external project permission slice | exercise `ADR 0202` on problem `625` with at least one permission-worthy action | see `External Project Permission Slice` below |
| no `.operator/runs` dependency | prove v2 success does not depend on legacy run snapshots | delete or move only the tested operation’s `.operator/runs` snapshot before replay-based read checks, then run `status`, `inspect`, and `list` against the same operation |

## Local Rows

Run the local rows first:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q \
tests/test_smoke_goal.py \
tests/test_event_sourced_command_application.py \
tests/test_operator_service_v2.py \
tests/test_operation_status_queries.py \
tests/test_operation_resolution.py \
tests/test_operation_projector.py
```

If the full suite is too expensive for the current wave, record that it was not run. Do not count
the targeted subset as full-suite evidence.

## Stream / Visibility Capture

For any live row used as evidence, capture the same operation id through all three supervisory
surfaces:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator status last --json
UV_CACHE_DIR=/tmp/uv-cache uv run operator watch last --once --json
UV_CACHE_DIR=/tmp/uv-cache uv run operator debug inspect last --json --full
```

If one surface lags or disagrees, record that as a failed or blocked visibility row rather than
folding it into a generic smoke result.

## Operator-on-Operator Rows

These rows are pytest-backed because that is the current repository truth for live smoke evidence.

### Minimal live prerequisites

- Codex OAuth available through `oauth_cli_kit`
- required opt-in environment variables set to `1`
- local ACP executables available
- network access and provider access available

### Commands

```sh
OPERATOR_RUN_CODEX_ACP_LIVE=1 \
UV_CACHE_DIR=/tmp/uv-cache \
uv run pytest -q -rs tests/test_live_codex_acp.py

OPERATOR_RUN_CODEX_CONTINUATION_SMOKE=1 \
UV_CACHE_DIR=/tmp/uv-cache \
uv run pytest -q -rs tests/test_live_codex_continuation.py

OPERATOR_RUN_MIXED_CODE_AGENT_SMOKE=1 \
UV_CACHE_DIR=/tmp/uv-cache \
uv run pytest -q -rs tests/test_live_mixed_code_agent_selection.py
```

Record the skip reason verbatim if any row skips. Skips do not count toward e2e closure.

## External Project Baseline

This is the required fresh v2 baseline run against the real external project:

```sh
cd ../erdosreshala/problems/625
env OPERATOR_CODEX_ACP__COMMAND='npx @zed-industries/codex-acp --' \
    OPERATOR_CODEX_ACP__MODEL='gpt-5.4' \
    OPERATOR_CODEX_ACP__EFFORT='low' \
    UV_CACHE_DIR=/tmp/uv-cache \
    uv run operator run --v2 --mode attached --agent codex_acp --max-iterations 100 \
    "Inspect problem/problem.md, solution/proof.md, and solution/verification/formalization-status.md. \
Summarize the current proof state and propose the next strongest honest route toward a full proof of problem 625."
```

After the run, record:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator status last --json
UV_CACHE_DIR=/tmp/uv-cache uv run operator inspect last --json
UV_CACHE_DIR=/tmp/uv-cache uv run operator list --json
```

The evidence note must include the emitted operation id.

## External Project Permission Slice

`ADR 0202` needs one real run against `../erdosreshala/problems/625` that exercises a permission
decision path. The objective must require at least one bounded action that is likely to trigger a
permission decision inside the problem subtree.

Use this prompt shape:

```sh
cd ../erdosreshala/problems/625
env OPERATOR_CODEX_ACP__COMMAND='npx @zed-industries/codex-acp --' \
    OPERATOR_CODEX_ACP__MODEL='gpt-5.4' \
    OPERATOR_CODEX_ACP__EFFORT='low' \
    UV_CACHE_DIR=/tmp/uv-cache \
    uv run operator run --v2 --mode attached --agent codex_acp --max-iterations 100 \
    "Inspect problem/problem.md, solution/proof.md, and solution/verification/formalization-status.md. \
If you find a real mismatch, make one bounded fix inside this problem subtree and explain it; otherwise explain why no fix was needed."
```

This run is not complete evidence for `ADR 0202` unless the evidence note records which of these
actually happened:

- permission approved
- permission rejected with follow-up-required behavior
- permission escalated to human
- no permission event observed

If no permission event is observed, record that result explicitly and run a second bounded prompt
that requires one repo-local write inside the problem subtree.

## Restart / Resume / Cancel Follow-up

For any live external-project operation chosen as the evidence anchor, also record at least one of:

- attached-mode completion without manual resume
- interrupt followed by `resume`
- `cancel` on the live v2 operation

Use the same operation id in the evidence note.

## Failure Handling

If a live row hangs or fails:

1. record the exact command
2. record how long it ran before you stopped waiting
3. capture a process snapshot or terminal output
4. classify the row as `failed` or `blocked`
5. add a short autopsy to the evidence note

Do not upgrade the row to passed based on a partial trace.

## Promotion Rules

- `ADR 0211` is not `Verified` until this procedure has been used for:
  - one fresh operator-on-operator live run; recorded on 2026-05-03 in
    `design/internal/v2-verification-evidence-2026-05-03-operator-on-operator-smoke.md`
  - one fresh external-project run against `../erdosreshala/problems/625`
- `ADR 0202` is not `Verified` until the external-project evidence includes a real permission path
- `ADR 0205` may use the targeted local rows plus broader v2 evidence, but it still should not be
  promoted beyond repository truth if the live command/control path remains unproven in e2e
