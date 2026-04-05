# ADR 0049: Remove the direct `claude_code` adapter after ACP migration

## Status

Accepted

## Context

`operator` historically kept two Claude-facing paths:

- `claude_code` as a direct headless CLI adapter
- `claude_acp` as an ACP-backed adapter

That split was initially useful because the direct CLI path was simpler and the older Claude ACP
package had compatibility gaps. After the ACP substrate work in ADR 0048 and live verification
against `@agentclientprotocol/claude-agent-acp`, the preferred Claude path is now `claude_acp`.

Keeping both Claude adapters long-term would:

- duplicate Claude-specific policy and test surface,
- preserve unnecessary agent-selection ambiguity,
- and weaken the architectural bias toward protocol-oriented integration.

## Decision

Treat `claude_acp` as the canonical Claude integration path.

The direct `claude_code` adapter is now a legacy compatibility path and should be removed after a
bounded migration window.

Before removal, the repository should:

- prefer `claude_acp` in defaults and documentation,
- keep `claude_code` only where compatibility still requires it,
- and avoid adding new product surface area that depends specifically on `claude_code`.

Actual code deletion was gated on:

- replacement of remaining default and smoke usage that still assumes `claude_code`,
- direct runtime evidence for the `claude_acp` path under the current canonical package,
- and regression coverage for any user-visible workflows that still depend on the direct adapter.

That migration is now complete in the current repository state:

- adapter construction exposes `claude_acp` and `codex_acp`, not a direct `claude_code` adapter
- current runtime and CLI surfaces resolve Claude sessions through `claude_acp`
- remaining `claude_code` mentions are historical references, not active adapter-construction paths

## Alternatives Considered

- Keep both Claude paths indefinitely.
- Remove `claude_code` immediately.
- Keep `claude_code` as the primary path and treat `claude_acp` as optional.

## Consequences

- Positive:
  - one canonical Claude integration path
  - lower adapter and documentation duplication
  - better alignment with the ACP substrate architecture
- Negative:
  - historical documentation may still refer to the retired direct adapter and requires deliberate
    cleanup rather than silent drift
- Follow-up implication:
  - future Claude-facing work should treat `claude_acp` as the only supported Claude adapter path
