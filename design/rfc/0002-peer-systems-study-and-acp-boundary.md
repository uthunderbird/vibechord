# RFC 0002: Peer-system study and ACP boundary for `operator`

## Status

Proposed

## Context

RFC 0001 argues that `operator` should adopt the ACP Python SDK as the default substrate for ACP
integration. That decision is directionally useful, but incomplete on its own.

The harder architectural question is not whether the SDK is relevant. It is where the boundary
should sit between:

- reusable ACP/session infrastructure,
- agent-runtime patterns from adjacent systems,
- and the operator-owned control plane.

This RFC answers that question by comparing four reference subjects:

- the ACP Python SDK,
- `kimi-cli`,
- `Mini-Agent`,
- and `OpenHands-CLI`.

The goal is not to imitate any one of them wholesale. The goal is to decide, with evidence, what
`operator` should reuse, what it should learn from, and what it should continue to own explicitly.

## Decision

`operator` should adopt the ACP Python SDK aggressively in the adapter and transport layer, but it
should not delegate control-plane semantics to the SDK or to shell-style agent runtimes.

Concretely:

- the ACP Python SDK should become the default substrate for ACP protocol mechanics,
- `OpenHands-CLI` should be treated as a lifecycle and confirmation-policy reference,
- `kimi-cli` should be treated as a session, wire, and approval-runtime reference,
- `Mini-Agent` should be treated as a simplicity and thin-core reference,
- and `operator` should remain the owner of run semantics, recovery, policy, persistence, and
  supervisory UX.

Peer systems are reference implementations and design signals. They are not architectural templates
for the whole product.

## Comparative Analysis

### ACP Python SDK

Observed shape:

- It provides canonical ACP schema models, client and agent lifecycle utilities, helper functions
  for ACP payloads, and subprocess launch wiring for ACP-compatible processes.
- Its value proposition is to avoid rebuilding JSON-RPC transports, schema models, and ACP
  connection glue.

What to borrow:

- ACP schema and message models.
- Session and client lifecycle plumbing.
- Subprocess stdio wiring.
- Generic payload helpers for content blocks, permissions, and tool calls.

What not to borrow:

- Product-level lifecycle policy.
- Run recovery semantics.
- Persistence and CLI truth surfaces.

Why:

- The SDK is a protocol substrate, not a control plane.
- Pushing run semantics into SDK-shaped abstractions would couple `operator` to a lower-level
  library boundary that does not represent the product.

### `kimi-cli`

Observed shape:

- It is primarily a user-facing interactive shell with optional ACP and wire-facing modes.
- Session persistence is first-class, with persisted session context and resume/load behavior.
- Approval handling is built into the runtime and surfaced clearly to the user.
- Wire/event streaming is treated as a primary runtime primitive.

What to borrow:

- Strong session persistence and resume framing.
- Explicit event and wire-stream thinking.
- A runtime-level separation between approval mechanics and UI rendering.

What not to borrow:

- Shell-first product shape.
- Deep per-action human approval as the default operator execution model.
- A conversation-centric runtime as the top-level owner of system behavior.

Why:

- `operator` is not primarily an interactive shell around one agent session.
- It supervises many runs and must preserve policy-driven automation paths without forcing shell UX
  into the center of the system.

### `Mini-Agent`

Observed shape:

- It is much closer to a single-agent execution loop than to a multi-run control plane.
- The architecture is centered on one agent runtime with pluggable tools and pluggable model
  clients.
- Observability is run-local rather than supervisory across many operations.

What to borrow:

- Thin execution core bias.
- Pluggable tool and provider boundaries.
- Simplicity over framework-heavy orchestration.

What not to borrow:

- Single-session assumptions.
- One-agent ownership of the whole runtime.
- Local-run observability as the main system truth.

Why:

- `operator` is valuable precisely because it sits outside a single agent loop and manages longer
  run lifecycle and recovery semantics.

### `OpenHands-CLI`

Observed shape:

- It is the closest peer in terms of explicit lifecycle vocabulary and confirmation policy.
- It uses a conversation-centric controller with explicit execution states such as running,
  waiting for confirmation, paused, finished, error, and stuck.
- It combines interactive UX, headless execution, and ACP-facing surfaces over one integrated
  runtime.

What to borrow:

- First-class lifecycle states.
- Confirmation-policy vocabulary that separates execution policy from tool implementation.
- Clear separation between a stateful controller and a step-oriented execution core.

What not to borrow:

- Conversation-level ownership as the main product abstraction.
- Treating the integrated agent runtime as the whole control plane.
- A shell/IDE-first product model as the architectural center.

Why:

- `operator` still needs an outer supervisory model with attached vs resumable semantics,
  background ownership, and cross-run observability that extends beyond one conversation runtime.

## Synthesis

The four subjects point to one consistent conclusion.

The ACP Python SDK is the right place to stop owning commodity ACP protocol mechanics.

`OpenHands-CLI` is the strongest reference for lifecycle vocabulary and confirmation-policy shape,
but not for top-level ownership.

`kimi-cli` is the strongest reference for session persistence, wire-oriented thinking, and approval
runtime structure, but not for shell-first product shape.

`Mini-Agent` is the strongest reminder to keep the execution core thin and pluggable, but not to
collapse `operator` into a single-agent runtime.

The common lesson is:

- borrow protocol and runtime primitives,
- borrow specific lifecycle and approval patterns,
- but keep product semantics and supervisory truth in `operator`.

## Boundary For `operator`

### What should move below the operator layer

- ACP schema and payload models.
- ACP client/session lifecycle glue.
- ACP subprocess startup and stdio framing.
- Generic request/response helpers for permissions, notifications, and tool-call envelopes.
- Reusable session accumulators or protocol-level event collectors when they do not impose product
  semantics.

### What must remain operator-owned

- operation run state machine,
- turn selection and brain-mediated decision flow,
- attached vs resumable semantics,
- background supervisor ownership,
- wakeups, daemon behavior, and recovery,
- cooldown and rate-limit policy,
- project profiles and harness rules,
- traceability and persisted truth,
- `inspect`, `report`, `list`, `agenda`, `fleet`, and `dashboard`,
- and operator-level policy about when to auto-approve, block, escalate, or stop.

### Why this boundary is correct

- The lower layer is protocol and session infrastructure.
- The upper layer is product behavior.
- Blurring them would make `operator` less explainable, harder to test, and more dependent on
  assumptions that belong to external runtimes.

## Alternatives Considered

- Keep the current bespoke ACP code and treat peer systems as irrelevant.
- Treat one peer system, especially `OpenHands-CLI`, as the primary architectural template.
- Push most operator lifecycle logic into SDK-shaped abstractions once the SDK is adopted.

The first option preserves unnecessary protocol duplication.

The second option imports a product model that is too centered on integrated shell or conversation
runtime behavior.

The third option weakens the core value of `operator`, which is explicit control-plane ownership of
run semantics and supervisory truth.

## Consequences

- Positive:
  - less bespoke ACP plumbing,
  - better protocol alignment,
  - clearer ownership boundary between adapters and control plane,
  - and a more disciplined basis for future adapter migrations.
- Negative:
  - an extra dependency surface through the ACP Python SDK,
  - migration work to preserve current logging and traceability expectations,
  - and continued need for a thin operator-owned bridge around SDK-backed adapters.
- Follow-up implication:
  - future ACP adapter work should be evaluated against this boundary, not against convenience in
    the moment.

## Open Questions

- Which adapter should migrate first: `claude_acp` or `codex_acp`?
- Does the ACP Python SDK cover all permission-request patterns we need, or do we still need a
  thin broker for operator-specific approval policy?
- How much of current adapter logging can move to SDK-backed structures without weakening
  `inspect`, recovery, or traceability semantics?

## Sources

- ACP Python SDK: [home](https://agentclientprotocol.github.io/python-sdk/),
  [use cases](https://agentclientprotocol.github.io/python-sdk/use-cases/)
- `kimi-cli`: primary repository and raw source files examined during this study
- `Mini-Agent`: primary repository and raw source files examined during this study
- `OpenHands-CLI`:
  [command reference](https://docs.openhands.dev/openhands/usage/cli/command-reference),
  [terminal mode](https://docs.openhands.dev/openhands/usage/cli/terminal),
  [IDE/ACP overview](https://docs.openhands.dev/openhands/usage/cli/ide/overview),
  [conversation architecture](https://docs.openhands.dev/sdk/arch/conversation),
  [agent architecture](https://docs.openhands.dev/sdk/arch/agent),
  [security guide](https://docs.openhands.dev/sdk/guides/security)
