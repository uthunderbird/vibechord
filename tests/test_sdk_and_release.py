from __future__ import annotations

from pathlib import Path

from vibechord import VibechordClient
from vibechord.release_checks import HARNESS_WORKFLOWS, run_release_checks


def test_sdk_uses_shared_operation_contracts(tmp_path: Path) -> None:
    client = VibechordClient(tmp_path)

    result = client.run("sdk goal")

    assert result.accepted is True
    assert result.operation_id is not None
    status = client.status(result.operation_id)
    assert status.status == "completed"
    assert status.goal == "sdk goal"
    assert client.fleet()[0].operation_id == result.operation_id
    assert client.live(result.operation_id)[-1].payload_kind == "operation.completed"


def test_sdk_live_message_uses_command_authority(tmp_path: Path) -> None:
    client = VibechordClient(tmp_path)
    result = client.run("sdk chat")
    assert result.operation_id is not None

    message = client.message(result.operation_id, "hello")

    assert message.accepted is True
    status = client.status(result.operation_id)
    assert status.recent_messages == ("hello",)


def test_release_checks_run_fake_harnesses_and_docs_audit() -> None:
    root = Path(__file__).resolve().parents[1]

    result = run_release_checks(root)

    assert result.passed is True
    harness_summaries = list((root / ".vibechord-harness").glob("*/summary.json"))
    assert len(harness_summaries) >= len(HARNESS_WORKFLOWS)
