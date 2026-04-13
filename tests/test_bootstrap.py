from __future__ import annotations

from agent_operator.bootstrap import (
    build_background_run_inspection_store,
    build_service,
)
from agent_operator.config import OperatorSettings
from agent_operator.runtime import BackgroundRunInspectionStore, InProcessAgentRunSupervisor


def test_build_service_uses_inprocess_supervisor_for_canonical_runtime() -> None:
    """The main composition root should host background work in-process.

    Examples:
        >>> service = build_service(OperatorSettings())
        >>> isinstance(
        ...     service._supervisor, InProcessAgentRunSupervisor
        ... )  # type: ignore[attr-defined]
        True
    """

    service = build_service(OperatorSettings())

    assert isinstance(
        service._supervisor, InProcessAgentRunSupervisor
    )  # type: ignore[attr-defined]
    assert (
        service._supervisor._session_registry is service._attached_session_registry
    )  # type: ignore[attr-defined]
    assert set(service._attached_session_registry.keys()) == {  # type: ignore[attr-defined]
        "claude_acp",
        "codex_acp",
        "opencode_acp",
    }


def test_build_background_run_inspection_store_is_supported_cli_surface() -> None:
    store = build_background_run_inspection_store(OperatorSettings())

    assert isinstance(store, BackgroundRunInspectionStore)
