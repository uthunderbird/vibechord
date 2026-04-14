from __future__ import annotations

from pathlib import Path

import yaml

from agent_operator.config import GlobalUserConfig, load_global_config, write_global_config

LOCAL_PROFILE_FILENAME = "operator-profile.yaml"


def discover_projects(roots: list[Path], max_depth: int = 4) -> list[Path]:
    """Discover project roots under the provided search roots.

    Args:
        roots: Search roots to scan.
        max_depth: Maximum directory depth to descend from each root.

    Returns:
        Resolved project directories containing `.operator/` or `operator-profile.yaml`.
    """

    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        _scan_project_root(
            root.expanduser().resolve(),
            depth=0,
            max_depth=max_depth,
            found=found,
            seen=seen,
        )
    return found


def project_name_for_root(project_root: Path) -> str:
    """Return the display name for a discovered project root."""

    profile_path = project_root / LOCAL_PROFILE_FILENAME
    if profile_path.is_file():
        payload = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
        if isinstance(payload, dict):
            name = payload.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return project_root.name


def add_project_root_parents(
    projects: list[Path],
    *,
    path: Path | None = None,
) -> tuple[GlobalUserConfig, bool]:
    """Persist parent directories for discovered projects into global config."""

    config = load_global_config(path)
    changed = False
    existing = {item.expanduser().resolve() for item in config.project_roots}
    for project in projects:
        parent = project.resolve().parent
        if parent not in existing:
            config.project_roots.append(parent)
            existing.add(parent)
            changed = True
    if changed:
        write_global_config(config, path)
    return config, changed


def _scan_project_root(
    path: Path,
    *,
    depth: int,
    max_depth: int,
    found: list[Path],
    seen: set[Path],
) -> None:
    if depth > max_depth or not path.is_dir() or path.is_symlink():
        return
    if _is_project_root(path):
        resolved = path.resolve()
        if resolved not in seen:
            found.append(resolved)
            seen.add(resolved)
        return
    try:
        children = sorted(path.iterdir(), key=lambda item: item.name)
    except OSError:
        return
    for child in children:
        if not child.is_dir() or child.is_symlink() or child.name.startswith("."):
            continue
        _scan_project_root(
            child,
            depth=depth + 1,
            max_depth=max_depth,
            found=found,
            seen=seen,
        )


def _is_project_root(path: Path) -> bool:
    return (path / ".operator").is_dir() or (path / LOCAL_PROFILE_FILENAME).is_file()
