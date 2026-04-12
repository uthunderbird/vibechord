from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any, BinaryIO, cast

import anyio
from pydantic import BaseModel, ValidationError

from .contracts import (
    AnswerAttentionParams,
    CancelOperationParams,
    GetStatusParams,
    InterruptOperationParams,
    ListOperationsParams,
    RunOperationParams,
)
from .service import McpToolError, OperatorMcpService

JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2025-03-26"


@dataclass(slots=True)
class McpToolDefinition:
    """Static description of one published MCP tool."""

    name: str
    description: str
    params_model: type[BaseModel]

    def payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": _mcp_input_schema(self.params_model.model_json_schema()),
        }


TOOL_DEFINITIONS = (
    McpToolDefinition(
        name="list_operations",
        description="List current operations, optionally filtered by status.",
        params_model=ListOperationsParams,
    ),
    McpToolDefinition(
        name="run_operation",
        description="Start a new operation and optionally wait for an outcome.",
        params_model=RunOperationParams,
    ),
    McpToolDefinition(
        name="get_status",
        description="Get the current status of one operation.",
        params_model=GetStatusParams,
    ),
    McpToolDefinition(
        name="answer_attention",
        description="Answer a blocking attention request for an operation.",
        params_model=AnswerAttentionParams,
    ),
    McpToolDefinition(
        name="cancel_operation",
        description="Cancel a running operation.",
        params_model=CancelOperationParams,
    ),
    McpToolDefinition(
        name="interrupt_operation",
        description="Interrupt the current agent turn without cancelling the operation.",
        params_model=InterruptOperationParams,
    ),
)


class OperatorMcpServer:
    """Minimal stdio MCP server for `operator`.

    Examples:
        >>> from io import BytesIO
        >>> server = OperatorMcpServer(service=None)  # doctest: +SKIP
        >>> server._encode_message({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})[:14]
        b'Content-Length'
    """

    def __init__(self, service: OperatorMcpService) -> None:
        self._service = service
        self._tools = {tool.name: tool for tool in TOOL_DEFINITIONS}

    def serve(self, stdin: BinaryIO, stdout: BinaryIO) -> None:
        """Run the server until stdin reaches EOF."""
        while True:
            message = self._read_message(stdin)
            if message is None:
                return
            response = self._dispatch(message)
            if response is not None:
                stdout.write(self._encode_message(response))
                stdout.flush()

    def _dispatch(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        request_id = message.get("id")
        if not isinstance(method, str):
            if request_id is None:
                return None
            return self._jsonrpc_error(request_id, -32600, "Invalid request.")
        if method == "notifications/initialized":
            return None
        if method == "initialize":
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": request_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "operator",
                        "version": self._server_version(),
                    },
                },
            }
        if method == "tools/list":
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": request_id,
                "result": {"tools": [tool.payload() for tool in TOOL_DEFINITIONS]},
            }
        if method == "tools/call":
            params = message.get("params")
            if not isinstance(params, dict):
                return self._jsonrpc_error(request_id, -32602, "Invalid tool call parameters.")
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(tool_name, str) or not isinstance(arguments, dict):
                return self._jsonrpc_error(request_id, -32602, "Invalid tool call parameters.")
            try:
                payload = anyio.run(self._call_tool, tool_name, arguments)
            except ValidationError:
                return self._tool_error(
                    request_id,
                    McpToolError(
                        "invalid_state",
                        "Tool arguments did not match the published schema.",
                    ),
                )
            except McpToolError as exc:
                return self._tool_error(request_id, exc)
            except Exception as exc:  # pragma: no cover - defensive server boundary
                return self._tool_error(
                    request_id,
                    McpToolError("internal_error", f"Unhandled MCP server error: {exc}"),
                )
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(payload, indent=2, ensure_ascii=False),
                        }
                    ],
                    "structuredContent": payload,
                },
            }
        if request_id is None:
            return None
        return self._jsonrpc_error(request_id, -32601, f"Method {method!r} was not found.")

    async def _call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any] | list[dict[str, object]]:
        if tool_name not in self._tools:
            raise McpToolError("internal_error", f"Unknown tool {tool_name!r}.")
        if tool_name == "list_operations":
            list_params = ListOperationsParams.model_validate(arguments)
            return await self._service.list_operations(status_filter=list_params.status_filter)
        if tool_name == "run_operation":
            run_params = RunOperationParams.model_validate(arguments)
            return await self._service.run_operation(
                goal=run_params.goal,
                agent=run_params.agent,
                wait=run_params.wait,
                timeout_seconds=run_params.timeout_seconds,
            )
        if tool_name == "get_status":
            status_params = GetStatusParams.model_validate(arguments)
            return await self._service.get_status(operation_id=status_params.operation_id)
        if tool_name == "answer_attention":
            answer_params = AnswerAttentionParams.model_validate(arguments)
            return await self._service.answer_attention(
                operation_id=answer_params.operation_id,
                attention_id=answer_params.attention_id,
                answer=answer_params.answer,
            )
        if tool_name == "cancel_operation":
            cancel_params = CancelOperationParams.model_validate(arguments)
            return await self._service.cancel_operation(
                operation_id=cancel_params.operation_id,
                reason=cancel_params.reason,
            )
        interrupt_params = InterruptOperationParams.model_validate(arguments)
        return await self._service.interrupt_operation(operation_id=interrupt_params.operation_id)

    @staticmethod
    def _read_message(stdin: BinaryIO) -> dict[str, Any] | None:
        headers: dict[str, str] = {}
        while True:
            line = stdin.readline()
            if line == b"":
                return None
            if line in {b"\r\n", b"\n"}:
                break
            decoded = line.decode("utf-8").strip()
            if ":" not in decoded:
                continue
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        content_length = headers.get("content-length")
        if content_length is None:
            return None
        body = stdin.read(int(content_length))
        if not body:
            return None
        decoded = json.loads(body.decode("utf-8"))
        return decoded if isinstance(decoded, dict) else None

    @staticmethod
    def _encode_message(message: dict[str, Any]) -> bytes:
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        return header + body

    @staticmethod
    def _jsonrpc_error(
        request_id: Any,
        code: int,
        message: str,
        data: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "error": {"code": code, "message": message},
        }
        if data is not None:
            payload["error"]["data"] = data
        return payload

    def _tool_error(self, request_id: Any, error: McpToolError) -> dict[str, Any]:
        data: dict[str, object] = {"code": error.code}
        if error.operation_id is not None:
            data["operation_id"] = error.operation_id
        return self._jsonrpc_error(request_id, -32000, error.message, data)

    @staticmethod
    def _server_version() -> str:
        try:
            return version("agent-operator")
        except PackageNotFoundError:
            return "0.1.0"


def _mcp_input_schema(schema: dict[str, Any]) -> dict[str, Any]:
    normalized = cast(dict[str, Any], _copy_json(schema))
    _strip_presentation_fields(normalized)
    if normalized.get("type") == "object":
        normalized.setdefault("additionalProperties", False)
    return normalized


def _strip_presentation_fields(schema: dict[str, Any]) -> None:
    schema.pop("title", None)
    schema.pop("default", None)
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for nested in properties.values():
            if isinstance(nested, dict):
                _strip_presentation_fields(nested)
    items = schema.get("items")
    if isinstance(items, dict):
        _strip_presentation_fields(items)


def _copy_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _copy_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy_json(item) for item in value]
    return value
