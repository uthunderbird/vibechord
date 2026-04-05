from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from agent_operator.domain import PermissionRequestSignature, PolicyEntry

JsonObject = dict[str, Any]


class AcpPermissionInteraction(StrEnum):
    APPROVAL = "approval"
    USER_INPUT = "user_input"


class AcpPermissionDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    WAIT_INPUT = "wait_input"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class AcpPermissionOptionView:
    option_id: str
    kind: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class AcpPermissionRequest:
    request_id: int
    adapter_key: str
    method: str
    interaction: AcpPermissionInteraction
    working_directory: Path
    session_id: str | None = None
    title: str | None = None
    command: list[str] | None = None
    tool_kind: str | None = None
    skill_name: str | None = None
    raw_input: JsonObject | None = None
    options: tuple[AcpPermissionOptionView, ...] = field(default_factory=tuple)
    raw_payload: JsonObject | None = None


def normalize_permission_request(
    *,
    adapter_key: str,
    working_directory: Path,
    payload: JsonObject,
) -> AcpPermissionRequest | None:
    request_id = payload.get("id")
    method = payload.get("method")
    if not isinstance(request_id, int) or not isinstance(method, str):
        return None
    params = payload.get("params")
    if not isinstance(params, dict):
        return None
    if method == "item/tool/requestUserInput":
        session_id = params.get("sessionId")
        return AcpPermissionRequest(
            request_id=request_id,
            adapter_key=adapter_key,
            method=method,
            interaction=AcpPermissionInteraction.USER_INPUT,
            working_directory=working_directory,
            session_id=session_id if isinstance(session_id, str) else None,
            raw_payload=payload,
        )
    if method not in {
        "session/request_permission",
        "item/commandExecution/requestApproval",
        "item/fileChange/requestApproval",
    }:
        return None
    session_id = params.get("sessionId")
    title = params.get("reason") or params.get("title")
    if method == "session/request_permission":
        tool_call = params.get("toolCall")
        if isinstance(tool_call, dict):
            title = tool_call.get("title") if isinstance(tool_call.get("title"), str) else title
            tool_kind = tool_call.get("kind") if isinstance(tool_call.get("kind"), str) else None
            raw_input = tool_call.get("rawInput")
            command = _extract_command(raw_input)
            skill_name = _extract_skill_name(raw_input)
        else:
            tool_kind = None
            raw_input = None
            command = None
            skill_name = None
        options = tuple(_normalize_permission_options(params.get("options")))
    else:
        tool_kind = None
        skill_name = None
        raw_input = None
        command = _extract_command(params.get("command"))
        options = ()
    return AcpPermissionRequest(
        request_id=request_id,
        adapter_key=adapter_key,
        method=method,
        interaction=AcpPermissionInteraction.APPROVAL,
        working_directory=working_directory,
        session_id=session_id if isinstance(session_id, str) else None,
        title=title if isinstance(title, str) else None,
        command=command,
        tool_kind=tool_kind,
        skill_name=skill_name,
        raw_input=raw_input if isinstance(raw_input, dict) else None,
        options=options,
        raw_payload=payload,
    )


def evaluate_permission_request(
    request: AcpPermissionRequest,
    *,
    auto_approve: bool,
) -> AcpPermissionDecision:
    if request.interaction is AcpPermissionInteraction.USER_INPUT:
        return AcpPermissionDecision.WAIT_INPUT
    if auto_approve and request.method == "session/request_permission":
        return AcpPermissionDecision.APPROVE
    return AcpPermissionDecision.ESCALATE


def render_permission_decision(
    *,
    request: AcpPermissionRequest,
    decision: AcpPermissionDecision,
) -> JsonObject:
    if request.interaction is AcpPermissionInteraction.USER_INPUT:
        return {"answers": {}}
    if decision is AcpPermissionDecision.ESCALATE:
        decision = AcpPermissionDecision.REJECT
    if request.method == "session/request_permission":
        option_id = _select_session_permission_option(request, decision)
        return {"outcome": {"outcome": "selected", "optionId": option_id}}
    return {"decision": "decline"}


def waiting_message_for_request(request: AcpPermissionRequest) -> str:
    if request.interaction is AcpPermissionInteraction.USER_INPUT:
        if request.adapter_key == "claude_acp":
            return "Claude ACP turn requested user input."
        if request.adapter_key == "codex_acp":
            return "Codex ACP turn requested user input."
        return "ACP turn requested user input."
    if request.adapter_key == "claude_acp":
        return "Claude ACP turn is waiting for approval."
    if request.adapter_key == "codex_acp":
        return "Codex ACP turn is waiting for approval."
    return "ACP turn is waiting for approval."


@dataclass(frozen=True)
class PermissionEvaluationResult:
    decision: AcpPermissionDecision
    rationale: str | None = None
    suggested_options: tuple[str, ...] = ()
    policy_title: str | None = None
    policy_rule_text: str | None = None


def permission_signature_for_request(request: AcpPermissionRequest) -> PermissionRequestSignature:
    return PermissionRequestSignature(
        adapter_key=request.adapter_key,
        method=request.method,
        interaction=request.interaction.value,
        title=request.title,
        tool_kind=request.tool_kind,
        skill_name=request.skill_name,
        command=list(request.command or []),
    )


def serialize_permission_signature(signature: PermissionRequestSignature) -> JsonObject:
    return signature.model_dump(mode="json")


def find_matching_permission_policy(
    request: AcpPermissionRequest,
    *,
    active_policies: list[PolicyEntry],
) -> PolicyEntry | None:
    signature = permission_signature_for_request(request)
    for policy in active_policies:
        for candidate in policy.applicability.permission_signatures:
            if candidate == signature:
                return policy
    return None


def serialize_permission_request(request: AcpPermissionRequest) -> JsonObject:
    return {
        "adapter_key": request.adapter_key,
        "method": request.method,
        "interaction": request.interaction.value,
        "working_directory": str(request.working_directory),
        "session_id": request.session_id,
        "title": request.title,
        "command": list(request.command or []),
        "tool_kind": request.tool_kind,
        "skill_name": request.skill_name,
        "signature": serialize_permission_signature(permission_signature_for_request(request)),
    }


def _normalize_permission_options(raw: object) -> list[AcpPermissionOptionView]:
    if not isinstance(raw, list):
        return []
    normalized: list[AcpPermissionOptionView] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        option_id = item.get("optionId")
        if not isinstance(option_id, str) or not option_id:
            continue
        kind = item.get("kind")
        name = item.get("name")
        normalized.append(
            AcpPermissionOptionView(
                option_id=option_id,
                kind=kind if isinstance(kind, str) else None,
                name=name if isinstance(name, str) else None,
            )
        )
    return normalized


def _extract_command(raw: object) -> list[str] | None:
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        return list(raw)
    if isinstance(raw, str):
        return [raw]
    return None


def _select_session_permission_option(
    request: AcpPermissionRequest,
    decision: AcpPermissionDecision,
) -> str:
    options = request.options
    if decision is AcpPermissionDecision.APPROVE:
        preferred_ids = (
            ("allow_always", "allow_once")
            if request.adapter_key == "claude_acp"
            else ("approved", "approved-execpolicy-amendment", "allow_always", "allow_once")
        )
        by_kind = ("allow_always", "allow_once")
    else:
        preferred_ids = ("reject",) if request.adapter_key == "claude_acp" else ("abort",)
        by_kind = ("reject_once", "reject")
    for candidate in preferred_ids:
        for option in options:
            if option.option_id == candidate:
                return option.option_id
    for option in options:
        if option.kind in by_kind:
            return option.option_id
    if options:
        return options[0].option_id
    raise ValueError(
        f"No ACP permission options available for {request.adapter_key} {request.method} {decision}"
    )


def _extract_skill_name(raw: object) -> str | None:
    if not isinstance(raw, dict):
        return None
    skill = raw.get("skill")
    return skill if isinstance(skill, str) and skill else None
