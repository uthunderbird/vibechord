# ADR 0148: Project profile schema completion and resolution contract

- Date: 2026-04-12

## Decision Status

Accepted

## Implementation Status

Implemented

## Context

`operator` already exposed project profiles through YAML, `ProjectProfile`,
`ResolvedProjectRunConfig`, `resolve_project_run_config(...)`, `operator project inspect`, and
`operator project resolve`.

Before this closure wave, the contract was incomplete in four concrete ways:

- `session_reuse_policy` was not a typed schema field
- `adapter_settings` had no committed shared-key schema or ACP `mcp_servers` wiring
- `project resolve` did not surface the full effective run contract
- the written config reference and ADR text were not anchored to exact repository evidence

This ADR closes the current repository truth rather than the broader aspirational
`CONFIG_UX_VISION.md`.

## Decision

### 1. Binding resolution order

For `operator run`, the binding resolution order is:

1. explicit CLI flag
2. project profile value
3. global default or hardcoded application default

No delivery or runtime component may invert that precedence for the resolved run fields committed
below.

### 2. Binding resolved run contract

`ResolvedProjectRunConfig` is the committed effective-default contract for `operator run`.

The binding resolved fields are:

| Field | Meaning |
|---|---|
| `profile_name` | selected profile identity |
| `cwd` | resolved working directory |
| `history_ledger` | resolved history-ledger enable/disable flag |
| `objective_text` | resolved objective text |
| `default_agents` | resolved allowed-agent list |
| `harness_instructions` | resolved harness text |
| `success_criteria` | resolved success-criteria list |
| `max_iterations` | resolved iteration cap |
| `run_mode` | resolved run mode |
| `involvement_level` | resolved involvement level |
| `session_reuse_policy` | resolved session-reuse policy |
| `message_window` | resolved operator-message window |
| `overrides` | CLI-origin override markers |

`operator project resolve` is the committed inspection surface for this resolved contract.

### 3. Binding profile schema

The committed `ProjectProfile` schema contains:

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

The schema has the following status split.

#### Active run-affecting fields

- `cwd`
- `history_ledger`
- `default_objective`
- `default_agents`
- `default_harness_instructions`
- `default_success_criteria`
- `default_max_iterations`
- `default_run_mode`
- `default_involvement_level`
- `session_reuse_policy`
- `default_message_window`

#### Stable but not resolved into `operator run` defaults

- `name`
- `adapter_settings`

`adapter_settings` is a typed per-adapter override map. Its committed shared keys are:

- `timeout_seconds`
- `mcp_servers`

Adapter-specific keys that match real adapter setting fields remain allowed and are applied only
when that field exists on the target adapter settings model.

#### Deferred fields

- `paths`
- `dashboard_prefs`

Both fields remain in the schema, but `project inspect` treats them as deferred rather than
presenting them as active runtime controls.

### 4. Session reuse policy contract

`session_reuse_policy` is typed as `SessionReusePolicy` with exactly these values:

- `always_new`
- `reuse_if_idle`

`reuse_if_idle` allows the operator to reuse an existing idle, non-one-shot session for the same
adapter instead of launching a fresh session. `always_new` requires a fresh session.

### 5. Authoring surfaces

The profile-authoring surfaces are:

- `operator init`
- `operator project create`
- manual YAML editing

`init` and `project create` both expose the currently implemented run-bound defaults:

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

## Closure Criteria And Evidence

### 1. The profile schema is typed and committed

Evidence:

- profile models:
  `src/agent_operator/domain/profile.py:ProjectProfile`
  `src/agent_operator/domain/profile.py:ProjectProfileAdapterSettings`
  `src/agent_operator/domain/profile.py:ProjectProfileMcpServer`
  `src/agent_operator/domain/profile.py:ResolvedProjectRunConfig`
- enum:
  `src/agent_operator/domain/enums.py:SessionReusePolicy`
- exports:
  `src/agent_operator/domain/__init__.py`

Verification:

- `tests/test_runtime.py::test_load_project_profile_validates_session_reuse_policy`
- `tests/test_runtime.py::test_load_project_profile_rejects_unknown_session_reuse_policy`

### 2. The resolved run contract is explicit and complete

Evidence:

- resolver:
  `src/agent_operator/runtime/profiles.py:resolve_project_run_config`
- resolved schema:
  `src/agent_operator/domain/profile.py:ResolvedProjectRunConfig`
- human and JSON inspection:
  `src/agent_operator/cli/commands/project.py:_emit_resolved_project_config`
  `src/agent_operator/cli/commands/project.py:project_resolve`

Verification:

- `tests/test_runtime.py::test_resolve_project_run_config_includes_history_ledger_and_session_reuse_policy`
- `tests/test_project_cli.py::test_project_resolve_surfaces_effective_defaults`
- `tests/test_project_cli.py::test_project_resolve_json_covers_all_run_resolution_fields`

### 3. Adapter settings have committed shared keys and ACP `mcp_servers` wiring

Evidence:

- adapter setting models:
  `src/agent_operator/config.py:ClaudeAcpAdapterSettings`
  `src/agent_operator/config.py:CodexAcpAdapterSettings`
  `src/agent_operator/config.py:OpencodeAcpAdapterSettings`
- profile application:
  `src/agent_operator/runtime/profiles.py:apply_project_profile_settings`
- ACP session payload wiring:
  `src/agent_operator/acp/session_runner.py:AcpSessionRunner`
  `src/agent_operator/acp/session_runtime.py:AcpAgentSessionRuntime`
- adapter/binding plumbing:
  `src/agent_operator/adapters/claude_acp.py:ClaudeAcpAgentAdapter`
  `src/agent_operator/adapters/codex_acp.py:CodexAcpAgentAdapter`
  `src/agent_operator/adapters/opencode_acp.py:OpencodeAcpAgentAdapter`
  `src/agent_operator/adapters/runtime_bindings.py:build_agent_runtime_bindings`

Verification:

- `tests/test_runtime.py::test_apply_project_profile_settings_updates_mcp_servers_and_timeout_seconds`
- `tests/test_acp_session_runner.py::test_session_runner_passes_configured_mcp_servers_to_session_new_and_load`

### 4. `session_reuse_policy` is wired to runtime session selection

Evidence:

- policy lookup:
  `src/agent_operator/application/loaded_operation.py:LoadedOperation.resolved_session_reuse_policy`
- reusable-session resolution:
  `src/agent_operator/application/loaded_operation.py:LoadedOperation.resolve_reusable_idle_session`
- start-path enforcement:
  `src/agent_operator/application/decision_execution.py:DecisionExecutionService._execute_start_agent`

Verification:

- `tests/test_attached_turn_service.py::test_start_agent_reuses_idle_session_when_profile_requests_reuse_if_idle`

### 5. Deferred fields are surfaced as deferred, not as active runtime controls

Evidence:

- inspect renderer:
  `src/agent_operator/cli/commands/project.py:_emit_project_profile`

Verification:

- `tests/test_project_cli.py::test_project_inspect_labels_no_op_and_reserved_profile_fields`

### 6. Authoring and docs match the implemented contract

Evidence:

- project authoring:
  `src/agent_operator/cli/commands/project.py:project_create`
  `src/agent_operator/cli/commands/run.py:init`
  `src/agent_operator/cli/options.py`
- committed config reference:
  `docs/reference/config.md`

Verification:

- `tests/test_project_cli.py::test_project_create_remains_explicit_profile_mutation`

## Consequences

- project-profile resolution is now a concrete, inspectable contract rather than an implicit merge
  behavior
- `session_reuse_policy` is schema-validated and runtime-effective
- shared adapter override keys are documented and ACP `mcp_servers` now reach session creation/load
  payloads
- `project inspect` no longer presents deferred fields as active runtime behavior

## Verification

Local verification for this ADR was completed with:

- `pytest tests/test_runtime.py tests/test_project_cli.py tests/test_attached_turn_service.py tests/test_acp_session_runner.py`
- `uv run pytest`

## Related

- [CONFIG_UX_VISION.md](../CONFIG_UX_VISION.md)
- [docs/reference/config.md](../../docs/reference/config.md)
- [ADR 0146](./0146-mcp-server-surface-and-tool-contract.md)
- [CLI-UX-VISION.md](../CLI-UX-VISION.md)
