from __future__ import annotations

import ast
from pathlib import Path

APPLICATION_DIR = (
    Path(__file__).resolve().parents[1] / "src" / "agent_operator" / "application"
)


def _python_sources(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def test_application_init_remains_export_only() -> None:
    module = ast.parse((APPLICATION_DIR / "__init__.py").read_text(encoding="utf-8"))

    for node in module.body:
        assert not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))


def test_application_modules_do_not_import_cli() -> None:
    offenders: list[str] = []

    for path in _python_sources(APPLICATION_DIR):
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("agent_operator.cli"):
                        offenders.append(f"{path.relative_to(APPLICATION_DIR)} -> {alias.name}")
            if (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.startswith("agent_operator.cli")
            ):
                offenders.append(f"{path.relative_to(APPLICATION_DIR)} -> {node.module}")

    assert offenders == []


def test_application_keeps_drive_and_event_sourcing_subpackages() -> None:
    assert (APPLICATION_DIR / "drive" / "__init__.py").exists()
    assert (APPLICATION_DIR / "event_sourcing" / "__init__.py").exists()


def test_application_keeps_commands_queries_and_runtime_subpackages() -> None:
    assert (APPLICATION_DIR / "commands" / "__init__.py").exists()
    assert (APPLICATION_DIR / "queries" / "__init__.py").exists()
    assert (APPLICATION_DIR / "runtime" / "__init__.py").exists()


def test_migrated_flat_application_family_modules_are_removed() -> None:
    retired = {
        "operation_agenda_queries.py",
        "operation_attention.py",
        "operation_cancellation.py",
        "operation_commands.py",
        "operation_control_state.py",
        "operation_dashboard_queries.py",
        "operation_delivery_commands.py",
        "operation_event_relay.py",
        "operation_fleet_workbench_queries.py",
        "operation_policy_context.py",
        "operation_process_dispatch.py",
        "operation_project_dashboard_queries.py",
        "operation_projections.py",
        "operation_runtime.py",
        "operation_runtime_context.py",
        "operation_runtime_reconciliation.py",
        "operation_state_views.py",
        "operation_traceability.py",
    }

    present = {path.name for path in APPLICATION_DIR.glob("*.py")}
    assert retired.isdisjoint(present)


def test_drive_loop_save_operation_only_via_advance_checkpoint() -> None:
    """ADR 0144: save_operation() in the drive loop must be called only from
    _advance_checkpoint(), which is the explicit read-path checkpoint helper.
    Direct calls to save_operation() outside _advance_checkpoint() would
    introduce new mutation-path snapshot writes and violate the write-path rule.
    """
    drive_file = APPLICATION_DIR / "drive" / "operation_drive.py"
    source = drive_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        if node.name == "_advance_checkpoint":
            continue
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Attribute)
                and child.attr == "save_operation"
            ):
                violations.append(
                    f"Direct save_operation() call in {node.name}() at line {child.lineno} "
                    f"— use _advance_checkpoint() instead (ADR 0144)"
                )

    assert violations == [], "\n".join(violations)


def test_event_sourced_operation_commands_do_not_force_snapshot_persistence() -> None:
    """ADR 0144: event-sourced command handling must not force snapshot writes."""
    command_file = APPLICATION_DIR / "commands" / "operation_commands.py"
    source = command_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "OperationCommandService"
    )
    method = next(
        node
        for node in class_node.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "apply_event_sourced_operation_command"
    )

    direct_save_calls = [
        child.lineno
        for child in ast.walk(method)
        if isinstance(child, ast.Attribute) and child.attr == "save_operation"
    ]
    persist_calls = [
        child
        for child in ast.walk(method)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "persist_command_effect_state"
    ]

    assert direct_save_calls == []
    assert len(persist_calls) == 1
    assert persist_calls[0].keywords == []


def test_answer_attention_request_command_path_does_not_use_legacy_snapshot_persistence() -> None:
    """ADR 0144: ANSWER_ATTENTION_REQUEST must not retain the legacy snapshot path."""
    command_file = APPLICATION_DIR / "commands" / "operation_commands.py"
    source = command_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "OperationCommandService"
    )
    method = next(
        node
        for node in class_node.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "_apply_answer_attention_request"
    )

    legacy_persist_calls = [
        child.lineno
        for child in ast.walk(method)
        if isinstance(child, ast.Attribute)
        and child.attr == "persist_legacy_snapshot_command_effect_state"
    ]
    runtime_guards = [
        child
        for child in ast.walk(method)
        if isinstance(child, ast.Raise)
        and isinstance(child.exc, ast.Call)
        and isinstance(child.exc.func, ast.Name)
        and child.exc.func.id == "RuntimeError"
    ]

    assert legacy_persist_calls == []
    assert len(runtime_guards) == 1


def test_finalize_pending_attention_resolutions_uses_no_legacy_snapshot_persistence() -> None:
    """ADR 0144: pending attention resolution finalization must replay from canonical events."""
    command_file = APPLICATION_DIR / "commands" / "operation_commands.py"
    source = command_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "OperationCommandService"
    )
    method = next(
        node
        for node in class_node.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "finalize_pending_attention_resolutions"
    )

    legacy_persist_calls = [
        child.lineno
        for child in ast.walk(method)
        if isinstance(child, ast.Attribute)
        and child.attr == "persist_legacy_snapshot_command_effect_state"
    ]
    append_calls = [
        child
        for child in ast.walk(method)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "append_domain_events"
    ]

    assert legacy_persist_calls == []
    assert len(append_calls) == 1


def test_record_policy_decision_uses_canonical_event_append_without_legacy_snapshot() -> None:
    """ADR 0144: RECORD_POLICY_DECISION must append canonical policy-context events."""
    command_file = APPLICATION_DIR / "commands" / "operation_commands.py"
    source = command_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "OperationCommandService"
    )
    method = next(
        node
        for node in class_node.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "record_policy_decision"
    )

    legacy_persist_calls = [
        child.lineno
        for child in ast.walk(method)
        if isinstance(child, ast.Attribute)
        and child.attr == "persist_legacy_snapshot_command_effect_state"
    ]
    append_calls = [
        child
        for child in ast.walk(method)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "append_domain_events"
    ]

    assert legacy_persist_calls == []
    assert len(append_calls) == 1


def test_revoke_policy_decision_uses_canonical_event_append_without_legacy_snapshot() -> None:
    """ADR 0144: REVOKE_POLICY_DECISION must append canonical policy-context events."""
    command_file = APPLICATION_DIR / "commands" / "operation_commands.py"
    source = command_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "OperationCommandService"
    )
    method = next(
        node
        for node in class_node.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "revoke_policy_decision"
    )

    legacy_persist_calls = [
        child.lineno
        for child in ast.walk(method)
        if isinstance(child, ast.Attribute)
        and child.attr == "persist_legacy_snapshot_command_effect_state"
    ]
    append_calls = [
        child
        for child in ast.walk(method)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "append_domain_events"
    ]

    assert legacy_persist_calls == []
    assert len(append_calls) == 1


def test_stop_agent_turn_uses_canonical_event_append_without_legacy_snapshot() -> None:
    """ADR 0144: STOP_AGENT_TURN must not retain direct snapshot persistence."""
    command_file = APPLICATION_DIR / "commands" / "operation_commands.py"
    source = command_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "OperationCommandService"
    )
    method = next(
        node
        for node in class_node.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "_apply_stop_agent_turn"
    )

    legacy_persist_calls = [
        child.lineno
        for child in ast.walk(method)
        if isinstance(child, ast.Attribute)
        and child.attr == "persist_legacy_snapshot_command_effect_state"
    ]
    append_calls = [
        child
        for child in ast.walk(method)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "append_domain_events"
    ]

    assert legacy_persist_calls == []
    assert len(append_calls) == 1


def test_stop_operation_uses_canonical_event_append_without_legacy_snapshot() -> None:
    """ADR 0144: STOP_OPERATION must not retain direct snapshot persistence."""
    command_file = APPLICATION_DIR / "commands" / "operation_commands.py"
    source = command_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "OperationCommandService"
    )
    method = next(
        node
        for node in class_node.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "_apply_stop_operation"
    )

    legacy_persist_calls = [
        child.lineno
        for child in ast.walk(method)
        if isinstance(child, ast.Attribute)
        and child.attr == "persist_legacy_snapshot_command_effect_state"
    ]
    append_calls = [
        child
        for child in ast.walk(method)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "append_domain_events"
    ]

    assert legacy_persist_calls == []
    assert len(append_calls) == 1


def test_control_state_coordinator_keeps_replay_sync_separate_from_snapshot_writes() -> None:
    """ADR 0144: canonical command-effect sync must not hide snapshot writes behind a flag."""
    control_file = APPLICATION_DIR / "commands" / "operation_control_state.py"
    source = control_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "OperationControlStateCoordinator"
    )
    persist_method = next(
        node
        for node in class_node.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "persist_command_effect_state"
    )

    direct_save_calls = [
        child.lineno
        for child in ast.walk(persist_method)
        if isinstance(child, ast.Attribute) and child.attr == "save_operation"
    ]

    assert direct_save_calls == []


def test_operation_lifecycle_uses_no_direct_snapshot_writes() -> None:
    """ADR 0144: lifecycle persistence must project via canonical events."""
    lifecycle_file = APPLICATION_DIR / "operation_lifecycle.py"
    source = lifecycle_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    direct_save_callers = sorted(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
        for child in ast.walk(node)
        if isinstance(child, ast.Attribute) and child.attr == "save_operation"
    )

    assert direct_save_callers == []


def test_queries_do_not_import_commands_family() -> None:
    offenders: list[str] = []
    queries_dir = APPLICATION_DIR / "queries"

    for path in _python_sources(queries_dir):
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("agent_operator.application.commands"):
                        offenders.append(f"{path.relative_to(APPLICATION_DIR)} -> {alias.name}")
            if (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.startswith("agent_operator.application.commands")
            ):
                offenders.append(f"{path.relative_to(APPLICATION_DIR)} -> {node.module}")

    assert offenders == []
