from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any, cast

import httpx
from oauth_cli_kit import get_token as get_codex_token  # type: ignore[import-untyped]

from agent_operator.domain import AgentResult, OperationGoal, OperationState
from agent_operator.dtos import (
    AgentTurnSummaryDTO,
    ArtifactNormalizationDTO,
    EvaluationDTO,
    MemoryEntryDraftDTO,
    PermissionDecisionDTO,
    QuestionAnswerDTO,
    StructuredDecisionDTO,
    build_strict_json_schema,
)
from agent_operator.providers.prompting import (
    build_artifact_normalization_prompt,
    build_decision_prompt,
    build_evaluation_prompt,
    build_memory_distillation_prompt,
    build_permission_decision_prompt,
    build_question_answer_prompt,
    build_turn_summary_prompt,
)


class CodexStructuredOutputProvider:
    def __init__(
        self,
        model: str,
        base_url: str,
        originator: str = "agent_operator",
        reasoning_effort: str = "low",
        timeout_seconds: float = 60.0,
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._originator = originator
        self._reasoning_effort = reasoning_effort
        self._timeout_seconds = timeout_seconds
        # Use a long read timeout for streaming responses: some brain calls can legitimately
        # take minutes, especially when the scheduler is synthesizing large state.
        self._httpx_timeout = httpx.Timeout(
            connect=60.0,
            read=self._timeout_seconds,
            write=60.0,
            pool=60.0,
        )

    async def decide_next_action(self, state: OperationState) -> StructuredDecisionDTO:
        payload = await self._request_structured_output(
            schema_name="brain_decision",
            schema=build_strict_json_schema(StructuredDecisionDTO.model_json_schema()),
            prompt=build_decision_prompt(state),
        )
        return StructuredDecisionDTO.model_validate(payload)

    async def answer_question(self, state: OperationState, question: str) -> str:
        payload = await self._request_structured_output(
            schema_name="question_answer",
            schema=build_strict_json_schema(QuestionAnswerDTO.model_json_schema()),
            prompt=build_question_answer_prompt(state, question),
        )
        return QuestionAnswerDTO.model_validate(payload).answer.strip()

    async def evaluate_result(self, state: OperationState) -> EvaluationDTO:
        payload = await self._request_structured_output(
            schema_name="evaluation",
            schema=build_strict_json_schema(EvaluationDTO.model_json_schema()),
            prompt=build_evaluation_prompt(state),
        )
        return EvaluationDTO.model_validate(payload)

    async def summarize_agent_turn(
        self,
        state: OperationState,
        *,
        operator_instruction: str,
        result: AgentResult,
    ) -> AgentTurnSummaryDTO:
        payload = await self._request_structured_output(
            schema_name="agent_turn_summary",
            schema=build_strict_json_schema(AgentTurnSummaryDTO.model_json_schema()),
            prompt=build_turn_summary_prompt(
                state,
                operator_instruction=operator_instruction,
                result=result,
            ),
        )
        return AgentTurnSummaryDTO.model_validate(payload)

    async def normalize_artifact(
        self,
        goal: OperationGoal,
        result: AgentResult,
    ) -> ArtifactNormalizationDTO:
        payload = await self._request_structured_output(
            schema_name="artifact_normalization",
            schema=build_strict_json_schema(ArtifactNormalizationDTO.model_json_schema()),
            prompt=build_artifact_normalization_prompt(goal, result),
        )
        return ArtifactNormalizationDTO.model_validate(payload)

    async def distill_memory(
        self,
        state: OperationState,
        *,
        scope: str,
        scope_id: str,
        source_refs: list[dict[str, str]],
        instruction: str,
    ) -> MemoryEntryDraftDTO:
        payload = await self._request_structured_output(
            schema_name="memory_entry_draft",
            schema=build_strict_json_schema(MemoryEntryDraftDTO.model_json_schema()),
            prompt=build_memory_distillation_prompt(
                state,
                scope=scope,
                scope_id=scope_id,
                source_refs=source_refs,
                instruction=instruction,
            ),
        )
        return MemoryEntryDraftDTO.model_validate(payload)

    async def evaluate_permission_request(
        self,
        state: OperationState,
        *,
        request_payload: dict[str, object],
        active_policy_payload: list[dict[str, object]],
    ) -> PermissionDecisionDTO:
        payload = await self._request_structured_output(
            schema_name="permission_decision",
            schema=build_strict_json_schema(PermissionDecisionDTO.model_json_schema()),
            prompt=build_permission_decision_prompt(
                state,
                request_payload=request_payload,
                active_policy_payload=active_policy_payload,
            ),
        )
        return PermissionDecisionDTO.model_validate(payload)

    async def _request_structured_output(
        self,
        *,
        schema_name: str,
        schema: dict[str, Any],
        prompt: str,
    ) -> dict[str, Any]:
        token = await asyncio.to_thread(get_codex_token)
        headers = {
            "Authorization": f"Bearer {token.access}",
            "chatgpt-account-id": token.account_id,
            "OpenAI-Beta": "responses=experimental",
            "originator": self._originator,
            "User-Agent": "agent_operator (python)",
            "accept": "text/event-stream",
            "content-type": "application/json",
        }
        body = {
            "model": self._model,
            "store": False,
            "stream": True,
            "instructions": (
                "You are the operator brain. Return only JSON matching the provided schema."
            ),
            "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
            "text": {
                "verbosity": "medium",
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": schema,
                    "strict": True,
                },
            },
            "reasoning": {"effort": self._reasoning_effort},
        }
        async with (
            httpx.AsyncClient(timeout=self._httpx_timeout) as client,
            client.stream("POST", self._base_url, headers=headers, json=body) as response,
        ):
            if response.status_code != 200:
                text = (await response.aread()).decode("utf-8", "ignore")
                raise RuntimeError(
                    "Codex structured output request failed with "
                    f"HTTP {response.status_code}: {text}"
                )
            text = await _consume_sse_text(response)
        return cast(dict[str, Any], httpx.Response(200, content=text.encode("utf-8")).json())

async def _consume_sse_text(response: httpx.Response) -> str:
    chunks: list[str] = []
    async for event in _iter_sse(response):
        if event.get("type") == "response.output_text.delta":
            delta = event.get("delta")
            if isinstance(delta, str):
                chunks.append(delta)
    text = "".join(chunks).strip()
    if not text:
        raise RuntimeError("Codex structured output response did not contain output text.")
    return text


async def _iter_sse(response: httpx.Response) -> AsyncGenerator[dict[str, Any]]:
    buffer: list[str] = []
    async for line in response.aiter_lines():
        if line == "":
            if not buffer:
                continue
            data_lines = [item[5:].strip() for item in buffer if item.startswith("data:")]
            buffer = []
            if not data_lines:
                continue
            raw = "\n".join(data_lines).strip()
            if not raw or raw == "[DONE]":
                continue
            yield json.loads(raw)
            continue
        buffer.append(line)
