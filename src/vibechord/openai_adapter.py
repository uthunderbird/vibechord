"""OpenAI Responses API operator-brain adapter."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol, cast

from vibechord.adapters import _brain_decision_from_payload
from vibechord.domain import BrainAction, BrainDecision, OperationSnapshot
from vibechord.jsonutil import to_jsonable


class HttpTransport(Protocol):
    """HTTP transport boundary for testable vendor adapters."""

    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]:
        """Post JSON and return a decoded JSON object."""


@dataclass(frozen=True)
class UrlLibHttpTransport:
    """Stdlib HTTP transport for JSON APIs."""

    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]:
        """Post a JSON payload through urllib."""

        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={**headers, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            decoded = json.loads(response.read().decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("OpenAI response JSON must be an object")
        return cast(dict[str, object], decoded)


@dataclass(frozen=True)
class OpenAIResponsesBrain:
    """Operator brain backed by OpenAI Responses structured outputs."""

    api_key: str
    model: str = "gpt-5.4"
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: float = 30.0
    transport: HttpTransport = UrlLibHttpTransport()

    def decide(self, snapshot: OperationSnapshot) -> BrainDecision:
        """Request a structured BrainDecision from the OpenAI Responses API."""

        if not self.api_key:
            return BrainDecision(BrainAction.FAIL, message="missing OpenAI API key")
        try:
            response = self.transport.post_json(
                f"{self.base_url.rstrip('/')}/responses",
                headers={"Authorization": f"Bearer {self.api_key}"},
                payload=self._payload(snapshot),
                timeout_seconds=self.timeout_seconds,
            )
        except urllib.error.HTTPError as exc:
            return BrainDecision(
                BrainAction.FAIL,
                message=f"OpenAI HTTP error {exc.code}: {exc.reason}",
            )
        except urllib.error.URLError as exc:
            return BrainDecision(
                BrainAction.FAIL, message=f"OpenAI URL error: {exc.reason}"
            )
        except TimeoutError:
            return BrainDecision(BrainAction.FAIL, message="OpenAI request timed out")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return BrainDecision(
                BrainAction.FAIL, message=f"OpenAI adapter error: {exc}"
            )

        decision_payload = _extract_decision_payload(response)
        if decision_payload is None:
            return BrainDecision(
                BrainAction.FAIL,
                message="OpenAI response did not contain a decision object",
            )
        return _brain_decision_from_payload(decision_payload)

    def _payload(self, snapshot: OperationSnapshot) -> dict[str, object]:
        return {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _SYSTEM_INSTRUCTIONS,
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(to_jsonable(snapshot), sort_keys=True),
                        }
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "vibechord_brain_decision",
                    "strict": True,
                    "schema": _DECISION_SCHEMA,
                }
            },
        }


_SYSTEM_INSTRUCTIONS = (
    "You are the vibechord operator brain. Return only a JSON object matching "
    "the schema. Choose one action: complete, fail, request_attention, "
    "invoke_agent, invoke_agents, or wait."
)

_DECISION_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "complete",
                "fail",
                "request_attention",
                "invoke_agent",
                "invoke_agents",
                "wait",
            ],
        },
        "message": {"type": "string"},
        "prompt": {"type": "string"},
        "agent_name": {"type": "string"},
        "agent_input": {"type": "string"},
        "agents": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "agent_name": {"type": "string"},
                    "agent_input": {"type": "string"},
                },
                "required": ["agent_name", "agent_input"],
            },
        },
    },
    "required": ["action", "message", "prompt", "agent_name", "agent_input", "agents"],
}


def _extract_decision_payload(
    response: dict[str, object],
) -> dict[object, object] | None:
    output_text = response.get("output_text")
    if isinstance(output_text, str):
        return _parse_decision_text(output_text)
    output = response.get("output")
    if not isinstance(output, list):
        return None
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if isinstance(text, str):
                parsed = _parse_decision_text(text)
                if parsed is not None:
                    return parsed
    return None


def _parse_decision_text(text: str) -> dict[object, object] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None
