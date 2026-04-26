from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from agent_operator.application.live_feed import (
    iter_live_feed,
    parse_canonical_live_feed_line,
)
from agent_operator.cli.workflows.control_runtime import _build_attention_stale_warning
from agent_operator.domain import (
    AttentionRequest,
    AttentionStatus,
    AttentionType,
    ExecutionBudget,
    InvolvementLevel,
    OperationGoal,
    OperationPolicy,
    OperationState,
    OperationStatus,
    RuntimeHints,
    StoredOperationDomainEvent,
)


def _state_settings() -> dict[str, object]:
    return {
        "policy": OperationPolicy(allowed_agents=[], involvement_level=InvolvementLevel.AUTO),
        "execution_budget": ExecutionBudget(max_iterations=10),
        "runtime_hints": RuntimeHints(operator_message_window=3, metadata={}),
    }


def test_iter_live_feed_emits_sequence_gap_warning_for_canonical_stream(tmp_path: Path) -> None:
    operation_id = "op-gap"
    path = tmp_path / f"{operation_id}.jsonl"
    path.write_text(
        "\n".join(
            [
                StoredOperationDomainEvent(
                    operation_id=operation_id,
                    sequence=1,
                    event_type="operation.created",
                    payload={"objective": "Gap test"},
                    timestamp=datetime(2026, 4, 26, 10, 0, tzinfo=UTC),
                ).model_dump_json(),
                StoredOperationDomainEvent(
                    operation_id=operation_id,
                    sequence=3,
                    event_type="operation.status.changed",
                    payload={"status": "running", "iteration": 1},
                    timestamp=datetime(2026, 4, 26, 10, 1, tzinfo=UTC),
                ).model_dump_json(),
                "",
            ]
        ),
        encoding="utf-8",
    )

    records = list(
        iter_live_feed(
            path,
            operation_id=operation_id,
            parser=parse_canonical_live_feed_line,
        )
    )

    assert [record.record_type for record in records] == ["event", "warning", "event"]
    assert records[1].warning_code == "sequence_gap"
    assert records[1].layer == "canonical"
    assert "missing sequence 2" in records[1].message


def test_build_attention_stale_warning_reports_answered_attention_still_open() -> None:
    operation = OperationState(
        operation_id="op-attention-stale",
        goal=OperationGoal(objective="Keep stale attention visible."),
        status=OperationStatus.NEEDS_HUMAN,
        attention_requests=[
            AttentionRequest(
                attention_id="att-1",
                operation_id="op-attention-stale",
                attention_type=AttentionType.QUESTION,
                title="Need branch choice",
                question="Which branch should I use?",
                status=AttentionStatus.OPEN,
                blocking=True,
            )
        ],
        **_state_settings(),
    )

    warning = _build_attention_stale_warning(operation, attention_id="att-1")

    assert warning is not None
    assert warning.layer == "overlay"
    assert warning.warning_code == "answered_attention_stale"
    assert "still appears open in status" in warning.message
