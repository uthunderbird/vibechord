# ADR 0148: Project profile schema completion and resolution contract

- Date: 2026-04-12

## Decision Status

Accepted

## Implementation Status

Implemented

## Context

`operator` already ships a YAML-backed project-profile surface through `ProjectProfile`,
`ResolvedProjectRunConfig`, `resolve_project_run_config(...)`, `operator project inspect`, and
`operator project resolve`.

Before this closure wave, the repository truth was uneven:

- run-resolution precedence already existed in code, but the committed config reference was still
  a placeholder
- `session_reuse_policy` was an untyped `str | None`
- `project inspect` surfaced `session_reuse_policy`, `dashboard_prefs`, and `paths` without
  clarifying whether they were wired runtime controls, passive metadata, or deferred fields
- `project create` and `init` did not expose all currently implemented run-bound defaults even
  though the schema already carried them

This ADR closes the schema and run-resolution contract to the current implemented repository
surface rather than to the broader aspirational `CONFIG_UX_VISION.md`.

## Decision

### Run resolution order

For `operator run`, the binding resolution order is:

1. explicit CLI flag
2. project profile value
3. global default or hardcoded application default

This contract applies to the run-bound resolved fields exposed by `ResolvedProjectRunConfig`.

### Binding run-resolved fields

The current resolved run contract is:

| Field | Source model | Semantics |
|---|---|---|
| `cwd` | `ResolvedProjectRunConfig.cwd` | working directory associated with the selected profile |
| `objective_text` | `ResolvedProjectRunConfig.objective_text` | resolved objective after CLI/profile fallback |
| `default_agents` | `ResolvedProjectRunConfig.default_agents` | resolved allowed-agent list |
| `harness_instructions` | `ResolvedProjectRunConfig.harness_instructions` | resolved harness text |
| `success_criteria` | `ResolvedProjectRunConfig.success_criteria` | resolved success-criteria list |
| `max_iterations` | `ResolvedProjectRunConfig.max_iterations` | resolved iteration cap |
| `run_mode` | `ResolvedProjectRunConfig.run_mode` | resolved run mode |
| `involvement_level` | `ResolvedProjectRunConfig.involvement_level` | resolved involvement tier |
| `message_window` | `ResolvedProjectRunConfig.message_window` | resolved operator-message window |
| `overrides` | `ResolvedProjectRunConfig.overrides` | CLI-origin override markers for resolved fields |

`operator project resolve` is the committed inspection surface for these resolved run defaults.

### Stable profile schema fields

The current committed profile schema is:

- `name`
- `cwd`
- `paths`
- `history_ledger`
- `default_objective`
- `default_agents`
- `default_harness_instructions`
- `default_success_criteria`
- `default_max_iterations`
- `default_run_mode`
- `default_involvement_level`
- `adapter_settings`
- `dashboard_prefs`
- `session_reuse_policy`
- `default_message_window`

The semantics are split as follows.

#### Run-bound stable fields

- `default_objective`
- `default_agents`
- `default_harness_instructions`
- `default_success_criteria`
- `default_max_iterations`
- `default_run_mode`
- `default_involvement_level`
- `default_message_window`
- `cwd`

#### Stable but non-run-resolved fields

- `name`: profile identity
- `history_ledger`: ledger enable/disable flag
- `paths`: stored path list, resolved relative to the profile file on load; currently not consumed
  by `operator run`
- `adapter_settings`: pass-through per-adapter override map applied only to known adapter settings
  fields; unknown adapter keys and unknown field names are ignored

#### Stub or reserved fields

- `session_reuse_policy`: typed as `SessionReusePolicy` with accepted values `always_new` and
  `reuse_if_idle`; currently parsed and surfaced but still a no-op stub until runtime session
  selection is wired to it
- `dashboard_prefs`: stored and surfaced, but not currently consumed by CLI or TUI behavior

### Authoring surfaces

The current profile authoring surfaces are:

- `operator init`
- `operator project create`
- manual YAML editing

`init` and `project create` currently support authoring these run-bound defaults directly:

- `cwd`
- `paths`
- `default_objective`
- `default_agents`
- `default_harness_instructions`
- `default_success_criteria`
- `default_max_iterations`
- `default_run_mode`
- `default_involvement_level`
- `default_message_window`

Stub or reserved fields remain manual-YAML-only.

## Consequences

- The committed config reference now matches the implemented profile and resolution surface.
- `session_reuse_policy` is schema-validated instead of being an arbitrary string.
- `project inspect` now distinguishes passive, reserved, and no-op fields from active run controls.
- `project resolve` is explicitly the run-default resolution surface, not a dump of the full
  profile schema.

## Grounding Evidence

- Schema and typing:
  - `src/agent_operator/domain/profile.py` (`ProjectProfile`, `ResolvedProjectRunConfig`)
  - `src/agent_operator/domain/enums.py` (`SessionReusePolicy`)
- Resolution and load/write behavior:
  - `src/agent_operator/runtime/profiles.py` (`load_project_profile_from_path`,
    `write_project_profile`, `apply_project_profile_settings`, `resolve_project_run_config`,
    `_resolve_profile_relative_paths`)
- CLI authoring and inspection:
  - `src/agent_operator/cli/commands/project.py` (`project_create`, `project_inspect`,
    `project_resolve`, `_emit_project_profile`, `_emit_resolved_project_config`)
  - `src/agent_operator/cli/commands/run.py` (`init`)
  - `src/agent_operator/cli/options.py`
- Schema reference:
  - `docs/reference/config.md`
- Verification:
  - `tests/test_runtime.py`
  - `tests/test_project_cli.py`
  - `tests/test_cli.py`

## Closure Evidence Matrix

| ADR clause | Repository evidence | Closure |
|---|---|---|
| run precedence is CLI > profile > global/app default | `src/agent_operator/runtime/profiles.py` `resolve_project_run_config` | closed |
| resolved run contract is explicit and inspectable | `src/agent_operator/domain/profile.py` `ResolvedProjectRunConfig`; `src/agent_operator/cli/commands/project.py` `project_resolve` | closed |
| `session_reuse_policy` is typed and validated | `src/agent_operator/domain/enums.py` `SessionReusePolicy`; `src/agent_operator/domain/profile.py` `ProjectProfile.session_reuse_policy`; `tests/test_runtime.py::test_load_project_profile_validates_session_reuse_policy` | closed |
| unknown `session_reuse_policy` values are rejected | `tests/test_runtime.py::test_load_project_profile_rejects_unknown_session_reuse_policy` | closed |
| `session_reuse_policy` is surfaced as a no-op stub, not implied runtime behavior | `src/agent_operator/cli/commands/project.py` `_emit_project_profile`; `tests/test_project_cli.py::test_project_inspect_labels_no_op_and_reserved_profile_fields` | closed |
| `adapter_settings` is documented as pass-through known-field overrides | `src/agent_operator/runtime/profiles.py` `apply_project_profile_settings`; `docs/reference/config.md` | closed |
| `paths` are resolved relative to the profile file and treated as stored profile paths | `src/agent_operator/runtime/profiles.py` `_resolve_profile_relative_paths`; `src/agent_operator/cli/commands/project.py` `_emit_project_profile` | closed |
| `dashboard_prefs` is explicitly reserved, not silently implied as active UX behavior | `src/agent_operator/cli/commands/project.py` `_emit_project_profile`; `docs/reference/config.md` | closed |
| `project create` and `init` expose the currently implemented run-bound defaults | `src/agent_operator/cli/commands/project.py` `project_create`; `src/agent_operator/cli/commands/run.py` `init`; `src/agent_operator/cli/options.py` | closed |
| `project resolve` JSON covers all resolved run fields | `tests/test_project_cli.py::test_project_resolve_json_covers_all_run_resolution_fields`; `tests/test_project_cli.py::test_project_resolve_surfaces_effective_defaults` | closed |
| config documentation is committed instead of placeholder-level | `docs/reference/config.md` | closed |

## Related

- [CONFIG_UX_VISION.md](../CONFIG_UX_VISION.md)
- [docs/reference/config.md](../../docs/reference/config.md)
- [ADR 0146](./0146-mcp-server-surface-and-tool-contract.md)
- [CLI-UX-VISION.md](../CLI-UX-VISION.md)
