from __future__ import annotations

from dataclasses import dataclass, field

from . import model_attention as _model_attention
from . import model_display as _model_display
from . import model_fleet as _model_fleet
from . import model_sessions as _model_sessions
from . import model_types as _model_types

AttentionSummary = _model_attention.AttentionSummary
oldest_blocking_attention = _model_attention.oldest_blocking_attention
oldest_nonblocking_attention = _model_attention.oldest_nonblocking_attention
oldest_operation_blocking_attention = _model_attention.oldest_operation_blocking_attention
oldest_task_blocking_attention = _model_attention.oldest_task_blocking_attention
oldest_task_nonblocking_attention = _model_attention.oldest_task_nonblocking_attention
operation_scope_attentions = _model_attention.operation_scope_attentions
task_attention_titles = _model_attention.task_attention_titles
task_scope_attentions = _model_attention.task_scope_attentions
task_signal_text = _model_attention.task_signal_text
tasks_with_blocking_attention = _model_attention.tasks_with_blocking_attention

event_detail_lines = _model_display.event_detail_lines
filtered_raw_transcript_lines = _model_display.filtered_raw_transcript_lines
normalize_key = _model_display.normalize_key
raw_transcript_lines = _model_display.raw_transcript_lines
session_event_glyph = _model_display.session_event_glyph
session_event_label = _model_display.session_event_label

TASK_LANE_ORDER = _model_fleet.TASK_LANE_ORDER
dashboard_tasks = _model_fleet.dashboard_tasks
filter_fleet_items = _model_fleet.filter_fleet_items
filtered_dashboard_tasks = _model_fleet.filtered_dashboard_tasks
filtered_decisions = _model_fleet.filtered_decisions
filtered_memory_entries = _model_fleet.filtered_memory_entries
payload_items = _model_fleet.payload_items
signal_text = _model_fleet.signal_text
sort_dashboard_tasks = _model_fleet.sort_dashboard_tasks
status_text = _model_fleet.status_text
task_lane = _model_fleet.task_lane
task_status_glyph = _model_fleet.task_status_glyph

filtered_session_timeline_events = _model_sessions.filtered_session_timeline_events
selected_session = _model_sessions.selected_session
selected_session_view = _model_sessions.selected_session_view
session_brief = _model_sessions.session_brief
session_identity_text = _model_sessions.session_identity_text
session_timeline_events = _model_sessions.session_timeline_events
sort_session_timeline_events = _model_sessions.sort_session_timeline_events
task_session_summary = _model_sessions.task_session_summary

FleetItem = _model_types.FleetItem
OperationTaskItem = _model_types.OperationTaskItem
TerminalSettings = _model_types.TerminalSettings
TimelineEventItem = _model_types.TimelineEventItem
optional_int = _model_types.optional_int
optional_text = _model_types.optional_text
text_tuple = _model_types.text_tuple


@dataclass(slots=True)
class FleetWorkbenchState:
    all_items: list[FleetItem] = field(default_factory=list)
    items: list[FleetItem] = field(default_factory=list)
    selected_index: int = 0
    selected_operation_payload: dict[str, object] | None = None
    selected_fleet_brief: dict[str, object] | None = None
    project: str | None = None
    total_operations: int = 0
    last_message: str | None = None
    pending_confirmation: str | None = None
    pending_answer_operation_id: str | None = None
    pending_answer_attention_id: str | None = None
    pending_answer_task_id: str | None = None
    pending_answer_blocking: bool = True
    pending_answer_text: str = ""
    pending_answer_prompt: str = "Answer text: "
    attention_picker_active: bool = False
    attention_picker_operation_id: str | None = None
    attention_picker_task_id: str | None = None
    attention_picker_index: int = 0
    help_overlay_active: bool = False
    view_level: str = "fleet"
    selected_task_index: int = 0
    operation_panel_mode: str = "detail"
    task_filter_query: str = ""
    pending_task_filter_text: str | None = None
    pending_task_filter_restore_query: str = ""
    selected_timeline_index: int = 0
    session_panel_mode: str = "timeline"
    session_filter_query: str = ""
    pending_session_filter_text: str | None = None
    pending_session_filter_restore_query: str = ""
    forensic_filter_query: str = ""
    pending_forensic_filter_text: str | None = None
    pending_forensic_filter_restore_query: str = ""
    filter_query: str = ""
    pending_filter_text: str | None = None
    pending_filter_restore_query: str = ""
    pending_palette_text: str | None = None
    pending_palette_preview: str | None = None
    converse_panel_active: bool = False
    converse_input_text: str = ""
    converse_history: list[dict[str, str]] = field(default_factory=list)
    converse_transcript_lines: list[str] = field(default_factory=list)
    converse_pending_command_text: str | None = None
    converse_editing_command: bool = False

    @property
    def selected_item(self) -> FleetItem | None:
        if not self.items or self.selected_index < 0 or self.selected_index >= len(self.items):
            return None
        return self.items[self.selected_index]

    @property
    def selected_task(self) -> OperationTaskItem | None:
        tasks = filtered_dashboard_tasks(self.selected_operation_payload, self.task_filter_query)
        if not tasks or self.selected_task_index < 0 or self.selected_task_index >= len(tasks):
            return None
        return tasks[self.selected_task_index]

    @property
    def selected_timeline_event(self) -> TimelineEventItem | None:
        events = filtered_session_timeline_events(
            self.selected_operation_payload,
            self.selected_task,
            self.session_filter_query,
        )
        if (
            not events
            or self.selected_timeline_index < 0
            or self.selected_timeline_index >= len(events)
        ):
            return None
        return events[self.selected_timeline_index]
