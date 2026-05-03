# v2 Verification Evidence Note: Live Codex ACP Preflight

- Date: 2026-05-03
- Repository HEAD: `493272696cdf353b9f8926bbece58134aede86eb`
- Worktree state: clean before the live preflight attempts
- Matrix row: live Codex ACP preflight
- Result: `passed` after ACP close-cleanup fix

## Environment Assumptions

- `uv` available: yes, `/opt/homebrew/bin/uv`
- `npx` available: yes, `/Users/thunderbird/.local/share/mise/installs/npm/11.10.0/bin/npx`
- local `codex-acp` executable available: yes,
  `/Users/thunderbird/.local/share/mise/installs/node/24.13.1/bin/codex-acp`
- `claude` available: yes, `/Users/thunderbird/.local/bin/claude`
- ACP executable/provider access: local executable initializes and completed the split one-shot and
  follow-up reload live rows when run with escalated sandbox/network permissions
- Network access: blocked for npm registry lookup through `npx`; direct `codex-acp` required
  escalated sandbox/network permissions for live rows
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

Post-fix split live rows:

```sh
OPERATOR_RUN_CODEX_ACP_LIVE=1 \
OPERATOR_CODEX_ACP_LIVE_COMMAND=codex-acp \
OPERATOR_CODEX_ACP_MODEL=gpt-5.4 \
OPERATOR_CODEX_ACP_REASONING_EFFORT=low \
OPERATOR_CODEX_ACP_LIVE_TIMEOUT_SECONDS=30 \
UV_CACHE_DIR=/tmp/uv-cache \
uv run pytest -q -rs tests/test_live_codex_acp.py::test_codex_acp_live_one_shot
```

```sh
OPERATOR_RUN_CODEX_ACP_LIVE=1 \
OPERATOR_CODEX_ACP_LIVE_COMMAND=codex-acp \
OPERATOR_CODEX_ACP_MODEL=gpt-5.4 \
OPERATOR_CODEX_ACP_REASONING_EFFORT=low \
OPERATOR_CODEX_ACP_LIVE_TIMEOUT_SECONDS=45 \
UV_CACHE_DIR=/tmp/uv-cache \
uv run pytest -q -rs tests/test_live_codex_acp.py::test_codex_acp_live_follow_up_reload
```

## Operation Context

- Operation id: not created
- Target workspace revision: not applicable
- Reused `.operator/` state: not applicable

## Evidence

- Status / outcome: initial pytest attempts failed or hung; after the close-cleanup fix, both split
  live rows passed with direct `codex-acp`
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

Follow-up harness change:

- `tests/test_live_codex_acp.py::test_codex_acp_live_one_shot` now covers a single ACP prompt and
  collect.
- `tests/test_live_codex_acp.py::test_codex_acp_live_follow_up_reload` now covers the collected
  session reload/follow-up path separately.
- `AcpSubprocessConnection.close()` now cancels lingering stdout/stderr reader tasks after the
  process exits, preventing `collect()` from timing out after an ACP response has already arrived.

Post-fix results:

```text
tests/test_live_codex_acp.py::test_codex_acp_live_one_shot
1 passed in 7.89s
```

```text
tests/test_live_codex_acp.py::test_codex_acp_live_follow_up_reload
1 passed in 16.22s
```

## Failure Or Blocker Notes

- The initial `npx @zed-industries/codex-acp --` command shape was blocked by npm registry DNS in
  the sandboxed environment.
- A local `codex-acp` executable avoided the `npx` registry lookup blocker.
- Running direct `codex-acp` without escalation still hit environment/provider permission failures
  while creating a session.
- Escalating the direct executable row removed the immediate sandbox failure but exposed a close
  hang after the ACP response had arrived.
- The live test now has a configurable bounded timeout; the same escalated row fails in bounded
  time instead of requiring manual process cleanup if this regression returns.
- The live test has been split so one-shot success and follow-up reload success are recorded
  independently.
- Follow-up on 2026-05-03 changed `tests/test_live_codex_acp.py` to run a bounded readiness check
  before opening the ACP JSON-RPC session. With the same blocked environment, the live row now
  reports:

  ```text
  SKIPPED [1] tests/test_live_codex_acp.py:41:
  codex ACP readiness check timed out: npx @zed-industries/codex-acp --help
  ```

- Because no operation id was created, this evidence still does not exercise stream/TUI visibility,
  restart/resume, permission, external-project, or no-`.operator/runs` dependency rows.

## Autopsy

- What was broken: the live Codex ACP preflight mixed environment failures with an adapter cleanup
  bug; once direct `codex-acp` could answer, `AcpSubprocessConnection.close()` could still wait
  forever on reader tasks after the process had exited.
- Why it was not caught earlier: skipped live tests do not exercise provider subprocess startup,
  and earlier diagnostics only covered the `npx` lookup path rather than the direct local
  executable path; unit coverage did not model reader tasks that outlive process exit.
- Category: leaked resource / lifecycle cleanup.
- Preventive mechanism: keep blocked live-preflight evidence explicit in ADR 0211 and keep the live
  test readiness guard so unavailable ACP executables are reported as bounded skips before the
  adapter opens a JSON-RPC session; keep the regression test that proves `close()` cancels lingering
  reader tasks; run direct `codex-acp` live rows with explicit escalation when validating this
  provider path.
