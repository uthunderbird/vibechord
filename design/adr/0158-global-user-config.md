# ADR 0158: Global user config (~/.operator/config.yaml)

- Date: 2026-04-13

## Decision Status

Accepted

## Implementation Status

Verified

## Context

The operator currently supports three layers of project-level configuration:

1. `operator-profile.yaml` — committed project defaults
2. `operator-profiles/*.yaml` — committed named profiles
3. `.operator/profiles/*.yaml` — local developer overrides

But WORKFLOW-UX-VISION.md defines a fourth layer:

> `~/.operator/config.yaml` — global user config: project roots to scan, PM provider
> credentials, global defaults. (Lowest priority in resolution order.)

This layer is absent. `config.py` defines `OperatorSettings` (a `pydantic_settings.BaseSettings`
subclass) that reads provider API keys and adapter settings from environment variables, but
there is no `~/.operator/config.yaml` loading. The resolution order documented in
CONFIG_UX_VISION.md is not fully implemented:

```
CLI flags                    ← highest priority
local profile
named committed profile
operator-profile.yaml default
global defaults (~/.operator/config.yaml)  ← lowest priority — MISSING
```

### What the global config must hold

Per WORKFLOW-UX-VISION.md:

- `project_roots` — list of directory paths to scan for fleet discovery (ADR 0159)
- global `OperatorSettings` defaults that the user wants to apply across all projects without
  setting environment variables (e.g., preferred brain model, default involvement level)
- PM provider credentials (for native GitHub provider; hooks for others — see ADR 0160)

## Decision

Add `~/.operator/config.yaml` loading to the config resolution stack.

### File location

`~/.operator/config.yaml` — under the user's home directory. The `~/.operator/` directory
is the canonical per-user operator data directory (alongside any future user-level caches or
state files).

### Schema

```yaml
# ~/.operator/config.yaml
project_roots:
  - ~/Projects/
  - ~/work/client-a/

defaults:
  involvement_level: auto          # default InvolvementLevel if no profile sets one
  brain_model: gpt-4.1             # override for users who want a different default brain
  message_window: 3                # override for operator_message_window default

providers:
  github:
    token: ghp_...                 # GitHub personal access token for --from github: intake
```

### Python schema

```python
class GlobalUserDefaults(BaseModel):
    involvement_level: str | None = None
    brain_model: str | None = None
    message_window: int | None = None

class GlobalProviderConfig(BaseModel):
    github: dict[str, str] = Field(default_factory=dict)

class GlobalUserConfig(BaseModel):
    project_roots: list[Path] = Field(default_factory=list)
    defaults: GlobalUserDefaults = Field(default_factory=GlobalUserDefaults)
    providers: GlobalProviderConfig = Field(default_factory=GlobalProviderConfig)
```

### Loading

`GlobalUserConfig` is loaded at process start by a new `load_global_config()` function in
`config.py` (or a new `src/agent_operator/global_config.py`):

```python
def load_global_config() -> GlobalUserConfig:
    path = Path.home() / ".operator" / "config.yaml"
    if not path.exists():
        return GlobalUserConfig()
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    return GlobalUserConfig.model_validate(data)
```

The file is optional — absence is not an error. An empty `GlobalUserConfig` is returned when
the file does not exist.

### Integration into resolution order

`GlobalUserConfig.defaults` values feed into `OperationProfile` resolution as lowest-priority
defaults in `runtime/profiles.py:resolve_project_run_config()`. Profile and CLI flags override
them. This does not require changes to the `OperatorSettings` class; global config values
supplement it.

### CLI: `operator config`

A new `operator config` command should expose:

```
operator config show          # print resolved global config (redacting token values)
operator config edit          # open ~/.operator/config.yaml in $EDITOR (create if absent)
operator config set-root PATH # append a project root to project_roots
```

These can live in a new `config.py` commands module or be added to `project.py`.

## Prerequisites for resolution

1. Create `GlobalUserConfig` Pydantic model.
2. Implement `load_global_config()` with graceful missing-file handling.
3. Integrate `GlobalUserConfig.defaults` into `resolve_project_run_config()` as the
   lowest-priority layer.
4. Add `operator config` CLI commands.
5. Tests: absent file returns empty defaults; present file overrides OperatorSettings defaults;
   CLI flags still override global config.

## Consequences

- The resolution order documented in CONFIG_UX_VISION.md and WORKFLOW-UX-VISION.md is
  fully implemented.
- `project_roots` is available for fleet auto-discovery (ADR 0159).
- GitHub token for `--from github:` intake (ADR 0160) has a permanent home.
- No breaking changes — all current behavior is unchanged when the file is absent.

## Related

- `src/agent_operator/config.py` — `OperatorSettings`
- `src/agent_operator/runtime/profiles.py` — `resolve_project_run_config`
- [WORKFLOW-UX-VISION.md §What's Committed vs. What Stays Internal](../WORKFLOW-UX-VISION.md)
- [ADR 0159](./0159-fleet-auto-discovery.md)
- [ADR 0160](./0160-pm-tool-intake-and-ticket-reporting.md)
