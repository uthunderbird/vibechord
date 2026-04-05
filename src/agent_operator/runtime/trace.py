from __future__ import annotations

import json
from pathlib import Path

from agent_operator.domain import (
    AgentTurnBrief,
    CommandBrief,
    DecisionMemo,
    EvaluationBrief,
    IterationBrief,
    OperationBrief,
    TraceBriefBundle,
    TraceRecord,
)
from agent_operator.runtime.files import atomic_write_text


class FileTraceStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    async def save_operation_brief(self, brief: OperationBrief) -> None:
        bundle = await self.load_brief_bundle(brief.operation_id) or TraceBriefBundle()
        bundle.operation_brief = brief
        atomic_write_text(self._brief_path(brief.operation_id), bundle.model_dump_json(indent=2))

    async def append_iteration_brief(self, operation_id: str, brief: IterationBrief) -> None:
        bundle = await self.load_brief_bundle(operation_id) or TraceBriefBundle()
        bundle.iteration_briefs = [
            item for item in bundle.iteration_briefs if item.iteration != brief.iteration
        ]
        bundle.iteration_briefs.append(brief)
        bundle.iteration_briefs.sort(key=lambda item: item.iteration)
        atomic_write_text(self._brief_path(operation_id), bundle.model_dump_json(indent=2))

    async def append_agent_turn_brief(
        self,
        operation_id: str,
        brief: AgentTurnBrief,
    ) -> None:
        bundle = await self.load_brief_bundle(operation_id) or TraceBriefBundle()
        bundle.agent_turn_briefs = [
            item
            for item in bundle.agent_turn_briefs
            if not (item.iteration == brief.iteration and item.session_id == brief.session_id)
        ]
        bundle.agent_turn_briefs.append(brief)
        atomic_write_text(self._brief_path(operation_id), bundle.model_dump_json(indent=2))
        agents_dir = self._operation_dir(operation_id) / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        summary_path = agents_dir / f"{brief.session_id}-{brief.iteration}.summary.json"
        atomic_write_text(summary_path, brief.model_dump_json(indent=2))

    async def append_command_brief(self, operation_id: str, brief: CommandBrief) -> None:
        bundle = await self.load_brief_bundle(operation_id) or TraceBriefBundle()
        bundle.command_briefs = [
            item for item in bundle.command_briefs if item.command_id != brief.command_id
        ]
        bundle.command_briefs.append(brief)
        atomic_write_text(self._brief_path(operation_id), bundle.model_dump_json(indent=2))

    async def append_evaluation_brief(self, operation_id: str, brief: EvaluationBrief) -> None:
        bundle = await self.load_brief_bundle(operation_id) or TraceBriefBundle()
        bundle.evaluation_briefs = [
            item for item in bundle.evaluation_briefs if item.iteration != brief.iteration
        ]
        bundle.evaluation_briefs.append(brief)
        bundle.evaluation_briefs.sort(key=lambda item: item.iteration)
        atomic_write_text(self._brief_path(operation_id), bundle.model_dump_json(indent=2))

    async def save_decision_memo(self, operation_id: str, memo: DecisionMemo) -> None:
        reasoning_dir = self._operation_dir(operation_id) / "reasoning"
        reasoning_dir.mkdir(parents=True, exist_ok=True)
        path = reasoning_dir / f"{memo.iteration}.json"
        atomic_write_text(path, memo.model_dump_json(indent=2))

    async def append_trace_record(self, operation_id: str, record: TraceRecord) -> None:
        path = self._timeline_path(operation_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json())
            handle.write("\n")

    async def write_report(self, operation_id: str, report: str) -> None:
        path = self._report_path(operation_id)
        atomic_write_text(path, report)

    async def load_brief_bundle(self, operation_id: str) -> TraceBriefBundle | None:
        path = self._brief_path(operation_id)
        if not path.exists():
            return None
        return TraceBriefBundle.model_validate_json(path.read_text(encoding="utf-8"))

    async def load_trace_records(self, operation_id: str) -> list[TraceRecord]:
        path = self._timeline_path(operation_id)
        if not path.exists():
            return []
        records: list[TraceRecord] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                records.append(TraceRecord.model_validate(json.loads(raw)))
        return records

    async def load_decision_memos(self, operation_id: str) -> list[DecisionMemo]:
        reasoning_dir = self._operation_dir(operation_id) / "reasoning"
        if not reasoning_dir.exists():
            return []
        memos: list[DecisionMemo] = []
        for path in sorted(reasoning_dir.glob("*.json")):
            memos.append(DecisionMemo.model_validate_json(path.read_text(encoding="utf-8")))
        return memos

    async def load_report(self, operation_id: str) -> str | None:
        path = self._report_path(operation_id)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def _operation_dir(self, operation_id: str) -> Path:
        return self._root / operation_id

    def _brief_path(self, operation_id: str) -> Path:
        return self._root / f"{operation_id}.brief.json"

    def _timeline_path(self, operation_id: str) -> Path:
        return self._root / f"{operation_id}.timeline.jsonl"

    def _report_path(self, operation_id: str) -> Path:
        return self._root / f"{operation_id}.report.md"
