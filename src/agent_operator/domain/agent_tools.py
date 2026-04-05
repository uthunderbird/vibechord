from __future__ import annotations

from agent_operator.domain.agent import AgentCapability


def standard_coding_agent_capabilities() -> list[AgentCapability]:
    return [
        AgentCapability(
            name="read_files",
            description="Can read repository files and documents.",
        ),
        AgentCapability(
            name="write_files",
            description="Can create new files in the working tree.",
        ),
        AgentCapability(
            name="edit_files",
            description="Can modify existing files in the working tree.",
        ),
        AgentCapability(
            name="grep_search",
            description="Can search repository text by pattern.",
        ),
        AgentCapability(
            name="glob_search",
            description="Can enumerate files and paths by glob-like matching.",
        ),
        AgentCapability(
            name="run_shell_commands",
            description="Can run shell commands in the working directory.",
        ),
    ]
