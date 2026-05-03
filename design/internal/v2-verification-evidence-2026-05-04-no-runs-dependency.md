# v2 Verification Evidence Note

- Date: 2026-05-04
- Repository HEAD: `705e4eef063c9ffd62b513d7644ebe420e521c2f`
- Worktree state: dirty only with local transient `operator-history.jsonl` before this evidence note
- Matrix row: no `.operator/runs` dependency
- Result: `passed`

## Environment Assumptions

- `uv` available: yes
- `npx` available: not required for this replay/read row
- ACP executable/provider access: not required for this replay/read row
- Network access: not required for this replay/read row
- Target workspace: `/Users/thunderbird/Projects/erdosreshala/problems/625`

## Command

```sh
find .operator/runs -maxdepth 1 -print
find .operator/runs -maxdepth 2 -type f -name '*9dae40c7*' -print
UV_CACHE_DIR=/tmp/uv-cache uv run operator status 9dae40c7-b49c-4e54-a184-4094d0c827c2 --json
UV_CACHE_DIR=/tmp/uv-cache uv run operator debug inspect 9dae40c7-b49c-4e54-a184-4094d0c827c2 --json --full
UV_CACHE_DIR=/tmp/uv-cache uv run operator list --json
```

## Operation Context

- Operation id: `9dae40c7-b49c-4e54-a184-4094d0c827c2`
- Target workspace revision: `acd8b4940d38a512e31e1eb3342e0bed5a318392`
- Reused `.operator/` state: yes, but no per-operation `.operator/runs` snapshot existed for the
  tested operation.

## Evidence

- Status / outcome: `operator status 9dae40c7-b49c-4e54-a184-4094d0c827c2 --json` returned
  `status: completed`, `source: event_sourced`, `task_counts.completed: 1`, `latest_turn.status:
  completed`, and `sync_alert: null`.
- Watch / stream signal: not repeated for this row; previous permission-slice watch for the same
  operation emitted canonical events through `operation.status.changed`.
- Inspect / forensic signal:
  `operator debug inspect 9dae40c7-b49c-4e54-a184-4094d0c827c2 --json --full` replayed the
  operation from canonical v2 event/checkpoint truth and showed events through
  `operation.status.changed`.
- Transcript / log signal: not required for this replay/read row; transcript evidence is recorded
  in `design/internal/v2-verification-evidence-2026-05-04-permission-slice.md`.
- Permission-path outcome: not applicable to this replay/read row.
- No-`.operator/runs` observation: `find .operator/runs -maxdepth 1 -print` printed only
  `.operator/runs`, and `find .operator/runs -maxdepth 2 -type f -name '*9dae40c7*' -print`
  printed no files. `operator list --json` still listed
  `9dae40c7-b49c-4e54-a184-4094d0c827c2` as `completed`.

## Failure Or Blocker Notes

- None for the no-`.operator/runs` dependency row.
- An earlier shell glob check using `.operator/runs/*` hit zsh `nomatch`; the recorded evidence
  uses `find` instead.

## Autopsy

- What was broken: nothing terminal in this row.
- Why it was not caught earlier: prior live rows reused a target workspace with an existing
  `.operator/runs` directory but did not explicitly prove the tested operation lacked a legacy run
  snapshot.
- Category: not applicable.
- Preventive mechanism: keep outcome-based evidence that public read surfaces resolve a concrete
  v2 operation when no matching `.operator/runs` snapshot exists.
