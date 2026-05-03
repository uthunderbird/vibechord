# v2 Verification Evidence Note: Live Codex ACP Preflight

- Date: 2026-05-03
- Repository HEAD: `493272696cdf353b9f8926bbece58134aede86eb`
- Worktree state: clean before the live preflight attempts
- Matrix row: live Codex ACP roundtrip
- Result: `blocked`

## Environment Assumptions

- `uv` available: yes, `/opt/homebrew/bin/uv`
- `npx` available: yes, `/Users/thunderbird/.local/share/mise/installs/npm/11.10.0/bin/npx`
- local `codex-acp` executable available: yes,
  `/Users/thunderbird/.local/share/mise/installs/node/24.13.1/bin/codex-acp`
- `claude` available: yes, `/Users/thunderbird/.local/bin/claude`
- ACP executable/provider access: local executable initializes, but `session/new` is blocked by
  environment/provider setup
- Network access: blocked for npm registry lookup through `npx`; direct `codex-acp` also logged a
  model-refresh network failure
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

Direct executable attempt:

```sh
OPERATOR_RUN_CODEX_ACP_LIVE=1 \
OPERATOR_CODEX_ACP_LIVE_COMMAND=codex-acp \
OPERATOR_CODEX_ACP_MODEL=gpt-5.4 \
OPERATOR_CODEX_ACP_REASONING_EFFORT=low \
UV_CACHE_DIR=/tmp/uv-cache \
uv run pytest -q -rs tests/test_live_codex_acp.py
```

Escalated direct executable attempt:

```sh
OPERATOR_RUN_CODEX_ACP_LIVE=1 \
OPERATOR_CODEX_ACP_LIVE_COMMAND=codex-acp \
OPERATOR_CODEX_ACP_MODEL=gpt-5.4 \
OPERATOR_CODEX_ACP_REASONING_EFFORT=low \
UV_CACHE_DIR=/tmp/uv-cache \
uv run pytest -q -rs tests/test_live_codex_acp.py
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

Observed direct executable behavior:

```text
codex-acp --help
WARNING: proceeding, even though we could not update PATH: Operation not permitted (os error 1)
Usage: codex-acp [OPTIONS]
```

With `OPERATOR_CODEX_ACP_LIVE_COMMAND=codex-acp`, ACP `initialize` succeeded, but `session/new`
returned JSON-RPC `Internal error`. The ACP log recorded:

```text
failed to refresh available models: stream disconnected before completion:
error sending request for url (https://chatgpt.com/backend-api/codex/models?client_version=0.124.0)
Failed to create session: Operation not permitted (os error 1)
```

The same direct executable row was then rerun with escalated sandbox/network permissions. It
produced no pytest output for more than three minutes. Process inspection showed the live pytest
and a child `codex-acp` process still running, so the attempt was stopped manually:

```text
uv run pytest -q -rs tests/test_live_codex_acp.py
/Users/thunderbird/Projects/operator/.venv/bin/python3 ... pytest -q -rs tests/test_live_codex_acp.py
/Users/thunderbird/.local/share/mise/installs/node/24.13.1/.../bin/codex-acp
```

Follow-up bounded-timeout rerun:

```sh
OPERATOR_RUN_CODEX_ACP_LIVE=1 \
OPERATOR_CODEX_ACP_LIVE_COMMAND=codex-acp \
OPERATOR_CODEX_ACP_MODEL=gpt-5.4 \
OPERATOR_CODEX_ACP_REASONING_EFFORT=low \
OPERATOR_CODEX_ACP_LIVE_TIMEOUT_SECONDS=20 \
UV_CACHE_DIR=/tmp/uv-cache \
uv run pytest -q -rs tests/test_live_codex_acp.py
```

Result:

```text
1 failed in 20.63s
TimeoutError
```

Post-timeout process checks found no remaining `test_live_codex_acp.py` pytest process and no
fresh `codex-acp` child process from that attempt.

## Failure Or Blocker Notes

- This row is blocked by live ACP subprocess startup in the current environment.
- The canonical trailing `--` command shape did not resolve the blocker.
- A local `codex-acp` executable avoids the `npx` registry lookup blocker, but the live row remains
  blocked at ACP `session/new` by environment/provider permissions.
- Escalating the direct executable row removed the immediate sandbox failure but exposed a hang with
  no pytest output for more than three minutes.
- The live test now has a configurable bounded timeout; the same escalated row fails in bounded
  time instead of requiring manual process cleanup.
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

- What was broken: the live Codex ACP preflight could not create a usable ACP session in this
  environment.
- Why it was not caught earlier: skipped live tests do not exercise provider subprocess startup,
  and earlier diagnostics only covered the `npx` lookup path rather than the direct local
  executable path.
- Category: unchecked external response.
- Preventive mechanism: keep blocked live-preflight evidence explicit in ADR 0211 and keep the live
  test readiness guard so unavailable ACP executables are reported as bounded skips before the
  adapter opens a JSON-RPC session; rerun the direct executable row only in an environment where
  Codex ACP can create sessions without filesystem/provider permission errors.
