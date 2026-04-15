# ADR 0146: MCP server surface and tool contract

- Date: 2026-04-12

## Decision Status

Accepted

## Implementation Status

Verified

## Context

`AGENT-INTEGRATION-VISION.md` identifies an MCP server (stdio transport) as the #3 priority
integration surface and the highest-leverage missing surface for the primary target audience:
Claude Code and Codex. Both natively understand MCP and can call MCP tools without subprocess
orchestration.

Before this closure wave, the repository had no committed MCP contract reference and no accepted
ADR grounding the inbound tool surface. Local implementation work existed, but the closure criteria
were not yet anchored to exact files, exact symbols, exact tests, and committed docs.

## Decision

`operator` exposes an inbound MCP server via `operator mcp` over stdio transport.

The initial published tool set contains exactly these six tools:

- `list_operations`
- `run_operation`
- `get_status`
- `answer_attention`
- `cancel_operation`
- `interrupt_operation`

Tool names and published parameter names are stable once published. Adding optional fields is
non-breaking. Removing or renaming a tool, a required parameter, or a committed response field is
a breaking change and requires deprecation handling consistent with ADR 0145.

The committed contract reference is `design/reference/mcp-tool-schemas.md`.

## Closure Criteria And Evidence

### 1. `operator mcp` exists as a stdio MCP entry point

Evidence:

- CLI registration: `src/agent_operator/cli/app.py`
- Command module: `src/agent_operator/cli/commands/mcp.py:mcp`
- Server boundary: `src/agent_operator/mcp/server.py:OperatorMcpServer.serve`
- Verification: `tests/test_mcp_server.py:test_mcp_server_handles_initialize_and_tools_list`

### 2. The server publishes exactly the six committed tools

Evidence:

- Tool registry: `src/agent_operator/mcp/server.py:TOOL_DEFINITIONS`
- Tool handlers: `src/agent_operator/mcp/server.py:OperatorMcpServer._call_tool`
- Service façade: `src/agent_operator/mcp/service.py:OperatorMcpService`
- Verification: `tests/test_mcp_server.py:test_mcp_server_handles_initialize_and_tools_list`

### 3. Tool parameter schemas are explicit, strict, and committed

Evidence:

- Input models:
  `src/agent_operator/mcp/contracts.py:ListOperationsParams`
  `src/agent_operator/mcp/contracts.py:RunOperationParams`
  `src/agent_operator/mcp/contracts.py:GetStatusParams`
  `src/agent_operator/mcp/contracts.py:AnswerAttentionParams`
  `src/agent_operator/mcp/contracts.py:CancelOperationParams`
  `src/agent_operator/mcp/contracts.py:InterruptOperationParams`
- Published JSON Schema generation:
  `src/agent_operator/mcp/server.py:McpToolDefinition.payload`
- Committed schema reference: `design/reference/mcp-tool-schemas.md`
- Verification:
  `tests/test_mcp_server.py:test_mcp_server_handles_initialize_and_tools_list`

### 4. Tool failures return structured MCP errors

Evidence:

- Structured tool error type: `src/agent_operator/mcp/service.py:McpToolError`
- JSON-RPC error mapping: `src/agent_operator/mcp/server.py:OperatorMcpServer._tool_error`
- Validation and unexpected-failure guards:
  `src/agent_operator/mcp/server.py:OperatorMcpServer._dispatch`
- Verification:
  `tests/test_mcp_server.py:test_mcp_server_returns_structured_tool_error`

### 5. The six-tool surface is wired to the existing operator runtime and query layer

Evidence:

- Service constructor:
  `src/agent_operator/mcp/service.py:build_operator_mcp_service`
- Runtime delegation:
  `src/agent_operator/mcp/service.py:OperatorMcpService.run_operation`
  `src/agent_operator/mcp/service.py:OperatorMcpService.get_status`
  `src/agent_operator/mcp/service.py:OperatorMcpService.answer_attention`
  `src/agent_operator/mcp/service.py:OperatorMcpService.cancel_operation`
  `src/agent_operator/mcp/service.py:OperatorMcpService.interrupt_operation`
- Verification:
  `tests/test_mcp_server.py:test_operator_mcp_service_lists_and_reports_status`
  `tests/test_mcp_server.py:test_operator_mcp_service_answer_cancel_interrupt_and_timeout_validation`

### 6. Claude Code configuration and MCP contract docs are committed

Evidence:

- User-facing entry snippet: `README.md`
- Integration index: `docs/integrations.md`
- CLI reference entry: `docs/reference/cli.md`
- Design authority alignment: `design/AGENT-INTEGRATION-VISION.md`
- Contract reference: `design/reference/mcp-tool-schemas.md`

### 7. Repository planning artifacts no longer describe the MCP command as open CLI work

Evidence:

- CLI design entry: `design/CLI-UX-VISION.md`

## Consequences

- Claude Code and Codex users can configure `operator` as an MCP server with a single stdio
  configuration snippet.
- The six-tool surface covers the basic supervise, inspect, answer, interrupt, and cancel loop
  without shell subprocess scraping.
- The committed schema reference and tests, not ad hoc examples, are the stability anchor for the
  inbound MCP contract.

## Verification

Local verification for this ADR was completed with:

- `uv run pytest tests/test_mcp_server.py`
- `uv run pytest`

Recorded on 2026-04-15:

- `uv run pytest tests/test_mcp_server.py` -> passed
- `uv run pytest` -> passed (`738 passed, 11 skipped`)

## Related

- [AGENT-INTEGRATION-VISION.md](../AGENT-INTEGRATION-VISION.md)
- [ADR 0145](./0145-cli-output-format-and-agent-integration-stability-contract.md)
- [CLI-UX-VISION.md](../CLI-UX-VISION.md)
