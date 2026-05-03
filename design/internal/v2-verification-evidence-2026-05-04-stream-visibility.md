# v2 Verification Evidence Note

- Date: 2026-05-04
- Repository HEAD before fix: `0da8c20374f81ea54d355980d28fc8071dafa886`
- Worktree state: dirty with the stream-visibility bug fix, regression test, and local transient
  `operator-history.jsonl`
- Matrix row: stream/TUI visibility smoke
- Result: `passed`

## Environment Assumptions

- `uv` available: yes
- ACP executable/provider access: not required for this replay/read row
- Network access: not required for this replay/read row
- Target workspace: `/Users/thunderbird/Projects/erdosreshala/problems/625`
- Target operation: `9dae40c7-b49c-4e54-a184-4094d0c827c2`

## Commands

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check \
  src/agent_operator/cli/workflows/control_runtime.py tests/test_cli.py

UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q \
  tests/test_cli.py::test_watch_once_json_includes_canonical_latest_turn_without_trace_brief \
  tests/test_cli.py::test_watch_once_emits_single_snapshot_and_exits \
  tests/test_operation_status_queries.py::test_status_payload_falls_back_to_canonical_latest_turn_when_trace_brief_is_missing

OPERATOR_DATA_DIR=/Users/thunderbird/Projects/erdosreshala/problems/625/.operator \
UV_CACHE_DIR=/tmp/uv-cache \
uv run operator watch 9dae40c7-b49c-4e54-a184-4094d0c827c2 --once --json
```

## Evidence

- Regression test:
  `tests/test_cli.py::test_watch_once_json_includes_canonical_latest_turn_without_trace_brief`
  catches the mutation where `watch --once --json` discards the trace brief produced by canonical
  latest-turn fallback.
- Targeted verification passed: `ruff check` returned `All checks passed!`; the three targeted
  pytest cases returned `3 passed`.
- Live replay/read verification passed against the external operation:
  `operator watch 9dae40c7-b49c-4e54-a184-4094d0c827c2 --once --json` emitted canonical events
  through `operation.status.changed` and its final JSON snapshot included
  `latest_turn.status: completed`, `latest_turn.agent_key: codex_acp`, and
  `latest_turn.session_id: 019def4a-5f1c-7f40-971b-274e151d7e64`.
- The same final JSON snapshot reported `status: completed`, matching the earlier `status --json`
  evidence for the permission-slice operation.

## Failure Or Blocker Notes

- No stream/TUI visibility blocker remains for ADR 0211 after this row.
- This row does not strengthen ADR 0202 permission-policy verification; the permission slice still
  observed no permission event.

## Autopsy

- What was broken: `watch --once --json` loaded the enriched status payload but discarded
  `brief` and `runtime_alert` before building the public live snapshot, so canonical latest-turn
  fallback was visible in `status --json` but missing from watch JSON.
- Why it was not caught earlier: existing watch tests checked terminal status and canonical event
  source selection, but not projection parity for `latest_turn` when legacy trace briefs are absent.
- Category: contract drift.
- Preventive mechanism: keep a CLI regression that seeds only canonical v2 events and asserts that
  watch JSON exposes the same latest-turn summary path as status JSON.
