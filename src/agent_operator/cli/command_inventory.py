"""Canonical CLI command inventory for ADR 0210."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CliCommandRecord:
    """Declared command-shape metadata for one CLI path."""

    path: str
    stability: str
    category: str
    notes: str


ADR_0219_CANONICAL_ROOT_COMMANDS: frozenset[str] = frozenset(
    {
        "agent",
        "answer",
        "ask",
        "cancel",
        "clear",
        "config",
        "fleet",
        "init",
        "interrupt",
        "mcp",
        "message",
        "pause",
        "policy",
        "project",
        "run",
        "status",
        "unpause",
        "watch",
    }
)


ADR_0219_GROUPING_BACKLOG: dict[str, tuple[str, ...]] = {
    "operation_detail": (
        "artifacts",
        "attention",
        "dashboard",
        "log",
        "memory",
        "report",
        "session",
        "tasks",
    ),
    "fleet_inventory": (
        "agenda",
        "history",
        "list",
    ),
    "edit": (
        "patch-criteria",
        "patch-harness",
        "patch-objective",
        "set-execution-profile",
    ),
    "advanced_nl": ("converse",),
    "autonomy": ("involvement",),
}


COMMAND_INVENTORY: tuple[CliCommandRecord, ...] = (
    CliCommandRecord("agent", "stable", "admin", "Namespace for configured agent inspection."),
    CliCommandRecord("agent list", "stable", "admin", "Machine-readable agent roster exists."),
    CliCommandRecord("agent show", "stable", "admin", "Machine-readable agent detail exists."),
    CliCommandRecord("agenda", "stable", "read", "Cross-operation actionable agenda."),
    CliCommandRecord("answer", "stable", "control", "Canonical attention-answer surface."),
    CliCommandRecord("artifacts", "stable", "read", "Canonical artifact inspection surface."),
    CliCommandRecord("ask", "stable", "read", "Read-only NL query surface."),
    CliCommandRecord("attention", "stable", "read", "Canonical attention inspection surface."),
    CliCommandRecord("cancel", "stable", "control", "Canonical cancellation surface."),
    CliCommandRecord("clear", "stable", "lifecycle", "Workspace runtime reset surface."),
    CliCommandRecord(
        "command", "transitional", "debug-alias", "Hidden top-level alias for debug command."
    ),
    CliCommandRecord("config", "stable", "admin", "Global operator config namespace."),
    CliCommandRecord("config edit", "stable", "admin", "Open global config in editor."),
    CliCommandRecord("config set-root", "stable", "admin", "Register project-discovery root."),
    CliCommandRecord("config show", "stable", "admin", "Redacted global config surface."),
    CliCommandRecord(
        "converse", "stable", "control", "Interactive NL dialogue over operator state."
    ),
    CliCommandRecord(
        "context", "transitional", "debug-alias", "Hidden top-level alias for debug context."
    ),
    CliCommandRecord(
        "daemon", "transitional", "debug-alias", "Hidden top-level alias for debug daemon."
    ),
    CliCommandRecord("dashboard", "stable", "read", "One-operation live dashboard."),
    CliCommandRecord("debug", "debug-only", "debug", "Canonical debug/repair namespace."),
    CliCommandRecord("debug command", "debug-only", "debug", "Low-level command enqueue surface."),
    CliCommandRecord("debug context", "debug-only", "debug", "Effective control-plane context."),
    CliCommandRecord("debug daemon", "debug-only", "debug", "Wakeup sweep and background resume."),
    CliCommandRecord("debug event", "debug-only", "debug", "Debug event repair namespace."),
    CliCommandRecord(
        "debug event append", "debug-only", "debug", "Allowlisted low-level event repair."
    ),
    CliCommandRecord("debug inspect", "debug-only", "debug", "Full forensic payload surface."),
    CliCommandRecord("debug recover", "debug-only", "debug", "Force stuck-session recovery."),
    CliCommandRecord("debug resume", "debug-only", "debug", "Manual resume/tick lifecycle aid."),
    CliCommandRecord("debug sessions", "debug-only", "debug", "Background/session inspection."),
    CliCommandRecord("debug tick", "debug-only", "debug", "Single scheduler cycle helper."),
    CliCommandRecord("debug trace", "debug-only", "debug", "Forensic trace surface."),
    CliCommandRecord("debug wakeups", "debug-only", "debug", "Wakeup queue inspection."),
    CliCommandRecord("fleet", "stable", "lifecycle", "Fleet-first supervision surface."),
    CliCommandRecord("history", "stable", "read", "Project history ledger surface."),
    CliCommandRecord("init", "stable", "lifecycle", "Workspace profile bootstrap."),
    CliCommandRecord(
        "inspect", "transitional", "debug-alias", "Hidden top-level alias for debug inspect."
    ),
    CliCommandRecord("interrupt", "stable", "control", "Canonical stop-turn control surface."),
    CliCommandRecord("involvement", "stable", "control", "Autonomy-level mutation surface."),
    CliCommandRecord("list", "stable", "read", "Persisted operation inventory."),
    CliCommandRecord("log", "stable", "read", "Condensed transcript/log surface."),
    CliCommandRecord("mcp", "stable", "integration", "Inbound MCP server entrypoint."),
    CliCommandRecord("memory", "stable", "read", "Canonical memory inspection surface."),
    CliCommandRecord("message", "stable", "control", "Durable operator-context injection surface."),
    CliCommandRecord(
        "patch-criteria", "stable", "control", "Canonical success-criteria patch surface."
    ),
    CliCommandRecord("patch-harness", "stable", "control", "Canonical harness patch surface."),
    CliCommandRecord("patch-objective", "stable", "control", "Canonical objective patch surface."),
    CliCommandRecord("pause", "stable", "control", "Canonical pause surface."),
    CliCommandRecord("policy", "stable", "policy", "Project policy namespace."),
    CliCommandRecord("policy explain", "stable", "policy", "Policy explainability surface."),
    CliCommandRecord("policy inspect", "stable", "policy", "Inspect one policy record."),
    CliCommandRecord("policy list", "stable", "policy", "List policy inventory."),
    CliCommandRecord("policy projects", "stable", "policy", "Projects-with-policies index."),
    CliCommandRecord("policy record", "stable", "policy", "Explicit policy mutation surface."),
    CliCommandRecord("policy revoke", "stable", "policy", "Explicit policy revocation surface."),
    CliCommandRecord("project", "stable", "project", "Project profile namespace."),
    CliCommandRecord("project create", "stable", "project", "Project-profile authoring surface."),
    CliCommandRecord(
        "project dashboard", "stable", "project", "Project-scoped supervision surface."
    ),
    CliCommandRecord("project inspect", "stable", "project", "Inspect one project profile."),
    CliCommandRecord("project list", "stable", "project", "Project profile inventory."),
    CliCommandRecord("project resolve", "stable", "project", "Resolved project-run configuration."),
    CliCommandRecord(
        "recover", "transitional", "debug-alias", "Hidden top-level alias for debug recover."
    ),
    CliCommandRecord("report", "stable", "read", "Retrospective operation report."),
    CliCommandRecord(
        "resume", "transitional", "debug-alias", "Hidden top-level alias for debug resume."
    ),
    CliCommandRecord("run", "stable", "lifecycle", "Canonical operation creation entrypoint."),
    CliCommandRecord("session", "stable", "read", "Task-addressed session surface."),
    CliCommandRecord(
        "sessions", "transitional", "debug-alias", "Hidden top-level alias for debug sessions."
    ),
    CliCommandRecord(
        "set-execution-profile", "stable", "control", "Execution-profile mutation surface."
    ),
    CliCommandRecord("smoke", "debug-only", "verification", "Hidden live verification namespace."),
    CliCommandRecord(
        "smoke alignment-post-research-plan",
        "debug-only",
        "verification",
        "Verification-only live smoke.",
    ),
    CliCommandRecord(
        "smoke alignment-post-research-plan-claude-acp",
        "debug-only",
        "verification",
        "Verification-only live smoke.",
    ),
    CliCommandRecord(
        "smoke codex-continuation",
        "debug-only",
        "verification",
        "Verification-only live smoke.",
    ),
    CliCommandRecord(
        "smoke mixed-agent-selection",
        "debug-only",
        "verification",
        "Verification-only live smoke.",
    ),
    CliCommandRecord(
        "smoke mixed-agent-selection-claude-acp",
        "debug-only",
        "verification",
        "Verification-only live smoke.",
    ),
    CliCommandRecord(
        "smoke mixed-code-agent-selection",
        "debug-only",
        "verification",
        "Verification-only live smoke.",
    ),
    CliCommandRecord(
        "smoke mixed-code-agent-selection-claude-acp",
        "debug-only",
        "verification",
        "Verification-only live smoke.",
    ),
    CliCommandRecord("status", "stable", "read", "Canonical shell-native one-operation summary."),
    CliCommandRecord(
        "stop-turn",
        "transitional",
        "debug-alias",
        "Hidden top-level alias kept during interrupt transition.",
    ),
    CliCommandRecord("tasks", "stable", "read", "Canonical task-board inspection surface."),
    CliCommandRecord(
        "tick", "transitional", "debug-alias", "Hidden top-level alias for debug tick."
    ),
    CliCommandRecord(
        "trace", "transitional", "debug-alias", "Hidden top-level alias for debug trace."
    ),
    CliCommandRecord("unpause", "stable", "control", "Canonical resume-after-pause surface."),
    CliCommandRecord(
        "wakeups", "transitional", "debug-alias", "Hidden top-level alias for debug wakeups."
    ),
    CliCommandRecord("watch", "stable", "read", "Lightweight live watch surface."),
)
