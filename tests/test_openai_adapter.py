from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from vibechord.domain import BrainAction, OperationSnapshot, OperationStatus
from vibechord.openai_adapter import OpenAIResponsesBrain


@dataclass
class FakeTransport:
    response: dict[str, object]
    calls: list[dict[str, object]]

    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.response


def test_openai_responses_brain_maps_output_text_decision() -> None:
    transport = FakeTransport(
        response={
            "output_text": (
                '{"action":"complete","message":"done","prompt":"",'
                '"agent_name":"","agent_input":""}'
            )
        },
        calls=[],
    )
    brain = OpenAIResponsesBrain(
        api_key="key",
        model="test-model",
        base_url="https://example.test/v1",
        transport=transport,
    )

    decision = brain.decide(_snapshot())

    assert decision.action == BrainAction.COMPLETE
    assert decision.message == "done"
    call = transport.calls[0]
    assert call["url"] == "https://example.test/v1/responses"
    assert call["headers"] == {"Authorization": "Bearer key"}
    payload = _payload(call)
    assert payload["model"] == "test-model"
    text_format = _text_format(payload)
    assert text_format["type"] == "json_schema"
    assert text_format["strict"] is True


def test_openai_responses_brain_maps_nested_output_content() -> None:
    transport = FakeTransport(
        response={
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": (
                                '{"action":"request_attention","message":"",'
                                '"prompt":"approve?","agent_name":"",'
                                '"agent_input":""}'
                            ),
                        }
                    ]
                }
            ]
        },
        calls=[],
    )
    brain = OpenAIResponsesBrain(api_key="key", transport=transport)

    decision = brain.decide(_snapshot())

    assert decision.action == BrainAction.REQUEST_ATTENTION
    assert decision.prompt == "approve?"


def test_openai_responses_brain_failure_is_explicit() -> None:
    brain = OpenAIResponsesBrain(api_key="", transport=FakeTransport({}, []))

    decision = brain.decide(_snapshot())

    assert decision.action == BrainAction.FAIL
    assert decision.message == "missing OpenAI API key"


def test_openai_responses_brain_missing_decision_is_explicit() -> None:
    brain = OpenAIResponsesBrain(
        api_key="key", transport=FakeTransport({"output_text": "not-json"}, [])
    )

    decision = brain.decide(_snapshot())

    assert decision.action == BrainAction.FAIL
    assert "did not contain" in decision.message


def _snapshot() -> OperationSnapshot:
    return OperationSnapshot(
        operation_id="op-1",
        goal="openai",
        status=OperationStatus.RUNNING,
        source_sequence=1,
    )


def _payload(call: dict[str, object]) -> dict[str, Any]:
    payload = call["payload"]
    assert isinstance(payload, dict)
    return payload


def _text_format(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload["text"]
    assert isinstance(text, dict)
    text_format = text["format"]
    assert isinstance(text_format, dict)
    return text_format
