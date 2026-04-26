from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import cast
from uuid import uuid4

import anyio

from agent_operator.application.commands.operation_delivery_commands import (
    OperationDeliveryCommandService,
    OperatorServiceLike,
)
from agent_operator.application.delivery_surface import DeliverySurfaceService
from agent_operator.application.live_feed import (
    LiveFeedEnvelope,
    parse_canonical_live_feed_line,
    parse_legacy_live_feed_line,
)
from agent_operator.application.queries.operation_projections import OperationProjectionService
from agent_operator.application.queries.operation_resolution import OperationResolutionService
from agent_operator.application.queries.operation_state_views import OperationStateViewService
from agent_operator.application.queries.operation_status_queries import OperationStatusQueryService
from agent_operator.application.service import OperatorService
from agent_operator.bootstrap import (
    build_background_run_inspection_store,
    build_command_inbox,
    build_event_sink,
    build_replay_service,
    build_service,
    build_store,
    build_trace_store,
    build_wakeup_inbox,
)
from agent_operator.cli.helpers.rendering import (
    build_runtime_alert,
    find_task_by_display_id,
    render_inspect_summary,
    render_status_brief,
    render_status_summary,
)
from agent_operator.config import OperatorSettings
from agent_operator.domain import (
    AttentionRequest,
    AttentionStatus,
    BackgroundRuntimeMode,
    ExecutionBudget,
    OperationBrief,
    OperationGoal,
    OperationPolicy,
    OperationState,
    OperationStatus,
    OperationSummary,
    RunEvent,
    RunMode,
    RunOptions,
    SessionStatus,
    TaskStatus,
)
from agent_operator.protocols import OperationCommandInbox, OperationStore
from agent_operator.runtime import prepare_operator_settings


class OperatorClient:
    """Thin async context manager for embedding `operator` inside Python code.

    Examples:
        ```python
        from pathlib import Path
        from agent_operator.client import OperatorClient

        async with OperatorClient(data_dir=Path(".operator")) as client:
            operation_id = await client.run("fix auth module", agents=["claude_acp"])
            status = await client.get_status(operation_id)
        ```
    """

    _TERMINAL_STATUSES = {
        OperationStatus.COMPLETED,
        OperationStatus.FAILED,
        OperationStatus.CANCELLED,
        OperationStatus.NEEDS_HUMAN,
    }
    _TERMINAL_EVENT_TYPES = {
        "operation.cycle_finished",
        "operation.completed",
        "operation.failed",
        "operation.cancelled",
    }

    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        event_file_timeout_seconds: float = 30.0,
        stream_poll_interval_seconds: float = 0.1,
        stream_drain_window_seconds: float = 1.0,
    ) -> None:
        """Initialize the SDK client.

        Args:
            data_dir: Operator data directory. When omitted, the client uses the same
                discovery logic as the CLI.
            event_file_timeout_seconds: Maximum time to wait for an operation event file
                to appear before returning from `stream_events`.
            stream_poll_interval_seconds: Poll cadence for event-file tailing.
            stream_drain_window_seconds: Quiet period after a terminal event before
                `stream_events` exits.

        Examples:
            ```python
            client = OperatorClient(data_dir=Path(".operator"))
            ```
        """

        self._configured_data_dir = data_dir
        self._event_file_timeout_seconds = event_file_timeout_seconds
        self._stream_poll_interval_seconds = stream_poll_interval_seconds
        self._stream_drain_window_seconds = stream_drain_window_seconds
        self._settings: OperatorSettings | None = None
        self._store: OperationStore | None = None
        self._command_inbox: OperationCommandInbox | None = None
        self._service: OperatorService | None = None
        self._resolution_service: OperationResolutionService | None = None
        self._delivery_surface: DeliverySurfaceService | None = None

    async def __aenter__(self) -> OperatorClient:
        """Load settings and initialize backing services.

        Returns:
            The entered client instance.

        Examples:
            ```python
            async with OperatorClient() as client:
                operations = await client.list_operations()
            ```
        """

        settings = (
            OperatorSettings()
            if self._configured_data_dir is None
            else OperatorSettings(data_dir=self._configured_data_dir)
        )
        self._settings = prepare_operator_settings(settings)
        self._store = build_store(self._settings)
        self._command_inbox = build_command_inbox(self._settings)
        self._service = build_service(self._settings)
        self._resolution_service = OperationResolutionService(
            store=self._store,
            replay_service=build_replay_service(self._settings),
            event_root=self._settings.data_dir / "operation_events",
            state_view_service=OperationStateViewService(),
        )
        status_queries = OperationStatusQueryService(
            store=self._store,
            projection_service=OperationProjectionService(),
            trace_store=build_trace_store(self._settings),
            background_inspection_store=build_background_run_inspection_store(self._settings),
            wakeup_inspection_store=build_wakeup_inbox(self._settings),
            replay_service=build_replay_service(self._settings),
            state_view_service=OperationStateViewService(),
            build_runtime_alert=build_runtime_alert,
            render_status_brief=render_status_brief,
            render_inspect_summary=render_inspect_summary,
            render_status_summary=render_status_summary,
        )
        commands = OperationDeliveryCommandService(
            store=self._store,
            command_inbox=self._command_inbox,
            service_factory=lambda: cast(
                OperatorServiceLike,
                self._build_operation_service_for_delivery(),
            ),
            find_task_by_display_id=find_task_by_display_id,
            state_loader=self._resolution_service,
        )
        self._delivery_surface = DeliverySurfaceService(
            resolver=self._resolution_service,
            status_queries=status_queries,
            commands=commands,
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        """Release client-owned resources.

        Examples:
            ```python
            client = OperatorClient()
            async with client:
                pass
            ```
        """

        self._service = None
        self._command_inbox = None
        self._store = None
        self._delivery_surface = None
        self._resolution_service = None
        self._settings = None

    async def list_operations(
        self,
        project: str | None = None,
    ) -> list[OperationSummary]:
        """List persisted operations in the current data directory.

        Args:
            project: Optional project label filter. This matches operations whose
                goal metadata carries `project=<value>`.

        Returns:
            Persisted operation summaries.

        Examples:
            ```python
            async with OperatorClient() as client:
                operations = await client.list_operations()
            ```
        """

        states = await self._require_resolution_service().list_canonical_operation_states()
        summaries = [
            OperationSummary(
                operation_id=operation.operation_id,
                status=operation.status,
                objective_prompt=operation.goal.objective_text,
                final_summary=operation.final_summary,
                focus=operation.current_focus.target_id
                if operation.current_focus is not None
                else None,
                runnable_task_count=sum(
                    1 for task in operation.tasks if task.status is TaskStatus.READY
                ),
                reusable_session_count=len(
                    [
                        session
                        for session in operation.sessions
                        if session.status is SessionStatus.IDLE
                    ]
                ),
                updated_at=operation.updated_at,
            )
            for operation in states
        ]
        if project is None:
            return summaries
        filtered: list[OperationSummary] = []
        for summary, operation in zip(summaries, states, strict=True):
            if operation.goal.metadata.get("project") == project:
                filtered.append(summary)
        return filtered

    async def run(
        self,
        goal: str,
        *,
        project: str | None = None,
        agents: list[str] | None = None,
        mode: str = "background",
    ) -> str:
        """Start one operation and return its identifier.

        Args:
            goal: Objective text for the operation.
            project: Optional project label recorded in operation metadata.
            agents: Optional allowed-agent override.
            mode: `"background"` for resumable wakeup mode or `"attached"` for
                inline attached execution.

        Returns:
            The created operation identifier.

        Examples:
            ```python
            async with OperatorClient() as client:
                operation_id = await client.run(
                    "fix auth module",
                    agents=["claude_acp"],
                    mode="background",
                )
            ```
        """

        settings = self._require_settings()
        objective = goal.strip()
        if not objective:
            raise ValueError("goal must not be empty.")
        operation_id = str(uuid4())
        allowed_agents = (
            [item.strip() for item in agents if item.strip()]
            if agents is not None
            else list(settings.default_allowed_agents)
        )
        goal_metadata = {"project": project} if project is not None else {}
        outcome = await self._build_operation_service(operation_id).run(
            OperationGoal(objective=objective, metadata=goal_metadata),
            options=self._build_run_options(mode),
            operation_id=operation_id,
            policy=OperationPolicy(allowed_agents=allowed_agents),
            budget=ExecutionBudget(),
        )
        return outcome.operation_id

    async def get_status(self, operation_id: str) -> OperationBrief:
        """Return a stable brief projection for one operation.

        Args:
            operation_id: Exact operation id, unique prefix, or `"last"`.

        Returns:
            A stable status brief for the selected operation.

        Examples:
            ```python
            async with OperatorClient() as client:
                brief = await client.get_status("last")
            ```
        """

        read_payload = await self._require_delivery_surface().build_read_payload(operation_id)
        resolved_operation_id = read_payload.operation_id
        operation = read_payload.operation
        outcome = read_payload.outcome
        if operation is None and outcome is None:
            raise RuntimeError(f"Operation {resolved_operation_id!r} was not found.")
        if operation is None:
            assert outcome is not None
            return OperationBrief(
                operation_id=resolved_operation_id,
                status=outcome.status,
                objective_brief=outcome.summary,
                latest_outcome_brief=outcome.summary,
            )
        blocker = next(
            (
                item.title
                for item in operation.attention_requests
                if item.status is AttentionStatus.OPEN and item.blocking
            ),
            None,
        )
        summary = outcome.summary if outcome is not None else operation.final_summary
        return OperationBrief(
            operation_id=operation.operation_id,
            status=operation.status,
            scheduler_state=operation.scheduler_state,
            involvement_level=operation.involvement_level,
            objective_brief=operation.goal.objective_text,
            harness_brief=operation.goal.harness_text,
            latest_outcome_brief=summary,
            blocker_brief=blocker,
            updated_at=operation.updated_at,
        )

    async def get_attention(self, operation_id: str) -> list[AttentionRequest]:
        """Return persisted attention requests for one operation.

        Args:
            operation_id: Exact operation id, unique prefix, or `"last"`.

        Returns:
            The operation's persisted attention requests.

        Examples:
            ```python
            async with OperatorClient() as client:
                attention = await client.get_attention("last")
            ```
        """

        operation = await self._load_operation(operation_id)
        return list(operation.attention_requests)

    async def answer_attention(
        self,
        operation_id: str,
        attention_id: str,
        text: str,
    ) -> None:
        """Answer one attention request and resume when the operation is blocked on it.

        Args:
            operation_id: Exact operation id, unique prefix, or `"last"`.
            attention_id: Exact attention request id or unique prefix.
            text: Human answer text.

        Examples:
            ```python
            async with OperatorClient() as client:
                await client.answer_attention("last", "att-123", "Deploy to staging.")
            ```
        """

        answer_text = text.strip()
        if not answer_text:
            raise ValueError("text must not be empty.")
        operation = await self._load_operation(operation_id)
        resolved_attention_id = self._resolve_attention_id(operation, attention_id)
        await self._require_delivery_surface().answer_attention(
            operation.operation_id,
            attention_id=resolved_attention_id,
            text=answer_text,
        )

    async def cancel(
        self,
        operation_id: str,
        *,
        reason: str | None = None,
    ) -> None:
        """Cancel one operation.

        Args:
            operation_id: Exact operation id, unique prefix, or `"last"`.
            reason: Optional cancellation reason recorded by the application layer.

        Examples:
            ```python
            async with OperatorClient() as client:
                await client.cancel("last")
            ```
        """
        cancel_reason = reason.strip() if reason is not None else None
        if cancel_reason == "":
            cancel_reason = None
        await self._require_delivery_surface().cancel_operation(
            operation_id,
            reason=cancel_reason,
        )

    async def message(
        self,
        operation_id: str,
        text: str,
    ) -> None:
        """Send a free-form operator message into the next planning cycle.

        Args:
            operation_id: Exact operation id, unique prefix, or `"last"`.
            text: Human guidance to inject into operator planning context.

        Examples:
            ```python
            async with OperatorClient() as client:
                await client.message("last", "Use the staging branch.")
            ```
        """

        await self._require_delivery_surface().message_operation(
            operation_id,
            text=text,
        )

    async def interrupt(
        self,
        operation_id: str,
        task_id: str | None = None,
    ) -> None:
        """Request the active attached turn to stop.

        Args:
            operation_id: Exact operation id, unique prefix, or `"last"`.
            task_id: Optional exact task id or unique prefix. When omitted, the active
                session for the operation is interrupted.

        Examples:
            ```python
            async with OperatorClient() as client:
                await client.interrupt("last")
            ```
        """

        await self._require_delivery_surface().interrupt_operation(operation_id, task_id=task_id)

    async def pause(self, operation_id: str) -> None:
        """Pause one operation after the current attached turn yields.

        Args:
            operation_id: Exact operation id, unique prefix, or `"last"`.

        Examples:
            ```python
            async with OperatorClient() as client:
                await client.pause("last")
            ```
        """

        await self._require_delivery_surface().pause_operation(operation_id)

    async def unpause(self, operation_id: str) -> None:
        """Resume a paused operation.

        Args:
            operation_id: Exact operation id, unique prefix, or `"last"`.

        Examples:
            ```python
            async with OperatorClient() as client:
                await client.unpause("last")
            ```
        """

        await self._require_delivery_surface().unpause_operation(operation_id)

    async def stream_events(
        self,
        operation_id: str,
    ) -> AsyncIterator[RunEvent]:
        """Yield persisted live events from the canonical or legacy event stream.

        The iterator waits for the event file to appear, tails appended lines, and
        exits after a terminal event plus a quiet drain window. If the operation is
        already terminal when called, the iterator drains the existing file and exits.

        Args:
            operation_id: Exact operation id, unique prefix, or `"last"`.

        Yields:
            Parsed `RunEvent` records.

        Examples:
            ```python
            async with OperatorClient() as client:
                async for event in client.stream_events("last"):
                    print(event.event_type)
            ```
        """

        resolved_operation_id = await self._resolve_operation_id(operation_id)
        path, parser = self._resolve_stream_path(resolved_operation_id)
        initial_terminal = await self._is_terminal_operation(resolved_operation_id)
        wait_deadline = anyio.current_time() + self._event_file_timeout_seconds
        terminal_deadline: float | None = None
        handle = None
        try:
            while True:
                if handle is None:
                    if not path.exists():
                        if initial_terminal:
                            return
                        if await self._is_terminal_operation(resolved_operation_id):
                            return
                        if anyio.current_time() >= wait_deadline:
                            return
                        await anyio.sleep(self._stream_poll_interval_seconds)
                        continue
                    handle = path.open(encoding="utf-8")
                position = handle.tell()
                line = handle.readline()
                if not line:
                    if initial_terminal:
                        return
                    if terminal_deadline is None and await self._is_terminal_operation(
                        resolved_operation_id
                    ):
                        terminal_deadline = anyio.current_time() + self._stream_drain_window_seconds
                    if terminal_deadline is not None and anyio.current_time() >= terminal_deadline:
                        return
                    await anyio.sleep(self._stream_poll_interval_seconds)
                    continue
                if not line.endswith("\n"):
                    handle.seek(position)
                    await anyio.sleep(self._stream_poll_interval_seconds)
                    continue
                envelope = parser(resolved_operation_id, line)
                assert envelope.event is not None
                event = envelope.event
                yield event
                if event.event_type in self._TERMINAL_EVENT_TYPES:
                    terminal_deadline = anyio.current_time() + self._stream_drain_window_seconds
        finally:
            if handle is not None:
                handle.close()

    def _resolve_stream_path(
        self,
        operation_id: str,
    ) -> tuple[Path, Callable[[str, str], LiveFeedEnvelope]]:
        settings = self._require_settings()
        canonical_path = settings.data_dir / "operation_events" / f"{operation_id}.jsonl"
        if canonical_path.exists():
            return canonical_path, parse_canonical_live_feed_line
        legacy_path = settings.data_dir / "events" / f"{operation_id}.jsonl"
        return legacy_path, parse_legacy_live_feed_line

    def _require_settings(self) -> OperatorSettings:
        if self._settings is None:
            raise RuntimeError("OperatorClient must be entered with 'async with' before use.")
        return self._settings

    def _require_store(self) -> OperationStore:
        if self._store is None:
            raise RuntimeError("OperatorClient must be entered with 'async with' before use.")
        return self._store

    def _require_command_inbox(self) -> OperationCommandInbox:
        if self._command_inbox is None:
            raise RuntimeError("OperatorClient must be entered with 'async with' before use.")
        return self._command_inbox

    def _build_operation_service(self, operation_id: str) -> OperatorService:
        settings = self._require_settings()
        return build_service(settings, event_sink=build_event_sink(settings, operation_id))

    def _build_operation_service_for_delivery(self) -> OperatorService:
        settings = self._require_settings()
        return build_service(settings)

    def _build_run_options(self, mode: str) -> RunOptions:
        if mode == "background":
            return RunOptions(
                run_mode=RunMode.RESUMABLE,
                background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
            )
        if mode == "attached":
            return RunOptions(
                run_mode=RunMode.ATTACHED,
                background_runtime_mode=BackgroundRuntimeMode.ATTACHED_LIVE,
            )
        raise ValueError("mode must be 'background' or 'attached'.")

    async def _load_operation(self, operation_id: str) -> OperationState:
        resolved_operation_id = await self._resolve_operation_id(operation_id)
        operation = await self._require_resolution_service().load_canonical_operation_state(
            resolved_operation_id
        )
        if operation is None:
            raise RuntimeError(f"Operation {resolved_operation_id!r} was not found.")
        return operation

    async def _resolve_operation_id(self, operation_ref: str) -> str:
        return await self._require_resolution_service().resolve_operation_id(operation_ref)

    def _resolve_attention_id(self, operation: OperationState, attention_ref: str) -> str:
        exact = next(
            (
                item.attention_id
                for item in operation.attention_requests
                if item.attention_id == attention_ref
            ),
            None,
        )
        if exact is not None:
            return exact
        matches = [
            item.attention_id
            for item in operation.attention_requests
            if item.attention_id.startswith(attention_ref)
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise RuntimeError(
                f"Attention reference {attention_ref!r} is ambiguous: {', '.join(matches)}"
            )
        raise RuntimeError(
            f"Attention request {attention_ref!r} was not found in "
            f"operation {operation.operation_id!r}."
        )

    def _resolve_task_session_id(self, operation: OperationState, task_ref: str) -> str:
        exact_matches = [item for item in operation.tasks if item.task_id == task_ref]
        matches = exact_matches or [
            item for item in operation.tasks if item.task_id.startswith(task_ref)
        ]
        if len(matches) > 1:
            raise RuntimeError(
                f"Task reference {task_ref!r} is ambiguous in operation {operation.operation_id!r}."
            )
        if not matches:
            raise RuntimeError(
                f"Task {task_ref!r} was not found in operation {operation.operation_id!r}."
            )
        task = matches[0]
        for session in operation.sessions:
            if task.task_id in session.bound_task_ids and session.status.value == "running":
                return session.session_id
        raise RuntimeError(f"Task {task_ref!r} is running but has no active session bound to it.")

    async def _is_terminal_operation(self, operation_id: str) -> bool:
        store = self._require_store()
        operation = await self._require_resolution_service().load_canonical_operation_state(
            operation_id
        )
        if operation is not None and operation.status in self._TERMINAL_STATUSES:
            return True
        outcome = await store.load_outcome(operation_id)
        return outcome is not None and outcome.status in self._TERMINAL_STATUSES

    def _require_resolution_service(self) -> OperationResolutionService:
        if self._resolution_service is None:
            raise RuntimeError("OperatorClient must be entered with 'async with' before use.")
        return self._resolution_service

    def _require_delivery_surface(self) -> DeliverySurfaceService:
        if self._delivery_surface is None:
            raise RuntimeError("OperatorClient must be entered with 'async with' before use.")
        return self._delivery_surface
