"""Workspace wiring for delivery surfaces."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from vibechord.adapters import (
    AdapterGateway,
    LocalRuleBrain,
    ProcessAgentAdapter,
    ProcessBrain,
    ScriptedAgentAdapter,
)
from vibechord.command import CommandApplication
from vibechord.driver import OperationDriver
from vibechord.openai_adapter import OpenAIResponsesBrain
from vibechord.projection import ProjectionService
from vibechord.protocols import OperatorBrain
from vibechord.store import JsonlEventStore
from vibechord.time import SystemClock


@dataclass(frozen=True)
class AppContext:
    """Wired application context."""

    root: Path
    event_store: JsonlEventStore
    command_application: CommandApplication
    projection_service: ProjectionService
    operation_driver: OperationDriver


def init_workspace(root: Path) -> Path:
    """Initialize workspace-local storage."""

    state_dir = root / ".vibechord"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "events.jsonl").touch(exist_ok=True)
    return state_dir


def build_context(root: Path) -> AppContext:
    """Build a default local application context."""

    state_dir = init_workspace(root)
    event_store = JsonlEventStore(state_dir / "events.jsonl", SystemClock())
    command_application = CommandApplication(event_store)
    projection_service = ProjectionService(event_store)
    agent_command = os.environ.get("VIBECHORD_AGENT_COMMAND")
    agent_adapter = (
        ProcessAgentAdapter(tuple(shlex.split(agent_command)))
        if agent_command
        else ScriptedAgentAdapter()
    )
    brain_command = os.environ.get("VIBECHORD_BRAIN_COMMAND")
    openai_key = os.environ.get("OPENAI_API_KEY")
    brain: OperatorBrain
    if brain_command:
        brain = ProcessBrain(tuple(shlex.split(brain_command)))
    elif openai_key:
        brain = OpenAIResponsesBrain(
            api_key=openai_key,
            model=os.environ.get("VIBECHORD_OPENAI_MODEL", "gpt-5.4"),
        )
    else:
        brain = LocalRuleBrain()
    gateway = AdapterGateway(brain, agent_adapter)
    operation_driver = OperationDriver(event_store, projection_service, gateway)
    return AppContext(
        root=root,
        event_store=event_store,
        command_application=command_application,
        projection_service=projection_service,
        operation_driver=operation_driver,
    )
