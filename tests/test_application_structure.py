from __future__ import annotations

import ast
from pathlib import Path

APPLICATION_DIR = (
    Path(__file__).resolve().parents[1] / "src" / "agent_operator" / "application"
)
CLI_DIR = Path(__file__).resolve().parents[1] / "src" / "agent_operator" / "cli"


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


def test_adr_0203_v2_mutation_paths_do_not_save_legacy_snapshots() -> None:
    """Catches reintroducing FileOperationStore.save_operation() into v2 mutation paths."""
    paths = [
        APPLICATION_DIR / "operator_service_v2.py",
        APPLICATION_DIR / "drive" / "drive_service.py",
        APPLICATION_DIR / "event_sourcing" / "event_sourced_commands.py",
    ]

    violations: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "save_operation":
                violations.append(f"{path.relative_to(APPLICATION_DIR)}:{node.lineno}")

    assert violations == [], "\n".join(violations)


def test_adr_0203_canonical_read_surfaces_use_event_first_resolution() -> None:
    """Catches read surfaces falling back to snapshot-only v2 operation enumeration."""
    root = Path(__file__).resolve().parents[1] / "src" / "agent_operator"
    required_references = {
        root / "application" / "queries" / "operation_resolution.py": [
            "_load_event_sourced_operation_state",
            "store.load_operation",
        ],
        root / "application" / "queries" / "operation_status_queries.py": [
            "_load_event_sourced_operation",
            "store.load_operation",
        ],
        root / "mcp" / "service.py": ["OperationResolutionService"],
        root / "client.py": ["list_canonical_operation_states"],
    }

    missing: list[str] = []
    for path, needles in required_references.items():
        source = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle not in source:
                missing.append(f"{path.relative_to(root)} missing {needle!r}")

    assert missing == [], "\n".join(missing)


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
    assert len(runtime_guards) == 0


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


def test_legacy_command_effect_persistence_uses_event_append_not_snapshot_save() -> None:
    """ADR 0144: the remaining legacy command-effect path must append canonically."""
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
        and node.name == "persist_legacy_snapshot_command_effect_state"
    )

    direct_save_calls = [
        child.lineno
        for child in ast.walk(persist_method)
        if isinstance(child, ast.Attribute) and child.attr == "save_operation"
    ]
    append_calls = [
        child
        for child in ast.walk(persist_method)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "append_domain_events"
    ]

    assert direct_save_calls == []
    assert len(append_calls) == 1


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


def test_attached_turns_use_no_direct_snapshot_writes() -> None:
    """ADR 0144: attached-turn live polling must not persist business state via save_operation()."""
    attached_turns_file = APPLICATION_DIR / "attached_turns.py"
    source = attached_turns_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    direct_save_callers = sorted(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
        for child in ast.walk(node)
        if isinstance(child, ast.Attribute) and child.attr == "save_operation"
    )

    assert direct_save_callers == []


def test_event_sourced_birth_does_not_emit_active_session_event() -> None:
    """ADR 0170 tranche 1: birth must not reintroduce active-session dual write."""
    birth_file = APPLICATION_DIR / "event_sourcing" / "event_sourced_birth.py"
    source = birth_file.read_text(encoding="utf-8")

    assert "operation.active_session_updated" not in source


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


def test_cli_subpackages_and_boundary_imports_match_adr_0120() -> None:
    """ADR 0120: CLI family packages and disallowed upward imports remain explicit."""
    for package_name in ("commands", "helpers", "rendering", "tui", "workflows"):
        assert (CLI_DIR / package_name / "__init__.py").exists()

    retired = {
        "commands_debug.py",
        "commands_fleet.py",
        "commands_operation_control.py",
        "commands_operation_detail.py",
        "commands_policy.py",
        "commands_project.py",
        "commands_run.py",
        "commands_smoke.py",
        "helpers_logs.py",
        "helpers_policy.py",
        "helpers_rendering.py",
        "helpers_resolution.py",
        "helpers_services.py",
        "rendering.py",
        "rendering_fleet.py",
        "rendering_operation.py",
        "rendering_project.py",
        "rendering_text.py",
        "tui.py",
        "tui_controller.py",
        "tui_io.py",
        "tui_models.py",
        "tui_rendering.py",
        "workflows.py",
        "workflows_control.py",
        "workflows_views.py",
        "workflows_workspace.py",
    }
    present = {path.name for path in CLI_DIR.glob("*.py")}
    assert retired.isdisjoint(present)

    offenders: list[str] = []
    for path in _python_sources(CLI_DIR):
        relative = path.relative_to(CLI_DIR)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                modules = [node.module]
            for module_name in modules:
                if relative.parts[0] == "helpers" and (
                    module_name == "agent_operator.cli.app"
                    or module_name.startswith("agent_operator.cli.commands")
                ):
                    offenders.append(f"{relative} -> {module_name}")
                if relative.parts[0] == "commands" and module_name == "agent_operator.cli.main":
                    offenders.append(f"{relative} -> {module_name}")
                if relative.parts[0] == "tui" and module_name == "agent_operator.cli.main":
                    offenders.append(f"{relative} -> {module_name}")

    assert offenders == []


def test_cli_main_remains_a_thin_facade_over_app_and_shared_exports() -> None:
    """ADR 0120: cli.main stays as a compatibility facade rather than a command root."""
    module = ast.parse((CLI_DIR / "main.py").read_text(encoding="utf-8"))

    assert all(
        not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        for node in module.body
    )
    imported_modules = sorted(
        f"{'.' * node.level}{node.module}"
        for node in module.body
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    assert imported_modules.count(".workflows") == 2
    assert "__future__" in imported_modules
    assert "agent_operator.bootstrap" in imported_modules
    assert ".app" in imported_modules
    assert ".helpers.rendering" in imported_modules


def test_cli_app_registers_commands_via_package_modules() -> None:
    """ADR 0120: command registration flows through cli.app package imports."""
    module = ast.parse((CLI_DIR / "app.py").read_text(encoding="utf-8"))

    command_imports = [
        f"{'.' * node.level}{node.module}"
        for node in module.body
        if isinstance(node, ast.ImportFrom) and node.module is not None
        and f"{'.' * node.level}{node.module}" == ".commands"
    ]

    assert len(command_imports) == 11
