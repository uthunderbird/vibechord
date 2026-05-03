# v2 Verification Evidence Note

- Date: 2026-05-03
- Repository HEAD: `618f93966530637c1c5690913c378539a1d691ce` plus uncommitted ADR 0211
  verification fixes in this wave
- Worktree state: dirty; code fixes and this evidence note were uncommitted during the successful
  live run
- Matrix row: operator-on-operator v2 smoke
- Result: `passed`

## Environment Assumptions

- `uv` available: yes
- `npx` available: yes, but this run used direct `codex-acp`
- ACP executable/provider access: yes; direct `codex-acp` launched Codex successfully
- Network access: escalated live ACP/provider access was available
- Target workspace: `/Users/thunderbird/Projects/operator`

## Command

```sh
OPERATOR_CODEX_ACP__COMMAND=codex-acp \
OPERATOR_CODEX_ACP__MODEL=gpt-5.4 \
OPERATOR_CODEX_ACP__EFFORT=low \
UV_CACHE_DIR=/tmp/uv-cache \
uv run operator run --v2 --mode attached --agent codex_acp --max-iterations 20 \
"Inspect README.md, design/VISION.md, and design/ARCHITECTURE.md. Summarize the main architectural boundaries in 5 concise bullets. Use only read-only commands."
```

## Operation Context

- Operation id: `2d4bd45f-68fb-4709-a91c-6cb587591689`
- Codex session id: `019def2f-7fe2-7de3-b7de-6a2b94324749`
- Target workspace revision: `618f93966530637c1c5690913c378539a1d691ce` plus uncommitted fixes
- Reused `.operator/` state: existing workspace state was reused; the operation id was fresh

## Evidence

- Status / outcome: `operator status 2d4bd45f-68fb-4709-a91c-6cb587591689 --json` returned
  `status: completed`, `task_counts.completed: 1`, `latest_turn.status: completed`, and
  `sync_alert: null`.
- Watch / stream signal: `operator watch 2d4bd45f-68fb-4709-a91c-6cb587591689 --once --json`
  emitted canonical events through `operation.status.changed` and reported the operation
  `completed`. The watch JSON snapshot left `latest_turn` as `null` while `status --json` populated
  it; this is recorded as a follow-up visibility consistency gap, not as failure of the terminal
  operation outcome.
- Inspect / forensic signal:
  `operator debug inspect 2d4bd45f-68fb-4709-a91c-6cb587591689 --json --full` showed
  `agent.turn.completed` and `session.observed_state.changed` events carrying the same `task_id`,
  `session_id`, and `iteration: 0`, followed by `operation.status.changed`.
- Transcript / log signal:
  `operator log 2d4bd45f-68fb-4709-a91c-6cb587591689 --agent codex --json --limit 50` resolved the
  Codex transcript at
  `/Users/thunderbird/.codex/sessions/2026/05/03/rollout-2026-05-03T23-52-40-019def2f-7fe2-7de3-b7de-6a2b94324749.jsonl`.
  The transcript recorded `approval=on-request`, `sandbox=workspace-write`, `model=gpt-5.4`, the
  three read-only `sed` commands, and the final five-bullet architectural summary.
- Permission-path outcome: no permission event was observed; the prompt used only read-only
  commands.
- No-`.operator/runs` observation: not exercised by this row.

## Failure Or Blocker Notes

- Earlier attempt `35d4c6d2-93f7-4863-b5ec-15e901e8f9e3` reached a Codex response but crashed
  during replay-backed prompt construction because a raw string was stored in
  `SessionState.status`.
- Earlier attempt `3475b609-e7c0-46f9-8e5c-28fd71dbd378` no longer crashed after enum
  normalization, but repeatedly replanned `start_agent` after successful one-shot turns because the
  policy executor did not terminalize successful one-shot operations.
- `operator debug daemon --once` was not used as positive evidence because it swept old backlog
  operations and can pollute targeted verification.

## Autopsy

- What was broken: replay of `session.observed_state.changed` could store raw status strings in
  `SessionState.status`, and successful one-shot ACP turns did not emit `operation.status.changed`.
- Why it was not caught earlier: existing unit coverage did not serialize replayed session records
  through the prompt path after a live terminal event, and did not assert that one-shot success is a
  terminal operation transition rather than another planning input.
- Category: silent type coercion; forgotten branch/missed case.
- Preventive mechanism: keep regression tests that assert replay preserves `SessionStatus` enum
  values and that successful one-shot turns complete the operation with stable `task_id` and
  `iteration` evidence.
