# Adapters

Status: `verified`

`vibechord` keeps provider-specific behavior outside the core operation loop.
The default local workspace wires deterministic adapters, and environment
variables can replace them with local process-backed adapters.

## Agent Process Adapter

Set `VIBECHORD_AGENT_COMMAND` to run agent invocations through a local process.
The adapter sends the agent input on stdin and maps stdout/stderr into an
`AgentResult`.

```sh
VIBECHORD_AGENT_COMMAND='python ./agent.py' uv run vibechord run "agent task"
```

## Direct Codex Exec Adapter

`CodexExecAdapter` runs one pinned Codex CLI execution through the existing
`AgentAdapter` protocol. Its configuration requires an absolute executable,
working directory, Codex home, complete environment, exact model, sandbox
network policy, and unique JSONL/final-message artifact paths.

The adapter always uses `codex exec --ephemeral --json`, disables ambient user
configuration and optional features explicitly, validates every nonblank JSONL
line, bounds retained artifacts, and requires a nonempty regular final-message
file. It does not create a process group or implement retries, resume, or ACP;
an enclosing supervisor remains responsible for whole-operation cancellation
and descendant cleanup.

`SingleAgentBrain` provides the matching deterministic operation policy: invoke
one configured adapter once, complete after one successful result, and never
wait, retry, request attention, or fan out.

## Brain Process Adapter

Set `VIBECHORD_BRAIN_COMMAND` to run operator-brain decisions through a local
process. The adapter sends an operation snapshot as JSON on stdin and expects a
JSON object on stdout:

```json
{
  "action": "complete",
  "message": "done"
}
```

Supported `action` values are the domain `BrainAction` values:

- `complete`
- `fail`
- `request_attention`
- `invoke_agent`
- `invoke_agents`
- `wait`

Invalid JSON, unknown actions, and non-zero exits become explicit failed
decisions. There is no silent fallback to the local rule brain.

For a native multi-worker operation, return `invoke_agents` with an `agents`
array. The operation loop records every `agent.invocation.started` event first,
invokes those workers concurrently through the configured agent adapter, and
then records one terminal event per worker in request order. Shared status
projections include each worker output. The event store remains the only
canonical writer; worker execution happens outside the store and is folded back
into canonical events by the driver.

```json
{
  "action": "invoke_agents",
  "message": "",
  "prompt": "",
  "agent_name": "",
  "agent_input": "",
  "agents": [
    {"agent_name": "planner", "agent_input": "draft the plan"},
    {"agent_name": "critic", "agent_input": "review the plan"}
  ]
}
```

## OpenAI Responses Brain Adapter

Set `OPENAI_API_KEY` to use the OpenAI Responses API as the operator brain. The
adapter is selected only when `VIBECHORD_BRAIN_COMMAND` is not set.

```sh
OPENAI_API_KEY='...' VIBECHORD_OPENAI_MODEL='gpt-5.4' uv run vibechord run "goal"
```

The adapter calls `POST /v1/responses` with structured JSON output configured
through `text.format.type = json_schema`. The returned JSON is mapped into the
domain `BrainDecision` shape. Missing credentials, HTTP errors, invalid JSON,
and missing decision content become explicit `fail` decisions.

## Verification

Process adapter behavior, direct Codex JSONL/final-message validation,
single-agent execution, native multi-worker decisions, and parallel fan-out are
covered by `tests/test_core.py`. OpenAI adapter DTO mapping and failure behavior
are covered by `tests/test_openai_adapter.py` without real network calls. Run
the full local gate:

```sh
uv run vibechord verify full
```
