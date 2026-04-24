from __future__ import annotations

import json
import shlex
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

import typer

from agent_operator.domain import AttentionStatus, OperationState, OperationStatus


class ConverseBrain(Protocol):
    async def converse(self, prompt: str): ...


class OperationStore(Protocol):
    async def load_operation(self, operation_id: str) -> OperationState | None: ...

    async def list_operations(self): ...


@dataclass(frozen=True)
class ConverseCommand:
    command_name: str
    operation_id: str
    text: str | None = None
    attention_id: str | None = None
    task_id: str | None = None


def build_converse_operation_prompt(
    state: OperationState,
    *,
    user_message: str,
    conversation_history: list[dict[str, str]],
    context_level: str,
    recent_events: list[dict[str, object]] | None,
) -> str:
    iteration_limit = 20 if context_level == "full" else 5
    context_sections = [
        f"Objective:\n{state.objective_state.objective}",
        "Harness Instructions:\n"
        f"{state.objective_state.harness_instructions or '(none)'}",
        f"Current status:\n{state.status.value}",
        f"Current focus:\n{json.dumps(_serialize_focus(state), ensure_ascii=True)}",
        "Open Attention Requests:\n"
        f"{_attention_requests_json(state, statuses={'open'})}",
        "Recent iteration history:\n"
        f"{json.dumps(
            _serialize_recent_iterations(state, limit=iteration_limit),
            ensure_ascii=True,
        )}",
    ]
    if context_level == "full":
        context_sections.extend(
            [
                f"Tasks:\n{json.dumps(_serialize_tasks(state), ensure_ascii=True)}",
                f"Sessions:\n{json.dumps(_serialize_sessions(state), ensure_ascii=True)}",
                "Current memory:\n"
                f"{json.dumps(_serialize_memory_entries(state), ensure_ascii=True)}",
                "Recent event log:\n"
                f"{json.dumps(recent_events or [], ensure_ascii=True)}",
            ]
        )
    return (
        "You are the operator brain's interactive natural-language conversation surface.\n"
        "Respond conversationally, grounded only in the provided operation context.\n"
        "Return JSON matching the schema.\n"
        "Set proposed_command to null for read-only answers.\n"
        "When a write action is appropriate, propose exactly one canonical CLI command string.\n"
        "Supported write commands are:\n"
        "- operator answer <operation-id> <attention-id> --text \"...\"\n"
        "- operator message <operation-id> \"...\"\n"
        "- operator pause <operation-id>\n"
        "- operator unpause <operation-id>\n"
        "- operator interrupt <operation-id> --task <task-id>\n"
        "- operator patch-objective <operation-id> \"...\"\n"
        "- operator cancel <operation-id>\n"
        "Do not claim that any command already executed.\n"
        "Dangerous commands still require structured confirmation; "
        "you may propose them but must not imply execution.\n"
        f"Conversation mode: operation\nContext level: {context_level}\n"
        f"Operation id: {state.operation_id}\n\n"
        "Conversation history so far:\n"
        f"{json.dumps(conversation_history, ensure_ascii=True)}\n\n"
        + "\n\n".join(context_sections)
        + "\n\nUser message:\n"
        + user_message
    )


def build_converse_fleet_prompt(
    operations: list[OperationState],
    *,
    user_message: str,
    conversation_history: list[dict[str, str]],
    context_level: str,
) -> str:
    fleet_payload: list[dict[str, object]] = []
    for operation in operations:
        entry: dict[str, object] = {
            "operation_id": operation.operation_id,
            "status": operation.status.value,
            "objective": operation.objective_state.objective,
            "project_profile_name": operation.goal.metadata.get("project_profile_name"),
            "iteration_count": len(operation.iterations),
            "open_attention_count": len(
                [
                    item
                    for item in operation.attention_requests
                    if item.status.value == "open"
                ]
            ),
            "blocking_attention_count": len(
                [
                    item
                    for item in operation.attention_requests
                    if item.status.value == "open" and item.blocking
                ]
            ),
        }
        if context_level == "full":
            entry["focus"] = _serialize_focus(operation)
            entry["tasks"] = _serialize_tasks(operation)
        fleet_payload.append(entry)
    return (
        "You are the operator brain's interactive natural-language conversation surface.\n"
        "Respond conversationally, grounded only in the provided fleet context.\n"
        "Return JSON matching the schema.\n"
        "Set proposed_command to null for read-only answers.\n"
        "When a write action is appropriate, propose exactly one canonical CLI command string "
        "with an explicit operation id.\n"
        "Supported write commands are:\n"
        "- operator answer <operation-id> <attention-id> --text \"...\"\n"
        "- operator message <operation-id> \"...\"\n"
        "- operator pause <operation-id>\n"
        "- operator unpause <operation-id>\n"
        "- operator interrupt <operation-id> --task <task-id>\n"
        "- operator patch-objective <operation-id> \"...\"\n"
        "- operator cancel <operation-id>\n"
        "Do not claim that any command already executed.\n"
        f"Conversation mode: fleet\nContext level: {context_level}\n\n"
        "Conversation history so far:\n"
        f"{json.dumps(conversation_history, ensure_ascii=True)}\n\n"
        "Fleet context:\n"
        f"{json.dumps(fleet_payload, ensure_ascii=True)}\n\n"
        "User message:\n"
        f"{user_message}"
    )


async def converse_async(
    *,
    operation_ref: str | None,
    project: str | None,
    context_level: str,
    build_brain: Callable[[object], ConverseBrain],
    load_settings: Callable[[], object],
    build_store: Callable[[object], OperationStore],
    build_event_sink: Callable[[object, str], object],
    execute_command: Callable[[ConverseCommand], Awaitable[None]],
) -> None:
    if context_level not in {"brief", "full"}:
        raise typer.BadParameter("--context must be one of: brief, full.")
    settings = load_settings()
    brain = build_brain(settings)
    history: list[dict[str, str]] = []
    resolved_operation_id: str | None = None
    if operation_ref is not None:
        try:
            resolved_operation_id = await resolve_ask_operation_id(
                operation_ref,
                store=build_store(settings),
            )
        except RuntimeError as exc:
            raise typer.BadParameter(str(exc)) from exc

    while True:
        if resolved_operation_id is not None:
            state = await build_store(settings).load_operation(resolved_operation_id)
            if state is None:
                raise typer.BadParameter(f"Operation {resolved_operation_id!r} was not found.")
            header = _format_operation_converse_header(state)
        else:
            operations = await _load_converse_fleet_operations(
                project,
                store=build_store(settings),
            )
            header = _format_fleet_converse_header(operations, project=project)
        if not history:
            typer.echo(header)
            typer.echo("─" * len(header))
        try:
            user_message = input("> ").strip()
        except EOFError:
            typer.echo()
            return
        if not user_message:
            continue
        if user_message.lower() in {"exit", "quit"}:
            return
        history.append({"role": "user", "content": user_message})
        if resolved_operation_id is not None:
            state = await build_store(settings).load_operation(resolved_operation_id)
            assert state is not None
            recent_events: list[dict[str, object]] | None = None
            if context_level == "full":
                recent_events = _load_recent_events(
                    build_event_sink=build_event_sink,
                    settings=settings,
                    operation_id=resolved_operation_id,
                )
            prompt = build_converse_operation_prompt(
                state,
                user_message=user_message,
                conversation_history=history[:-1],
                context_level=context_level,
                recent_events=recent_events,
            )
        else:
            operations = await _load_converse_fleet_operations(
                project,
                store=build_store(settings),
            )
            prompt = build_converse_fleet_prompt(
                operations,
                user_message=user_message,
                conversation_history=history[:-1],
                context_level=context_level,
            )
        turn = await brain.converse(prompt)
        answer = turn.answer.strip()
        typer.echo(answer)
        history.append({"role": "assistant", "content": answer})
        proposed_command_text = (
            turn.proposed_command.strip() if turn.proposed_command is not None else None
        )
        if not proposed_command_text:
            continue
        typer.echo(f"→ Proposed action: {proposed_command_text}")
        decision = input("   Execute? [y/N/edit] ").strip().lower()
        if decision not in {"y", "edit"}:
            history.append({"role": "system", "content": "Proposed command declined."})
            continue
        command_text = proposed_command_text
        if decision == "edit":
            edited = typer.edit(command_text)
            if edited is None or not edited.strip():
                history.append({"role": "system", "content": "Proposed command edit cancelled."})
                continue
            command_text = edited.strip()
        try:
            command = parse_converse_command(
                command_text,
                default_operation_id=resolved_operation_id,
            )
        except RuntimeError as exc:
            typer.echo(str(exc), err=True)
            history.append(
                {
                    "role": "system",
                    "content": f"Invalid proposed command: {command_text}",
                }
            )
            continue
        if converse_command_requires_typed_confirmation(command):
            confirmation = input(f"   Type {command.operation_id} to confirm: ").strip()
            if confirmation != command.operation_id:
                typer.echo("cancelled")
                history.append(
                    {
                        "role": "system",
                        "content": f"Dangerous command not confirmed: {command_text}",
                    }
                )
                continue
        await execute_command(command)
        history.append({"role": "system", "content": f"Executed: {command_text}"})


def parse_converse_command(
    command_text: str,
    *,
    default_operation_id: str | None = None,
) -> ConverseCommand:
    tokens = shlex.split(command_text)
    if not tokens:
        raise RuntimeError("Empty proposed command.")
    if tokens[0] == "operator":
        tokens = tokens[1:]
    if not tokens:
        raise RuntimeError("Proposed command must start with an operator subcommand.")
    command_name = tokens[0]
    positionals: list[str] = []
    text: str | None = None
    task_id: str | None = None
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--text":
            if index + 1 >= len(tokens):
                raise RuntimeError("Proposed command is missing a value for --text.")
            text = tokens[index + 1]
            index += 2
            continue
        if token == "--task":
            if index + 1 >= len(tokens):
                raise RuntimeError("Proposed command is missing a value for --task.")
            task_id = tokens[index + 1]
            index += 2
            continue
        if token.startswith("--"):
            raise RuntimeError(f"Unsupported converse option: {token}")
        positionals.append(token)
        index += 1

    def _resolve_operation_id(positional_index: int = 0) -> str:
        if len(positionals) > positional_index:
            return positionals[positional_index]
        if default_operation_id is not None:
            return default_operation_id
        raise RuntimeError("Proposed command is missing an operation id.")

    if command_name == "answer":
        if len(positionals) >= 2:
            operation_id = positionals[0]
            attention_id = positionals[1]
        elif len(positionals) == 1 and default_operation_id is not None:
            operation_id = default_operation_id
            attention_id = positionals[0]
        else:
            raise RuntimeError("`operator answer` requires an operation id and attention id.")
        if text is None:
            raise RuntimeError("`operator answer` requires --text.")
        return ConverseCommand(
            command_name=command_name,
            operation_id=operation_id,
            attention_id=attention_id,
            text=text,
        )
    if command_name in {"message", "patch-objective"}:
        operation_id = _resolve_operation_id()
        if len(positionals) >= 2:
            text = " ".join(positionals[1:])
        if not text:
            raise RuntimeError(f"`operator {command_name}` requires text.")
        return ConverseCommand(command_name=command_name, operation_id=operation_id, text=text)
    if command_name in {"pause", "unpause", "cancel"}:
        return ConverseCommand(command_name=command_name, operation_id=_resolve_operation_id())
    if command_name == "interrupt":
        operation_id = _resolve_operation_id()
        if task_id is None:
            raise RuntimeError("`operator interrupt` requires --task.")
        return ConverseCommand(
            command_name=command_name,
            operation_id=operation_id,
            task_id=task_id,
        )
    raise RuntimeError(f"Unsupported converse command: {command_name}")


def converse_command_requires_typed_confirmation(command: ConverseCommand) -> bool:
    return command.command_name in {"cancel", "patch-objective"}


def _format_operation_converse_header(state: OperationState) -> str:
    blocking_count = len(
        [
            item
            for item in state.attention_requests
            if item.status is AttentionStatus.OPEN and item.blocking
        ]
    )
    budget = getattr(state, "execution_budget", None)
    max_iterations_value = getattr(budget, "max_iterations", None)
    max_iterations = max_iterations_value if max_iterations_value is not None else "?"
    return (
        f"Operator › {state.operation_id} · {state.status.value} · "
        f"iter {len(state.iterations)}/{max_iterations} · {blocking_count} blocking attention"
    )


def _format_fleet_converse_header(
    operations: list[OperationState], *, project: str | None = None
) -> str:
    blocking_count = sum(
        1
        for operation in operations
        for attention in operation.attention_requests
        if attention.status is AttentionStatus.OPEN and attention.blocking
    )
    label = f"fleet:{project}" if project is not None else "fleet"
    return (
        f"Operator › {label} · {len(operations)} active operations · "
        f"{blocking_count} blocking attention"
    )


async def _load_converse_fleet_operations(
    project: str | None,
    *,
    store: OperationStore,
) -> list[OperationState]:
    summaries = await store.list_operations()
    operations: list[OperationState] = []
    for summary in summaries:
        operation = await store.load_operation(summary.operation_id)
        if operation is None:
            continue
        if operation.status in {
            OperationStatus.COMPLETED,
            OperationStatus.FAILED,
            OperationStatus.CANCELLED,
        }:
            continue
        profile_name = operation.goal.metadata.get("project_profile_name")
        if project is not None and profile_name != project:
            continue
        operations.append(operation)
    return sorted(operations, key=lambda item: item.created_at)


async def resolve_ask_operation_id(
    operation_ref: str,
    *,
    store: OperationStore,
) -> str:
    summaries = await store.list_operations()
    if operation_ref == "last":
        if not summaries:
            raise RuntimeError("No persisted operations were found.")
        states = [
            operation
            for summary in summaries
            if (operation := await store.load_operation(summary.operation_id)) is not None
        ]
        if not states:
            raise RuntimeError("No persisted operations were found.")
        return max(states, key=lambda item: item.created_at).operation_id
    exact = next(
        (item.operation_id for item in summaries if item.operation_id == operation_ref),
        None,
    )
    if exact is not None:
        return exact
    prefix_matches = [
        item.operation_id for item in summaries if item.operation_id.startswith(operation_ref)
    ]
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    if len(prefix_matches) > 1:
        raise RuntimeError(
            f"Operation reference {operation_ref!r} is ambiguous. Matches: "
            + ", ".join(sorted(prefix_matches))
        )
    profile_matches = []
    for summary in summaries:
        operation = await store.load_operation(summary.operation_id)
        if operation is None:
            continue
        profile_name = operation.goal.metadata.get("project_profile_name")
        if isinstance(profile_name, str) and profile_name == operation_ref:
            profile_matches.append(operation)
    if profile_matches:
        return max(profile_matches, key=lambda item: item.created_at).operation_id
    raise RuntimeError(f"Operation {operation_ref!r} was not found.")


def _load_recent_events(
    *,
    build_event_sink: Callable[[object, str], object],
    settings: object,
    operation_id: str,
) -> list[dict[str, object]]:
    event_sink = build_event_sink(settings, operation_id)
    return [
        _serialize_run_event(event)
        for event in list(event_sink.iter_events(operation_id))[-20:]
    ]


def _serialize_run_event(event) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "kind": event.kind.value,
        "category": event.category,
        "operation_id": event.operation_id,
        "iteration": event.iteration,
        "task_id": event.task_id,
        "session_id": event.session_id,
        "dedupe_key": event.dedupe_key,
        "timestamp": event.timestamp.isoformat(),
        "not_before": event.not_before.isoformat() if event.not_before is not None else None,
        "payload": dict(event.payload),
    }


def _serialize_decision(decision) -> dict[str, object]:
    return {
        "action_type": decision.action_type.value,
        "target_agent": decision.target_agent,
        "session_id": decision.session_id,
        "session_name": decision.session_name,
        "one_shot": decision.one_shot,
        "workfront_key": decision.workfront_key,
        "instruction": decision.instruction,
        "rationale": decision.rationale,
        "confidence": decision.confidence,
        "assumptions": list(decision.assumptions),
        "expected_outcome": decision.expected_outcome,
        "focus_task_id": decision.focus_task_id,
        "new_features": [
            {
                "title": item.title,
                "acceptance_criteria": item.acceptance_criteria,
                "notes": list(item.notes),
            }
            for item in decision.new_features
        ],
        "feature_updates": [
            {
                "feature_id": item.feature_id,
                "status": item.status.value if item.status is not None else None,
                "title": item.title,
                "acceptance_criteria": item.acceptance_criteria,
                "append_notes": list(item.append_notes),
            }
            for item in decision.feature_updates
        ],
        "new_tasks": [
            {
                "title": item.title,
                "goal": item.goal,
                "definition_of_done": item.definition_of_done,
                "assigned_agent": item.assigned_agent,
                "brain_priority": item.brain_priority,
                "dependencies": list(item.dependencies),
                "notes": list(item.notes),
            }
            for item in decision.new_tasks
        ],
        "task_updates": [
            {
                "task_id": item.task_id,
                "status": item.status.value if item.status is not None else None,
                "title": item.title,
                "goal": item.goal,
                "definition_of_done": item.definition_of_done,
                "brain_priority": item.brain_priority,
                "assigned_agent": item.assigned_agent,
                "append_notes": list(item.append_notes),
                "linked_session_id": item.linked_session_id,
                "session_policy": (
                    item.session_policy.value if item.session_policy is not None else None
                ),
                "add_memory_refs": list(item.add_memory_refs),
                "add_artifact_refs": list(item.add_artifact_refs),
                "add_dependencies": list(item.add_dependencies),
                "remove_dependencies": list(item.remove_dependencies),
                "dependency_removal_reason": item.dependency_removal_reason,
            }
            for item in decision.task_updates
        ],
        "blocking_focus": (
            {
                "kind": decision.blocking_focus.kind.value,
                "target_id": decision.blocking_focus.target_id,
                "blocking_reason": decision.blocking_focus.blocking_reason,
                "interrupt_policy": decision.blocking_focus.interrupt_policy.value,
                "resume_policy": decision.blocking_focus.resume_policy.value,
            }
            if decision.blocking_focus is not None
            else None
        ),
        "metadata": dict(decision.metadata),
    }


def _serialize_session_handle(session) -> dict[str, object]:
    return {
        "adapter_key": session.adapter_key,
        "session_id": session.session_id,
        "session_name": session.session_name,
        "display_name": session.display_name,
        "one_shot": session.one_shot,
        "metadata": dict(session.metadata),
    }


def _serialize_agent_result(result) -> dict[str, object]:
    return {
        "session_id": result.session_id,
        "status": result.status.value,
        "output_text": result.output_text,
        "artifacts": [
            {
                "name": artifact.name,
                "kind": artifact.kind,
                "uri": artifact.uri,
                "content": artifact.content,
                "metadata": dict(artifact.metadata),
            }
            for artifact in result.artifacts
        ],
        "error": (
            {
                "code": result.error.code,
                "message": result.error.message,
                "retryable": result.error.retryable,
                "raw": dict(result.error.raw) if result.error.raw is not None else None,
            }
            if result.error is not None
            else None
        ),
        "completed_at": (
            result.completed_at.isoformat() if result.completed_at is not None else None
        ),
        "structured_output": (
            dict(result.structured_output) if result.structured_output is not None else None
        ),
        "usage": (
            {
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "total_tokens": result.usage.total_tokens,
                "context_window_size": result.usage.context_window_size,
                "context_tokens_used": result.usage.context_tokens_used,
                "cost_amount": result.usage.cost_amount,
                "cost_currency": result.usage.cost_currency,
                "metadata": dict(result.usage.metadata),
            }
            if result.usage is not None
            else None
        ),
        "transcript": result.transcript,
        "raw": dict(result.raw) if result.raw is not None else None,
    }


def _serialize_turn_summary(summary) -> dict[str, object]:
    return {
        "declared_goal": summary.declared_goal,
        "actual_work_done": summary.actual_work_done,
        "route_or_target_chosen": summary.route_or_target_chosen,
        "repo_changes": list(summary.repo_changes),
        "progress_class": summary.progress_class,
        "blocker_keys": list(summary.blocker_keys),
        "state_delta": summary.state_delta,
        "verification_status": summary.verification_status,
        "remaining_blockers": list(summary.remaining_blockers),
        "recommended_next_step": summary.recommended_next_step,
        "rationale": summary.rationale,
    }


def _serialize_focus(state: OperationState) -> dict[str, object] | None:
    focus = state.current_focus
    if focus is None:
        return None
    return {
        "kind": focus.kind.value,
        "target_id": focus.target_id,
        "mode": focus.mode.value,
        "blocking_reason": focus.blocking_reason,
        "interrupt_policy": focus.interrupt_policy.value,
        "resume_policy": focus.resume_policy.value,
        "created_at": focus.created_at.isoformat(),
    }


def _serialize_tasks(state: OperationState) -> list[dict[str, object]]:
    return [
        {
            "task_id": task.task_id,
            "task_short_id": task.task_short_id,
            "title": task.title,
            "goal": task.goal,
            "definition_of_done": task.definition_of_done,
            "status": task.status.value,
            "brain_priority": task.brain_priority,
            "effective_priority": task.effective_priority,
            "feature_id": task.feature_id,
            "dependencies": list(task.dependencies),
            "assigned_agent": task.assigned_agent,
            "linked_session_id": task.linked_session_id,
            "session_policy": task.session_policy.value,
            "memory_refs": list(task.memory_refs),
            "artifact_refs": list(task.artifact_refs),
            "attempt_count": task.attempt_count,
            "notes": list(task.notes),
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        }
        for task in state.tasks
    ]


def _serialize_sessions(state: OperationState) -> list[dict[str, object]]:
    return [
        {
            "session_id": session.session_id,
            "adapter_key": session.adapter_key,
            "status": session.status.value,
            "session_name": session.handle.session_name,
            "display_name": session.handle.display_name,
            "one_shot": session.handle.one_shot,
            "current_execution_id": session.current_execution_id,
            "last_terminal_execution_id": session.last_terminal_execution_id,
            "bound_task_ids": list(session.bound_task_ids),
            "last_result_iteration": session.last_result_iteration,
            "latest_iteration": session.latest_iteration,
            "attached_turn_started_at": (
                session.attached_turn_started_at.isoformat()
                if session.attached_turn_started_at is not None
                else None
            ),
            "last_progress_at": (
                session.last_progress_at.isoformat()
                if session.last_progress_at is not None
                else None
            ),
            "last_event_at": (
                session.last_event_at.isoformat() if session.last_event_at is not None else None
            ),
            "waiting_reason": session.waiting_reason,
            "cooldown_until": (
                session.cooldown_until.isoformat() if session.cooldown_until is not None else None
            ),
            "cooldown_reason": session.cooldown_reason,
            "last_rate_limited_at": (
                session.last_rate_limited_at.isoformat()
                if session.last_rate_limited_at is not None
                else None
            ),
            "recovery_summary": session.recovery_summary,
            "recovery_count": session.recovery_count,
            "recovery_attempted_at": (
                session.recovery_attempted_at.isoformat()
                if session.recovery_attempted_at is not None
                else None
            ),
            "last_recovered_at": (
                session.last_recovered_at.isoformat()
                if session.last_recovered_at is not None
                else None
            ),
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
        }
        for session in state.sessions
    ]


def _serialize_memory_entries(state: OperationState) -> list[dict[str, object]]:
    return [
        {
            "memory_id": entry.memory_id,
            "scope": entry.scope.value,
            "scope_id": entry.scope_id,
            "summary": entry.summary,
            "source_refs": [
                {
                    "kind": source_ref.kind,
                    "ref_id": source_ref.ref_id,
                }
                for source_ref in entry.source_refs
            ],
            "freshness": entry.freshness.value,
            "superseded_by": entry.superseded_by,
            "created_at": entry.created_at.isoformat(),
            "updated_at": entry.updated_at.isoformat(),
        }
        for entry in state.memory_entries
    ]


def _serialize_recent_iterations(
    state: OperationState,
    *,
    limit: int,
) -> list[dict[str, object]]:
    return [
        {
            "index": item.index,
            "decision": _serialize_decision(item.decision) if item.decision is not None else None,
            "task_id": item.task_id,
            "session": (
                _serialize_session_handle(item.session) if item.session is not None else None
            ),
            "result": _serialize_agent_result(item.result) if item.result is not None else None,
            "turn_summary": (
                _serialize_turn_summary(item.turn_summary)
                if item.turn_summary is not None
                else None
            ),
            "notes": list(item.notes),
        }
        for item in state.iterations[-limit:]
    ]


def _attention_requests_json(
    state: OperationState,
    *,
    statuses: set[str],
) -> str:
    return json.dumps(
        [
            {
                "attention_id": item.attention_id,
                "operation_id": item.operation_id,
                "attention_type": item.attention_type.value,
                "target_scope": item.target_scope.value,
                "target_id": item.target_id,
                "title": item.title,
                "question": item.question,
                "context_brief": item.context_brief,
                "suggested_options": list(item.suggested_options),
                "blocking": item.blocking,
                "status": item.status.value,
                "answer_text": item.answer_text,
                "answer_source_command_id": item.answer_source_command_id,
                "created_at": item.created_at.isoformat(),
                "answered_at": (
                    item.answered_at.isoformat() if item.answered_at is not None else None
                ),
                "resolved_at": (
                    item.resolved_at.isoformat() if item.resolved_at is not None else None
                ),
                "resolution_summary": item.resolution_summary,
                "metadata": dict(item.metadata),
            }
            for item in state.attention_requests
            if item.status.value in statuses
        ],
        ensure_ascii=True,
    )
