from __future__ import annotations

import json

from agent_operator.domain import (
    AgentResult,
    IterationState,
    MemoryFreshness,
    OperationGoal,
    OperationState,
    SessionStatus,
)

_RESULT_EXCERPT_LIMIT = 4000
_RESULT_EXCERPT_HEAD = 2000
_RESULT_EXCERPT_TAIL = 2000


def _excerpt_result_text(text: str, *, limit: int = _RESULT_EXCERPT_LIMIT) -> str:
    if len(text) <= limit:
        return text
    head = text[: min(_RESULT_EXCERPT_HEAD, limit)]
    tail_budget = max(0, limit - len(head))
    tail = text[-min(_RESULT_EXCERPT_TAIL, tail_budget) :] if tail_budget > 0 else ""
    marker = "\n...\n[operator excerpt omitted middle content]\n...\n"
    if not tail:
        return head
    combined = head + marker + tail
    if len(combined) <= limit:
        return combined
    overflow = len(combined) - limit
    if overflow >= len(tail):
        return head
    return head + marker + tail[overflow:]


def _serialize_turn_summary(iteration: IterationState) -> dict[str, object] | None:
    summary = iteration.turn_summary
    if summary is None:
        return None
    return dict(summary.model_dump(mode="json"))


def _completed_iteration_history(
    state: OperationState,
    *,
    limit: int,
) -> tuple[list[object], dict[str, object] | None]:
    completed = [iteration for iteration in state.iterations if iteration.result is not None]
    if not completed:
        return [], None
    latest_completed = completed[-1]
    older_completed = completed[:-1][-max(0, limit - 1) :]
    history: list[object] = []
    for iteration in older_completed:
        result = iteration.result
        assert result is not None
        payload: dict[str, object] = {
            "index": iteration.index,
            "task_id": iteration.task_id,
            "decision": (
                iteration.decision.model_dump(mode="json")
                if iteration.decision is not None
                else None
            ),
            "turn_summary": _serialize_turn_summary(iteration),
            "result_status": result.status.value,
            "result_error": (
                result.error.message
                if result.error is not None
                else None
            ),
            "notes": iteration.notes,
        }
        if iteration.turn_summary is None and result.output_text:
            payload["result_excerpt"] = _excerpt_result_text(result.output_text)
        history.append(payload)
    latest_result = latest_completed.result
    assert latest_result is not None
    latest_payload: dict[str, object] = {
        "index": latest_completed.index,
        "task_id": latest_completed.task_id,
        "decision": (
            latest_completed.decision.model_dump(mode="json")
            if latest_completed.decision is not None
            else None
        ),
        "turn_summary": _serialize_turn_summary(latest_completed),
        "full_result": latest_result.output_text,
        "result_status": latest_result.status.value,
        "result_error": (
            latest_result.error.message
            if latest_result.error is not None
            else None
        ),
        "notes": latest_completed.notes,
    }
    return history, latest_payload


def _serialize_recent_iterations(
    state: OperationState,
    limit: int = 5,
) -> list[dict[str, object]]:
    recent = state.iterations[-limit:]
    older_completed, latest_completed = _completed_iteration_history(state, limit=limit)
    by_index: dict[int, dict[str, object]] = {}
    for item in older_completed:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        if isinstance(index, int):
            by_index[index] = item
    if latest_completed is not None:
        index = latest_completed.get("index")
        if isinstance(index, int):
            by_index[index] = latest_completed
    rendered: list[dict[str, object]] = []
    for iteration in recent:
        if iteration.index in by_index:
            rendered.append(by_index[iteration.index])
            continue
        rendered.append(
            {
                "index": iteration.index,
                "task_id": iteration.task_id,
                "decision": (
                    iteration.decision.model_dump(mode="json")
                    if iteration.decision is not None
                    else None
                ),
                "turn_summary": _serialize_turn_summary(iteration),
                "result_status": None,
                "result_error": None,
                "notes": iteration.notes,
            }
        )
    return rendered


def _serialize_recent_decisions(
    state: OperationState,
    limit: int = 10,
) -> list[dict[str, object]]:
    return [
        {
            "action_type": record.action_type,
            "more_actions": record.more_actions,
            "wake_cycle_id": record.wake_cycle_id,
            "timestamp": record.timestamp.isoformat(),
        }
        for record in state.recent_decisions[-limit:]
    ]


def _serialize_recent_agent_outputs(
    state: OperationState,
    limit: int = 5,
) -> list[dict[str, object]]:
    return [
        {
            "iteration": brief.iteration,
            "agent_key": brief.agent_key,
            "status": brief.status,
            "output_text": brief.result_brief or "",
        }
        for brief in state.agent_turn_briefs[-limit:]
    ]


def _serialize_tasks(state: OperationState) -> list[dict[str, object]]:
    tasks = sorted(state.tasks, key=lambda item: (-item.effective_priority, item.created_at))
    return [
        {
            "task_id": task.task_id,
            "title": task.title,
            "goal": task.goal,
            "definition_of_done": task.definition_of_done,
            "status": task.status.value,
            "brain_priority": task.brain_priority,
            "effective_priority": task.effective_priority,
            "dependencies": task.dependencies,
            "assigned_agent": task.assigned_agent,
            "linked_session_id": task.linked_session_id,
            "session_policy": task.session_policy.value,
            "memory_refs": task.memory_refs,
            "artifact_refs": task.artifact_refs,
            "notes": task.notes[-3:],
        }
        for task in tasks
    ]


def _serialize_sessions(state: OperationState) -> list[dict[str, object]]:
    return [
        {
            "session_id": record.session_id,
            "adapter_key": record.adapter_key,
            "display_name": record.handle.display_name,
            "session_name": record.handle.session_name,
            "one_shot": record.handle.one_shot,
            "status": record.status.value,
            "bound_task_ids": record.bound_task_ids,
            "last_result_iteration": record.last_result_iteration,
        }
        for record in state.sessions
        if record.status not in {SessionStatus.CANCELLED}
    ]


def _serialize_memory_entries(state: OperationState) -> list[dict[str, object]]:
    return [
        {
            "memory_id": memory.memory_id,
            "scope": memory.scope.value,
            "scope_id": memory.scope_id,
            "summary": memory.summary,
            "freshness": memory.freshness.value,
            "source_refs": [ref.model_dump(mode="json") for ref in memory.source_refs],
            "superseded_by": memory.superseded_by,
        }
        for memory in state.memory_entries
        if memory.freshness is MemoryFreshness.CURRENT
    ]


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


def _serialize_operator_messages(state: OperationState, limit: int = 5) -> list[dict[str, object]]:
    recent = [
        message for message in state.operator_messages if not message.dropped_from_context
    ][-limit:]
    return [
        {
            "message_id": message.message_id,
            "submitted_at": message.submitted_at.isoformat(),
            "text": message.text,
        }
        for message in recent
    ]


def _serialize_agent_descriptors(state: OperationState) -> list[dict[str, object]]:
    raw = state.runtime_hints.metadata.get("available_agent_descriptors")
    if not isinstance(raw, list):
        return []
    rendered: list[dict[str, object]] = []
    for item in raw:
        if isinstance(item, dict):
            rendered.append(item)
    return rendered


def _serialize_attention_requests(
    state: OperationState,
    *,
    statuses: set[str],
) -> list[dict[str, object]]:
    rendered: list[dict[str, object]] = []
    for attention in state.attention_requests:
        if attention.status.value not in statuses:
            continue
        rendered.append(
            {
                "attention_id": attention.attention_id,
                "type": attention.attention_type.value,
                "status": attention.status.value,
                "blocking": attention.blocking,
                "title": attention.title,
                "question": attention.question,
                "context_brief": attention.context_brief,
                "suggested_options": attention.suggested_options,
                "target_scope": attention.target_scope.value,
                "target_id": attention.target_id,
                "answer_text": attention.answer_text,
            }
        )
    return rendered


def _attention_requests_json(state: OperationState, *, statuses: set[str]) -> str:
    return json.dumps(
        _serialize_attention_requests(state, statuses=statuses),
        ensure_ascii=True,
    )


def _project_policy_json(state: OperationState) -> str:
    policy_entries = [
        {
            "policy_id": policy.policy_id,
            "title": policy.title,
            "category": policy.category.value,
            "rule_text": policy.rule_text,
            "applicability": policy.applicability.model_dump(mode="json"),
            "rationale": policy.rationale,
            "source_refs": [ref.model_dump(mode="json") for ref in policy.source_refs],
        }
        for policy in state.active_policies
    ]
    return json.dumps(policy_entries, ensure_ascii=True)


def build_permission_decision_prompt(
    state: OperationState,
    *,
    request_payload: dict[str, object],
    active_policy_payload: list[dict[str, object]],
) -> str:
    if state.involvement_level.value == "approval_heavy":
        involvement_instruction = (
            "Current involvement level is approval_heavy. Escalation to a blocking human "
            "attention request is allowed when human judgment is genuinely required."
        )
    elif state.involvement_level.value == "collaborative":
        involvement_instruction = (
            "Current involvement level is collaborative. Escalate this request to a human "
            "when it involves a significant choice the user would want to make themselves "
            "(major route changes, destructive actions, project-shaping decisions). "
            "For routine or clearly safe/unsafe requests, decide autonomously."
        )
    else:
        involvement_instruction = (
            f"Current involvement level is {state.involvement_level.value}. Do not escalate "
            "this request to a human. The operator must decide autonomously by returning "
            "decision=approve or decision=reject."
        )
    return (
        "You are the operator's permission evaluator.\n"
        "Decide whether this ACP permission request should be approved now, rejected now, "
        "or escalated to a blocking human attention request.\n\n"
        f"{involvement_instruction}\n\n"
        "Decision rules:\n"
        "- Be conservative.\n"
        "- Do not approve broad, destructive, or weakly understood requests.\n"
        "- Use active autonomy policies if they clearly support the request.\n"
        "- Return decision=approve only when the request is narrow, understandable, "
        "and safe in context.\n"
        "- Return decision=reject when the request is clearly unsafe or out of policy.\n"
        "- Return decision=escalate only when the current involvement level explicitly allows "
        "human escalation and human judgment is needed.\n"
        "- If you escalate, provide short suggested_options the human can choose from.\n"
        "- If you approve or reject and the rule is reusable, provide a short policy_title and "
        "policy_rule_text suitable for a project autonomy policy.\n\n"
        f"Objective:\n{state.objective_state.objective}\n\n"
        f"Harness:\n{state.objective_state.harness_instructions}\n\n"
        f"Active policies:\n{json.dumps(active_policy_payload, ensure_ascii=True)}\n\n"
        f"Permission request:\n{json.dumps(request_payload, ensure_ascii=True)}\n"
    )


def _policy_coverage_json(state: OperationState) -> str:
    return json.dumps(state.policy_coverage.model_dump(mode="json"), ensure_ascii=True)


def build_decision_prompt(state: OperationState) -> str:
    available_agents = state.policy.allowed_agents or ["claude_acp"]
    run_mode = str(state.runtime_hints.metadata.get("run_mode", "attached"))
    involvement_instruction = {
        "unattended": (
            "Current involvement level is unattended. Prefer defer-and-continue over global "
            "blocking when safe. Use REQUEST_CLARIFICATION only for hard-stop conditions that "
            "cannot be deferred."
        ),
        "auto": (
            "Current involvement level is auto. Surface conceptually novel situations and policy "
            "gaps as attention requests instead of silently inventing policy."
        ),
        "collaborative": (
            "Current involvement level is collaborative. Ask more readily before strategic route "
            "changes, major reprioritization, or project-shaping decisions."
        ),
        "approval_heavy": (
            "Current involvement level is approval_heavy. Prefer asking before consequential "
            "decisions and avoid assuming approval on sensitive changes."
        ),
    }[state.involvement_level.value]
    wait_instruction = (
        "WAIT_FOR_AGENT is unavailable in this runtime because background wakeups are not "
        "enabled yet. Do not return WAIT_FOR_AGENT.\n"
        if state.runtime_hints.metadata.get("background_runtime_mode")
        not in {"resumable_wakeup", "attached_live"}
        else (
            "WAIT_FOR_AGENT is valid only when there is a real in-flight dependency and you "
            "must include a blocking focus. In attached mode the scheduler remains interruptible "
            "while waiting, so do not use WAIT_FOR_AGENT to monopolize the run on one agent.\n"
        )
    )
    run_mode_instruction = (
        "Current run mode is attached. Prefer direct serial progress over background orchestration."
        "\n"
        if run_mode == "attached"
        else (
            "Current run mode is resumable. You may use background-wait semantics when they are "
            "explicitly valid.\n"
        )
    )
    separate_phase_instruction = ""
    if state.goal.metadata.get("requires_separate_agent_runs") is True:
        separate_phase_instruction = (
            "This goal requires separate agent runs for separate phases. Finish phase 1, "
            "evaluate it, and only then start a new run for phase 2.\n"
        )
    continuation_instruction = ""
    if state.goal.metadata.get("requires_same_agent_session") is True:
        continuation_instruction = (
            "This goal prefers reusing the same session when prior thread context matters. "
            "If a reusable compatible session exists for the active task, prefer "
            "CONTINUE_AGENT.\n"
        )
    one_shot_instruction = ""
    if state.goal.metadata.get("prefer_one_shot_agent_runs") is True:
        one_shot_instruction += (
            "This goal prefers one-shot runs by default when no follow-up in the same session is "
            "expected.\n"
        )
    if state.goal.metadata.get("prefer_one_shot_for_swarm") is True:
        one_shot_instruction += (
            "This goal specifically prefers /swarm-style runs to be one-shot unless explicit "
            "session reuse is required.\n"
        )
    return (
        "You are the operator brain for a task-first multi-agent control plane.\n"
        "Choose the next structured action and, if needed, propose task graph updates.\n"
        "Tasks are the primary planning unit. Sessions are execution resources.\n"
        "You may create or update tasks, set focus_task_id, and choose an immediate action.\n"
        "Only choose an agent listed in allowed_agents.\n"
        "The instruction field is the exact message that will be sent to the agent.\n"
        "For START_AGENT and CONTINUE_AGENT, set workfront_key to a short stable identifier for "
        "the bounded delegated front. Reuse the same workfront_key only when it is truly the same "
        "concrete front; change it when replanning to a different slice.\n"
        "Do not paste the whole operator prompt, full history, or policy block into instruction.\n"
        "Send only the final actionable directive the agent should execute next, with the "
        "minimal extra context the agent actually needs.\n"
        "For reusable sessions, prefer short follow-ups like 'Continue.' or one precise next "
        "step instead of restating the whole objective.\n"
        "For implementation work, require the agent to commit and push after each completed "
        "feature-sized slice instead of batching many features into one unpublished change.\n"
        "If the repository does not exist remotely yet, prefer having the agent create a "
        "private repository and use gh for repository creation, push, and related GitHub "
        "operations when gh is available.\n"
        "If the agent raises a complex open question without a clear bounded choice and the "
        "decision cannot be made safely from the current context alone, ask the agent to run "
        "swarm mode grounded in the relevant VISION or product vision, then decide based on "
        "that swarm outcome instead of answering ad hoc.\n"
        "The deterministic scheduler will reject illegal dependency transitions, unsupported "
        "session reuse, and invalid waits.\n"
        "When starting a new session, you may set session_name to a short human-readable name.\n"
        "Set one_shot=true for disposable runs that should not be resumed.\n"
        f"{separate_phase_instruction}"
        f"{continuation_instruction}"
        f"{one_shot_instruction}"
        f"{wait_instruction}"
        "If a task is blocked by dependencies, do not force it to running.\n"
        "Use APPLY_POLICY only for an actual policy/context application step.\n"
        "If no executable repository-progress action is currently available and the operation "
        "must wait for a real non-human change, use WAIT_FOR_MATERIAL_CHANGE with a "
        "blocking_focus that explains the dependency barrier.\n"
        "Treat Policy coverage status=uncovered as a deterministic signal that this project "
        "scope already has policy, but none currently applies. If the next step needs a "
        "reusable project rule or precedent, prefer attention_type=policy_gap instead of "
        "inventing one silently.\n"
        "When the next step needs a reusable project rule or precedent before acting, set "
        "metadata.requires_policy_decision=true. Include metadata.policy_question when the "
        "policy question should differ from rationale. The runtime may convert a non-terminal "
        "decision into policy_gap attention when project policy coverage is missing.\n"
        "Use STOP only when the objective has been achieved and should end successfully now.\n"
        "Use FAIL when the objective should end as failed and the failure reason should be "
        "surfaced explicitly.\n"
        "Use REQUEST_CLARIFICATION only when the user must answer.\n"
        "When you use REQUEST_CLARIFICATION, also set attention_type, attention_title, "
        "attention_context, and attention_options when useful.\n"
        "Choose attention_type=question for a bounded missing fact or preference.\n"
        "Choose attention_type=policy_gap when the operator needs a reusable project rule or "
        "precedent before proceeding confidently.\n"
        "Choose attention_type=novel_strategic_fork when the operator has reached a "
        "consequential route choice that is not a simple factual question.\n"
        "Choose attention_type=blocked_external_dependency only for a real outside-the-operator "
        "dependency or gate.\n"
        "Do not use attention_type=approval_request for REQUEST_CLARIFICATION; that type is "
        "reserved for agent-side approval/escalation waits.\n\n"
        f"{run_mode_instruction}"
        f"{involvement_instruction}\n\n"
        f"Objective:\n{state.objective_state.objective}\n\n"
        "Harness Instructions:\n"
        f"{state.objective_state.harness_instructions or '(none)'}\n\n"
        f"Involvement Level:\n{state.involvement_level.value}\n\n"
        "Success Criteria:\n"
        f"{json.dumps(state.objective_state.success_criteria, ensure_ascii=True)}\n\n"
        f"Active project policy:\n{_project_policy_json(state)}\n\n"
        f"Policy coverage:\n{_policy_coverage_json(state)}\n\n"
        f"Goal metadata:\n{json.dumps(state.goal.metadata, ensure_ascii=True)}\n\n"
        f"Allowed agents:\n{json.dumps(available_agents, ensure_ascii=True)}\n\n"
        "Available Agent Descriptors:\n"
        f"{json.dumps(_serialize_agent_descriptors(state), ensure_ascii=True)}\n\n"
        f"Current status:\n{state.status.value}\n\n"
        f"Current focus:\n{json.dumps(_serialize_focus(state), ensure_ascii=True)}\n\n"
        f"Tasks:\n{json.dumps(_serialize_tasks(state), ensure_ascii=True)}\n\n"
        f"Sessions:\n{json.dumps(_serialize_sessions(state), ensure_ascii=True)}\n\n"
        f"Current memory:\n{json.dumps(_serialize_memory_entries(state), ensure_ascii=True)}\n\n"
        "Recent Operator Messages:\n"
        f"{json.dumps(_serialize_operator_messages(state), ensure_ascii=True)}\n\n"
        "Open Attention Requests:\n"
        f"{_attention_requests_json(state, statuses={'open'})}\n\n"
        "Answered Attention Pending Replan:\n"
        f"{_attention_requests_json(state, statuses={'answered'})}\n\n"
        "Recent decision history:\n"
        f"{json.dumps(_serialize_recent_decisions(state), ensure_ascii=True)}\n\n"
        "Recent agent outputs (last agent turn output_text per iteration):\n"
        "Use this to detect orientation loops (agent reads files and reports assessment without "
        "making progress) and repeated identical outputs. If you see the same assessment text "
        "appearing across multiple iterations without any task status change, the agent is stuck "
        "and you should change strategy (e.g., provide a more specific directive, decompose the "
        "task further, or escalate).\n"
        f"{json.dumps(_serialize_recent_agent_outputs(state), ensure_ascii=True)}\n\n"
        "Recent iteration history:\n"
        f"{json.dumps(_serialize_recent_iterations(state), ensure_ascii=True)}"
    )


def build_evaluation_prompt(state: OperationState) -> str:
    return (
        "You are evaluating whether the operator should continue.\n"
        "Return a structured evaluation only.\n"
        "Mark goal_satisfied=true only when the latest deliverable actually satisfies the "
        "requested final artifact.\n"
        "Do not treat harness compliance or execution-policy compliance as objective success.\n"
        "If the latest agent result clearly asks for human approval, escalation, or access "
        "outside the current sandbox, prefer blocking for clarification unless another "
        "available path can continue safely.\n"
        "If important tasks remain open or blocked without resolution, continue unless the "
        "objective is irrecoverably blocked.\n\n"
        f"Objective:\n{state.objective_state.objective}\n\n"
        "Harness Instructions:\n"
        f"{state.objective_state.harness_instructions or '(none)'}\n\n"
        "Success Criteria:\n"
        f"{json.dumps(state.objective_state.success_criteria, ensure_ascii=True)}\n\n"
        f"Active project policy:\n{_project_policy_json(state)}\n\n"
        f"Policy coverage:\n{_policy_coverage_json(state)}\n\n"
        f"Tasks:\n{json.dumps(_serialize_tasks(state), ensure_ascii=True)}\n\n"
        f"Current memory:\n{json.dumps(_serialize_memory_entries(state), ensure_ascii=True)}\n\n"
        "Recent iteration history:\n"
        f"{json.dumps(_serialize_recent_iterations(state), ensure_ascii=True)}"
    )


def build_question_answer_prompt(state: OperationState, question: str) -> str:
    return (
        "You are the operator brain's read-only question answering surface.\n"
        "Answer the user's question about this single operation using only the provided operation "
        "state.\n"
        "This surface is strictly read-only: do not claim to have modified operation state, "
        "scheduled work, answered attention, or performed any side effect.\n"
        "If the provided state is insufficient, say what is missing.\n"
        "Prefer concise, direct answers grounded in the operation context.\n\n"
        f"Objective:\n{state.objective_state.objective}\n\n"
        "Harness Instructions:\n"
        f"{state.objective_state.harness_instructions or '(none)'}\n\n"
        "Success Criteria:\n"
        f"{json.dumps(state.objective_state.success_criteria, ensure_ascii=True)}\n\n"
        f"Current status:\n{state.status.value}\n\n"
        f"Current focus:\n{json.dumps(_serialize_focus(state), ensure_ascii=True)}\n\n"
        f"Tasks:\n{json.dumps(_serialize_tasks(state), ensure_ascii=True)}\n\n"
        f"Sessions:\n{json.dumps(_serialize_sessions(state), ensure_ascii=True)}\n\n"
        f"Current memory:\n{json.dumps(_serialize_memory_entries(state), ensure_ascii=True)}\n\n"
        "Open Attention Requests:\n"
        f"{_attention_requests_json(state, statuses={'open'})}\n\n"
        "Answered Attention Pending Replan:\n"
        f"{_attention_requests_json(state, statuses={'answered'})}\n\n"
        "Recent Operator Messages:\n"
        f"{json.dumps(_serialize_operator_messages(state), ensure_ascii=True)}\n\n"
        "Recent iteration history:\n"
        f"{json.dumps(_serialize_recent_iterations(state), ensure_ascii=True)}\n\n"
        "User question:\n"
        f"{question}"
    )


def build_converse_operation_prompt(
    state: OperationState,
    *,
    user_message: str,
    conversation_history: list[dict[str, str]],
    context_level: str,
    recent_events: list[dict[str, object]] | None,
) -> str:
    iteration_limit = 20 if context_level == "full" else 5
    recent_iterations_json = json.dumps(
        _serialize_recent_iterations(state, limit=iteration_limit),
        ensure_ascii=True,
    )
    context_sections = [
        f"Objective:\n{state.objective_state.objective}",
        "Harness Instructions:\n"
        f"{state.objective_state.harness_instructions or '(none)'}",
        f"Current status:\n{state.status.value}",
        f"Current focus:\n{json.dumps(_serialize_focus(state), ensure_ascii=True)}",
        "Open Attention Requests:\n"
        f"{_attention_requests_json(state, statuses={'open'})}",
        f"Recent iteration history:\n{recent_iterations_json}",
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
                [item for item in operation.attention_requests if item.status.value == "open"]
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
        "When a write action is appropriate, propose exactly one canonical "
        "CLI command string with an explicit operation id.\n"
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


def build_turn_summary_prompt(
    state: OperationState,
    *,
    operator_instruction: str,
    result: AgentResult,
) -> str:
    return (
        "You are the operator brain's turn summarizer.\n"
        "Return only structured JSON.\n"
        "Summarize what the agent actually accomplished in this completed turn.\n"
        "Do not overclaim. Distinguish attempted work from completed work.\n"
        "If the turn only inspected, compared routes, or documented blockers, say that directly.\n"
        "If no repo change or proof/product delta occurred, say so explicitly.\n"
        "Set progress_class to one of: material_delta, inspection_only, no_verified_delta.\n"
        "Use blocker_keys for short stable blocker-family tags when blockers repeat across turns.\n"
        "Recommended next step should be the most concrete truthful next move "
        "implied by the result.\n\n"
        f"Objective:\n{state.objective_state.objective}\n\n"
        "Harness Instructions:\n"
        f"{state.objective_state.harness_instructions or '(none)'}\n\n"
        "Success Criteria:\n"
        f"{json.dumps(state.objective_state.success_criteria, ensure_ascii=True)}\n\n"
        "Operator instruction for this turn:\n"
        f"{operator_instruction}\n\n"
        "Current task board:\n"
        f"{json.dumps(_serialize_tasks(state), ensure_ascii=True)}\n\n"
        "Current memory:\n"
        f"{json.dumps(_serialize_memory_entries(state), ensure_ascii=True)}\n\n"
        "Completed agent result:\n"
        f"{result.output_text}"
    )


def build_artifact_normalization_prompt(goal: OperationGoal, result: AgentResult) -> str:
    instruction = goal.metadata.get("result_normalization_instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        raise RuntimeError("Goal does not provide result_normalization_instruction.")
    return (
        "You are the operator brain's artifact normalizer.\n"
        "Take the raw agent result and rewrite or extract only the final artifact needed "
        "by the operator.\n"
        "Preserve substantive content. Remove process scaffolding, meta commentary, "
        "and agent-specific wrappers when they are not part of the desired artifact.\n"
        "Return structured output only.\n\n"
        f"Objective:\n{goal.objective_text}\n\n"
        f"Success criteria:\n{json.dumps(goal.success_criteria, ensure_ascii=True)}\n\n"
        f"Goal metadata:\n{json.dumps(goal.metadata, ensure_ascii=True)}\n\n"
        f"Normalization instruction:\n{instruction}\n\n"
        "Raw agent output:\n"
        f"{result.output_text}"
    )


def build_memory_distillation_prompt(
    state: OperationState,
    *,
    scope: str,
    scope_id: str,
    source_refs: list[dict[str, str]],
    instruction: str,
) -> str:
    return (
        "You are the operator brain's memory distiller.\n"
        "Write a compact durable memory entry derived from the provided sources.\n"
        "Do not invent facts not supported by the sources.\n"
        "The memory entry must be useful for future continuation and should exclude irrelevant "
        "process chatter.\n"
        "Return structured output only.\n\n"
        f"Objective:\n{state.objective_state.objective}\n\n"
        "Harness Instructions:\n"
        f"{state.objective_state.harness_instructions or '(none)'}\n\n"
        f"Tasks:\n{json.dumps(_serialize_tasks(state), ensure_ascii=True)}\n\n"
        f"Scope: {scope}\n"
        f"Scope id: {scope_id}\n"
        f"Source refs: {json.dumps(source_refs, ensure_ascii=True)}\n"
        f"Instruction: {instruction}\n\n"
        "Recent iteration history:\n"
        f"{json.dumps(_serialize_recent_iterations(state), ensure_ascii=True)}"
    )
