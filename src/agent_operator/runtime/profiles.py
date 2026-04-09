from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from agent_operator.config import OperatorSettings
from agent_operator.domain import (
    InvolvementLevel,
    ProjectProfile,
    ResolvedProjectRunConfig,
    RunMode,
)


@dataclass(frozen=True)
class OperatorDataDirResolution:
    path: Path
    source: str


@dataclass(frozen=True)
class ProjectProfileSelection:
    profile: ProjectProfile | None
    path: Path | None
    source: str | None
    candidate_names: tuple[str, ...] = ()


class _IndentedSafeDumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        super().increase_indent(flow, False)


LOCAL_PROFILE_FILENAME = "operator-profile.yaml"
COMMITTED_PROFILE_DIRNAME = "operator-profiles"


def resolve_operator_data_dir(
    settings: OperatorSettings,
    *,
    cwd: Path | None = None,
) -> OperatorDataDirResolution:
    configured = Path(settings.data_dir)
    current = (cwd or Path.cwd()).resolve()
    if configured.is_absolute():
        return OperatorDataDirResolution(path=configured, source="configured")
    if "data_dir" in settings.model_fields_set or configured != Path(".operator"):
        return OperatorDataDirResolution(
            path=(current / configured).resolve(),
            source="configured",
        )
    for parent in (current, *current.parents):
        candidate = parent / ".operator"
        if candidate.is_dir():
            return OperatorDataDirResolution(path=candidate, source="discovered_ancestor")
    for parent in (current, *current.parents):
        if (parent / ".git").exists():
            return OperatorDataDirResolution(
                path=parent / ".operator",
                source="discovered_git_root",
            )
    return OperatorDataDirResolution(path=current / ".operator", source="cwd_default")


def discover_workspace_root(cwd: Path | None = None) -> Path:
    current = (cwd or Path.cwd()).resolve()
    for parent in (current, *current.parents):
        if (parent / ".operator").is_dir():
            return parent
    for parent in (current, *current.parents):
        if (parent / ".git").exists():
            return parent
    return current


def prepare_operator_settings(
    settings: OperatorSettings,
    *,
    cwd: Path | None = None,
) -> OperatorSettings:
    settings.data_dir = resolve_operator_data_dir(settings, cwd=cwd).path
    return settings


def profile_dir(settings: OperatorSettings) -> Path:
    return settings.data_dir / "profiles"


def committed_profile_dir(*, cwd: Path | None = None) -> Path:
    return discover_workspace_root(cwd) / COMMITTED_PROFILE_DIRNAME


def committed_default_profile_path(*, cwd: Path | None = None) -> Path:
    return discover_workspace_root(cwd) / LOCAL_PROFILE_FILENAME


def list_project_profiles(settings: OperatorSettings) -> list[str]:
    names: set[str] = set()
    for root in (profile_dir(settings), committed_profile_dir()):
        if not root.exists():
            continue
        names.update(
            path.stem
            for path in root.iterdir()
            if path.is_file() and path.suffix in {".yaml", ".yml"}
        )
    return sorted(names)


def profile_path(settings: OperatorSettings, name: str) -> Path:
    for root in (profile_dir(settings), committed_profile_dir()):
        for candidate in (root / f"{name}.yaml", root / f"{name}.yml"):
            if candidate.exists():
                return candidate
    raise RuntimeError(f"Project profile {name!r} was not found.")


def load_project_profile(settings: OperatorSettings, name: str) -> ProjectProfile:
    candidate = profile_path(settings, name)
    return load_project_profile_from_path(candidate, default_name=name)


def load_project_profile_from_path(
    path: Path,
    *,
    default_name: str | None = None,
) -> ProjectProfile:
    candidate = path.resolve()
    payload = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        label = default_name or candidate.stem
        raise RuntimeError(f"Profile {label!r} must deserialize to a mapping.")
    payload.setdefault("name", default_name or candidate.parent.name)
    _resolve_profile_relative_paths(payload, base_dir=candidate.parent)
    return ProjectProfile.model_validate(payload)


def discover_local_project_profile(
    settings: OperatorSettings,
    *,
    cwd: Path | None = None,
) -> ProjectProfileSelection:
    del settings
    launch_dir = (cwd or Path.cwd()).resolve()
    candidate = launch_dir / LOCAL_PROFILE_FILENAME
    if not candidate.is_file():
        return ProjectProfileSelection(profile=None, path=None, source=None)
    profile = load_project_profile_from_path(candidate)
    return ProjectProfileSelection(
        profile=profile,
        path=candidate,
        source="local_profile_file",
        candidate_names=(candidate.name,),
    )


def discover_project_profile_name(
    settings: OperatorSettings,
    *,
    cwd: Path | None = None,
) -> str | None:
    selection = discover_local_project_profile(settings, cwd=cwd)
    return selection.profile.name if selection.profile is not None else None


def discover_project_profile(
    settings: OperatorSettings,
    *,
    cwd: Path | None = None,
) -> ProjectProfile | None:
    selection = discover_local_project_profile(settings, cwd=cwd)
    return selection.profile


def write_project_profile(
    settings: OperatorSettings,
    profile: ProjectProfile,
    *,
    force: bool = False,
    local: bool = True,
    cwd: Path | None = None,
) -> Path:
    root = profile_dir(settings) if local else committed_profile_dir(cwd=cwd)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{profile.name}.yaml"
    if path.exists() and not force:
        raise RuntimeError(
            f"Project profile {profile.name!r} already exists. Use --force to overwrite it."
        )
    payload = _prune_profile_payload(profile.model_dump(mode="json"))
    path.write_text(
        yaml.dump(
            payload,
            Dumper=_IndentedSafeDumper,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    return path


def apply_project_profile_settings(
    settings: OperatorSettings,
    profile: ProjectProfile | None,
) -> None:
    if profile is None:
        return
    if profile.cwd is not None:
        settings.claude.working_directory = profile.cwd
        settings.claude_acp.working_directory = profile.cwd
        settings.codex_acp.working_directory = profile.cwd
        settings.opencode_acp.working_directory = profile.cwd
    for adapter_key, overrides in profile.adapter_settings.items():
        target = getattr(settings, adapter_key, None)
        if target is None:
            continue
        for field_name, value in overrides.items():
            if hasattr(target, field_name):
                setattr(target, field_name, value)


def resolve_project_run_config(
    settings: OperatorSettings,
    *,
    profile: ProjectProfile | None,
    objective: str | None,
    harness: str | None,
    success_criteria: list[str] | None,
    allowed_agents: list[str] | None,
    max_iterations: int | None,
    run_mode: RunMode | None,
    involvement_level: InvolvementLevel | None,
) -> ResolvedProjectRunConfig:
    overrides: list[str] = []

    default_objective = profile.default_objective if profile is not None else None
    if objective is not None and (
        default_objective is not None and objective != default_objective
    ):
        overrides.append("objective")
    if harness is not None:
        overrides.append("harness")
    if success_criteria is not None:
        overrides.append("success_criteria")
    if allowed_agents is not None:
        overrides.append("allowed_agents")
    if max_iterations is not None:
        overrides.append("max_iterations")
    if run_mode is not None:
        overrides.append("run_mode")
    if involvement_level is not None:
        overrides.append("involvement_level")

    resolved_objective = objective if objective is not None else default_objective
    resolved_harness = (
        harness
        if harness is not None
        else (profile.default_harness_instructions if profile is not None else None)
    )
    resolved_success_criteria = (
        list(success_criteria)
        if success_criteria is not None
        else (list(profile.default_success_criteria) if profile is not None else [])
    )
    resolved_agents = (
        list(allowed_agents)
        if allowed_agents is not None
        else (
            list(profile.default_agents)
            if profile is not None and profile.default_agents
            else list(settings.default_allowed_agents)
        )
    )
    resolved_iterations = (
        max_iterations
        if max_iterations is not None
        else (
            profile.default_max_iterations
            if profile is not None and profile.default_max_iterations is not None
            else 100
        )
    )
    resolved_run_mode = (
        run_mode
        if run_mode is not None
        else (
            profile.default_run_mode
            if profile is not None and profile.default_run_mode is not None
            else RunMode.ATTACHED
        )
    )
    resolved_involvement = (
        involvement_level
        if involvement_level is not None
        else (
            profile.default_involvement_level
            if profile is not None and profile.default_involvement_level is not None
            else InvolvementLevel.AUTO
        )
    )

    resolved_message_window = (
        profile.default_message_window
        if profile is not None and profile.default_message_window is not None
        else 3
    )

    return ResolvedProjectRunConfig(
        profile_name=profile.name if profile is not None else None,
        cwd=profile.cwd if profile is not None else None,
        objective_text=resolved_objective,
        default_agents=resolved_agents,
        harness_instructions=resolved_harness,
        success_criteria=resolved_success_criteria,
        max_iterations=resolved_iterations,
        run_mode=resolved_run_mode,
        involvement_level=resolved_involvement,
        message_window=resolved_message_window,
        overrides=overrides,
    )


def _prune_profile_payload(value: object) -> object:
    if isinstance(value, dict):
        pruned: dict[str, object] = {}
        for key, child in value.items():
            normalized = _prune_profile_payload(child)
            if normalized in (None, "", [], {}):
                continue
            pruned[str(key)] = normalized
        return pruned
    if isinstance(value, list):
        items = [_prune_profile_payload(item) for item in value]
        return [item for item in items if item not in (None, "", [], {})]
    return value


def _resolve_profile_relative_paths(payload: dict[str, object], *, base_dir: Path) -> None:
    cwd_value = payload.get("cwd")
    if isinstance(cwd_value, str) and cwd_value.strip():
        candidate = Path(cwd_value)
        if not candidate.is_absolute():
            payload["cwd"] = (base_dir / candidate).resolve()

    paths_value = payload.get("paths")
    if isinstance(paths_value, list):
        resolved_paths: list[Path | object] = []
        for item in paths_value:
            if isinstance(item, str) and item.strip():
                candidate = Path(item)
                resolved_paths.append(
                    (base_dir / candidate).resolve() if not candidate.is_absolute() else candidate
                )
            else:
                resolved_paths.append(item)
        payload["paths"] = resolved_paths
