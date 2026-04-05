# ADR 0050: Shared ACP session runner beneath vendor adapters

## Status

Accepted

## Context

After the ACP substrate seam from ADR 0048, `claude_acp` and `codex_acp` still duplicate a large
session-execution skeleton:

- connection initialization,
- session create/load,
- prompt dispatch,
- notification draining,
- in-memory session bookkeeping,
- terminal collection,
- and cancel/close flow.

At the same time, the adapters still differ in meaningful vendor policy:

- Claude-specific model and permission-mode behavior,
- Claude-specific cooldown/rate-limit classification,
- Codex-specific config-option wiring,
- Codex-specific approval/sandbox semantics,
- and vendor-specific request handling.

The repository needs a deduplication step that removes the duplicated lifecycle skeleton without
collapsing vendor policy into one generic adapter.

## Decision

Introduce a shared operator-owned ACP session runner beneath `claude_acp` and `codex_acp`.

The runner owns:

- shared ACP session state,
- create/load/prompt lifecycle,
- notification draining,
- transcript accumulation,
- terminal collection,
- and generic cancel/close choreography.

Vendor adapters remain as thin policy shells that provide narrow hooks for:

- session configuration,
- request handling,
- error classification,
- connection reuse policy,
- and user-facing status wording.

The design is composition-first. It does not introduce an inheritance-heavy base adapter.

That shared runner is now the active repository shape:

- both `claude_acp` and `codex_acp` compose a shared `AcpSessionRunner`
- shared ACP session lifecycle logic lives in `src/agent_operator/acp/session_runner.py`
- vendor adapters remain thin policy shells around runner hooks and adapter-specific connection
  configuration

## Alternatives Considered

- Keep duplicated adapter lifecycle code.
- Introduce a single generic ACP adapter with vendor flags.
- Introduce a hook-heavy `BaseAcpAdapter` inheritance hierarchy.

Keeping the duplication would preserve avoidable lifecycle drift.

A single generic adapter would obscure meaningful Claude/Codex differences.

A hook-heavy base class would overfit the abstraction and conflict with the repository bias toward
small explicit abstractions.

## Consequences

- Positive:
  - less duplicated ACP adapter lifecycle code,
  - clearer separation between shared session mechanics and vendor policy,
  - easier parity testing,
  - and a cleaner landing zone for future shared permission and usage work.
- Negative:
  - one more internal abstraction layer,
  - some test churn around private adapter internals,
  - and a new shared contract that must remain narrow.
- Follow-up implication:
  - the shared runner seam is now the evaluation point for further ACP utility adoption.
  - `SessionAccumulator` is already used within the shared runner; other contrib helpers such as
    `ToolCallTracker` remain a separate follow-up decision rather than part of the baseline ADR.
