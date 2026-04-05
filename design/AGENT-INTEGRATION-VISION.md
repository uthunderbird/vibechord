# Agent Integration Vision

## Purpose

This document specifies how AI agents — Claude Code, Codex, OpenClaw, nanobot, and custom agent frameworks — integrate with `operator` as a client. It covers the priority ordering of integration surfaces, the design of each viable surface, and the forward path for surfaces that are deferred.

The audience is developers building agentic systems that need to start, supervise, and interact with operator-managed operations programmatically.

This is a design specification. Implementation details (specific library versions, MCP spec revision numbers) are noted but not adjudicated here.

---

## Design Principles

**P1 — CLI is the baseline; polish it first.**
The existing `--json` CLI surface already works for agents that execute shell commands. The highest ROI investment is making it agent-grade before building new surfaces.

**P2 — Build for the primary audience first.**
The primary audience is developers using Claude Code and Codex. MCP is native to that toolchain. The second surface is MCP, not a general-purpose REST API.

**P3 — Don't build what's free.**
The JSONL event file (`.operator/events/<op-id>.jsonl`) is already written by the operator loop. Documenting it as a public agent integration surface costs nothing and provides real-time event streaming to any agent that can `tail -f`.

**P4 — MCP over REST for local agents.**
A REST server requires a port, a running process, and authentication. Local agents (Claude Code, Codex, Python scripts) don't need this. MCP via stdio transport is the right model — the agent launches `operator mcp` as a subprocess and communicates over stdin/stdout, consistent with how operator already works.

**P5 — Stability contract from day one.**
Agent integration surfaces are public APIs. The `--json` output schema, event file schema, MCP tool signatures, and Python SDK interface all carry a stability commitment: breaking changes require a deprecation cycle.

---

## Priority Order

| # | Surface | Status | Rationale |
|---|---------|--------|-----------|
| 1 | **CLI `--json` (polished)** | Exists — needs polish | Already works; agents that run CLI commands get immediate value; polish is highest ROI per effort |
| 2 | **File-based event streaming** | Exists — needs documentation | Free win; `.operator/events/<op-id>.jsonl` is already written; agents get real-time events with zero new code |
| 3 | **MCP server (stdio transport)** | New build | Native to Claude Code + Codex toolchain; highest adoption leverage for primary audience |
| 4 | **Python SDK** | New build | Thin async wrapper over service layer; enables Python agent framework embedding without subprocess spawning |
| 5 | **REST API** | Deferred | For remote/hosted operator instances; adds port management and auth complexity not needed for local-agent use cases |
| 6 | **JSON-RPC via stdio** | Deferred | Subsumed by MCP (which uses JSON-RPC as its transport) for the primary audience |
| 7 | **A2A** | Deferred — forward-noted | Wrong fit for agent-as-client use case; right fit for `operator_acp` (operator as delegated sub-operator in a larger hierarchy) |
| 8 | **ACP** | Separate document — out of scope here | Operator-as-server surface (other operators connecting to this operator). Implementation exists in `src/agent_operator/acp/`; design belongs in `operator_acp` architecture document. |

---

## Surface 1: CLI `--json` — Polish Specification

The CLI is the baseline agent surface. An agent that executes shell commands can use operator today with zero new surfaces. The following additions make it fully agent-grade.

### Semantic Exit Codes

All commands that start, resume, or report on operation state exit with a code that reflects the operation outcome:

| Exit code | Meaning |
|-----------|---------|
| `0` | Operation completed successfully (`status=completed`) |
| `1` | Operation failed (`status=failed`) or command error |
| `2` | Operation needs human (`status=needs_human`) — blocking attention is open |
| `3` | Operation cancelled (`status=cancelled`) |
| `4` | Operator internal error (unexpected state) |

Applies to: `run`, `resume` (debug), and any command that reports terminal operation state.

### `--wait` Flag on `run`

```bash
operator run "fix auth module" --wait [--timeout 300] [--json]
```

Blocks until the operation reaches a terminal state OR a blocking attention opens. Returns with the appropriate exit code. `--timeout` in seconds (default: none — waits indefinitely).

**Documented limitation:** For operations expected to run longer than a few minutes, use the fire-and-poll pattern instead. `--wait` holds the calling process open; long operations will exhaust agent context windows.

### Fire-and-Poll Pattern (Canonical Agent Pattern)

For long-running operations, the canonical agent integration pattern is fire-and-poll:

```bash
# Start the operation, capture ID
OP=$(operator run "fix auth module" --json | jq -r .operation_id)

# Poll loop
while true; do
  STATE=$(operator status $OP --brief --json | jq -r .status)

  case "$STATE" in
    needs_human)
      ATT_ID=$(operator attention $OP --json | jq -r '.attention_requests[0].attention_id')
      QUESTION=$(operator attention $OP --json | jq -r '.attention_requests[0].question')
      # Agent decides answer based on question, then:
      operator answer $OP $ATT_ID --text "$(decide_answer "$QUESTION")"
      ;;
    completed|failed|cancelled)
      break
      ;;
  esac
  sleep 30
done
```

This pattern works today with no new code. It should be documented as the primary recommended agent integration approach.

### `--brief` Output for Status Polling

Single-line machine-readable status format for efficient polling:

```
op-abc123  RUNNING  iter=14/100  tasks=2r·3q·1b  att=[!!1]
```

Fields: operation ID, status, iteration progress, task summary, attention badge. Designed for parsing with `awk`, `cut`, or `jq -r`.

### Schema Stability Contract

The `--json` output of all commands is a public agent API surface. Stability rules:

- **Non-breaking:** adding new optional fields to any JSON payload
- **Breaking (requires deprecation cycle):** removing fields, changing field types, changing field names
- **Breaking (requires deprecation cycle):** changing `--json` output structure for any command

The full schema will be documented in `docs/AGENT-API.md` (pending — see Open Items for Implementation). Until that document exists, the `--json` output of each command serves as the de facto schema. Adding new optional fields is non-breaking; all other changes (removing fields, changing field types, changing field names, changing output structure) require a deprecation cycle.

---

## Surface 2: File-Based Event Streaming

### Path Convention

```
<data_dir>/events/<operation_id>.jsonl
```

Default location with standard project setup:

```
.operator/events/op-abc123.jsonl
```

Each line is a JSONL-encoded `RunEvent` emitted by the operator loop at every state transition.

### Agent Usage

```bash
# Follow events in real time
tail -f .operator/events/op-abc123.jsonl | jq .

# Wait for a specific event type (attention opened)
tail -f .operator/events/op-abc123.jsonl | \
  jq --unbuffered 'select(.kind == "attention_opened")'

# Wait for terminal state
tail -f .operator/events/op-abc123.jsonl | \
  jq --unbuffered 'select(.kind | test("operation_completed|operation_failed|operation_cancelled"))' | \
  head -1
```

### Why This Is Valuable

Agents get real-time event push without polling. The event stream includes: iteration completions, attention opens, agent turn progress updates, brain decisions, task status changes, stop condition fires. This is superior to polling `status --json` every 30 seconds for latency-sensitive agent loops.

### Documented Event Kinds

| Kind | When emitted |
|------|-------------|
| `iteration_started` | Operator loop begins a new iteration |
| `iteration_completed` | Operator loop iteration finishes |
| `attention_opened` | A new attention request is created |
| `attention_answered` | An attention request is answered |
| `agent_turn_started` | An agent session begins a turn |
| `agent_turn_completed` | An agent session turn finishes |
| `operation_completed` | Operation reaches `completed` state |
| `operation_failed` | Operation reaches `failed` state |
| `operation_cancelled` | Operation reaches `cancelled` state |
| `task_assigned` | A task is assigned to an agent |
| `task_completed` | A task reaches completed state |

### Public API Commitment

The event file path convention and `RunEvent` JSON schema are part of the agent integration surface. The path is stable as long as `data_dir` is stable. The event schema follows the same stability contract as `--json` output.

---

## Surface 3: MCP Server

### Entry Point

```bash
operator mcp
```

Launches an MCP server over stdio. The agent (Claude Code, Codex) launches this as a subprocess and communicates over its stdin/stdout using the MCP JSON-RPC framing. No TCP port. No server management.

### Configuration for Claude Code

```json
{
  "mcpServers": {
    "operator": {
      "command": "operator",
      "args": ["mcp"],
      "env": {
        "OPERATOR_DATA_DIR": "/path/to/project/.operator"
      }
    }
  }
}
```

For project-local configuration, `OPERATOR_DATA_DIR` can be omitted — operator discovers the data dir from the working directory using the standard git-root discovery logic.

**Combining MCP control with file-based event streaming (Surface 2):** To use file-based event streaming alongside MCP, the agent needs the event file path: `<OPERATOR_DATA_DIR>/events/<operation_id>.jsonl`. The `OPERATOR_DATA_DIR` value is set in the MCP server configuration above. Agents using the recommended Claude Code config should read `OPERATOR_DATA_DIR` from their environment to construct the event file path for a given operation ID. Example:

```python
import os
data_dir = os.environ.get("OPERATOR_DATA_DIR", ".operator")
event_file = f"{data_dir}/events/{operation_id}.jsonl"
```

### Tool Set (6 Core Tools)

| Tool | Parameters | Returns | LLM description |
|------|-----------|---------|-----------------|
| `list_operations` | `project?: string` | Array of `OperationBrief` | *List all active and recent operations. Use to understand what is currently running before starting new work.* |
| `run_operation` | `goal: string, project?: string, mode?: "background"\|"attached", agents?: string[]` | `{operation_id, status}` | *Start a new operation toward a goal. Returns an operation ID for subsequent monitoring. Use `mode="background"` (default) with the fire-and-poll pattern for long-running operations. `mode="attached"` blocks until the operation reaches a terminal state or a blocking attention opens; governed by the MCP client's tool timeout configuration.* |
| `get_status` | `operation_id: string` | `OperationBrief` + attention summary (see schema below) | *Get the current status of an operation, including any blocking attention requests that need a response.* |
| `answer_attention` | `operation_id: string, attention_id: string, text: string` | `{success: bool}` | *Answer a blocking attention request to allow the operation to continue. Use when `get_status` shows `status=needs_human`.* |
| `cancel_operation` | `operation_id: string` | `{success: bool}` | *Cancel a running operation. Use when the goal is no longer relevant or the operation should be abandoned.* |
| `interrupt_operation` | `operation_id: string, task_id?: string` | `{success: bool}` | *Interrupt the current agent turn so the operator re-evaluates next steps. Does not cancel the operation. When `task_id` is omitted, interrupts all active agent turns for the operation.* |

All `operation_id` parameters accept `last` to refer to the most recently started operation in the configured data dir.

### Agent Names

The `agents` parameter in `run_operation` accepts adapter names as configured in the active project profile. Valid values are the same as `--agent` on the CLI (e.g., `claude_acp`, `codex_acp`). Omit `agents` to use the profile's `default_agents` list. To discover what agents are configured, check `list_operations` result entries' agent fields, or read the project's `operator-profile.yaml`.

### `get_status` Return Schema (provisional)

The `get_status` tool returns a JSON object. This is the provisional schema pending `docs/AGENT-API.md`:

```json
{
  "operation_id": "op-abc123",
  "status": "running | needs_human | completed | failed | cancelled",
  "goal": "Fix auth module",
  "iteration": 14,
  "max_iterations": 100,
  "task_summary": {
    "running": 2,
    "queued": 3,
    "blocked": 1,
    "completed": 4,
    "failed": 0
  },
  "attention_requests": [
    {
      "attention_id": "att-7f2a",
      "attention_type": "policy_gap",
      "blocking": true,
      "question": "Should I commit directly to main or use a branch?"
    }
  ],
  "started_at": "2026-04-03T10:00:00Z"
}
```

Fields are stable per the schema stability contract. Additional optional fields may be added without a deprecation cycle.

### Error Handling

MCP tool errors return structured error objects:

```json
{
  "code": 2,
  "message": "Operation op-abc123 has status needs_human — answer the blocking attention before proceeding"
}
```

Error codes match CLI exit code semantics (0=completed, 1=failed, 2=needs_human, 3=cancelled, 4=internal error).

### Recommended Agent Workflow via MCP

```
1. list_operations           → see what is already running
2. run_operation(goal=...)   → start new work, get operation_id
3. get_status(op_id)         → poll until status changes
4. answer_attention(...)     → when status=needs_human
5. get_status(op_id)         → confirm operation resumed
6. repeat 3–5 until terminal state
```

---

## Surface 4: Python SDK

### Import

```python
from agent_operator.client import OperatorClient
```

### Design

Thin async wrapper over the existing service layer. Direct Python method calls — no subprocess spawning, no serialization overhead. The `OperatorClient` manages settings loading and resource lifecycle.

```python
from pathlib import Path
from agent_operator.client import OperatorClient

async def run_with_supervision(goal: str) -> str:
    async with OperatorClient(data_dir=Path(".operator")) as client:
        op_id = await client.run(goal, agents=["claude_acp"])

        async for event in client.stream_events(op_id):
            if event.kind == "attention_opened":
                attentions = await client.get_attention(op_id)
                for att in attentions:
                    answer = decide_answer(att.question, att.suggested_options)
                    await client.answer_attention(op_id, att.attention_id, answer)
            elif event.kind in ("operation_completed", "operation_failed"):
                break

        status = await client.get_status(op_id)
        return status.status.value
```

### API Surface

```python
class OperatorClient:
    async def list_operations(self, project: str | None = None) -> list[OperationSummary]: ...
    async def run(self, goal: str, *, project: str | None = None,
                  agents: list[str] | None = None,
                  mode: str = "background") -> str: ...           # returns operation_id
    async def get_status(self, operation_id: str) -> OperationBrief: ...
    async def get_attention(self, operation_id: str) -> list[AttentionRequest]: ...
    async def answer_attention(self, operation_id: str,
                               attention_id: str, text: str) -> None: ...
    async def cancel(self, operation_id: str) -> None: ...  # No confirmation prompt — SDK callers are responsible for confirming with the user before calling cancel()
    async def interrupt(self, operation_id: str,
                        task_id: str | None = None) -> None: ...
    async def stream_events(self, operation_id: str) -> AsyncIterator[RunEvent]: ...
```

`operation_id="last"` is accepted by all methods that take an operation ID.

### `stream_events` Termination Contract

The `stream_events` iterator yields events as they are written to the event file. Termination behavior:

- The iterator terminates automatically when an `operation_completed`, `operation_failed`, or `operation_cancelled` event is received and no further writes occur within a drain window (default: 1 second).
- If the operation is already in a terminal state when `stream_events` is called, the method drains the existing file and returns without hanging.
- Callers may break out of the iterator at any time.
- The iterator does not raise on file-not-found if the operation has not yet started writing events; it waits for the file to appear.

### Implementation Cost

Low. The `OperatorService` and `FileOperationStore` already implement all of this. The SDK is a thin async context manager that handles settings loading (same logic as CLI `_load_settings()`), wraps the service calls, and exposes `stream_events` via the existing JSONL event file.

---

## Surface 5: REST API (Deferred)

**When to build:** When operator has a remote or hosted deployment use case — i.e., when the agent cannot run operator as a local subprocess (sandboxed hosted agent environments, browser-accessible dashboards, multi-user team deployments).

**Design sketch when built:**
- FastAPI, async, stateless over file-backed state
- Endpoints mirror MCP tools: `GET /operations`, `POST /operations`, `GET /operations/{id}`, `POST /operations/{id}/answer`, `DELETE /operations/{id}`
- Server-Sent Events endpoint for real-time streaming: `GET /operations/{id}/events`
- Authentication: API key in header (for single-user) or JWT (for multi-user)

---

## Surface 6: JSON-RPC via stdio (Deferred)

**Why deferred:** MCP already uses JSON-RPC as its transport layer. Building a bare JSON-RPC stdio surface would duplicate MCP for the same audience. The incremental value is only for non-Claude non-Python agent builders who need a lightweight process-isolation model without MCP overhead. Revisit if that audience requests it.

---

## Surface 7: A2A — Forward Note

**Current fit:** A2A (Agent-to-Agent protocol) is designed for peer-to-peer task delegation between agents. The current use case in this document — agents calling operator as a client — is a command-and-control pattern that doesn't match A2A's peer model.

**Future fit:** `operator_acp` — operator acting as a delegated sub-operator within a larger agent hierarchy — maps directly to A2A's peer-delegation model. The ACP implementation already exists in `src/agent_operator/acp/` (`client.py`, `session_runner.py`, `permissions.py`). The next step is evaluating whether A2A is the right protocol for operator-to-operator communication in the context of the existing ACP architecture. This evaluation should happen now, not when `operator_acp` is "designed" — it is already partially implemented.

[assumption: A2A spec announced at Google I/O 2025; early stage; track for stability before committing to wire format compatibility]

---

## Surface 8: ACP — Separate Architecture Document

**Scope of this document:** This document covers integration surfaces where *other agents use operator as a client* (command-and-control pattern). ACP addresses the inverse: *operator acting as a server that other operators connect to as a sub-operator* (peer delegation pattern).

**Current status:** ACP is implemented in `src/agent_operator/acp/` (`client.py`, `session_runner.py`, `permissions.py`, `sdk_client.py`). The ACP surface is intentionally out of scope for this document — it belongs in a dedicated `operator_acp` architecture document.

**In the priority table:** ACP is not listed because it is not an agent-integration surface in the sense this document addresses. It is an operator-integration surface — the right home is a peer-delegation design document that covers operator-as-sub-operator, session handoff, and the A2A evaluation noted in Surface 7.

---

## Interaction with CLI-UX-VISION.md

The following additions to `CLI-UX-VISION.md` follow from this document:

| Addition | Section |
|----------|---------|
| Semantic exit codes table | Output Format Conventions |
| `--wait [--timeout N]` on `operator run` | `operator run` specification |
| `operator mcp` as a secondary-visible command | Secondary commands |
| Schema stability contract | Output Format Conventions |
| Fire-and-poll pattern reference | New "Agent Usage" subsection |

---

## Open Items for Implementation

- Semantic exit codes for `run`, `status`, and all terminal-state-reporting commands
- `--wait` and `--timeout` on `operator run`
- `operator mcp` command: MCP stdio server, 6 core tools, JSON-RPC framing per MCP spec
- MCP configuration snippet in README and `docs/AGENT-API.md`
- `docs/AGENT-API.md`: JSON schema documentation for all `--json` output surfaces and event file format
- Event kind enumeration: document all emitted `RunEvent.kind` values and their fields
- Python SDK: `agent_operator.client.OperatorClient` async context manager
- `stream_events` implementation: reads from `.operator/events/<op-id>.jsonl` with async file tail
- `operation_id="last"` resolution in all agent-facing surfaces
