from __future__ import annotations

from pathlib import Path
from typing import Protocol

from agent_operator.acp.permissions import AcpPermissionRequest, PermissionEvaluationResult


class PermissionEvaluator(Protocol):
    async def evaluate(
        self,
        *,
        operation_id: str,
        working_directory: Path,
        request: AcpPermissionRequest,
    ) -> PermissionEvaluationResult: ...
