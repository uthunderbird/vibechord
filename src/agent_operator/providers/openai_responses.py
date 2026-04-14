from __future__ import annotations

from typing import Any, cast

import httpx

from agent_operator.domain import AgentResult, OperationGoal, OperationState
from agent_operator.dtos import (
    FILE_TOOL_LIST_DIR,
    FILE_TOOL_NAMES,
    FILE_TOOL_READ_FILE,
    FILE_TOOL_SEARCH_TEXT,
    AgentTurnSummaryDTO,
    ArtifactNormalizationDTO,
    ConverseTurnDTO,
    DecisionStep,
    EvaluationDTO,
    FileContextStep,
    FileToolCallStep,
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


class OpenAIResponsesStructuredOutputProvider:
    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
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

    async def converse(self, prompt: str) -> ConverseTurnDTO:
        payload = await self._request_structured_output(
            schema_name="converse_turn",
            schema=build_strict_json_schema(ConverseTurnDTO.model_json_schema()),
            prompt=prompt,
        )
        return ConverseTurnDTO.model_validate(payload)

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

    async def decide_with_file_context(self, state: OperationState) -> FileContextStep:
        """One LLM round-trip with file tools enabled.

        Returns FileToolCallStep if the model wants to read a file, or DecisionStep
        if the model has produced a final structured decision. The service is responsible
        for running the loop, executing file reads, emitting events, and persisting memory.

        Falls back to a plain decide_next_action call if the API response cannot be
        parsed as a tool call (e.g. the endpoint does not support tools + json_schema).
        """
        url = f"{self._base_url}/responses"
        body = {
            "model": self._model,
            "input": build_decision_prompt(state),
            "tools": _FILE_TOOLS,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "brain_decision",
                    "schema": build_strict_json_schema(StructuredDecisionDTO.model_json_schema()),
                    "strict": True,
                }
            },
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self._httpx_timeout) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
        raw = response.json()

        tool_call = _extract_tool_call(raw)
        if tool_call is not None:
            tool_name, arguments = tool_call
            if tool_name in FILE_TOOL_NAMES:
                return FileToolCallStep(tool_name=tool_name, arguments=arguments)

        # No tool call — extract structured decision as usual
        try:
            payload = _extract_response_json(raw)
        except RuntimeError:
            # Fallback: re-request without tools
            payload = await self._request_structured_output(
                schema_name="brain_decision",
                schema=build_strict_json_schema(StructuredDecisionDTO.model_json_schema()),
                prompt=build_decision_prompt(state),
            )
        return DecisionStep(dto=StructuredDecisionDTO.model_validate(payload))

    async def _request_structured_output(
        self,
        *,
        schema_name: str,
        schema: dict[str, Any],
        prompt: str,
    ) -> dict[str, Any]:
        url = f"{self._base_url}/responses"
        body = {
            "model": self._model,
            "input": prompt,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": schema,
                    "strict": True,
                }
            },
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self._httpx_timeout) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
        return _extract_response_json(response.json())

_FILE_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": FILE_TOOL_READ_FILE,
        "description": (
            "Read the text content of a file in the project directory. "
            "Path must be relative to the project root. No write access."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file from the project root.",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": FILE_TOOL_LIST_DIR,
        "description": (
            "List the entries (files and subdirectories) in a directory. "
            "Path must be relative to the project root."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the directory from the project root.",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": FILE_TOOL_SEARCH_TEXT,
        "description": (
            "Search for a text pattern in files under a given directory. "
            "Returns matching lines with file paths. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regular expression pattern to search for.",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Relative path to the directory or file to search within. "
                        "Defaults to project root if omitted."
                    ),
                },
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def _extract_tool_call(
    payload: dict[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    """Extract a function_call from an OpenAI Responses API response, if present."""
    import json as _json

    for item in payload.get("output", []):
        if item.get("type") == "function_call":
            name = item.get("name", "")
            raw_args = item.get("arguments", "{}")
            try:
                arguments = _json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except ValueError:
                arguments = {}
            if isinstance(arguments, dict):
                return name, arguments
    return None


def _extract_response_json(payload: dict[str, Any]) -> dict[str, Any]:
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    response = httpx.Response(200, content=text.encode("utf-8"))
                    return cast(dict[str, Any], response.json())
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return cast(
            dict[str, Any],
            httpx.Response(200, content=output_text.encode("utf-8")).json(),
        )
    raise RuntimeError("Structured output response did not contain parsable JSON text.")
