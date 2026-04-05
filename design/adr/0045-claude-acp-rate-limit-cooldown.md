# ADR 0045: Claude ACP Rate Limit Cooldown

## Status

Accepted

## Context

Claude ACP can fail with a provider-side rate-limit message such as `Internal error: You've hit your limit · resets 1am (Asia/Almaty)`.

Before this change, operator treated that the same as any other generic agent failure. In practice that caused immediate reuse attempts against the same Claude session, which is wasteful and can spiral into repeated failed turns while the provider cooldown is still active.

## Decision

When Claude ACP returns a recognized rate-limit failure, operator now:

- classifies it as `claude_acp_rate_limited`,
- records a session-level cooldown window,
- blocks the operation on that session until the cooldown expires,
- and refuses to resume normal scheduling for that blocked session before the cooldown deadline.

The default cooldown is one hour when no more precise retry window is available from the error payload.

## Alternatives Considered

- Treat rate limits as ordinary failures and let the brain decide what to do next.
- Immediately start a replacement Claude session after rate-limit failure.
- Convert rate-limit failures into attention requests that require manual user action.

## Consequences

- Positive: operator stops hammering a rate-limited Claude worker and preserves the session for later reuse.
- Positive: blocked state now reflects a real external gate instead of looking like an ordinary failed proof or implementation step.
- Negative: some runs will remain blocked until a manual `resume` after cooldown expiry, rather than opportunistically trying again earlier.
- Follow-up: if Claude ACP later exposes structured retry-after metadata, operator can refine the cooldown window beyond the current one-hour default.
