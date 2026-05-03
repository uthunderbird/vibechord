# v2 Verification Evidence Note: Full Suite Baseline

- Date: 2026-05-03
- Repository HEAD: `1228de6fec8e8f30bfe757af65099e2f7ff48a18`
- Worktree state: dirty with this evidence note, `docs/reference/v2-verification.md`,
  `design/adr/0211-v2-end-to-end-verification-matrix.md`, and
  `tests/test_v2_verification_docs.py` modified
- Matrix row: full `uv run pytest`
- Result: `passed`

## Environment Assumptions

- `uv` available: yes
- `npx` available: not required for this local row
- ACP executable/provider access: not required for this local row
- Network access: not required for this local row
- Target workspace: `/Users/thunderbird/Projects/operator`

## Command

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run pytest
```

## Operation Context

- Operation id: not applicable
- Target workspace revision: not applicable
- Reused `.operator/` state: not applicable

## Evidence

- Status / outcome: `1097 passed, 11 skipped in 48.44s`
- Watch / stream signal: not applicable to this local row
- Inspect / forensic signal: not applicable to this local row
- Transcript / log signal: not applicable to this local row
- Permission-path outcome: not applicable to this local row
- No-`.operator/runs` observation: not applicable to this local row

## Failure Or Blocker Notes

- None for the full-suite baseline row.
- This evidence does not close the live operator-on-operator, external-project, permission-path,
  restart/resume, stream/TUI visibility, or no-`.operator/runs` dependency rows.
- Because the worktree was dirty, this row is useful as current repository-wide regression
  evidence, but it is not a clean release-closure artifact.

## Autopsy

- What was broken: nothing in this matrix row.
- Why it was not caught earlier: not applicable.
- Category: not applicable.
- Preventive mechanism: keep the pinned evidence note linked from ADR 0211 and covered by static
  documentation tests.
