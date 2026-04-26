# ADR 0190: Dynamic Agent Model And Effort Overrides

- Date: 2026-04-15

## Decision Status

Accepted

## Implementation Status

Verified

Skim-safe status on 2026-04-27:

- `implemented`: project profiles now carry typed per-adapter `allowed_models` allowlists alongside
  adapter defaults
- `implemented`: runtime control now supports bounded operation-local `set_execution_profile`
  mutation for one explicitly named already allowed adapter
- `implemented`: `codex_acp` execution-profile truth now includes the adapter-owned execution-policy
  fields `approval_policy` and `sandbox_mode` when those fields are part of the authored
  allowlisted/default Codex profile
- `implemented`: execution-profile overlays now persist as operation-local runtime truth, separate
  from launch defaults and project profile data
- `implemented`: event-sourced command handling, attached-turn reuse compatibility, and operation
  query/status surfaces now expose requested vs effective execution-profile truth
- `verified`: targeted execution-profile regression slices and the full repository test suite pass
  at the repository state that closes this ADR
- `not allowed`: this feature must not permit adapter switching at runtime

## Context

`operator` already has the basic ingredients for adapter selection and adapter-specific launch
defaults, but it still treats model and effort mostly as static launch configuration:

- global runtime settings already expose adapter defaults such as:
  - `claude_acp.model`
  - `claude_acp.effort`
  - `codex_acp.model`
  - `codex_acp.reasoning_effort`
  - and, under `ADR 0010`, `codex_acp.approval_policy` and `codex_acp.sandbox_mode`
- project profiles already expose `adapter_settings` as a bounded per-adapter override map
- runtime control already allows operation-local mutation of some policy fields, for example
  `set_allowed_agents`, `patch_objective`, and `patch_harness`

This leaves a real operational gap.

In practice, operators often need to keep the same agent adapter but change the execution profile
mid-operation:

- move the same adapter to a cheaper or faster model for a narrow slice
- raise effort for a difficult bounded tranche
- lower effort after a hard route-selection turn is done

The current system does not commit a bounded authority for that change. The only durable knobs are
the adapter defaults resolved at launch.

At the same time, the repository already has strong boundaries that this feature must preserve:

- project profiles are reusable defaults, not live operation state
- runtime control may patch operation-local behavior, but that mutation must remain explicit,
  inspectable, and bounded
- adapter identity is part of the stable runtime contract; changing model/effort is materially
  smaller than switching from `claude_acp` to `codex_acp`

The design problem is therefore not "let the operator choose any agent settings at any time".

The real problem is:

- allow model/effort changes dynamically,
- only within one already allowed adapter named explicitly by adapter key,
- only within an explicit profile- or settings-authored allowlist,
- while keeping default launch configuration and live operation overlays separate.

For `codex_acp`, current repository truth also includes a narrower adjacent requirement:

- when Codex execution policy is part of the authored effective/allowed profile, session reuse and
  runtime rebinding must compare that policy too rather than silently treating it as unrelated
  ambient config

## Decision

Introduce bounded dynamic execution-profile overrides for an already allowed adapter.

This feature does not depend on a single operation-wide "selected adapter" concept. It acts on one
explicitly named adapter key inside the operation's allowed-agent set.

### 1. Adapter defaults remain defaults, not locks

The existing adapter settings fields such as:

- `claude_acp.model`
- `claude_acp.effort`
- `codex_acp.model`
- `codex_acp.reasoning_effort`

remain the resolved default execution profile for a new operation.

They are no longer treated as the only model/effort pair the operation may ever use.

### 2. Project profiles gain explicit `allowed_models`

Each adapter settings block may define an optional `allowed_models` field.

`allowed_models` is the bounded allowlist of execution profiles that the operator may select for
that adapter during the operation.

This field is configuration-time authority. It is user-authored and inspectable through profile
surfaces.

If `allowed_models` is absent or empty for an adapter, dynamic model/effort switching is disabled
for that adapter. The operation stays on the resolved launch default execution profile unless a
later explicit feature extends that authority.

`allowed_models` is not a raw free-form list of dicts.

The typed schema direction is:

- each adapter may expose only profiles shaped like its own native model-setting fields
- each allowed profile may contain only:
  - `model`
  - and that adapter's existing effort field, if the adapter has one
- and only adapter-specific execution-policy fields already committed elsewhere, where a prior ADR
  has made them part of that adapter's authored runtime contract
- no unrelated transport, timeout, MCP wiring, substrate, or command fields are valid inside
  `allowed_models`

This keeps the allowlist as execution-profile authority, not a second adapter-settings mutation
surface.

Current support boundary for this ADR:

- `codex_acp`: supported through `model` + `reasoning_effort`, with optional exact-match
  `approval_policy` + `sandbox_mode` fields because `ADR 0010` already exposes those as
  adapter-owned Codex execution-policy settings
- `claude_acp`: supported through `model` + `effort`
- adapters without an existing effort field, such as `opencode_acp`, are out of scope for this ADR
  rather than forced into a fake cross-adapter schema

### 3. Runtime mutation is operation-local and adapter-stable

The operator may apply a dedicated operation command that changes the execution profile for one
adapter key already present in the operation's allowed-agent policy.

The command targets one adapter key, not an implicit "current adapter" concept and not one existing
session id. In a multi-adapter operation, the user or delivery surface must name the adapter key
explicitly.

That command may mutate only:

- `model`
- the adapter's existing effort field
- and, for `codex_acp` only, the already-committed adapter execution-policy fields
  `approval_policy` and `sandbox_mode`

It must not mutate:

- the adapter key
- the allowed-agent list
- unrelated adapter transport fields such as command, timeout, substrate backend, or MCP server
  wiring
- any execution-policy or transport field not already committed as part of that adapter's authored
  execution-profile contract

Changing adapter identity remains the job of `set_allowed_agents` or a future distinct feature, not
this one.

The override may be set before the target adapter has any live session.

In that case:

- the command updates only operation-local runtime truth
- no existing session is modified
- the override takes effect the next time the operator starts or reuses a compatible session for
  that adapter

Changing the overlay for one allowed adapter is otherwise a no-op until that adapter is actually
used again.

### 4. Session reuse must honor effective execution profile

If a reusable idle session exists for the target adapter but its effective model/effort does not
match the operation's current execution-profile overlay, that session is not reusable for the next
turn.

The operator must either:

- start a fresh session for that adapter with the requested allowed execution profile, or
- continue reusing a matching session when one already exists

This preserves the existing session-reuse boundary: reuse is only valid when the effective adapter
configuration relevant to the session still matches.

## Configuration Contract

The committed configuration direction is:

- `adapter_settings` remains the single project-profile home for adapter-specific defaults and
  bounded adapter-specific override authority
- `allowed_models` is nested under one adapter's settings, not promoted to a profile-top-level
  field

Conceptually:

```yaml
adapter_settings:
  codex_acp:
    model: gpt-5.4
    reasoning_effort: low
    approval_policy: never
    sandbox_mode: workspace-write
    allowed_models:
      - model: gpt-5.4
        reasoning_effort: low
        approval_policy: never
        sandbox_mode: workspace-write
      - model: gpt-5.4
        reasoning_effort: high
        approval_policy: never
        sandbox_mode: workspace-write
      - model: gpt-5.4-mini
        reasoning_effort: medium
        approval_policy: auto
        sandbox_mode: danger-full-access
  claude_acp:
    model: claude-sonnet-4-6
    effort: low
    allowed_models:
      - model: claude-sonnet-4-6
        effort: low
      - model: claude-sonnet-4-6
        effort: high
```

The exact typed schema should preserve current adapter-specific field names rather than inventing a
false cross-adapter semantic uniformity.

That means:

- Codex-backed adapters may continue to use `reasoning_effort`
- Claude-backed adapters may continue to use `effort`

The user-facing feature is still "dynamic model and effort changes", but the persisted schema
should stay grounded in the real adapter setting models already present in the repository.

## Core Design Contract

### Terminology

This ADR uses the following terms consistently:

- `launch default execution profile`:
  the model plus adapter-native effort field, and any adapter-specific execution-policy adjuncts
  explicitly committed as part of that adapter's profile contract, resolved at run start for one
  adapter
- `execution-profile overlay`:
  the operation-local runtime override for that adapter's profile fields committed by this ADR
- `effective execution profile`:
  the execution profile currently in force for one adapter after applying the overlay, if any, to
  the launch default
- `effective adapter runtime settings`:
  the runtime-usable adapter settings derived from the effective execution profile plus the
  adapter's unchanged non-profile runtime fields

`project profile` remains the authored reusable project configuration object.

`execution profile` is narrower than the full adapter settings object: it means the model, the
adapter's native effort field when present, and only those adapter-specific execution-policy fields
that this ADR explicitly admits into one adapter's authored profile contract.

`runtime bindings` are an implementation consequence of materializing effective adapter runtime
settings. They are not a separate source of truth.

### Runtime Contract

The operation must persist two layers separately:

#### A. Launch default execution profile

These are the launch-time resolved model and adapter-native effort field after environment, global
config, and project-profile resolution.

They remain the baseline truth for the operation and continue to live in the run's persisted launch
metadata snapshot of effective adapter runtime settings.

#### B. Operation-local execution-profile overlay

This is the live runtime override chosen during the operation for one adapter's committed
execution-profile fields.

It is:

- explicit
- inspectable
- operation-scoped
- resumable
- and not written back into the project profile or global settings

The overlay is allowed to differ from the launch default execution profile only when the requested
execution profile appears in that adapter's `allowed_models` allowlist.

## Persistence And Replay Contract

The canonical persistence split is:

- launch-time effective adapter runtime settings remain persisted as operation goal metadata,
  consistent with the existing run-continuity contract
- runtime execution-profile overlays become canonical operation-local control-plane state derived
  from event-sourced operation commands, not project-profile data and not delivery-local caches

This means the runtime must not treat the project profile as a mutable store for live model/effort
selection.

Replay and resume semantics are:

1. restore the persisted launch-time effective adapter runtime-settings snapshot
2. replay accepted execution-profile-override commands into operation-local control state
3. derive the current effective execution profile for each adapter as:
   - launch default execution profile when no runtime overlay exists
   - otherwise the latest accepted runtime overlay for that adapter

If no overlay exists for an adapter, resume and recover continue to use the persisted launch-time
effective adapter runtime settings with no special-case mutation.

This ADR does not require a second mutable profile-like blob in goal metadata. The runtime overlay
belongs to operation command / checkpoint truth so replay, resume, and inspection rebuild the same
effective state deterministically.

The ordered runtime restore sequence for `resume` and `recover` is:

1. load the persisted launch-time effective adapter runtime-settings snapshot
2. replay accepted execution-profile-override commands into operation-local control state
3. materialize effective adapter runtime settings, and then any needed runtime bindings, from the
   combined launch-default-plus-overlay state
4. ask the session manager to evaluate compatibility and perform reuse / start decisions only after
   step 3 completes

The same ordering applies to any foreground path that accepts `set_execution_profile` and then
continues the operation in the same process. Immediate replan or subsequent agent-start decisions
must see the materialized effective adapter runtime settings, not only the accepted command record.

## Session-Manager Compatibility Contract

This feature does not move live-session lifecycle authority out of the session-manager boundary.

The operator-visible compatibility input is a normalized execution-profile stamp for one adapter:

- `adapter_key`
- `model`
- the adapter's native effort field name
- the adapter's native effort field value
- `approval_policy`, when the adapter profile contract includes it
- `sandbox_mode`, when the adapter profile contract includes it

The operator owns this normalized stamp as durable coordination truth.

The session manager remains responsible for live-session compatibility decisions, including:

- determining whether an idle session matches the current effective execution-profile stamp
- declining reuse when the stamp does not match
- starting or reattaching a session under the requested effective profile when reuse is not valid

The operator remains responsible only for:

- deriving the current effective execution-profile stamp from launch defaults plus runtime overlay
- asking for continuation or fresh start against that stamp
- recording durable session truth and command-derived state

The operator must not inspect transport-local internals to decide compatibility. Compatibility is a
session-manager decision against operator-provided normalized execution-profile truth.

## Migration And Compatibility Contract

This feature is intended as a replay-compatible additive extension, not as a requirement to rewrite
historical operation state.

Legacy behavior is:

- operations created before execution-profile overlays exist are interpreted as having no runtime
  overlay for any adapter
- checkpoints that contain no execution-profile overlay state are valid and replay as
  launch-default-only operations
- event streams that contain no `set_execution_profile` command effects are valid and require no
  synthetic migration events

If checkpoint schema or projection format needs to grow to expose execution-profile overlay state,
that is a checkpoint-format evolution concern rather than a business-state migration requirement.
The replay rule remains additive: missing overlay data means "no override exists."

This ADR does not require rewriting old operations, fabricating historical override events, or
promoting legacy launch defaults into synthetic runtime overlays.

## Command And Interface Contract

The runtime mutation introduced by this ADR is a first-class event-sourced operation command.

The committed command direction is:

- add `OperationCommandType.SET_EXECUTION_PROFILE`
- target scope: `operation`
- target id: the operation id
- payload:
  - `adapter_key`
  - `model`
  - exactly one adapter-native effort field when that adapter supports effort
  - for `codex_acp` only, optional `approval_policy` and `sandbox_mode`

The command is replan-triggering control-plane input, comparable in lifecycle treatment to other
bounded operation-local mutations such as `set_allowed_agents`.

Deterministic rejection cases include at least:

- target adapter key is not currently allowed for the operation
- requested profile is not present in that adapter's `allowed_models` allowlist
- payload omits `model`
- payload includes unknown fields
- payload mixes fields from another adapter's schema
- payload attempts to mutate adapter identity or any transport / command field not explicitly
  admitted by this ADR for the targeted adapter

This command applies only to future turns. In-flight turns are not hot-swapped.

Authoritative interface exposure is:

- project inspection / config-reference surfaces show authored defaults plus `allowed_models`
  authority
- operation query / status surfaces show:
  - launch default execution profile
  - current runtime overlay, if any
  - current effective execution profile after overlay application
- command inspection surfaces show the requested `set_execution_profile` command and whether it was
  accepted or rejected

The ADR does not require one generic merged dump. It requires the existing project-vs-operation
surface split to remain visible while making requested vs effective execution profile inspectable.

## Failure Modes And Visibility Contract

Deterministic command rejection is not the only user-visible edge for this feature.

If a `set_execution_profile` command is accepted but later runtime application fails, the runtime
must surface that failure explicitly rather than silently falling back to stale defaults.

Important post-acceptance failure cases include:

- no reusable session matches the effective execution-profile stamp and fresh session start fails
- resume or recover reconstructs command-derived overlay state but cannot materialize effective
  adapter runtime settings
- operation query or status surfaces temporarily lag the accepted command while replan or recovery
  is still in progress

Required visibility behavior:

- command surfaces must continue to show that the command was accepted
- operation/query surfaces must not falsely claim the new profile is effective until runtime
  materialization succeeds
- if runtime materialization or fresh start fails, the operation must surface a truthful blocked,
  failed, or alerting state rather than quietly proceeding on the old profile
- attached-mode surfaces must not recommend ordinary continuation as if the new profile were active
  when activation actually failed

This ADR permits transient sequencing lag between command acceptance and later runtime effect, but
that lag must be truthful in inspection surfaces. Silent fallback to the prior execution profile is
not an acceptable steady-state failure behavior.

## Validation Rules

The feature must enforce the following rules deterministically.

### Adapter identity

- The target adapter key must already be allowed for the operation.
- The runtime command payload must name the adapter key explicitly.
- The runtime command must not change the adapter key.

### Allowlist

- The requested execution-profile fields must exactly match one allowlisted execution profile for
  the adapter.
- If no allowlist exists for that adapter, reject the command.

### Field scope

- Only model, the adapter's existing effort field, and any adapter-specific execution-policy fields
  explicitly admitted by this ADR are mutable through this feature.
- Unknown fields are rejected.
- Adapters may not borrow another adapter's effort field name.
- Adapters may not borrow another adapter's execution-policy field.
- Adapters without an existing effort field are outside this ADR's dynamic effort-switching scope.

### Session compatibility

- In-flight turns are not hot-swapped.
- The new profile applies only to future turns started after the command is applied.
- Reuse of an idle session is allowed only when the session manager determines that the session's
  execution-profile stamp matches the current effective execution-profile stamp for that adapter.

### Persistence and replay

- Launch defaults and runtime overlays must remain separate persisted layers.
- Resume and recover must rebuild the effective execution profile from the launch-default
  execution-profile snapshot plus replayed accepted override commands.
- Delivery surfaces must not become the source of truth for effective execution profile state.

## Alternatives Considered

### 1. Do nothing; keep model and effort fixed at launch

Rejected.

This preserves simplicity but forces unnecessary operation restarts for bounded profile changes
that are smaller than adapter switching.

### 2. Allow arbitrary runtime edits to all adapter settings

Rejected.

This would punch through the current project-profile and adapter-boundary design. It would also
allow mutation of transport and execution-policy fields that materially change runtime behavior far
beyond the narrow model/effort problem.

### 3. Treat dynamic model change as agent switching

Rejected.

The repository already models adapter choice through allowed-agent policy. Switching
`claude_acp -> codex_acp` is materially different from staying on `codex_acp` and moving from one
allowed model/effort profile to another.

Collapsing those into one control would blur policy authority and make session semantics harder to
reason about.

### 4. Introduce a single universal cross-adapter `effort` field

Rejected for persistence format.

The operator may present the capability conceptually as model/effort selection, but the persisted
config should not pretend that adapters share one identical native field. Current repository truth
already distinguishes `effort` and `reasoning_effort`, and this ADR keeps that distinction.

### 5. Store runtime override back into the project profile

Rejected.

That would violate the existing project-profile versus live-operation boundary. The runtime overlay
is operation-local control-plane truth and must remain replayable without mutating the authored
profile.

## Consequences

### Positive

- Operators can adapt cost, speed, and depth within one adapter without restarting the whole
  operation.
- Profile authors can make that flexibility explicit and bounded instead of relying on ad hoc
  runtime improvisation.
- The feature aligns with existing `adapter_settings` and runtime command patterns rather than
  inventing a second configuration system.
- Session reuse becomes more truthful because compatibility now includes execution profile, not just
  adapter key.

### Negative

- Session-selection logic becomes stricter because profile mismatches can force new sessions.
- The profile schema grows slightly.
- Delivery surfaces must explain clearly that defaults and allowed dynamic profiles are different
  concepts.
- Event-sourced control state and operation-query surfaces gain a new execution-profile concept that
  must remain consistent with session-manager behavior.

### Risk

- If `allowed_models` is typed too loosely, the feature will drift into arbitrary adapter mutation.
- If runtime state and project profile are not kept separate, the feature will violate ADR 0018's
  profile-vs-operation boundary.
- If the delivery command ships before replay restoration, runtime rebinding, session compatibility,
  and query truth land together, accepted commands can misrepresent the effective execution profile
  the runtime will actually use.

## Follow-On Delivery And Verification Notes

This ADR does not mark the feature as implemented.

The sections above are the design authority.

This section records delivery sequencing and verification guidance that follows from that authority.

### Rollout gate

The `set_execution_profile` command and any user-facing delivery surface for it must remain hidden,
disabled, or otherwise unavailable until all of the following are implemented together:

- replay-backed execution-profile overlay restoration
- effective runtime adapter-setting / binding materialization from launch defaults plus overlay
- session-manager compatibility enforcement against the effective execution-profile stamp
- operation query / status exposure of launch default, overlay, and effective execution profile

It is not acceptable to ship the command first and let replay, compatibility, or query truth catch
up later.

### Expected tranche order

Tranche 1:

- typed `allowed_models` schema and config-reference updates
- replay-compatible operation-local overlay state model
- effective runtime materialization logic from launch defaults plus overlay

Tranche 2:

- session-manager compatibility enforcement
- operation query / status projection of launch default, overlay, and effective profile
- migration-compatible replay / resume / recover behavior for legacy operations

Tranche 3:

- `set_execution_profile` command and delivery entrypoints
- command inspection surfaces
- end-to-end verification for attached, resume, and recover flows

The command is not considered ready for user exposure before Tranche 2 is complete.

The expected implementation wave should then cover, in implementation terms already committed by
the contract sections above:

1. typed `allowed_models` support in project-profile schema and config reference
2. runtime persistence for operation-local execution-profile overlays through canonical command /
   checkpoint truth, with replay and resume reconstruction rules
3. a dedicated `set_execution_profile` operation command with explicit adapter-key targeting and
   deterministic payload validation
4. normalized execution-profile stamps plus session-manager compatibility checks against the current
   effective profile
5. CLI and query surfaces that expose both:
   - the default profile
   - the current effective runtime override
   - and the resulting effective execution profile
6. verification that disallowed adapter switching and malformed cross-adapter payloads are rejected
   explicitly
7. verification that replay, resume, recover, session reuse, and delivery truth remain correct when
   an execution-profile override exists

## Repository Evidence

Current repository truth that grounds this ADR:

- adapter defaults exist today in:
  [config.py](/Users/thunderbird/Projects/operator/src/agent_operator/config.py:20)
- project profiles already expose bounded per-adapter settings in:
  [profile.py](/Users/thunderbird/Projects/operator/src/agent_operator/domain/profile.py:14)
- profile adapter overrides are already applied at run start in:
  [profiles.py](/Users/thunderbird/Projects/operator/src/agent_operator/runtime/profiles.py:173)
- effective adapter settings are already snapshotted into operation goal metadata and restored on
  resume / recover in:
  [control_runtime.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/workflows/control_runtime.py:45)
  and
  [control_runtime.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/workflows/control_runtime.py:426)
- profile and resolved-run boundary is already committed in:
  [ADR 0018](/Users/thunderbird/Projects/operator/design/adr/0018-project-profile-schema-and-override-model.md)
  and
  [ADR 0148](/Users/thunderbird/Projects/operator/design/adr/0148-project-profile-schema-completion-and-resolution-contract.md)
- runtime control already supports bounded operation-local policy mutation through
  `set_allowed_agents` and patch commands, while `OperationCommandType` currently contains no
  model/effort override command:
  [enums.py](/Users/thunderbird/Projects/operator/src/agent_operator/domain/enums.py:192)
- current event-sourced command handling already provides the canonical mutation pattern for bounded
  operation-local runtime changes in:
  [event_sourced_commands.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/event_sourcing/event_sourced_commands.py:358)
- current reusable-idle selection is still adapter-key based and therefore needs the compatibility
  strengthening this ADR now specifies:
  [loaded_operation.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/loaded_operation.py:330)
- Codex execution-policy fields already exist as adapter-owned authored runtime settings under
  `ADR 0010`, which is why this ADR now admits them for `codex_acp` profile matching rather than
  treating them as arbitrary transport mutation:
  [ADR 0010](/Users/thunderbird/Projects/operator/design/adr/0010-expose-codex-acp-execution-policy.md)
- project and operation policy/query surfaces already distinguish profile scope from operation-local
  truth in:
  [operation_policy_context.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/runtime/operation_policy_context.py:17)
- Claude ACP effort is already an operator-owned mapped setting rather than a native ACP runtime
  RPC:
  [ADR 0043](/Users/thunderbird/Projects/operator/design/adr/0043-claude-acp-effort-via-thinking-token-env.md)

## Verification

Verified locally on 2026-04-23 with targeted evidence plus full `pytest -q`.

Repository truth advanced on 2026-04-27 by extending the verified Codex tranche so execution-
profile overlays, session stamps, and reuse compatibility also carry `approval_policy` and
`sandbox_mode` for `codex_acp`, consistent with `ADR 0010`.

Repository evidence for the closure criteria:

- accepted execution-profile override commands persist as canonical operation-local overlays through
  event-sourced command handling and replay-backed state:
  [operation_commands.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/commands/operation_commands.py:1212),
  [event_sourced_commands.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/event_sourcing/event_sourced_commands.py:379),
  [operation.py](/Users/thunderbird/Projects/operator/src/agent_operator/domain/operation.py:88),
  [checkpoints.py](/Users/thunderbird/Projects/operator/src/agent_operator/domain/checkpoints.py:61),
  covered by
  [test_operation_command_service.py](/Users/thunderbird/Projects/operator/tests/test_operation_command_service.py:2476)
- resume restores launch-default adapter settings from operation metadata, then continues using the
  reconstructed effective runtime settings:
  [control_runtime.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/workflows/control_runtime.py:440),
  covered by
  [test_cli.py](/Users/thunderbird/Projects/operator/tests/test_cli.py:6525)
- idle session reuse is rejected when the concrete session stamp does not match the current
  effective execution profile:
  [loaded_operation.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/loaded_operation.py:95),
  covered by
  [test_attached_turn_service.py](/Users/thunderbird/Projects/operator/tests/test_attached_turn_service.py:741)
- Codex execution-policy fields participate in accepted override persistence, session-profile
  application events, and idle-session compatibility matching:
  [runtime_bindings.py](/Users/thunderbird/Projects/operator/src/agent_operator/adapters/runtime_bindings.py:201),
  [loaded_operation.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/loaded_operation.py:97),
  [operation_turn_execution.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_turn_execution.py:536),
  covered by
  [test_event_sourced_command_application.py](/Users/thunderbird/Projects/operator/tests/test_event_sourced_command_application.py:461),
  [test_operation_command_service.py](/Users/thunderbird/Projects/operator/tests/test_operation_command_service.py:2480),
  [test_attached_turn_service.py](/Users/thunderbird/Projects/operator/tests/test_attached_turn_service.py:795)
- operation query/status surfaces expose launch default, overlay, allowed models, and effective
  execution-profile truth:
  [operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/queries/operation_projections.py:491),
  [operation_status_queries.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/queries/operation_status_queries.py:208),
  covered by
  [test_operation_projections.py](/Users/thunderbird/Projects/operator/tests/test_operation_projections.py:214)
  and
  [test_operation_status_queries.py](/Users/thunderbird/Projects/operator/tests/test_operation_status_queries.py:74)
- deterministic rejection covers malformed payloads, unallowlisted profiles, and unsupported
  adapters without permitting adapter switching:
  [operation_commands.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/commands/operation_commands.py:1212),
  covered by
  [test_operation_command_service.py](/Users/thunderbird/Projects/operator/tests/test_operation_command_service.py:2542)
  and
  [test_operation_command_service.py](/Users/thunderbird/Projects/operator/tests/test_operation_command_service.py:2592)

This closure wave ran:

- `pytest -q tests/test_operation_command_service.py tests/test_attached_turn_service.py tests/test_operation_projections.py tests/test_operation_status_queries.py`
- `pytest -q`

Verification notes:

- `resume` is directly covered.
- `recover` uses the same effective-adapter-settings restore path as `resume` in
  [control_runtime.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/workflows/control_runtime.py:426),
  but this closure wave does not add a dedicated recover-only regression.
- in-flight turn hot-swap prevention remains an implementation inference from the command/update
  path plus the session-start compatibility rules; no separate dedicated regression was added here.

The design requires verification of at least the following behaviors:

- accepted execution-profile override commands replay into the same effective execution profile after
  checkpoint reload
- `resume` and `recover` restore launch defaults, apply overlay state, materialize effective
  runtime settings, and only then make session reuse / fresh-start decisions
- idle session reuse is rejected when the session's execution-profile stamp does not match the
  current effective profile
- idle session reuse continues to work when the stamp does match the current effective profile
- accepted commands do not hot-swap in-flight turns
- operation query / status / CLI surfaces show launch default, current overlay, and current
  effective profile truthfully
- accepted-command plus later runtime-activation failure surfaces as an explicit blocked / failed /
  alert state rather than silent fallback
- legacy operations and checkpoints with no overlay state replay as launch-default-only operations

Representative verification slices should include:

- event-sourced command application coverage
- operation command service and replay-backed persistence coverage
- operation entrypoint / resume / recover coverage
- CLI or query-surface coverage for effective-profile visibility
- attached or session-manager coverage for compatibility-driven reuse decisions
