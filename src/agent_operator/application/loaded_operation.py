from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from agent_operator.domain import (
    AgentResult,
    AgentSessionHandle,
    ArtifactRecord,
    BackgroundRunHandle,
    FocusKind,
    MemoryFreshness,
    MemoryScope,
    OperationState,
    SessionRecord,
    SessionRecordStatus,
    SessionReusePolicy,
    TaskDraft,
    TaskPatch,
    TaskState,
    TaskStatus,
)
from agent_operator.protocols import AgentSessionManager


class LoadedOperation:
    """Own one loaded operation's local state mechanics."""

    def __init__(self, *, attached_session_registry: AgentSessionManager) -> None:
        self._attached_session_registry = attached_session_registry

    def attach_initial_sessions(
        self,
        state: OperationState,
        attached_sessions: list[AgentSessionHandle],
    ) -> None:
        include_agent_key = len(self.allowed_adapters(state)) > 1
        root_task = self.find_task(state, state.objective_state.root_task_id or "")
        for handle in attached_sessions:
            decorated = self.decorate_session_handle(
                handle,
                handle.session_name,
                include_agent_key,
                handle.one_shot,
            )
            record = self.ensure_session_record(state, decorated)
            record.status = SessionRecordStatus.IDLE
            record.updated_at = datetime.now(UTC)
            if root_task is not None and root_task.linked_session_id is None:
                root_task.linked_session_id = decorated.session_id
                root_task.assigned_agent = decorated.adapter_key
                root_task.updated_at = datetime.now(UTC)
        active = next(
            (record.handle for record in state.sessions if not record.handle.one_shot),
            None,
        )
        if active is not None and root_task is not None and root_task.linked_session_id is None:
            root_task.linked_session_id = active.session_id

    def resolve_working_directory(
        self,
        state: OperationState,
        task: TaskState | None,
        session: AgentSessionHandle | None = None,
    ) -> Path:
        candidates: list[AgentSessionHandle] = []
        if session is not None:
            candidates.append(session)
        if task is not None and task.linked_session_id is not None:
            record = self.find_session_record(state, task.linked_session_id)
            if record is not None:
                candidates.append(record.handle)
        focused_session = self.focused_session_handle(state)
        if focused_session is not None:
            candidates.append(focused_session)
        latest_non_one_shot = self.latest_non_one_shot_session_handle(state)
        if latest_non_one_shot is not None:
            candidates.append(latest_non_one_shot)
        for candidate in candidates:
            working_directory = candidate.metadata.get("working_directory")
            if isinstance(working_directory, str) and working_directory:
                return Path(working_directory)
        objective_working_directory = state.objective_state.metadata.get("working_directory")
        if isinstance(objective_working_directory, str) and objective_working_directory:
            return Path(objective_working_directory)
        return Path.cwd()

    def apply_task_mutations(
        self,
        state: OperationState,
        new_tasks: list[TaskDraft],
        task_updates: list[TaskPatch],
    ) -> None:
        for draft in new_tasks:
            state.tasks.append(
                TaskState(
                    title=draft.title,
                    goal=draft.goal,
                    definition_of_done=draft.definition_of_done,
                    brain_priority=draft.brain_priority,
                    effective_priority=draft.brain_priority,
                    assigned_agent=draft.assigned_agent,
                    session_policy=draft.session_policy,
                    dependencies=list(draft.dependencies),
                    notes=list(draft.notes),
                    status=TaskStatus.PENDING,
                )
            )
        for patch in task_updates:
            task = self.find_task(state, patch.task_id)
            if task is None:
                continue
            if patch.title is not None:
                task.title = patch.title
            if patch.goal is not None:
                task.goal = patch.goal
            if patch.definition_of_done is not None:
                task.definition_of_done = patch.definition_of_done
            if patch.status is not None:
                task.status = patch.status
                if patch.status in {TaskStatus.PENDING, TaskStatus.READY, TaskStatus.BLOCKED}:
                    self.mark_task_memory_stale(state, task.task_id)
            if patch.brain_priority is not None:
                task.brain_priority = patch.brain_priority
            if patch.assigned_agent is not None:
                task.assigned_agent = patch.assigned_agent
            if patch.linked_session_id is not None:
                task.linked_session_id = patch.linked_session_id
            if patch.session_policy is not None:
                task.session_policy = patch.session_policy
            for note in patch.append_notes:
                task.notes.append(note)
            for ref in patch.add_memory_refs:
                if ref not in task.memory_refs:
                    task.memory_refs.append(ref)
            for ref in patch.add_artifact_refs:
                if ref not in task.artifact_refs:
                    task.artifact_refs.append(ref)
            task.updated_at = datetime.now(UTC)

    def resolve_focus_task(
        self,
        state: OperationState,
        requested_task_id: str | None,
    ) -> TaskState | None:
        if requested_task_id:
            task = self.find_task(state, requested_task_id)
            if task is not None:
                return task
        if state.current_focus and state.current_focus.kind is FocusKind.TASK:
            task = self.find_task(state, state.current_focus.target_id)
            if task is not None:
                return task
        return self.highest_priority_task(state, statuses={TaskStatus.READY, TaskStatus.RUNNING})

    def find_task(self, state: OperationState, task_id: str) -> TaskState | None:
        for task in state.tasks:
            if task.task_id == task_id:
                return task
        return None

    def find_iteration_for_session(
        self,
        state: OperationState,
        session_id: str,
        preferred_iteration: int | None = None,
    ):
        if preferred_iteration is not None:
            for iteration in state.iterations:
                if iteration.index == preferred_iteration:
                    return iteration
        for iteration in reversed(state.iterations):
            if iteration.session is not None and iteration.session.session_id == session_id:
                return iteration
        return None

    def highest_priority_task(
        self,
        state: OperationState,
        *,
        statuses: set[TaskStatus],
    ) -> TaskState | None:
        candidates = [task for task in state.tasks if task.status in statuses]
        if not candidates:
            return None
        return sorted(candidates, key=lambda task: (-task.effective_priority, task.created_at))[0]

    def allowed_adapters(self, state: OperationState) -> set[str]:
        return (
            set(state.policy.allowed_agents)
            if state.policy.allowed_agents
            else set(self._attached_session_registry.keys())
        )

    def upsert_session_record(
        self,
        state: OperationState,
        session: AgentSessionHandle,
        task: TaskState | None,
    ) -> SessionRecord:
        record = self.ensure_session_record(state, session)
        if task is not None and task.task_id not in record.bound_task_ids:
            record.bound_task_ids.append(task.task_id)
        record.updated_at = datetime.now(UTC)
        return record

    def find_session_record(
        self,
        state: OperationState,
        session_id: str | None,
    ) -> SessionRecord | None:
        if session_id is None:
            return None
        for record in state.sessions:
            if record.session_id == session_id:
                return record
        return None

    def ensure_session_record(
        self,
        state: OperationState,
        session: AgentSessionHandle,
    ) -> SessionRecord:
        for record in state.sessions:
            if record.session_id == session.session_id:
                record.handle = session
                return record
        record = SessionRecord(handle=session)
        state.sessions.append(record)
        return record

    def upsert_background_run(
        self,
        state: OperationState,
        run: BackgroundRunHandle,
        session_id: str | None,
        task_id: str | None,
    ) -> None:
        run = run.model_copy(
            update={
                "session_id": session_id or run.session_id,
                "task_id": task_id or run.task_id,
            }
        )
        for index, existing in enumerate(state.background_runs):
            if existing.run_id == run.run_id:
                state.background_runs[index] = run
                return
        state.background_runs.append(run)

    def find_background_run(
        self,
        state: OperationState,
        run_id: str,
    ) -> BackgroundRunHandle | None:
        for run in state.background_runs:
            if run.run_id == run_id:
                return run
        return None

    def decorate_background_session(
        self,
        run: BackgroundRunHandle,
        session_name: str | None,
        state: OperationState,
        *,
        fallback: AgentSessionHandle | None = None,
        one_shot: bool = False,
    ) -> AgentSessionHandle:
        if fallback is not None:
            handle = fallback.model_copy(update={"one_shot": one_shot})
        else:
            session_id = run.session_id or f"background-{run.run_id}"
            handle = AgentSessionHandle(
                adapter_key=run.adapter_key,
                session_id=session_id,
                session_name=session_name,
                one_shot=one_shot,
                metadata={},
            )
        metadata = dict(handle.metadata)
        metadata["background_run_id"] = run.run_id
        if run.raw_ref:
            metadata["background_log_path"] = run.raw_ref
        include_agent_key = len(self.allowed_adapters(state)) > 1
        return self.decorate_session_handle(
            handle.model_copy(update={"metadata": metadata}),
            session_name or handle.session_name,
            include_agent_key,
            handle.one_shot,
        )

    def resolve_session_for_continuation(
        self,
        state: OperationState,
        requested_session_id: str | None,
        task: TaskState | None,
    ) -> SessionRecord | None:
        session_id = requested_session_id or (
            task.linked_session_id if task is not None else None
        )
        if (
            session_id is None
            and state.current_focus is not None
            and state.current_focus.kind is FocusKind.SESSION
        ):
            session_id = state.current_focus.target_id
        if session_id is None and task is not None:
            latest_task_session = self.latest_bound_non_one_shot_session(state, task.task_id)
            if latest_task_session is not None:
                session_id = latest_task_session.session_id
        if session_id is None:
            waiting_matches = [
                record
                for record in state.sessions
                if not record.handle.one_shot
                and record.status is SessionRecordStatus.WAITING
            ]
            if len(waiting_matches) == 1:
                return waiting_matches[0]
        if session_id is None:
            return None
        for record in state.sessions:
            if record.session_id == session_id and not record.handle.one_shot:
                return record
        return None

    def resolve_reusable_idle_session(
        self,
        state: OperationState,
        adapter_key: str,
        task: TaskState | None,
    ) -> SessionRecord | None:
        preferred_ids: list[str] = []
        if task is not None and task.linked_session_id is not None:
            preferred_ids.append(task.linked_session_id)
        if state.current_focus is not None and state.current_focus.kind is FocusKind.SESSION:
            preferred_ids.append(state.current_focus.target_id)
        for session_id in preferred_ids:
            record = self.find_session_record(state, session_id)
            if (
                record is not None
                and record.adapter_key == adapter_key
                and record.status is SessionRecordStatus.IDLE
                and not record.handle.one_shot
            ):
                return record
        idle_matches = [
            record
            for record in state.sessions
            if record.adapter_key == adapter_key
            and record.status is SessionRecordStatus.IDLE
            and not record.handle.one_shot
        ]
        if not idle_matches:
            return None
        return sorted(idle_matches, key=lambda item: item.updated_at, reverse=True)[0]

    def resolved_session_reuse_policy(self, state: OperationState) -> SessionReusePolicy:
        resolved_profile = state.goal.metadata.get("resolved_project_profile")
        if isinstance(resolved_profile, dict):
            raw_policy = resolved_profile.get("session_reuse_policy")
            if isinstance(raw_policy, str) and raw_policy:
                return SessionReusePolicy(raw_policy)
        return SessionReusePolicy.ALWAYS_NEW

    def decorate_session_handle(
        self,
        handle: AgentSessionHandle,
        session_name: str | None,
        include_agent_key: bool,
        one_shot: bool,
    ) -> AgentSessionHandle:
        display_name = session_name
        if session_name and include_agent_key:
            display_name = f"{session_name} [{handle.adapter_key}]"
        metadata = dict(handle.metadata)
        if session_name:
            metadata["session_display_name"] = display_name
        if one_shot:
            metadata["one_shot"] = "true"
        return handle.model_copy(
            update={
                "session_name": session_name,
                "display_name": display_name,
                "one_shot": one_shot,
                "metadata": metadata,
            }
        )

    def mark_task_memory_stale(self, state: OperationState, task_id: str) -> None:
        for memory in state.memory_entries:
            if (
                memory.scope is MemoryScope.TASK
                and memory.scope_id == task_id
                and memory.freshness is MemoryFreshness.CURRENT
            ):
                memory.freshness = MemoryFreshness.STALE
                memory.updated_at = datetime.now(UTC)

    def store_result_artifact(
        self,
        state: OperationState,
        task: TaskState | None,
        session: AgentSessionHandle,
        result: AgentResult,
    ) -> ArtifactRecord:
        artifact = ArtifactRecord(
            kind="agent_result",
            producer=session.adapter_key,
            task_id=task.task_id if task is not None else None,
            session_id=session.session_id,
            content=result.output_text,
        )
        state.artifacts.append(artifact)
        return artifact

    def mark_root_task_terminal(self, state: OperationState, status: TaskStatus) -> None:
        if state.objective_state.root_task_id is None:
            return
        root = self.find_task(state, state.objective_state.root_task_id)
        if root is not None:
            root.status = status
            root.updated_at = datetime.now(UTC)

    def find_latest_result(self, state: OperationState) -> AgentResult | None:
        for iteration in reversed(state.iterations):
            if iteration.result is not None:
                return iteration.result
        return None

    def latest_result_for_session(
        self,
        state: OperationState,
        session_id: str | None,
    ) -> AgentResult | None:
        if session_id is None:
            focused = self.focused_session_handle(state)
            if focused is not None:
                session_id = focused.session_id
        for iteration in reversed(state.iterations):
            if iteration.result is not None and iteration.result.session_id == session_id:
                return iteration.result
        return None

    def focused_session_handle(self, state: OperationState) -> AgentSessionHandle | None:
        if state.current_focus is None or state.current_focus.kind is not FocusKind.SESSION:
            return None
        record = self.find_session_record(state, state.current_focus.target_id)
        return record.handle if record is not None else None

    def latest_non_one_shot_session_handle(
        self,
        state: OperationState,
    ) -> AgentSessionHandle | None:
        matches = [record for record in state.sessions if not record.handle.one_shot]
        if not matches:
            return None
        matches.sort(key=lambda item: (item.updated_at, item.created_at), reverse=True)
        return matches[0].handle

    def latest_bound_non_one_shot_session(
        self,
        state: OperationState,
        task_id: str,
    ) -> SessionRecord | None:
        matches = [
            record
            for record in state.sessions
            if task_id in record.bound_task_ids and not record.handle.one_shot
        ]
        if not matches:
            return None
        matches.sort(
            key=lambda item: (
                item.latest_iteration or -1,
                item.updated_at,
                item.created_at,
            ),
            reverse=True,
        )
        return matches[0]

    def session_has_pending_result_slot(self, record: SessionRecord) -> bool:
        if record.latest_iteration is None:
            return False
        if record.last_result_iteration is None:
            return True
        return record.last_result_iteration < record.latest_iteration

    def build_restart_instruction(self, state: OperationState, instruction: str) -> str:
        latest_result = self.find_latest_result(state)
        if latest_result is None or not latest_result.output_text:
            return instruction
        return (
            "Previous session context was not reusable, so continue from the latest result.\n\n"
            f"Latest result:\n{latest_result.output_text}\n\n"
            f"Next instruction:\n{instruction}"
        )
