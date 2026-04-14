# ADR 0159: Fleet auto-discovery via project_roots

- Date: 2026-04-13

## Decision Status

Accepted

## Implementation Status

Verified

## Context

`operator fleet` and `operator list` today operate on the `.operator/` directory of the
current working directory (or the git root discovered from it). There is no mechanism for
aggregating operations across multiple projects.

WORKFLOW-UX-VISION.md defines a multi-project fleet model:

> The fleet view aggregates operations from all configured project roots. Roots are configured
> in `~/.operator/config.yaml`:
>
> ```yaml
> project_roots:
>   - ~/Projects/
>   - ~/work/client-a/
> ```
>
> Operator scans each root for directories containing a `.operator/` data dir or an
> `operator-profile.yaml`. Scan depth is configurable (default: 4 levels).

The first-run UX adds:

> If `operator fleet` is invoked with no roots configured and no local `.operator/` dir,
> operator auto-discovers projects by scanning under `~/` (depth-limited to 3 levels) and
> prompts: "Found N projects — Add them to your fleet view? [Y/n]"

## Decision

Implement fleet auto-discovery as an extension to `operator fleet` and `operator list`.

### Prerequisites

ADR 0158 must be implemented first — `project_roots` is stored in `~/.operator/config.yaml`.

### Discovery algorithm

```python
def discover_projects(roots: list[Path], max_depth: int = 4) -> list[Path]:
    """Return paths of git roots that contain .operator/ or operator-profile.yaml."""
    found = []
    for root in roots:
        _scan(root.expanduser(), depth=0, max_depth=max_depth, found=found)
    return found

def _scan(path: Path, depth: int, max_depth: int, found: list[Path]) -> None:
    if depth > max_depth:
        return
    if (path / ".operator").is_dir() or (path / "operator-profile.yaml").is_file():
        found.append(path)
        return  # do not scan inside a project root
    for child in path.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            _scan(child, depth + 1, max_depth, found)
```

Symlinks are not followed. Hidden directories (`.*`) are skipped. Scan stops descending
into a directory once it is identified as a project root (no nested projects).

### First-run UX

When `operator fleet` is called and:
- `project_roots` in `~/.operator/config.yaml` is empty or the file does not exist, AND
- no `.operator/` directory exists in the current git root

Then:
1. Auto-scan `~/` with depth 3.
2. If projects are found, prompt:

```
Found 3 projects with operator data:
  ~/Projects/my-repo
  ~/Projects/other-repo
  ~/work/client-a/project

Add them to your fleet view? [Y/n]
```

3. On `Y`: write the parent directories of the discovered projects as `project_roots` entries
   in `~/.operator/config.yaml` (creating the file if absent).
4. On `n`: continue with local-only fleet view, no file written.

If `--json` is used, skip the interactive prompt and use local-only mode.

### Fleet data aggregation

After discovery, `fleet_async` and `list_async` in `cli/workflows.py` must:
1. Collect all discovered project roots.
2. For each root, load its `.operator/` state (operations, statuses).
3. Merge and sort results by recency or status.
4. Add a `project` column to fleet output showing the project name (from
   `operator-profile.yaml` `name` field, or the directory name as fallback).

### Filtering

Fleet filtering (existing `--project` flag) filters by project name. With multi-project
fleet, this becomes more useful — `operator fleet --project my-repo` shows only that project.

### `operator fleet --discover`

An explicit discovery command for non-interactive use:

```
operator fleet --discover [--depth N] [--add]
```

- `--discover` runs the scan and prints discovered projects.
- `--add` writes the discovered roots to `~/.operator/config.yaml` without prompting.

## Prerequisites for resolution

1. ADR 0158 implemented (`GlobalUserConfig` with `project_roots` available).
2. Implement `discover_projects()` scanner.
3. Extend `fleet_async` and `list_async` to aggregate across discovered projects.
4. Implement first-run UX prompt in `operator fleet`.
5. Add `operator fleet --discover [--add]` flag.
6. Tests: scanner finds projects at depth ≤ max_depth; hidden dirs skipped; symlinks not
   followed; nested projects not double-counted; first-run prompt writes config on `Y`.

## Consequences

- `operator fleet` becomes a true cross-project command, not a local-only view.
- First-run UX makes onboarding frictionless — the user does not need to configure roots
  manually before getting a useful fleet view.
- Scan is file-system-only at discovery time; active operation data is loaded lazily per
  project on demand.

## Related

- `src/agent_operator/cli/commands/fleet.py` — target for new flags
- `src/agent_operator/cli/workflows.py` — `fleet_async`, `list_async` aggregation
- [WORKFLOW-UX-VISION.md §Multi-Project Fleet View](../WORKFLOW-UX-VISION.md)
- [ADR 0158](./0158-global-user-config.md)
