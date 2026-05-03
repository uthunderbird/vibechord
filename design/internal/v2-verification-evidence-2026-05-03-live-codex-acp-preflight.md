# v2 Verification Evidence Note: Live Codex ACP Preflight

- Date: 2026-05-03
- Repository HEAD: `493272696cdf353b9f8926bbece58134aede86eb`
- Worktree state: clean before the live preflight attempts
- Matrix row: live Codex ACP roundtrip
- Result: `blocked`

## Environment Assumptions

- `uv` available: yes, `/opt/homebrew/bin/uv`
- `npx` available: yes, `/Users/thunderbird/.local/share/mise/installs/npm/11.10.0/bin/npx`
- `claude` available: yes, `/Users/thunderbird/.local/bin/claude`
- ACP executable/provider access: blocked before ACP initialize
- Network access: blocked for npm registry lookup in this execution environment
- Target workspace: `/Users/thunderbird/Projects/operator`

## Command

```sh
OPERATOR_RUN_CODEX_ACP_LIVE=1 \
OPERATOR_CODEX_ACP_MODEL=gpt-5.4 \
OPERATOR_CODEX_ACP_REASONING_EFFORT=low \
UV_CACHE_DIR=/tmp/uv-cache \
uv run pytest -q -rs tests/test_live_codex_acp.py
```

Second attempt with the canonical trailing `--` command shape:

```sh
OPERATOR_RUN_CODEX_ACP_LIVE=1 \
OPERATOR_CODEX_ACP_LIVE_COMMAND='npx @zed-industries/codex-acp --' \
OPERATOR_CODEX_ACP_MODEL=gpt-5.4 \
OPERATOR_CODEX_ACP_REASONING_EFFORT=low \
UV_CACHE_DIR=/tmp/uv-cache \
uv run pytest -q -rs tests/test_live_codex_acp.py
```

Diagnostic command:

```sh
npx @zed-industries/codex-acp --help
```

## Operation Context

- Operation id: not created
- Target workspace revision: not applicable
- Reused `.operator/` state: not applicable

## Evidence

- Status / outcome: both pytest attempts failed before an ACP session handle was initialized
- Watch / stream signal: not applicable; no operation was created
- Inspect / forensic signal: not applicable; no operation was created
- Transcript / log signal: not applicable; no Codex ACP session was established
- Permission-path outcome: not exercised
- No-`.operator/runs` observation: not exercised

Observed pytest failure:

```text
agent_operator.acp.client.AcpProtocolError:
ACP subprocess closed before completing all pending requests.
```

Observed diagnostic failure:

```text
npm error code ENOTFOUND
npm error network request to https://registry.npmjs.org/@zed-industries%2fcodex-acp failed,
reason: getaddrinfo ENOTFOUND registry.npmjs.org
```

## Failure Or Blocker Notes

- This row is blocked by live ACP subprocess startup in the current environment.
- The canonical trailing `--` command shape did not resolve the blocker.
- Follow-up on 2026-05-03 changed `tests/test_live_codex_acp.py` to run a bounded readiness check
  before opening the ACP JSON-RPC session. With the same blocked environment, the live row now
  reports:

  ```text
  SKIPPED [1] tests/test_live_codex_acp.py:41:
  codex ACP readiness check timed out: npx @zed-industries/codex-acp --help
  ```

- Because no operation id was created, this evidence does not exercise stream/TUI visibility,
  restart/resume, permission, external-project, or no-`.operator/runs` dependency rows.

## Autopsy

- What was broken: the live Codex ACP preflight could not initialize the ACP subprocess.
- Why it was not caught earlier: skipped live tests do not exercise provider subprocess startup,
  and the environment lacked npm registry resolution during diagnostic execution.
- Category: unchecked external response.
- Preventive mechanism: keep blocked live-preflight evidence explicit in ADR 0211 and keep the live
  test readiness guard so unavailable ACP executables are reported as bounded skips before the
  adapter opens a JSON-RPC session.
