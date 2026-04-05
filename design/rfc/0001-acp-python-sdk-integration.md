# RFC 0001: Adopt the ACP Python SDK to shrink direct ACP integration code

## Status

Proposed

## Historical note

This RFC still describes ACP integration beneath the older `AgentAdapter` public lifecycle.
Current repository truth uses runtime-contract boundaries from ADR 0081, ADR 0082, ADR 0083,
ADR 0089, and ADR 0091. Read this RFC as substrate history, not as the current public runtime
shape.

## Context

`operator` currently carries a substantial amount of direct ACP plumbing:

- subprocess startup and stdio framing,
- JSON-RPC request/response handling,
- session lifecycle management,
- permission prompt handling,
- tool-call and notification parsing,
- and adapter-specific process orchestration for `claude_acp` and `codex_acp`.

The Agent Client Protocol Python SDK already advertises the exact building blocks that overlap with this code:

- `acp.schema` for canonical payload models,
- `acp.agent` / `acp.client` for async connection and lifecycle orchestration,
- `acp.helpers` for content blocks, tool calls, permissions, and notifications,
- `acp.contrib` for session accumulators, permission brokers, and tool-call trackers,
- and `spawn_agent_process` / `spawn_client_process` for stdio process wiring.  
  See the SDK home page and quickstart overview for the current public surface. The SDK explicitly positions itself as a way to ship ACP-compatible agents and clients “without rebuilding JSON-RPC transports or schema models.”  
  Sources: [SDK home](https://agentclientprotocol.github.io/python-sdk/) and [quick links / choose a path](https://agentclientprotocol.github.io/python-sdk/).

That creates a plausible refactor path: move ACP transport and session machinery into the SDK, keep `operator` focused on orchestration, persistence, CLI truth, and policy.

RFC 0002 provides the deeper comparative rationale for that boundary by studying the ACP Python SDK
alongside `kimi-cli`, `Mini-Agent`, and `OpenHands-CLI` as reference systems rather than as
drop-in templates.

RFC 0003 defines the next refactor layer above that boundary: a shared ACP session runner beneath
vendor adapters, so SDK adoption does not leave duplicated session-execution skeletons in
`claude_acp` and `codex_acp`.

Current status:

- the bespoke ACP transport and adapter path is implemented,
- this RFC's SDK-backed replacement path is planned,
- and the document does not claim that the SDK-backed path is already verified in the repository.

## Decision

Adopt the ACP Python SDK as the default implementation substrate for ACP-backed coding agents, but
make the ACP boundary explicit as an operator-owned ACP substrate beneath the existing
session-oriented `AgentAdapter` lifecycle.

That contract question is not "should `operator` call the SDK directly?" It is "what ACP-facing
interface does `operator` own so that a bespoke ACP client and an SDK-backed ACP client can be
swapped underneath the adapters without moving operator policy or runtime semantics into the ACP
layer?"

For this RFC, that operator-owned ACP substrate is responsible for:

- launching or attaching to ACP-speaking worker commands and maintaining stdio transport,
- issuing ACP requests and receiving ACP notifications through canonical payload models,
- managing session creation and session loading primitives,
- translating ACP permission and tool-call events into stable adapter-consumable structures,
- and exposing the raw metadata/hooks that adapters need for operator observability and recovery.

The operator-level coexistence mechanism for migration is a per-adapter ACP substrate seam.
In practical terms, bootstrap and background-worker composition should resolve an ACP substrate
implementation for each ACP adapter key independently:

- `codex_acp` can be bound to either the bespoke ACP substrate or the SDK-backed ACP substrate,
- `claude_acp` can be bound to either the bespoke ACP substrate or the SDK-backed ACP substrate,
- and those choices must be injectable without changing the `AgentAdapter` lifecycle above them.

During migration, `operator` should be able to run one ACP adapter on the bespoke substrate and the
other on the SDK-backed substrate at the same time. Rollback should mean switching the affected
adapter back to the bespoke substrate while leaving the higher operator flow unchanged.

The `AgentAdapter` contract remains the operator-facing lifecycle above that ACP substrate. The
migration is only acceptable if `start`, `send`, `poll`, `collect`, `cancel`, and `close` keep the
same operator-visible semantics around:

- follow-up and session-load behavior,
- `WAITING_INPUT` and other progress projection,
- approval-routing outcomes and permission waits,
- background-worker startup / handoff / completion behavior,
- and close / cleanup semantics.

`operator` should continue to own:

- run lifecycle and scheduling,
- attached vs resumable semantics,
- background supervision and recovery,
- wakeups and event persistence,
- CLI-facing reporting / inspect surfaces,
- policy / approval routing at the operator level,
- and project-profile resolution.

In other words:

- the SDK should absorb low-level ACP protocol and session machinery by implementing the
  operator-owned ACP substrate,
- ACP adapters should continue to present the existing session-oriented `AgentAdapter` lifecycle
  above that substrate,
- and `operator` should retain the higher-level control plane and every operator-visible semantic
  attached to that lifecycle.

## Dependencies and prerequisites

Adopting the SDK is not limited to replacing `src/agent_operator/acp/client.py`.

This RFC assumes the SDK can be introduced as a normal Python dependency. It also assumes that SDK
adoption does not remove the need for ACP-speaking worker executables, or an equivalent
adapter-specific launch target, for `claude_acp` and `codex_acp` unless a separate RFC changes that
runtime assumption. The SDK is the client-side substrate, not the worker implementation.

The migration will likely touch:

- dependency management and locking for the ACP Python SDK itself,
- ACP adapter constructors and internal connection/session helpers,
- the per-adapter ACP substrate seam in bootstrap and background-worker composition,
- adapter settings and command surfaces in `src/agent_operator/config.py`,
- project-profile overrides in `src/agent_operator/runtime/profiles.py`,
- CLI and inspection consumers that read session metadata or upstream logs,
- and ACP-focused tests that currently fake or patch `AcpConnection` behavior directly.

`operator` may still need thin local seams where tests, log discovery, or observability require
stable hooks above the SDK-backed substrate.

## Scope of change

### What should move into the SDK-backed layer

- JSON-RPC framing and I/O over stdio.
- Session create/load lifecycle glue used by current ACP adapters.
- ACP-side permission request/response envelopes and helper types.
- Tool call and content block helpers.
- ACP schema validation and protocol-level payload shaping.

### What should stay in `operator`

- operation state machine and turn selection,
- brain decision logic,
- run persistence and traceability,
- wakeup / timeout / recovery behavior,
- project profile loading and CLI launch ergonomics,
- `inspect`, `report`, `list`, and `agenda` rendering,
- red-team / swarm orchestration,
- operator-facing progress projection and persisted truth,
- operator-level approval, blocking, and escalation policy,
- and any operator-specific policy about when a request should be auto-approved, blocked, or escalated.

The boundary is therefore:

- the SDK may own ACP wire mechanics, canonical models, and generic session helpers by satisfying
  the operator-owned ACP substrate contract,
- adapters may translate substrate events into the session-oriented `AgentAdapter` contract,
- but `operator` still owns policy decisions, user-facing run semantics, durable observability, and
  the lifecycle guarantees attached to `AgentAdapter`.

If the SDK does not expose the same raw stderr, notification, session-metadata, or transcript hooks
that `operator` currently uses for recovery, inspection, and log discovery, a thin local
compatibility shim should remain above the SDK rather than forcing those operator concerns into
upstream abstractions.

The migration also should not assume that `claude_acp` and `codex_acp` collapse into one identical
path. The current adapters already differ in connection reuse and session reload behavior, so the
SDK-backed implementation may still need adapter-specific normalization above the shared ACP
substrate.

Choosing `codex_acp` first only reduces first-adapter risk; it does not remove shared ACP substrate
risks in bootstrap wiring, background-worker startup, session metadata projection, or observability
hooks.

## Alternatives Considered

- Keep the current direct integration code.
- Replace the entire operator layer with the SDK.
- Use the SDK only for schema validation, while keeping our hand-rolled transport.

The first option preserves status quo but leaves us maintaining duplicated ACP machinery.  
The second option overreaches: it would throw away operator-specific orchestration that is not the SDK’s job.  
The third option is weak: the transport/session code is the biggest maintenance burden, so using only the schema layer would leave most of the duplication intact.

## Consequences

- Positive:
  - less custom ACP transport code to maintain,
  - more alignment with the upstream protocol implementation,
  - lower risk of drift in session/permission/tool-call handling,
  - better interoperability with ACP-compatible editors and clients.
- Negative:
  - an extra dependency and upgrade surface,
  - possible API churn while the SDK evolves,
  - some current adapter-specific behavior may need to be re-expressed in SDK terms,
  - the operator codebase must still keep a thin compatibility layer for project-specific behavior.
- Follow-up implication:
  - we should treat this as a staged migration, not a big-bang rewrite.

## Migration Plan

### Phase 1: Inventory and boundary definition

- Map current ACP code paths in:
  - `src/agent_operator/adapters/claude_acp.py`
  - `src/agent_operator/adapters/codex_acp.py`
  - `src/agent_operator/acp/client.py`
  - `src/agent_operator/bootstrap.py`
  - `src/agent_operator/background_worker.py`
  - `src/agent_operator/config.py`
  - `src/agent_operator/runtime/profiles.py`
- Classify each function as:
  - transport,
  - session lifecycle,
  - permission handling,
  - configuration / launch-target wiring,
  - inspection / observability support,
  - or operator-specific orchestration.
- Define the per-adapter ACP substrate seam that bootstrap and the background worker will both use
  so each ACP adapter key can be bound independently to either the bespoke or SDK-backed substrate
  during migration.

### Phase 2: SDK-backed adapter spike

- Build a narrow proof-of-concept adapter using the SDK for `codex_acp` first.
- Use `codex_acp` as the first migration target because it is the lower-risk first adapter
  migration, not because it eliminates shared ACP migration risk:
  - it already reloads sessions instead of preserving a long-lived live connection across collects,
  - it does not currently carry the Claude-specific cooldown classification path,
  - and its adapter-specific startup policy is narrower than `claude_acp`.
- Keep the per-adapter ACP substrate seam in place from the start so `codex_acp` can use the
  SDK-backed substrate while `claude_acp` remains on the bespoke substrate.
- Keep the operator-facing API unchanged.
- Verify:
  - prompt/response round-trip,
  - permission handling,
  - session load and follow-up continuation,
  - `WAITING_INPUT` projection,
  - one-shot vs reusable session behavior,
  - background-worker startup and completion handoff,
  - wakeup-driven resume reconciliation,
  - CLI/log parity for session metadata and upstream transcript discovery,
  - mixed-mode composition with one ACP adapter on the SDK-backed substrate and the other on the
    bespoke substrate,
  - and log/trace parity with the current implementation.

Do not advance beyond this phase if the SDK-backed `codex_acp` path loses any of those behaviors or
requires application-layer contract changes to recover them. Also do not advance if the new
per-adapter ACP substrate seam only works in attached paths but not in background-worker
composition.

### Phase 3: Gradual replacement

- Keep `claude_acp` on the bespoke substrate while `codex_acp` is migrated and verified.
- Treat the interim state, where one ACP adapter is SDK-backed and the other remains bespoke, as an
  acceptable compatibility stage.
- Keep bootstrap wiring, background-worker composition, and any observability hooks that depend on
  ACP session metadata dual-path during this stage if that is what the per-adapter ACP substrate
  seam requires.
- Migrate `claude_acp` only after the `codex_acp` SDK-backed path passes the Phase 2 regression
  gates.
- Preserve existing tests while swapping implementation details. Require verification from:
  - adapter unit tests for prompt, follow-up, permission, and progress behavior,
  - background-worker and resume-path tests for wakeups and reconciliation,
  - direct local runtime evidence for the SDK-backed `codex_acp` path,
  - direct local runtime evidence for the SDK-backed `claude_acp` path before the bespoke Claude
    substrate is removed,
  - direct verification of the mixed deployment stage where one ACP adapter is SDK-backed and the
    other remains bespoke,
  - and inspection/log artifact comparison when observability hooks change.
- Add or keep regression coverage around:
  - permission prompts and operator-side approval behavior,
  - session restart and follow-up continuation,
  - `WAITING_INPUT` progress handling,
  - one-shot vs reusable session semantics,
  - failure classification,
  - background worker startup and completion,
  - wakeup reconciliation after resumable turns,
  - per-adapter ACP substrate seam behavior in both attached and background-worker composition,
  - session metadata and log-path parity needed by CLI and inspection consumers,
  - and Claude rate-limit cooldown behavior.

If the SDK-backed `claude_acp` path cannot preserve cooldown inputs, permission semantics, or
reusable-session behavior without excessive glue, the migration should stop at a partial state
rather than forcing both adapters through one shared implementation.

### Phase 4: Remove dead code

- Delete ACP transport and helper code only after both ACP adapters satisfy the regression gates and
  the remaining operator-level shims are clearly identified.
- Require deletion evidence from:
  - direct runtime evidence for each migrated ACP adapter,
  - explicit verification of the mixed bespoke/SDK-backed deployment stage,
  - parity checks for background-worker startup, wakeup reconciliation, and CLI/log metadata
    discovery,
  - and confirmation that rollback no longer depends on dual-path bootstrap, background-worker, or
    observability wiring.
- Keep only the operator-specific wrapper logic that genuinely belongs above the SDK.
- Retain any thin local compatibility layer that remains necessary for observability or policy
  projection.
- If a stage regresses runtime behavior, rollback should mean switching the affected adapter back to
  the bespoke substrate and leaving any required dual-path bootstrap, background-worker, or
  observability seams in place until parity is restored.

## Open Questions

- Does the SDK already cover all permission-handling cases we need, or will we still need a thin custom broker?
- Can the SDK preserve the exact logging and traceability shapes we currently rely on for `inspect` and recovery?
- Can the SDK-backed `claude_acp` path preserve current reusable-session and cooldown behavior without excessive adapter-local glue?
- What is the narrowest operator-owned configuration or injection surface that can drive the
  per-adapter ACP substrate seam without turning migration scaffolding into a permanent
  public interface?

## Success Criteria

- The operator can launch at least one ACP-backed worker through the SDK without changing external CLI semantics.
- Existing operator run/recovery behavior remains intact across follow-up, waiting-input, background-wakeup, and one-shot session paths.
- The amount of handwritten ACP transport code in the repo is materially smaller.
- Verification includes adapter tests, background-runtime tests, direct runtime checks for each
  migrated ACP adapter before its bespoke path is removed, and explicit evidence for the mixed
  bespoke/SDK-backed deployment stage.
- The old bespoke ACP path is deleted only after both ACP adapters meet the named regression gates.

## Final Ledger

- target document: `design/rfc/0001-acp-python-sdk-integration.md`
- rounds completed:
  - round 1: dependencies, prerequisites, interface impacts, and architectural boundary claims
  - round 2: migration order, failure modes, rollback or compatibility risks, verification
    adequacy, and implementation realism
  - round 3: wording precision, consistency, internal coherence, and readability
- key fixes made:
  - clarified the operator-owned ACP boundary and preserved `AgentAdapter` lifecycle semantics
  - added the per-adapter ACP substrate seam for mixed bespoke/SDK-backed coexistence and rollback
  - raised the deletion bar to require per-adapter runtime evidence plus mixed-mode verification
  - normalized terminology around the injected ACP layer and reduced repeated mechanism wording
  - removed embedded round-by-round repair ledgers from the RFC body
- critique artifact paths:
  - `design/rfc/0001-acp-python-sdk-integration.round1-critique.md`
  - `design/rfc/0001-acp-python-sdk-integration.round2-critique.md`
  - `design/rfc/0001-acp-python-sdk-integration.round3-critique.md`
- residual issues still open:
  - the exact implementation form of the per-adapter ACP substrate seam remains open by design
  - SDK coverage for Claude cooldown handling, permission brokering, and observability hooks still
    requires implementation-time verification
