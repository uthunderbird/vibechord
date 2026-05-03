from __future__ import annotations

from collections.abc import Mapping

from agent_operator.domain.agent import AgentSessionHandle
from agent_operator.domain.operation import ExecutionProfileOverride, ExecutionProfileStamp


def effective_execution_profile_stamp(
    *,
    goal_metadata: Mapping[str, object],
    execution_profile_overrides: Mapping[str, ExecutionProfileOverride],
    adapter_key: str,
) -> ExecutionProfileStamp | None:
    override = execution_profile_overrides.get(adapter_key)
    if override is not None:
        return ExecutionProfileStamp(
            adapter_key=adapter_key,
            model=override.model,
            effort_field_name=override.effort_field_name,
            effort_value=override.effort_value,
            approval_policy=override.approval_policy,
            sandbox_mode=override.sandbox_mode,
        )

    raw_snapshot = goal_metadata.get("effective_adapter_settings")
    if not isinstance(raw_snapshot, dict):
        return None
    raw_adapter = raw_snapshot.get(adapter_key)
    if not isinstance(raw_adapter, dict):
        return None
    model = raw_adapter.get("model")
    if not isinstance(model, str) or not model.strip():
        return None

    if adapter_key == "codex_acp":
        raw_effort = raw_adapter.get("reasoning_effort")
        effort_value = raw_effort if isinstance(raw_effort, str) and raw_effort.strip() else None
        return ExecutionProfileStamp(
            adapter_key=adapter_key,
            model=model.strip(),
            effort_field_name="reasoning_effort",
            effort_value=effort_value,
            approval_policy=_optional_str(raw_adapter.get("approval_policy")),
            sandbox_mode=_optional_str(raw_adapter.get("sandbox_mode")),
        )

    raw_effort = raw_adapter.get("effort")
    effort_value = raw_effort if isinstance(raw_effort, str) and raw_effort.strip() else None
    return ExecutionProfileStamp(
        adapter_key=adapter_key,
        model=model.strip(),
        effort_field_name="effort" if adapter_key == "claude_acp" else None,
        effort_value=effort_value,
    )


def execution_profile_request_metadata(
    *,
    goal_metadata: Mapping[str, object],
    execution_profile_overrides: Mapping[str, ExecutionProfileOverride],
    adapter_key: str,
) -> dict[str, str]:
    stamp = effective_execution_profile_stamp(
        goal_metadata=goal_metadata,
        execution_profile_overrides=execution_profile_overrides,
        adapter_key=adapter_key,
    )
    if stamp is None:
        return {}
    metadata = {
        "execution_profile_model": stamp.model,
        "execution_profile_adapter_key": adapter_key,
    }
    if stamp.effort_field_name is not None and stamp.effort_value is not None:
        metadata[f"execution_profile_{stamp.effort_field_name}"] = stamp.effort_value
    if stamp.approval_policy is not None:
        metadata["execution_profile_approval_policy"] = stamp.approval_policy
    if stamp.sandbox_mode is not None:
        metadata["execution_profile_sandbox_mode"] = stamp.sandbox_mode
    return metadata


def execution_profile_stamp_from_handle(
    handle: AgentSessionHandle,
) -> ExecutionProfileStamp | None:
    raw_model = handle.metadata.get("execution_profile_model")
    if not isinstance(raw_model, str) or not raw_model.strip():
        return None
    model = raw_model.strip()
    approval_policy = _optional_str(handle.metadata.get("execution_profile_approval_policy"))
    sandbox_mode = _optional_str(handle.metadata.get("execution_profile_sandbox_mode"))
    raw_reasoning_effort = handle.metadata.get("execution_profile_reasoning_effort")
    if isinstance(raw_reasoning_effort, str) and raw_reasoning_effort.strip():
        return ExecutionProfileStamp(
            adapter_key=handle.adapter_key,
            model=model,
            effort_field_name="reasoning_effort",
            effort_value=raw_reasoning_effort.strip(),
            approval_policy=approval_policy,
            sandbox_mode=sandbox_mode,
        )
    raw_effort = handle.metadata.get("execution_profile_effort")
    if isinstance(raw_effort, str) and raw_effort.strip():
        return ExecutionProfileStamp(
            adapter_key=handle.adapter_key,
            model=model,
            effort_field_name="effort",
            effort_value=raw_effort.strip(),
            approval_policy=approval_policy,
            sandbox_mode=sandbox_mode,
        )
    return ExecutionProfileStamp(
        adapter_key=handle.adapter_key,
        model=model,
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
    )


def _optional_str(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
