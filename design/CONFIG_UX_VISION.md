# Configuration and UX Vision for Operation Profiles

This document defines where user-facing configuration, runtime state, and system-level data live in the operator architecture. It establishes the separation between config-time (user-authored) and runtime-state (operator-owned) storage.

**Status:** `planned` — architectural direction established; implementation pending.

---

## Core Principle: Config vs State Separation

The operator distinguishes two ownership domains:

| Domain | Owner | Mutability | Storage |
|--------|-------|-----------|---------|
| Config-time | User / VCS | User-controlled | YAML, environment variables |
| Runtime-state | Operator | Patchable during operation, operator-owned | JSON in `.operator/` |

**Config-time data** is user-authored defaults that describe intent. It is read once at run start. Subsequent changes require a new run or explicit commands.

**Runtime-state data** is operator-owned, created and mutated during operation execution. It is persisted for resumability and inspection.

---

## Storage Architecture

### Config-Time Storage (User-Owned)

| Location | Schema | Purpose |
|----------|--------|---------|
| `operator-profile.yaml` | `ProjectProfile` | Local project defaults |
| `.operator/profiles/*.yaml` | `ProjectProfile` | Named profiles (local, not committed) |
| `operator-profiles/*.yaml` | `ProjectProfile` | Committed profiles (shared across team) |
| Environment variables | `OperatorSettings` | Secrets, API keys, provider config |
| CLI flags | — | Runtime overrides (not persisted) |

**`ProjectProfile` fields:**

```python
class ProjectProfile(BaseModel):
    name: str
    cwd: Path | None
    paths: list[Path]
    history_ledger: bool
    default_objective: str | None          # user-authored default goal
    default_agents: list[str]               # agent selection
    default_harness_instructions: str | None
    default_success_criteria: list[str]
    default_max_iterations: int | None
    default_run_mode: RunMode | None
    default_involvement_level: InvolvementLevel | None
    adapter_settings: dict[str, dict[str, object]]  # per-adapter config (models, effort, etc.)
    dashboard_prefs: dict[str, object]
    session_reuse_policy: str | None
    default_message_window: int | None
```

**Resolution order:**

1. CLI flag override (highest priority)
2. Project profile value
3. Global `OperatorSettings` default (lowest priority)

See `runtime/profiles.py:resolve_project_run_config()` for the implementation.

---

### Runtime-State Storage (Operator-Owned)

All files reside under `.operator/` in the project root or discovered ancestor git root.

| Location | Schema | Purpose |
|----------|--------|---------|
| `{op-id}.operation.json` | `OperationState` (includes `OperationGoal`, tasks, sessions) | Liveoperation state |
| `policies/{policy_id}.json` | `PolicyEntry` | Learned policies from attention answers |
| `memory/{scope_id}/*.json` | `MemoryEntry` | Distilled context (operation-scope and project-scope) |
| `events/{op-id}.jsonl` | `RunEvent` | Domain event log |
| `runs/{op-id}.timeline.jsonl` | `TraceRecord` | Narrative timeline |
| `facts/{scope}/` | `StoredFact` | Runtime facts |
| `acp/{adapter_key}/{session}.jsonl` | — | ACP session logs |

**Operation state includes:**

- `OperationGoal`: live objective, harness instructions, success criteria (patchable)
- `TaskState[]`: task graph with status, dependencies, memory refs
- `SessionState[]`: agent session handles and lifecycle
- `AttentionRequest[]`: open and answered attention requests
- `OperatorMessage[]`: context injection messages
- `ObjectiveState`, `FeatureState`, etc.

**Key invariants:**

- State is persisted after every mutation (event-sourced domain model).
- Memory entries supersede by file path within scope; they are not append-only.
- Policy entries are append-only but revocable.
- The `.operator/` directory is gitignored by default (self-contained runtime state).

---

### System-Level Storage (Code-Owned)

| Location | Schema | Purpose |
|----------|--------|---------|
| In-code registry | `AgentDescriptor` | Adapter declarations with capabilities |
| `AgentRuntimeBinding` | — | Composition root for adapter instantiation |

**`AgentDescriptor` fields:**

```python
class AgentDescriptor(BaseModel):
    key: str                              # stable identifier: "claude_acp", "codex_acp"
    display_name: str                     # human-readable: "Claude Code via ACP"
    capabilities: list[AgentCapability]  # behavioral claims
    supports_follow_up: bool
    supports_cancellation: bool
    metadata: dict[str, Any]
```

**Registry implementation:**

```python
# adapters/runtime_bindings.py

def _claude_descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        key="claude_acp",
        display_name="Claude Code via ACP",
        capabilities=[
            AgentCapability(name="acp", description="ACP session over stdio"),
            AgentCapability(name="follow_up", description="Can resume Claude sessions"),
            *standard_coding_agent_capabilities(),
        ],
        supports_follow_up=True,
        supports_cancellation=True,
    )

def build_agent_runtime_bindings(settings: OperatorSettings, ...) -> dict[str, AgentRuntimeBinding]:
    return {
        "claude_acp": AgentRuntimeBinding(
            agent_key="claude_acp",
            descriptor=_claude_descriptor(),
            build_adapter_runtime=...,
            build_session_runtime=...,
        ),
        "codex_acp": AgentRuntimeBinding(...),
    }
```

**Rationale:**

- Adapters are system-provided, not user-authored.
- Adding or removing adapters requires code changes.
- VISION.md specifies protocol-oriented integration, not dynamic discovery.
- Descriptor metadata (identity, capabilities) lives with adapter implementation.

---

## Where Key User-Facing Elements Live

### Goal / Objective

**Config-time:** `ProjectProfile.default_objective` (YAML)

**Runtime:** `OperationGoal.objective` (JSON in `.operator/{op-id}.operation.json`)

**Patchable:** Yes, via `operator patch-objective` command during a running operation.

**Flow:**

1. User authors default objective in `operator-profile.yaml`.
2. `run` command resolves default → `ResolvedProjectRunConfig`.
3. Resolved value initializes `OperationGoal.objective`.
4. During operation, `patch_objective` command updates `OperationGoal.objective` inruntime state.

---

### Harness Instructions

**Config-time:** `ProjectProfile.default_harness_instructions` (YAML)

**Runtime:** `OperationGoal.harness_instructions` (JSON)

**Patchable:** Yes, via `operator patch-harness-instructions`.

The brain reads the full `harness_instructions` at every planning cycle. It encodes execution policy (branch strategy, commit conventions, etc.), distinct from the goal itself.

---

### Success Criteria

**Config-time:** `ProjectProfile.default_success_criteria` (YAML)

**Runtime:** `OperationGoal.success_criteria` (JSON)

**Patchable:** Yes, via `operator patch-success-criteria`.

---

### Todo / Task Graph

**Storage:** Runtime state only.

**Location:** `TaskState[]` inside `OperationState` (JSON).

**User-facing:** CLI command `operator tasks op-id` reads persisted state and renders the task graph.

**Rationale:** Tasks are runtime entities proposed by the brain and managed by the deterministic runtime. They do not exist at config-time.

---

### Memory / Context

**Storage:** Runtime state only.

**Location:** `.operator/memory/{scope_id}/` (JSON).

**Scopes:**

- **Operation-scope:** context built during one operation; superseded when same file path is re-read.
- **Project-scope:** context that persists across operations; created via user-accepted `document_update_proposal` attention.

**User-facing:** CLI command `operator memory op-id` inspects distilled memory entries.

**Rationale:** Memory is operator-internal context for planning, not user-authored configuration.

---

### Agent Descriptors

**Storage:** In-code registry.

**User-facing:** CLI discovery commands:

```sh
operator agent list              # Show available agents: key, display_name
operator agent show <key>        # Show capabilities, current configuration
```

**No YAML storage:** Agent definitions are system capabilities, not user configuration.

---

### Available Models

**Storage:** Provider-determined, not operator-owned.

**Configuration path:**

```python
# config.py — OperatorSettings
class ClaudeAcpAdapterSettings(BaseModel):
    command: str = "npx @agentclientprotocol/claude-agent-acp"
    model: str | None = None  # user-configurable
    effort: Literal["none", "low", "medium", "high", "max"] | None = None
    ...

# runtime/profiles.py — ProjectProfile
class ProjectProfile(BaseModel):
    ...
    adapter_settings: dict[str, dict[str, object]] = {}
    # Example: adapter_settings = {"claude_acp": {"model": "claude-3-opus"}}
```

**Resolution:**

1. Environment variable / `OperatorSettings.claude_acp.model` (default)
2. Project profile override: `adapter_settings.claude_acp.model`
3. CLI flag override (rare)

**Validation:** Provider-side at runtime. If model is unavailable, provider returns an error. Operator does not pre-validate.

**What does NOT exist:**

- ❌ `AgentDescriptor.supported_models` — model lists rot; provider API is the truth.
- ❌ Project-level model constraints (allowlists) — API key scope is the real constraint.
- ❌ Config-time model validation — provider errors are clearer than pre-validation.

---

## CLI Discovery Surface

### Project Profile Management

```sh
operator init                     # Create operator-profile.yaml in current directory
operator project list             # List available profiles
operator project show [name]      # Show profile details
operator project resolve          # Resolve effective profile (CLI + profile + defaults)
```

### Agent Discovery

```sh
operator agent list               # List available agents
operator agent show <key>        # Show agent details and current configuration
```

### Runtime Inspection

```sh
operator status <op-id>           # Operation status and attention summary
operator tasks <op-id>            # Task graph with dependencies
operator memory <op-id>           # Distilled memory entries
operator artifacts <op-id>        # Durable outputs
operator trace <op-id>            # Forensic event log
operator log <op-id> [--agent]    # Raw agent session log
```

### Runtime Modification

```sh
operator message <op-id> "..."    # Inject context for next planning cycle
operator answer <op-id> [att-id]  # Answer a blocking attention request
operator patch-objective <op-id> "..."  # Update live objective
operator patch-harness <op-id> "..."     # Update harness instructions
operator patch-success <op-id> "..."    # Update success criteria
```

---

## Summary Table

| Data Type | Storage | Config-Time | Runtime-State | Patchable |
|-----------|---------|-------------|---------------|-----------|
| Project defaults | `operator-profile.yaml` | ✅ | ❌ | No (re-run) |
| Objective | `.operator/{op-id}.operation.json` | Default in profile | ✅ | Yes (`patch-objective`) |
| Harness instructions | `.operator/{op-id}.operation.json` | Default in profile | ✅ | Yes (`patch-harness`) |
| Success criteria | `.operator/{op-id}.operation.json` | Default in profile | ✅ | Yes (`patch-success`) |
| Task graph | `.operator/{op-id}.operation.json` | ❌ | ✅ | No (brain-managed) |
| Memory | `.operator/memory/` | ❌ | ✅ | No (operator-owned) |
| Policies | `.operator/policies/` | ❌ | ✅ | Revoke only |
| Agent descriptors | In-code registry | ❌ | ❌ | No (system-owned) |
| Available models | Provider API | Settings override | ❌ | No (provider-owned) |

---

## Design Rationale

### Why YAML for Config?

- Human-readable and human-editable.
- VCS-trackable (user can commit `operator-profiles/*.yaml`).
- Multiple profiles per project (e.g., `opsbot.yaml` for nightly automation).
- CLI can scaffold defaults (`operator init`).

### Why JSON for Runtime State?

- Programmatic read/write during operation execution.
- Structured for event-sourced domain model.
- Atomic writes with retry (see `FileOperationStore._read_text_with_retry`).
- Separate from user-authored configuration (prevents accidental edits).

### Why In-Code Registry for Agents?

- Adapters are system capabilities, not plugins.
- VISION.md explicitly rejects dynamic agent discovery.
- Protocol-oriented integration allows future adapters without core changes.
- Keeps descriptor metadata close to adapter implementation.

### Why No Model Lists in Descriptors?

- Model availability is provider-dependent (API key scope, regional availability).
- Hardcoded model lists in code will lag behind provider offerings.
- Runtime validation by provider gives clearer error messages.
- Configuration belongs in `OperatorSettings` and `ProjectProfile`, not identity metadata.

---

## Non-Goals

- ❌ Dynamic agent discovery at runtime (plugin architecture).
- ❌ Project-level model allowlists (use API key scope).
- ❌ Config-time model validation (provider validates).
- ❌ User-authored agent definitions (agents are system-provided).
- ❌ YAML for runtime state (state is operator-owned).

---

## Implementation Notes

### Current State

- `ProjectProfile` schema: `implemented` (see `domain/profile.py`).
- Profile resolution: `implemented` (see `runtime/profiles.py`).
- Operation state persistence: `implemented` (see `runtime/store.py`).
- Agent registry: `implemented` (see `adapters/runtime_bindings.py`).
- CLI commands: `partial` (discovery commands `agent list`, `agent show` not yet implemented).

### Required Additions

1. **Agent discovery commands:**

   ```python
   # cli/main.py

   def agent_list() -> None:
       """List available agents."""
       bindings = build_agent_runtime_bindings(OperatorSettings())
       for key, binding in sorted(bindings.items()):
           typer.echo(f"{key}  {binding.descriptor.display_name}")

   def agent_show(key: str) -> None:
       """Show agent details and current configuration."""
       bindings = build_agent_runtime_bindings(OperatorSettings())
       binding = bindings.get(key)
       if not binding:
           raise typer.BadParameter(f"Unknown agent: {key}")
       # Display: capabilities, adapter settings
   ```

2. **Document the `operator-profile.yaml` schema in user docs** (see `docs/reference/config.md` placeholder).

3. **Do NOT add:**

   - `supported_models` or `default_model` to `AgentDescriptor`.
   - Project-level model constraint fields.
   - Config-time model validation functions.

---

## ACP Protocol Resilience

### Required Session Parameters

All ACP session lifecycle methods (`session/new`, `session/load`, `session/fork`, `session/resume`)
**must** include the `mcpServers` field in their parameters, even when the value is an empty list.
Some ACP implementations (notably Codex ACP) reject requests with missing `mcpServers` rather than
defaulting to `[]`.

**Canonical call sites** (as of this writing):

| Method | Location | Notes |
|--------|----------|-------|
| `session/new` | `acp/session_runner.py:_new_session()` | Always includes `cwd` + `mcpServers: []` |
| `session/load` | `acp/session_runner.py:send()` | Always includes `cwd` + `mcpServers: []` |
| `session/load` | `acp/session_runner.py:_reattach_for_poll()` | Always includes `cwd` + `mcpServers: []` |
| `session/new` | `acp/session_runtime.py:_start_new_session()` | Always includes `cwd` + `mcpServers: []` |
| `session/load` | `acp/session_runtime.py:send()` | Always includes `cwd` + `mcpServers: []` |

**Rule:** When adding a new call to any session lifecycle method, always include `mcpServers: []`
(or the configured MCP server list, when that becomes configurable). The `AcpSdkConnection`
defensively applies `payload.get("mcpServers", [])`, but `AcpSubprocessConnection` sends params
verbatim -- so the caller is responsible for completeness.

### Error Classification for Protocol Mismatches

Both `codex_acp.py` and `claude_acp.py` error classifiers detect protocol parameter errors
(`"Invalid params"`, `"missing field"`, etc.) and classify them as `*_protocol_mismatch` with
`retryable=True` and `recovery_mode="new_session"`. This ensures that protocol-level bugs in
upstream ACP implementations surface as diagnosable, retryable errors rather than opaque permanent
failures.

### Known Adapter Quirks

| Adapter | Quirk | Mitigation |
|---------|-------|------------|
| Codex ACP | Rejects `session/load` without `mcpServers` field | Always send `mcpServers: []` |
| Codex ACP | Does not reuse connections across turns | `should_reuse_live_connection` returns `False` |
| Claude ACP | Rate limit errors in various formats | Pattern matching in `_looks_like_rate_limit()` |

---

## References

- `[VISION.md]` — Core thesis, protocol-oriented integration, agent adapter contract.
- `[ARCHITECTURE.md]` — Storage model, operation state structure, traceability layers.
- `[runtime/profiles.py]` — Profile resolution implementation.
- `[domain/profile.py]` — `ProjectProfile` schema.
- `[domain/operation.py]` — `OperationGoal`, `OperationState` schemas.
- `[adapters/runtime_bindings.py]` — Agent registry implementation.