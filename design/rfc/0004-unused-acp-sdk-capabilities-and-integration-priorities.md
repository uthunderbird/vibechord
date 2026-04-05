# RFC 0004: Unused ACP SDK capabilities and integration priorities for `operator`

## Status

Proposed

## Context

RFC 0001 defines the operator-owned ACP substrate boundary and the migration toward the ACP Python
SDK.

RFC 0003 defines the next refactor layer above that substrate: a shared ACP session runner beneath
vendor adapters.

Those RFCs answer where the ACP boundary should sit and where the next deduplication seam should
sit. They do not yet answer a different practical question:

Which ACP SDK capabilities does `operator` still leave unused, and which of those are worth
integrating next?

That question matters because the SDK surface is broader than the narrow subset currently exercised
by `operator`.

Based on the current installed SDK surface and the repository integration:

- the SDK exposes client-side permission decisions, file operations, terminal operations, extension
  hooks, and session updates,
- the SDK exposes richer agent-side session control methods such as list, fork, resume, close, and
  authenticate,
- the SDK ships `acp.contrib` helpers such as `PermissionBroker`, `SessionAccumulator`, and
  `ToolCallTracker`,
- and the schema includes usage-related models such as `Usage` and `UsageUpdate`.

At the same time, the current SDK-backed substrate in
[`src/agent_operator/acp/sdk_client.py`](/Users/thunderbird/Projects/operator/src/agent_operator/acp/sdk_client.py)
uses only a narrower set:

- `initialize`
- `session/new`
- `session/load`
- `session/set_mode`
- `session/set_model`
- `session/set_config_option`
- `session/prompt`
- `session/cancel`
- `session/update`
- and `session/request_permission`

The rest is currently unsupported or not yet wired into operator semantics.

## Decision

Treat the unused ACP SDK capabilities as a prioritized backlog, not as a flat checklist.

The next integrations should be driven by operator value and architectural fit, not by a desire to
maximize SDK surface area.

The recommended priority order is:

1. shared permission-policy integration over SDK permission hooks,
2. shared session accumulation and tool-call tracking,
3. usage propagation and observability,
4. richer session control methods,
5. extension hooks only when standard ACP surfaces are insufficient,
6. file and terminal mediation only when there is a specific operator-level need.

This RFC also makes one boundary explicit:

`operator` should not assume that plan negotiation, plan acceptance, plan correction, or
plan-question workflows are already first-class ACP SDK features. Those product semantics should
remain operator-owned unless a concrete protocol-native representation is established.

## Capability Inventory

### Already used in `operator`

The current ACP substrate and adapters already use:

- permission request handling,
- session update delivery,
- basic session create/load lifecycle,
- session mode/model/config setting,
- prompt/send,
- and cancel.

These are the current minimal ACP-backed execution mechanics.

### Present in the SDK but not yet meaningfully integrated

#### Shared permission brokerage

The SDK provides a client-side permission loop and also ships `acp.contrib.PermissionBroker`.

`operator` currently handles permission requests through adapter-local logic, with narrow
auto-approve cases and no shared policy engine above the SDK hook.

This is the highest-value missing integration because:

- the protocol surface already exists,
- the operator already needs a real policy layer,
- and both Claude and Codex paths currently duplicate decision logic.

#### Session accumulation and tool-call tracking

The SDK exposes:

- `SessionAccumulator`
- `SessionSnapshot`
- `ToolCallTracker`

These overlap with bookkeeping that `operator` still performs manually in ACP-backed adapters.

They are not equally good candidates for adoption.

`SessionAccumulator` is the natural fit for the current architecture. It is a client-side
accumulator that consumes `SessionNotification` values and produces a derived `SessionSnapshot`
covering tool calls, plan entries, current mode, available commands, user messages, agent
messages, and agent thoughts.

`ToolCallTracker` is not the same kind of utility. It is primarily a producer-side helper for
emitting `tool_call` and `tool_call_update` messages. That makes it a much better fit for an
ACP server/agent implementation than for the current `operator` client runtime.

The architectural rule for this area is therefore:

- `SessionAccumulator` may be adopted later as an **internal helper inside the shared ACP session
  runner** from RFC 0003,
- but it should not become the canonical operator-owned session state,
- and `ToolCallTracker` should remain deferred until `operator` has a real ACP-producer use case.

In other words:

- `AcpSessionState` remains the source of truth for runner lifecycle and operator semantics,
- `SessionAccumulator` is only a derived structured view,
- and `ToolCallTracker` is intentionally out of scope for the current client-side ACP integration.

#### Usage propagation

The schema exposes:

- `Usage`
- `UsageUpdate`

`operator` does not currently surface usage/cost/token telemetry as a first-class ACP-backed
progress channel.

This is a real protocol-native capability and a likely observability improvement.

#### Richer session control

The SDK agent-side interface includes:

- `list_sessions`
- `fork_session`
- `resume_session`
- `close_session`
- `authenticate`

These are not currently mapped through the operator-owned ACP substrate.

They matter because they may support:

- better session reuse and inspection,
- cleaner recovery stories,
- future side-channel tasks such as safe summarization or session branching,
- and more honest lifecycle ownership.

#### Extension hooks

The SDK supports:

- `ext_method`
- `ext_notification`

These should be treated as a bounded escape hatch, not a default integration mechanism.

They are useful only when:

- a needed capability is real and stable,
- and it cannot be expressed cleanly through standard ACP requests, responses, or notifications.

#### File and terminal mediation

The SDK client-side surface includes:

- `write_text_file`
- `read_text_file`
- `create_terminal`
- `terminal_output`
- `release_terminal`
- `wait_for_terminal_exit`
- `kill_terminal`

The current `operator` SDK substrate explicitly rejects these operations.

This is an intentional omission today, not evidence that the SDK lacks the capability.

These hooks are lower priority because:

- `operator` already has working vendor/runtime paths for most coding flows,
- and enabling them safely would require explicit operator policy about allowed I/O and terminal
  ownership.

## What is not yet protocol-native enough to assume

The following product behaviors are important to `operator`, but this RFC does **not** conclude
that the ACP SDK already provides them as a standard first-class protocol contract:

- switching into planning mode,
- presenting a plan for acceptance,
- asking plan-specific clarification questions,
- correcting a proposed plan,
- and accepting or rejecting a plan as a distinct protocol step.

Those workflows may still be expressible through:

- ordinary session updates,
- ordinary prompts,
- permission-style or tool-style intermediate requests,
- or extension methods.

But that is not the same thing as the SDK already providing a canonical plan-negotiation API.

`operator` should therefore continue to treat plan negotiation semantics as operator-owned until a
cleaner protocol-native model is proven.

## Recommended Integration Order

### Priority 1: Shared permission policy layer

Build a shared operator-owned permission decision layer above the SDK permission hook.

This layer should decide:

- auto-approve,
- auto-reject,
- block awaiting user input,
- or escalate to a higher operator policy state.

It should not remain split between `claude_acp` and `codex_acp`.

### Priority 2: Shared session accumulation and tool-call tracking

Adopt or wrap SDK contrib utilities only where they actually reduce duplicated bookkeeping inside
the shared ACP session runner from RFC 0003.

For the current architecture, this means:

- `SessionAccumulator` is the main candidate for integration,
- and it should be used as an internal helper beneath operator-owned runner state rather than as a
  replacement for that state.

This work should align with RFC 0003 rather than becoming a separate parallel abstraction.

`ToolCallTracker` is explicitly **not** part of this priority unless `operator` gains a concrete
need to emit ACP tool-call updates as a producer.

### Priority 3: Usage and cost observability

Wire `Usage` / `UsageUpdate` through the ACP session runner into operator-facing progress,
traceability, and possibly inspect/report surfaces.

This should be done carefully and labeled honestly as:

- implemented only when the data is actually present,
- and not inferred when a vendor path does not supply it.

### Priority 4: Richer session control

Extend the operator-owned ACP substrate to support:

- `list_sessions`
- `fork_session`
- `resume_session`
- `close_session`
- `authenticate`

Only integrate the methods with a clear operator use case and verification path.

### Priority 5: Extension hooks

Support `ext_method` / `ext_notification` only when a concrete needed capability cannot be
expressed cleanly through the standard ACP surface.

Do not turn extensions into the default integration path.

### Priority 6: File and terminal mediation

Revisit file/terminal hooks only if operator-level workflows genuinely benefit from routing them
through ACP rather than through existing vendor/runtime paths.

This should be policy-led, not protocol-led.

## Alternatives Considered

- Ignore all unused SDK capabilities and keep the current narrow ACP subset indefinitely.
- Try to integrate every available SDK capability immediately.
- Treat extension hooks as the universal answer for missing behavior such as planning workflows.

Ignoring the unused capabilities would leave real value on the table, especially around permission
policy, session accumulation, and usage.

Integrating everything immediately would create abstraction churn and policy confusion.

Using extension hooks as the default answer would weaken interoperability and make the ACP boundary
less disciplined.

## Consequences

- Positive:
  - clearer backlog for ACP integration work,
  - less confusion between protocol-native hooks and operator-owned semantics,
  - and better prioritization of the next high-value ACP features.
- Negative:
  - more explicit staged work instead of a one-time ACP migration claim,
  - and a need to verify capability-by-capability rather than assuming the SDK solves everything at
    once.
- Follow-up implication:
  - future ACP work should justify why a capability belongs in the next slice instead of being
    opportunistically added.

## Open Questions

- Should the shared permission layer wrap `PermissionBroker` directly or expose an operator-owned
  policy contract above it?
- How much of `SessionAccumulator` should be adopted directly versus wrapped behind operator-owned
  models?
- Which operator-facing surfaces should expose usage data first?
- Does `fork_session` have an immediate operator use case, or should it remain dormant until one is
  proven?

## Relationship to RFC 0001 and RFC 0003

RFC 0001 defines the ACP SDK substrate migration.

RFC 0003 defines the shared ACP session runner above that substrate.

This RFC identifies the next missing SDK-backed capabilities worth integrating into those layers and
clarifies that plan semantics still remain operator-owned above ACP.
