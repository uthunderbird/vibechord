from __future__ import annotations

from datetime import UTC, datetime

from agent_operator.application.commands.operation_attention import OperationAttentionCoordinator
from agent_operator.application.commands.operation_control_state import (
    OperationControlStateCoordinator,
)
from agent_operator.application.event_sourcing.event_sourced_commands import (
    EventSourcedCommandApplicationService,
)
from agent_operator.application.loaded_operation import LoadedOperation
from agent_operator.application.operation_lifecycle import OperationLifecycleCoordinator
from agent_operator.application.process_signals import ProcessManagerSignal
from agent_operator.application.runtime.operation_event_relay import OperationEventRelay
from agent_operator.application.runtime.operation_policy_context import (
    OperationPolicyContextCoordinator,
)
from agent_operator.application.runtime.operation_process_dispatch import (
    OperationProcessSignalDispatcher,
)
from agent_operator.application.runtime.operation_runtime_context import OperationRuntimeContext
from agent_operator.domain import (
    AgentSessionHandle,
    AttentionRequest,
    AttentionStatus,
    BackgroundRunStatus,
    CommandStatus,
    CommandTargetScope,
    ExecutionProfileStamp,
    FocusKind,
    FocusMode,
    FocusState,
    InterruptPolicy,
    InvolvementLevel,
    IterationState,
    OperationCommand,
    OperationCommandType,
    OperationDomainEventDraft,
    OperationState,
    OperationStatus,
    PermissionRequestSignature,
    PolicyApplicability,
    PolicyCategory,
    PolicyEntry,
    PolicySourceRef,
    PolicyStatus,
    ResumePolicy,
    RunMode,
    SchedulerState,
    TraceRecord,
)
from agent_operator.protocols import (
    AgentSessionManager,
    OperationCommandInbox,
    OperationRuntime,
    TraceStore,
)


class OperationCommandService:
    def __init__(
        self,
        *,
        loaded_operation: LoadedOperation,
        command_inbox: OperationCommandInbox | None,
        trace_store: TraceStore,
        policy_context_coordinator: OperationPolicyContextCoordinator,
        attention_coordinator: OperationAttentionCoordinator,
        attached_session_registry: AgentSessionManager,
        operation_runtime: OperationRuntime | None,
        event_sourced_command_service: EventSourcedCommandApplicationService,
        event_relay: OperationEventRelay,
        control_state_coordinator: OperationControlStateCoordinator,
        lifecycle_coordinator: OperationLifecycleCoordinator,
        process_signal_dispatcher: OperationProcessSignalDispatcher,
        runtime_context: OperationRuntimeContext,
    ) -> None:
        self._loaded_operation = loaded_operation
        self._command_inbox = command_inbox
        self._trace_store = trace_store
        self._policy_context_coordinator = policy_context_coordinator
        self._attention_coordinator = attention_coordinator
        self._attached_session_registry = attached_session_registry
        self._operation_runtime = operation_runtime
        self._event_sourced_command_service = event_sourced_command_service
        self._event_relay = event_relay
        self._control_state_coordinator = control_state_coordinator
        self._lifecycle_coordinator = lifecycle_coordinator
        self._process_signal_dispatcher = process_signal_dispatcher
        self._runtime_context = runtime_context

    async def drain_commands(
        self,
        state: OperationState,
        *,
        iteration: IterationState | None = None,
        attached_session: AgentSessionHandle | None = None,
    ) -> None:
        if self._command_inbox is None:
            return
        await self.reconcile_command_statuses(state)
        pending = await self._command_inbox.list_pending(state.operation_id)
        if not pending:
            return
        for command in pending:
            await self.apply_command(
                state,
                command,
                iteration=iteration,
                attached_session=attached_session,
            )

    async def apply_command(
        self,
        state: OperationState,
        command: OperationCommand,
        *,
        iteration: IterationState | None = None,
        attached_session: AgentSessionHandle | None = None,
    ) -> bool:
        trace_iteration = iteration.index if iteration is not None else len(state.iterations)
        if command.command_id in state.processed_command_ids:
            await self.reconcile_single_command_status(command, CommandStatus.APPLIED)
            return False
        if command.command_type is OperationCommandType.ANSWER_ATTENTION_REQUEST:
            return await self._apply_answer_attention_request(
                state,
                command,
                trace_iteration=trace_iteration,
            )
        if command.command_type is OperationCommandType.RECORD_POLICY_DECISION:
            return await self.record_policy_decision(state, command, trace_iteration)
        if command.command_type is OperationCommandType.REVOKE_POLICY_DECISION:
            return await self.revoke_policy_decision(state, command, trace_iteration)
        if command.command_type is OperationCommandType.STOP_AGENT_TURN:
            return await self._apply_stop_agent_turn(
                state,
                command,
                trace_iteration=trace_iteration,
                iteration=iteration,
                attached_session=attached_session,
            )
        if command.command_type is OperationCommandType.STOP_OPERATION:
            return await self._apply_stop_operation(
                state,
                command,
                trace_iteration=trace_iteration,
            )
        return await self._apply_operation_target_command(
            state,
            command,
            trace_iteration=trace_iteration,
        )

    async def mark_command_applied(
        self,
        state: OperationState,
        command: OperationCommand,
        iteration: int,
        summary: str,
        *,
        applied_at: datetime | None = None,
        prior_status: CommandStatus | None = None,
        previous_execution_profile: ExecutionProfileStamp | None = None,
    ) -> None:
        event_payload: dict[str, object] = {
            "command_id": command.command_id,
            "command_type": command.command_type.value,
            "status": CommandStatus.APPLIED.value,
            "prior_status": prior_status.value if prior_status is not None else None,
        }
        if command.command_type is OperationCommandType.SET_EXECUTION_PROFILE:
            adapter_key = str(command.payload.get("adapter_key", "")).strip()
            current_model = str(command.payload.get("model", "")).strip()
            current_effort = command.payload.get("effort")
            current_approval_policy = command.payload.get("approval_policy")
            current_sandbox_mode = command.payload.get("sandbox_mode")
            event_payload.update(
                {
                    "adapter_key": adapter_key,
                    "previous_model": (
                        previous_execution_profile.model
                        if previous_execution_profile is not None
                        else None
                    ),
                    "previous_effort_field_name": (
                        previous_execution_profile.effort_field_name
                        if previous_execution_profile is not None
                        else None
                    ),
                    "previous_effort_value": (
                        previous_execution_profile.effort_value
                        if previous_execution_profile is not None
                        else None
                    ),
                    "previous_approval_policy": (
                        previous_execution_profile.approval_policy
                        if previous_execution_profile is not None
                        else None
                    ),
                    "previous_sandbox_mode": (
                        previous_execution_profile.sandbox_mode
                        if previous_execution_profile is not None
                        else None
                    ),
                    "current_model": current_model or None,
                    "current_effort_field_name": (
                        "reasoning_effort" if adapter_key == "codex_acp" else "effort"
                    ),
                    "current_effort_value": (
                        current_effort.strip()
                        if isinstance(current_effort, str) and current_effort.strip()
                        else None
                    ),
                    "current_approval_policy": (
                        current_approval_policy.strip()
                        if isinstance(current_approval_policy, str)
                        and current_approval_policy.strip()
                        else None
                    ),
                    "current_sandbox_mode": (
                        current_sandbox_mode.strip()
                        if isinstance(current_sandbox_mode, str)
                        and current_sandbox_mode.strip()
                        else None
                    ),
                }
            )
        if self._command_inbox is not None:
            await self._command_inbox.update_status(
                command.command_id,
                CommandStatus.APPLIED,
                applied_at=applied_at or datetime.now(UTC),
            )
        await self._event_relay.emit(
            "command.applied",
            state,
            iteration,
            event_payload,
        )
        await self._trace_store.append_trace_record(
            state.operation_id,
            TraceRecord(
                operation_id=state.operation_id,
                iteration=iteration,
                category="command",
                title=f"Command {command.command_type.value}",
                summary=summary,
                refs={"operation_id": state.operation_id, "command_id": command.command_id},
                payload={
                    "status": CommandStatus.APPLIED.value,
                    "prior_status": prior_status.value if prior_status is not None else None,
                },
            ),
        )

    async def reject_command(
        self,
        state: OperationState,
        command: OperationCommand,
        iteration: int,
        reason: str,
    ) -> None:
        if self._command_inbox is not None:
            await self._command_inbox.update_status(
                command.command_id,
                CommandStatus.REJECTED,
                rejection_reason=reason,
            )
        await self._event_relay.emit(
            "command.rejected",
            state,
            iteration,
            {
                "command_id": command.command_id,
                "command_type": command.command_type.value,
                "status": CommandStatus.REJECTED.value,
                "rejection_reason": reason,
            },
        )
        await self._trace_store.append_trace_record(
            state.operation_id,
            TraceRecord(
                operation_id=state.operation_id,
                iteration=iteration,
                category="command",
                title=f"Command {command.command_type.value}",
                summary=reason,
                refs={"operation_id": state.operation_id, "command_id": command.command_id},
                payload={
                    "status": CommandStatus.REJECTED.value,
                    "rejection_reason": reason,
                },
            ),
        )

    async def record_policy_decision(
        self,
        state: OperationState,
        command: OperationCommand,
        iteration: int,
    ) -> bool:
        if not self._policy_context_coordinator.has_policy_store:
            await self.reject_command(state, command, iteration, "Policy store is not configured.")
            return False
        project_scope = self.resolve_policy_scope(state)
        if project_scope is None:
            await self.reject_command(
                state,
                command,
                iteration,
                "This operation does not expose a project policy scope.",
            )
            return False

        title = str(command.payload.get("title", "")).strip()
        rule_text = str(command.payload.get("text", "")).strip()
        rationale = str(command.payload.get("rationale", "")).strip() or None
        source_refs = [PolicySourceRef(kind="command", ref_id=command.command_id)]
        if command.target_scope is CommandTargetScope.ATTENTION_REQUEST:
            attention = self.find_attention_request(state, command.target_id)
            if attention is None:
                await self.reject_command(
                    state,
                    command,
                    iteration,
                    "Target attention request was not found.",
                )
                return False
            source_refs.append(
                PolicySourceRef(kind="attention_request", ref_id=attention.attention_id)
            )
            if not title:
                title = attention.title
            if not rule_text:
                rule_text = (attention.answer_text or "").strip()
            if rationale is None and attention.resolution_summary:
                rationale = attention.resolution_summary
        elif command.target_scope is not CommandTargetScope.OPERATION:
            await self.reject_command(
                state,
                command,
                iteration,
                f"Unsupported command target scope: {command.target_scope.value}.",
            )
            return False

        if not title:
            await self.reject_command(
                state,
                command,
                iteration,
                "RECORD_POLICY_DECISION requires non-empty payload.title.",
            )
            return False
        if not rule_text:
            await self.reject_command(
                state,
                command,
                iteration,
                (
                    "RECORD_POLICY_DECISION requires non-empty payload.text or an "
                    "answered attention request."
                ),
            )
            return False
        raw_category = (
            str(command.payload.get("category", "")).strip()
            or PolicyCategory.GENERAL.value
        )
        try:
            category = PolicyCategory(raw_category)
        except ValueError:
            await self.reject_command(
                state,
                command,
                iteration,
                f"Unsupported policy category: {raw_category}.",
            )
            return False

        entry = PolicyEntry(
            project_scope=project_scope,
            title=title,
            category=category,
            rule_text=rule_text,
            applicability=self.build_policy_applicability(command),
            rationale=rationale,
            source_refs=source_refs,
        )
        policy_store = self._policy_context_coordinator._policy_store
        assert policy_store is not None
        await policy_store.save(entry)
        await self.refresh_policy_context(state)
        applied_at = datetime.now(UTC)
        result = await self._event_sourced_command_service.append_domain_events(
            state.operation_id,
            self._policy_context_domain_events(state, command, applied_at=applied_at),
        )
        self._control_state_coordinator.refresh_state_from_checkpoint(state, result.checkpoint)
        await self._control_state_coordinator.persist_command_effect_state(state)
        await self.mark_command_applied(
            state,
            command,
            iteration,
            f"Recorded policy {entry.policy_id} in scope {project_scope}.",
            applied_at=applied_at,
        )
        await self._process_signal_dispatcher.dispatch(
            state,
            iteration,
            ProcessManagerSignal(
                operation_id=state.operation_id,
                signal_type="policy_context_changed",
                source_command_id=command.command_id,
                metadata={"policy_id": entry.policy_id},
            ),
        )
        return True

    async def revoke_policy_decision(
        self,
        state: OperationState,
        command: OperationCommand,
        iteration: int,
    ) -> bool:
        policy_store = self._policy_context_coordinator._policy_store
        if policy_store is None:
            await self.reject_command(state, command, iteration, "Policy store is not configured.")
            return False
        project_scope = self.resolve_policy_scope(state)
        if project_scope is None:
            await self.reject_command(
                state,
                command,
                iteration,
                "This operation does not expose a project policy scope.",
            )
            return False
        policy_id = str(command.payload.get("policy_id", "")).strip()
        if not policy_id:
            await self.reject_command(
                state,
                command,
                iteration,
                "REVOKE_POLICY_DECISION requires non-empty payload.policy_id.",
            )
            return False
        entry = await policy_store.load(policy_id)
        if entry is None:
            await self.reject_command(
                state,
                command,
                iteration,
                "Target policy entry was not found.",
            )
            return False
        if entry.project_scope != project_scope:
            await self.reject_command(
                state,
                command,
                iteration,
                "Target policy entry is outside this operation's project scope.",
            )
            return False
        if entry.status is not PolicyStatus.ACTIVE:
            await self.reject_command(
                state,
                command,
                iteration,
                "Target policy entry is not active.",
            )
            return False
        entry.status = PolicyStatus.REVOKED
        entry.revoked_reason = str(command.payload.get("reason", "")).strip() or None
        applied_at = datetime.now(UTC)
        entry.revoked_at = applied_at
        entry.source_refs.append(PolicySourceRef(kind="command", ref_id=command.command_id))
        await policy_store.save(entry)
        await self.refresh_policy_context(state)
        result = await self._event_sourced_command_service.append_domain_events(
            state.operation_id,
            self._policy_context_domain_events(state, command, applied_at=applied_at),
        )
        self._control_state_coordinator.refresh_state_from_checkpoint(state, result.checkpoint)
        await self._control_state_coordinator.persist_command_effect_state(state)
        await self.mark_command_applied(
            state,
            command,
            iteration,
            f"Revoked policy {entry.policy_id}.",
            applied_at=applied_at,
        )
        await self._process_signal_dispatcher.dispatch(
            state,
            iteration,
            ProcessManagerSignal(
                operation_id=state.operation_id,
                signal_type="policy_context_changed",
                source_command_id=command.command_id,
                metadata={"policy_id": entry.policy_id},
            ),
        )
        return True

    async def reconcile_command_statuses(self, state: OperationState) -> None:
        if self._command_inbox is None:
            return
        for command in await self._command_inbox.list(state.operation_id):
            if command.status is CommandStatus.REJECTED:
                continue
            if command.command_id in state.processed_command_ids:
                await self.reconcile_single_command_status(command, CommandStatus.APPLIED)

    async def reconcile_single_command_status(
        self,
        command: OperationCommand,
        target_status: CommandStatus,
    ) -> None:
        if self._command_inbox is None or command.status is target_status:
            return
        await self._command_inbox.update_status(
            command.command_id,
            target_status,
            applied_at=datetime.now(UTC) if target_status is CommandStatus.APPLIED else None,
        )

    async def finalize_pending_attention_resolutions(self, state: OperationState) -> None:
        pending_ids = list(dict.fromkeys(state.pending_attention_resolution_ids))
        if not pending_ids:
            pending_ids = [
                attention.attention_id
                for attention in state.attention_requests
                if attention.status is AttentionStatus.ANSWERED
            ]
        if not pending_ids:
            return
        resolved_at = datetime.now(UTC)
        state.pending_attention_resolution_ids = []
        changed = False
        for attention_id in pending_ids:
            attention = self.find_attention_request(state, attention_id)
            if attention is None or attention.status is not AttentionStatus.ANSWERED:
                continue
            resolution_summary = "Resolved via operator replanning after human answer."
            result = await self._event_sourced_command_service.append_domain_events(
                state.operation_id,
                [
                    OperationDomainEventDraft(
                        event_type="attention.request.resolved",
                        payload={
                            "attention_id": attention.attention_id,
                            "attention_type": attention.attention_type.value,
                            "status": AttentionStatus.RESOLVED.value,
                            "resolution_summary": resolution_summary,
                            "resolved_at": resolved_at.isoformat(),
                        },
                    )
                ],
            )
            self._control_state_coordinator.refresh_state_from_checkpoint(state, result.checkpoint)
            attention = self.find_attention_request(state, attention_id)
            if attention is None or attention.status is not AttentionStatus.RESOLVED:
                continue
            changed = True
            await self._event_relay.emit(
                "attention.request.resolved",
                state,
                len(state.iterations),
                {
                    "attention_id": attention.attention_id,
                    "attention_type": attention.attention_type.value,
                    "status": attention.status.value,
                    "resolution_summary": attention.resolution_summary,
                    "resolved_at": (
                        attention.resolved_at.isoformat()
                        if attention.resolved_at is not None
                        else None
                    ),
                },
            )
            if attention.attention_type.value == "approval_request":
                policy_written = await self.auto_record_approval_attention_policy(state, attention)
                if policy_written:
                    changed = True
        if changed:
            await self._control_state_coordinator.persist_command_effect_state(state)

    async def auto_record_approval_attention_policy(
        self,
        state: OperationState,
        attention: AttentionRequest,
    ) -> bool:
        policy_store = self._policy_context_coordinator._policy_store
        if policy_store is None:
            return False
        project_scope = self.resolve_policy_scope(state)
        if project_scope is None:
            return False
        metadata = attention.metadata if isinstance(attention.metadata, dict) else {}
        raw_signature = metadata.get("signature")
        signature: PermissionRequestSignature | None = None
        permission_signatures: list[PermissionRequestSignature] = []
        signature_payload: dict[str, object] = {}
        if isinstance(raw_signature, dict):
            signature_payload = {
                key: raw_signature[key]
                for key in (
                    "adapter_key",
                    "method",
                    "interaction",
                    "title",
                    "tool_kind",
                    "skill_name",
                    "command",
                )
                if key in raw_signature
            }
            raw_command = signature_payload.get("command")
            if isinstance(raw_command, list) and all(
                isinstance(item, str) for item in raw_command
            ):
                signature_payload["command"] = list(raw_command)
            try:
                signature = PermissionRequestSignature.model_validate(signature_payload)
            except Exception:
                signature = None
        if signature is not None:
            permission_signatures = [signature]
        adapter_key = (
            str(signature_payload.get("adapter_key", "")).strip()
            if isinstance(signature_payload.get("adapter_key"), str)
            else ""
        )
        title = str(metadata.get("policy_title", "")).strip() or attention.title
        rule_text = str(metadata.get("policy_rule_text", "")).strip()
        if not rule_text and attention.answer_text:
            rule_text = attention.answer_text.strip()
        if not title or not rule_text:
            return False
        applicability = PolicyApplicability(
            agent_keys=[adapter_key] if adapter_key else [],
            permission_signatures=permission_signatures,
        )
        entry = PolicyEntry(
            project_scope=project_scope,
            title=title,
            category=PolicyCategory.AUTONOMY,
            rule_text=rule_text,
            applicability=applicability,
            rationale=f"Auto-generated from resolved approval request {attention.attention_id}.",
            source_refs=[PolicySourceRef(kind="attention_request", ref_id=attention.attention_id)],
        )
        await policy_store.save(entry)
        await self.refresh_policy_context(state)
        return True

    async def reject_if_replan_conflict(
        self,
        state: OperationState,
        command: OperationCommand,
        trace_iteration: int,
        command_type: OperationCommandType,
    ) -> bool:
        if not command.command_id or command.command_type is not command_type:
            return False
        if not state.pending_replan_command_ids:
            return False
        inbox_commands: list[OperationCommand] = []
        if self._command_inbox is not None:
            inbox_commands = await self._command_inbox.list(state.operation_id)
        for pending_id in state.pending_replan_command_ids:
            if pending_id == command.command_id:
                continue
            if self._command_inbox is not None:
                matching = next(
                    (item for item in inbox_commands if item.command_id == pending_id),
                    None,
                )
                if matching is None or matching.command_type is not command_type:
                    continue
                if matching.status is CommandStatus.REJECTED:
                    continue
            await self.reject_command(
                state,
                command,
                trace_iteration,
                (
                    "concurrent_patch_conflict: another patch on the same field "
                    "is already pending replan."
                ),
            )
            return True
        return False

    async def apply_event_sourced_operation_command(
        self,
        state: OperationState,
        command: OperationCommand,
        trace_iteration: int,
    ) -> bool:
        assert self._event_sourced_command_service is not None
        previous_execution_profile = None
        if command.command_type is OperationCommandType.SET_EXECUTION_PROFILE:
            adapter_key = str(command.payload.get("adapter_key", "")).strip()
            if adapter_key:
                previous_execution_profile = (
                    self._loaded_operation.effective_execution_profile_stamp(
                        state,
                        adapter_key,
                    )
                )
        result = await self._event_sourced_command_service.apply(command)
        self._control_state_coordinator.refresh_state_from_checkpoint(state, result.checkpoint)
        await self._control_state_coordinator.persist_command_effect_state(state)
        if not result.applied:
            await self.reject_command(
                state,
                command,
                trace_iteration,
                (
                    result.rejection_reason
                    or f"Unsupported command type: {command.command_type.value}."
                ),
            )
            return False
        if command.command_type in {
            OperationCommandType.PATCH_OBJECTIVE,
            OperationCommandType.PATCH_HARNESS,
            OperationCommandType.PATCH_SUCCESS_CRITERIA,
            OperationCommandType.INJECT_OPERATOR_MESSAGE,
            OperationCommandType.SET_ALLOWED_AGENTS,
            OperationCommandType.SET_EXECUTION_PROFILE,
        }:
            state.pending_replan_command_ids.append(command.command_id)
        await self.mark_command_applied(
            state,
            command,
            trace_iteration,
            f"Command {command.command_type.value} applied via canonical event append.",
            previous_execution_profile=previous_execution_profile,
        )
        return True

    async def refresh_policy_context(self, state: OperationState) -> None:
        await self._policy_context_coordinator.refresh_policy_context(state)

    def _policy_context_domain_events(
        self,
        state: OperationState,
        command: OperationCommand,
        *,
        applied_at: datetime,
    ) -> list[OperationDomainEventDraft]:
        return [
            OperationDomainEventDraft(
                event_type="command.accepted",
                payload={
                    "command_id": command.command_id,
                    "command_type": command.command_type.value,
                    "target_scope": command.target_scope.value,
                    "target_id": command.target_id,
                    "submitted_by": command.submitted_by,
                    "submitted_at": command.submitted_at.isoformat(),
                },
                timestamp=applied_at,
                causation_id=command.command_id,
                correlation_id=command.command_id,
            ),
            OperationDomainEventDraft(
                event_type="policy.active_set.updated",
                payload={
                    "active_policies": [
                        policy.model_dump(mode="json") for policy in state.active_policies
                    ]
                },
                timestamp=applied_at,
                causation_id=command.command_id,
                correlation_id=command.command_id,
            ),
            OperationDomainEventDraft(
                event_type="policy.coverage.updated",
                payload=state.policy_coverage.model_dump(mode="json"),
                timestamp=applied_at,
                causation_id=command.command_id,
                correlation_id=command.command_id,
            ),
        ]

    def resolve_policy_scope(self, state: OperationState) -> str | None:
        return self._policy_context_coordinator.resolve_policy_scope(state)

    def build_policy_applicability(self, command: OperationCommand) -> PolicyApplicability:
        return self._policy_context_coordinator.build_policy_applicability(command)

    def find_attention_request(
        self,
        state: OperationState,
        attention_id: str | None,
    ) -> AttentionRequest | None:
        return self._attention_coordinator.find_attention_request(state, attention_id)

    def _normalize_policy_strings(self, raw_value: object) -> list[str]:
        return self._policy_context_coordinator.normalize_policy_strings(raw_value)

    def _parse_policy_run_modes(self, raw_value: object) -> list[RunMode]:
        return self._policy_context_coordinator.parse_policy_run_modes(raw_value)

    def _parse_policy_involvement_levels(self, raw_value: object) -> list[InvolvementLevel]:
        return self._policy_context_coordinator.parse_policy_involvement_levels(raw_value)

    async def _apply_answer_attention_request(
        self,
        state: OperationState,
        command: OperationCommand,
        *,
        trace_iteration: int,
    ) -> bool:
        snapshot_attention = self.find_attention_request(state, command.target_id)
        if snapshot_attention is not None:
            checkpoint = (
                await self._event_sourced_command_service.seed_attention_request_from_state(
                    state,
                    snapshot_attention,
                )
            )
            self._control_state_coordinator.refresh_state_from_checkpoint(state, checkpoint)
        result = await self._event_sourced_command_service.apply(command)
        replayed_attention = next(
            (
                attention
                for attention in result.checkpoint.attention_requests
                if attention.attention_id == command.target_id
            ),
            None,
        )
        if replayed_attention is not None:
            self._control_state_coordinator.refresh_state_from_checkpoint(
                state,
                result.checkpoint,
            )
        if not result.applied:
            if (
                result.rejection_reason == "Target attention request was not found."
                and self.find_attention_request(state, command.target_id) is not None
            ):
                snapshot_attention = self.find_attention_request(state, command.target_id)
                assert snapshot_attention is not None
                checkpoint = (
                    await self._event_sourced_command_service.seed_attention_request_from_state(
                        state,
                        snapshot_attention,
                    )
                )
                self._control_state_coordinator.refresh_state_from_checkpoint(state, checkpoint)
                result = await self._event_sourced_command_service.apply(command)
                replayed_attention = next(
                    (
                        attention
                        for attention in result.checkpoint.attention_requests
                        if attention.attention_id == command.target_id
                    ),
                    None,
                )
                if replayed_attention is not None:
                    self._control_state_coordinator.refresh_state_from_checkpoint(
                        state,
                        result.checkpoint,
                    )
            if not result.applied:
                await self.reject_command(
                    state,
                    command,
                    trace_iteration,
                    result.rejection_reason
                    or f"Unsupported command type: {command.command_type.value}.",
                )
                return False
        answered_attention = self.find_attention_request(state, command.target_id)
        if (
            answered_attention is not None
            and answered_attention.status is AttentionStatus.ANSWERED
            and answered_attention.attention_id not in state.pending_attention_resolution_ids
        ):
            state.pending_attention_resolution_ids.append(answered_attention.attention_id)
        if answered_attention is not None and answered_attention.blocking:
            has_blocking_open_attention = any(
                attention.blocking and attention.status is AttentionStatus.OPEN
                for attention in state.attention_requests
            )
            if not has_blocking_open_attention:
                self._lifecycle_coordinator.mark_running(state)
        if (
            state.current_focus is not None
            and state.current_focus.kind is FocusKind.ATTENTION_REQUEST
            and state.current_focus.target_id == command.target_id
        ):
            state.current_focus = None
        await self._control_state_coordinator.persist_command_effect_state(state)
        await self.mark_command_applied(
            state,
            command,
            trace_iteration,
            "Attention answer recorded via canonical event append.",
        )
        if answered_attention is not None:
            await self._process_signal_dispatcher.dispatch(
                state,
                trace_iteration,
                ProcessManagerSignal(
                    operation_id=state.operation_id,
                    signal_type="attention_answer_recorded",
                    source_command_id=command.command_id,
                    metadata={"attention_id": answered_attention.attention_id},
                ),
            )
        return True

    async def _apply_stop_agent_turn(
        self,
        state: OperationState,
        command: OperationCommand,
        *,
        trace_iteration: int,
        iteration: IterationState | None,
        attached_session: AgentSessionHandle | None,
    ) -> bool:
        if command.target_scope is not CommandTargetScope.SESSION:
            await self.reject_command(
                state,
                command,
                trace_iteration,
                "STOP_AGENT_TURN requires session target scope.",
            )
            return False
        if attached_session is None or iteration is None:
            await self.reject_command(
                state,
                command,
                trace_iteration,
                "No active attached agent turn is available to stop.",
            )
            return False
        if command.target_id not in {None, attached_session.session_id}:
            await self.reject_command(
                state,
                command,
                trace_iteration,
                "Session target does not match the active attached turn.",
            )
            return False
        if state.scheduler_state is SchedulerState.DRAINING:
            await self.reject_command(
                state,
                command,
                trace_iteration,
                "The active attached turn is already stopping.",
            )
            return False
        try:
            await self._attached_session_registry.cancel(attached_session)
        except Exception as exc:
            await self.reject_command(
                state,
                command,
                trace_iteration,
                f"Failed to stop the active attached turn: {exc}",
            )
            return False
        applied_at = datetime.now(UTC)
        record = self._loaded_operation.ensure_session_record(state, attached_session)
        record.waiting_reason = "Stopping the active attached agent turn."
        record.updated_at = applied_at
        state.scheduler_state = SchedulerState.DRAINING
        state.current_focus = FocusState(
            kind=FocusKind.SESSION,
            target_id=attached_session.session_id,
            mode=FocusMode.BLOCKING,
            blocking_reason="Stopping the active attached agent turn.",
            interrupt_policy=InterruptPolicy.TERMINAL_ONLY,
            resume_policy=ResumePolicy.REPLAN,
        )
        result = await self._event_sourced_command_service.append_domain_events(
            state.operation_id,
            [
                OperationDomainEventDraft(
                    event_type="command.accepted",
                    payload={
                        "command_id": command.command_id,
                        "command_type": command.command_type.value,
                        "target_scope": command.target_scope.value,
                        "target_id": command.target_id,
                        "submitted_by": command.submitted_by,
                        "submitted_at": command.submitted_at.isoformat(),
                    },
                    timestamp=applied_at,
                    causation_id=command.command_id,
                    correlation_id=command.command_id,
                ),
                OperationDomainEventDraft(
                    event_type="session.waiting_reason.updated",
                    payload={
                        "session_id": attached_session.session_id,
                        "waiting_reason": record.waiting_reason,
                        "updated_at": applied_at.isoformat(),
                    },
                    timestamp=applied_at,
                    causation_id=command.command_id,
                    correlation_id=command.command_id,
                ),
                OperationDomainEventDraft(
                    event_type="scheduler.state.changed",
                    payload={"scheduler_state": SchedulerState.DRAINING.value},
                    timestamp=applied_at,
                    causation_id=command.command_id,
                    correlation_id=command.command_id,
                ),
                OperationDomainEventDraft(
                    event_type="operation.focus.updated",
                    payload={"focus": state.current_focus.model_dump(mode="json")},
                    timestamp=applied_at,
                    causation_id=command.command_id,
                    correlation_id=command.command_id,
                ),
            ],
        )
        state.sessions = [item.model_copy(deep=True) for item in result.checkpoint.sessions]
        state.scheduler_state = result.checkpoint.scheduler_state
        state.current_focus = (
            result.checkpoint.current_focus.model_copy(deep=True)
            if result.checkpoint.current_focus is not None
            else None
        )
        state.processed_command_ids = list(result.checkpoint.processed_command_ids)
        await self._control_state_coordinator.persist_command_effect_state(state)
        await self.mark_command_applied(
            state,
            command,
            trace_iteration,
            "Stop requested for the active attached turn.",
            applied_at=applied_at,
        )
        return True

    async def _apply_stop_operation(
        self,
        state: OperationState,
        command: OperationCommand,
        *,
        trace_iteration: int,
    ) -> bool:
        if command.target_scope is not CommandTargetScope.OPERATION:
            await self.reject_command(
                state,
                command,
                trace_iteration,
                "STOP_OPERATION requires operation target scope.",
            )
            return False
        if command.target_id not in {None, state.operation_id}:
            await self.reject_command(
                state,
                command,
                trace_iteration,
                "Operation target does not match the current operation.",
            )
            return False
        active_session_record = state.active_session_record
        active_session = active_session_record.handle if active_session_record is not None else None
        if active_session is not None and self._attached_session_registry.has(
            active_session.adapter_key
        ):
            try:
                await self._attached_session_registry.cancel(active_session)
            except Exception as exc:
                await self.reject_command(
                    state,
                    command,
                    trace_iteration,
                    f"Failed to cancel active session: {exc}",
                )
                return False
        running_run_ids = [
            run.run_id for run in state.background_runs if run.status is BackgroundRunStatus.RUNNING
        ]
        if running_run_ids and self._operation_runtime is not None:
            await self._operation_runtime.cancel_operation_runs(running_run_ids)
        applied_at = datetime.now(UTC)
        result = await self._event_sourced_command_service.append_domain_events(
            state.operation_id,
            [
                OperationDomainEventDraft(
                    event_type="command.accepted",
                    payload={
                        "command_id": command.command_id,
                        "command_type": command.command_type.value,
                        "target_scope": command.target_scope.value,
                        "target_id": command.target_id,
                        "submitted_by": command.submitted_by,
                        "submitted_at": command.submitted_at.isoformat(),
                    },
                    timestamp=applied_at,
                    causation_id=command.command_id,
                    correlation_id=command.command_id,
                ),
                *[
                    OperationDomainEventDraft(
                        event_type="execution.observed_state.changed",
                        payload={
                            "execution_id": run.run_id,
                            "observed_state": BackgroundRunStatus.CANCELLED.value,
                            "completed_at": applied_at.isoformat(),
                            "updated_at": applied_at.isoformat(),
                        },
                        timestamp=applied_at,
                        causation_id=command.command_id,
                        correlation_id=command.command_id,
                    )
                    for run in state.background_runs
                    if run.status is BackgroundRunStatus.RUNNING
                ],
                OperationDomainEventDraft(
                    event_type="operation.status.changed",
                    payload={
                        "status": OperationStatus.CANCELLED.value,
                        "final_summary": "Operation cancelled.",
                    },
                    timestamp=applied_at,
                    causation_id=command.command_id,
                    correlation_id=command.command_id,
                ),
                OperationDomainEventDraft(
                    event_type="operation.focus.updated",
                    payload={"focus": None},
                    timestamp=applied_at,
                    causation_id=command.command_id,
                    correlation_id=command.command_id,
                ),
                OperationDomainEventDraft(
                    event_type="scheduler.state.changed",
                    payload={"scheduler_state": SchedulerState.ACTIVE.value},
                    timestamp=applied_at,
                    causation_id=command.command_id,
                    correlation_id=command.command_id,
                ),
            ],
        )
        state.background_runs = [
            item.model_copy(deep=True) for item in result.checkpoint.executions
        ]
        state.status = result.checkpoint.status
        state.final_summary = result.checkpoint.final_summary
        if state.objective is not None:
            state.objective.summary = result.checkpoint.final_summary
        state.current_focus = None
        state.scheduler_state = result.checkpoint.scheduler_state
        state.processed_command_ids = list(result.checkpoint.processed_command_ids)
        await self._control_state_coordinator.persist_command_effect_state(state)
        await self.mark_command_applied(
            state,
            command,
            trace_iteration,
            "Operation cancelled by command.",
            applied_at=applied_at,
        )
        return True

    async def _apply_operation_target_command(
        self,
        state: OperationState,
        command: OperationCommand,
        *,
        trace_iteration: int,
    ) -> bool:
        if command.target_scope is not CommandTargetScope.OPERATION:
            await self.reject_command(
                state,
                command,
                trace_iteration,
                f"Unsupported command target scope: {command.target_scope.value}.",
            )
            return False
        if command.target_id not in {None, state.operation_id}:
            await self.reject_command(
                state,
                command,
                trace_iteration,
                "Operation target does not match the current operation.",
            )
            return False
        for command_type in (
            OperationCommandType.PATCH_OBJECTIVE,
            OperationCommandType.PATCH_HARNESS,
            OperationCommandType.SET_ALLOWED_AGENTS,
            OperationCommandType.SET_EXECUTION_PROFILE,
            OperationCommandType.PATCH_SUCCESS_CRITERIA,
        ):
            if await self.reject_if_replan_conflict(state, command, trace_iteration, command_type):
                return False
        if command.command_type is OperationCommandType.SET_EXECUTION_PROFILE:
            rejection_reason = self._validate_execution_profile_command(state, command)
            if rejection_reason is not None:
                await self.reject_command(state, command, trace_iteration, rejection_reason)
                return False
        if self._event_sourced_command_service is not None:
            return await self.apply_event_sourced_operation_command(state, command, trace_iteration)
        await self.reject_command(
            state,
            command,
            trace_iteration,
            f"Unsupported command type: {command.command_type.value}.",
        )
        return False

    def _validate_execution_profile_command(
        self,
        state: OperationState,
        command: OperationCommand,
    ) -> str | None:
        payload = command.payload
        adapter_key = payload.get("adapter_key")
        if not isinstance(adapter_key, str) or not adapter_key.strip():
            return "SET_EXECUTION_PROFILE requires non-empty payload.adapter_key."
        adapter_key = adapter_key.strip()
        unknown_keys = set(payload) - {
            "adapter_key",
            "model",
            "effort",
            "approval_policy",
            "sandbox_mode",
        }
        if unknown_keys:
            return (
                "SET_EXECUTION_PROFILE does not support payload fields: "
                + ", ".join(sorted(str(item) for item in unknown_keys))
                + "."
            )
        if adapter_key not in state.policy.allowed_agents:
            return f"Adapter {adapter_key!r} is not currently allowed for this operation."
        raw_model = payload.get("model")
        if not isinstance(raw_model, str) or not raw_model.strip():
            return "SET_EXECUTION_PROFILE requires non-empty payload.model."
        model = raw_model.strip()
        effort = payload.get("effort")
        if effort is not None and (not isinstance(effort, str) or not effort.strip()):
            return "payload.effort must be a non-empty string when provided."
        approval_policy = payload.get("approval_policy")
        if approval_policy is not None and (
            not isinstance(approval_policy, str) or not approval_policy.strip()
        ):
            return "payload.approval_policy must be a non-empty string when provided."
        sandbox_mode = payload.get("sandbox_mode")
        if sandbox_mode is not None and (
            not isinstance(sandbox_mode, str) or not sandbox_mode.strip()
        ):
            return "payload.sandbox_mode must be a non-empty string when provided."
        if adapter_key != "codex_acp":
            unsupported_keys: list[str] = []
            if approval_policy is not None:
                unsupported_keys.append("approval_policy")
            if sandbox_mode is not None:
                unsupported_keys.append("sandbox_mode")
            if unsupported_keys:
                return (
                    f"Adapter {adapter_key!r} does not support payload fields: "
                    + ", ".join(unsupported_keys)
                    + "."
                )
        allowed_map = state.goal.metadata.get("allowed_execution_profiles")
        if not isinstance(allowed_map, dict):
            return f"Adapter {adapter_key!r} has no allowed execution profiles."
        raw_profiles = allowed_map.get(adapter_key)
        if not isinstance(raw_profiles, list) or not raw_profiles:
            return f"Adapter {adapter_key!r} has no allowed execution profiles."
        if adapter_key == "codex_acp":
            for entry in raw_profiles:
                if not isinstance(entry, dict):
                    continue
                if entry.get("model") != model:
                    continue
                reasoning_effort = entry.get("reasoning_effort")
                if effort is None and reasoning_effort not in {None, ""}:
                    continue
                if effort is not None and (
                    not isinstance(reasoning_effort, str) or reasoning_effort != effort
                ):
                    continue
                allowed_approval_policy = entry.get("approval_policy")
                if approval_policy is None and allowed_approval_policy not in {None, ""}:
                    continue
                if approval_policy is not None and (
                    not isinstance(allowed_approval_policy, str)
                    or allowed_approval_policy != approval_policy
                ):
                    continue
                allowed_sandbox_mode = entry.get("sandbox_mode")
                if sandbox_mode is None and allowed_sandbox_mode not in {None, ""}:
                    continue
                if sandbox_mode is not None and (
                    not isinstance(allowed_sandbox_mode, str)
                    or allowed_sandbox_mode != sandbox_mode
                ):
                    continue
                return None
            return "Requested codex_acp execution profile is not allowlisted."
        if adapter_key == "claude_acp":
            for entry in raw_profiles:
                if not isinstance(entry, dict):
                    continue
                if entry.get("model") != model:
                    continue
                allowed_effort = entry.get("effort")
                if effort is None and allowed_effort in {None, ""}:
                    return None
                if isinstance(allowed_effort, str) and allowed_effort == effort:
                    return None
            return "Requested claude_acp execution profile is not allowlisted."
        return f"Adapter {adapter_key!r} does not support dynamic execution profiles."
