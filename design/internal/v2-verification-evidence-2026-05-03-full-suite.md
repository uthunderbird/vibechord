# v2 Verification Evidence Note: Full Suite Baseline

- Date: 2026-05-03
- Repository HEAD: `618f93966530637c1c5690913c378539a1d691ce`
- Worktree state: dirty with ADR 0211 replay/one-shot fixes, regression tests, and evidence
  updates
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

- Status / outcome: `1106 passed, 12 skipped in 43.09s`
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
