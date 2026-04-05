# ADR 0051: Shared ACP permission policy and normalized request model

## Status

Accepted

## Context

After ADR 0050 introduced a shared ACP session runner, permission handling still remained split
between `claude_acp` and `codex_acp`.

Both adapters were independently doing the same high-level work:

- detect ACP permission-related requests,
- normalize enough payload to classify the request,
- decide whether to auto-approve, reject, or wait for input,
- render an ACP response,
- and update runner state to reflect blocking input.

This duplicated logic made future permission work harder, especially for later RFC 0004 slices.

## Decision

Introduce a shared operator-owned ACP permission policy layer with a normalized request model.

The design is:

- the runner or adapter hook normalizes raw ACP permission-like payloads into a small
  `AcpPermissionRequest`,
- shared policy decides an abstract `AcpPermissionDecision`,
- adapter-local code remains responsible only for vendor-specific safe-auto-approve predicates,
- shared rendering turns the abstract decision back into ACP response payloads,
- and the runner state records the resulting waiting/input state in the same way as before.

This ADR does not introduce human approval UI and does not move operator-level approval workflows
into ACP-specific code.

That shared seam is now the active repository shape:

- shared normalization, decision, rendering, and signature helpers live in
  `src/agent_operator/acp/permissions.py`
- both `claude_acp` and `codex_acp` use that shared ACP permission layer
- adapter-local code remains responsible for vendor-specific safe-auto-approve predicates and
  adapter-specific escalation wording

## Alternatives Considered

- Keep all permission logic inside each adapter.
- Move all request handling into one fully generic ACP policy engine.
- Wait until a larger human-approval feature exists before deduplicating anything.

Keeping all logic adapter-local would preserve avoidable duplication.

A fully generic policy engine would over-compress vendor-specific behavior and hide important ACP
differences too early.

Waiting would make later permission and session-control work harder because the duplication would
remain in the critical path.

## Consequences

- Positive:
  - less duplicated permission handling,
  - clearer split between normalization, policy, and rendering,
  - easier future integration of richer approval behavior.
- Negative:
  - one more internal model layer,
  - and a need to keep the normalized request shape narrow and compatibility-focused.
- Follow-up implication:
  - later human approval UI or operator-level approval policy should build above this normalized
    request/decision seam rather than bypassing it.
