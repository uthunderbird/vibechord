# v2 Verification Evidence Note

- Date: 2026-05-04
- Repository HEAD: `e889eb98ade717bb22f1d6c25979964e74799885`
- Worktree state: dirty only with local transient `operator-history.jsonl` before this evidence note
- Matrix row: external project smoke against `../erdosreshala/problems/625`
- Result: `passed`

## Environment Assumptions

- `uv` available: yes
- `npx` available: yes, but this run used direct `codex-acp`
- ACP executable/provider access: yes; direct `codex-acp` launched Codex successfully
- Network access: escalated live ACP/provider access was available
- Target workspace: `/Users/thunderbird/Projects/erdosreshala/problems/625`

## Command

```sh
OPERATOR_CODEX_ACP__COMMAND=codex-acp \
OPERATOR_CODEX_ACP__MODEL=gpt-5.4 \
OPERATOR_CODEX_ACP__EFFORT=low \
UV_CACHE_DIR=/tmp/uv-cache \
uv run operator run --v2 --mode attached --agent codex_acp --max-iterations 30 \
"Inspect problem/problem.md, solution/proof.md, and solution/verification/formalization-status.md. Summarize the current proof state and propose the next strongest honest route toward a full proof of problem 625. Use read-only commands only."
```

## Operation Context

- Operation id: `b77cfdca-6991-4869-af9d-5c71100be3fc`
- Codex session id: `019def38-b6ce-79c2-a26e-f9ae9945cec9`
- Target workspace revision: `acd8b4940d38a512e31e1eb3342e0bed5a318392`
- Reused `.operator/` state: yes; the target workspace already had `.operator/` and legacy
  `.operator/runs/` state, so this row does not prove no-`.operator/runs` independence.

## Evidence

- Status / outcome: `operator status b77cfdca-6991-4869-af9d-5c71100be3fc --json` returned
  `status: completed`, `source: event_sourced`, `task_counts.completed: 1`, `latest_turn.status:
  completed`, and `sync_alert: null`.
- Watch / stream signal: `operator watch b77cfdca-6991-4869-af9d-5c71100be3fc --once --json`
  emitted canonical events through `operation.status.changed` and reported `status: completed`.
  As in the operator-on-operator row, the JSON snapshot left `latest_turn` as `null` while
  `status --json` populated it.
- Inspect / forensic signal:
  `operator debug inspect b77cfdca-6991-4869-af9d-5c71100be3fc --json --full` showed
  `operation.created`, `brain.decision.made`, `operation.focus.updated`, `session.created`,
  `agent.turn.completed`, `session.observed_state.changed`, and `operation.status.changed`.
- Transcript / log signal:
  `operator log b77cfdca-6991-4869-af9d-5c71100be3fc --agent codex --json --limit 20` resolved the
  Codex transcript at
  `/Users/thunderbird/.codex/sessions/2026/05/04/rollout-2026-05-04T00-02-44-019def38-b6ce-79c2-a26e-f9ae9945cec9.jsonl`.
  The transcript recorded `approval=on-request`, `sandbox=workspace-write`, `model=gpt-5.4`, the
  explicit `/swarm` fallback check, read-only inspection commands, and the final proof-state route
  recommendation.
- Permission-path outcome: no permission event was observed; the prompt used read-only commands.
- No-`.operator/runs` observation: not exercised by this row.

## Failure Or Blocker Notes

- The row initially looked stuck because status showed `running_without_active_session` while the
  attached run was still draining a large stream of ACP notifications. It eventually wrote
  `agent.turn.completed`, `session.observed_state.changed`, and `operation.status.changed`.
- The target ACP raw log `.operator/acp/codex_acp/proof-state-scan.jsonl` grew to about 2.1 GB for
  this one bounded read-only run. This is an operational evidence/storage problem, not a failure of
  the external smoke outcome.
- The external workspace had pre-existing dirty state unrelated to this verification row; the
  worker reported no files modified by the read-only task, but `operator-history.jsonl` changed as a
  run ledger.

## Autopsy

- What was broken: no terminal failure occurred in this row, but the live evidence path exposed
  excessive ACP raw-log growth and repeated the `watch --once --json` latest-turn omission.
- Why it was not caught earlier: earlier evidence used smaller operator-on-operator prompts and did
  not run a real external workspace with a long profile harness plus verbose ACP token streaming.
- Category: leaked resource; stale cache/state.
- Preventive mechanism: add bounded ACP raw-log retention/truncation and align watch snapshot
  assembly with the same latest-turn projection used by status.
