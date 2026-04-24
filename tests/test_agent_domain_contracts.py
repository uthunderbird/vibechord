from datetime import UTC, datetime

from agent_operator.domain import (
    AgentArtifact,
    AgentProgress,
    AgentProgressState,
    AgentResult,
    AgentResultStatus,
    AgentUsage,
)


def test_agent_progress_exposes_minimal_core_and_optional_extensions() -> None:
    updated_at = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)

    progress = AgentProgress(
        session_id="sess-1",
        state=AgentProgressState.WAITING_INPUT,
        message="Waiting for approval.",
        updated_at=updated_at,
        progress_text="Blocked on permission request.",
        partial_output="Draft patch prepared.",
        usage=AgentUsage(
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            context_window_size=200_000,
            context_tokens_used=1_234,
            cost_amount=0.42,
            cost_currency="USD",
            metadata={"provider": "acp"},
        ),
        artifacts=[
            AgentArtifact(
                name="plan.md",
                kind="file",
                uri="file:///tmp/plan.md",
                metadata={"role": "draft"},
            )
        ],
        raw={"vendor_state": "needs_approval"},
    )

    assert progress.session_id == "sess-1"
    assert progress.state is AgentProgressState.WAITING_INPUT
    assert progress.message == "Waiting for approval."
    assert progress.updated_at == updated_at
    assert progress.progress_text == "Blocked on permission request."
    assert progress.partial_output == "Draft patch prepared."
    assert progress.usage is not None
    assert progress.usage.total_tokens == 30
    assert progress.artifacts[0].name == "plan.md"
    assert progress.raw == {"vendor_state": "needs_approval"}


def test_agent_result_exposes_minimal_core_and_optional_extensions() -> None:
    completed_at = datetime(2026, 4, 24, 12, 5, tzinfo=UTC)

    result = AgentResult(
        session_id="sess-1",
        status=AgentResultStatus.SUCCESS,
        output_text="Applied patch successfully.",
        artifacts=[
            AgentArtifact(
                name="diff.txt",
                kind="report",
                content="patch summary",
            )
        ],
        completed_at=completed_at,
        structured_output={"changed_files": ["src/app.py"]},
        usage=AgentUsage(
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
        ),
        transcript="assistant: Applied patch successfully.",
        raw={"vendor_stop_reason": "end_turn"},
    )

    assert result.session_id == "sess-1"
    assert result.status is AgentResultStatus.SUCCESS
    assert result.output_text == "Applied patch successfully."
    assert result.artifacts[0].name == "diff.txt"
    assert result.error is None
    assert result.completed_at == completed_at
    assert result.structured_output == {"changed_files": ["src/app.py"]}
    assert result.usage is not None
    assert result.usage.total_tokens == 30
    assert result.transcript == "assistant: Applied patch successfully."
    assert result.raw == {"vendor_stop_reason": "end_turn"}
