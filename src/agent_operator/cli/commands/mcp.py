from __future__ import annotations

import sys

from agent_operator.mcp.server import OperatorMcpServer
from agent_operator.mcp.service import build_operator_mcp_service

from ..app import app


@app.command()
def mcp() -> None:
    """Start the inbound operator MCP server on stdio."""
    server = OperatorMcpServer(build_operator_mcp_service())
    server.serve(sys.stdin.buffer, sys.stdout.buffer)
