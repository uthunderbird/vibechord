# ADR 0004: Adopt ACP As The Codex Integration Boundary

## Status

Accepted

## Historical note

This ADR remains correct about ACP as the Codex integration boundary, but its references to the
session-oriented `AgentAdapter` contract are historical. Current public runtime truth is defined by
ADR 0081, ADR 0082, ADR 0083, and ADR 0089.

## Context

`operator` needs a programmatic way to drive Codex as an external agent.

An earlier design direction assumed a terminal-driven integration using `tmux`. That approach is workable as a spike, but it has the wrong abstraction level for a long-lived operator runtime:

- it depends on terminal behavior rather than an explicit protocol,
- it weakens cancellation and session semantics,
- it makes progress detection heuristic,
- it is brittle under UI or formatting changes,
- and it pushes transcript parsing into the adapter as a primary control mechanism.

We now have a better integration target: `codex-acp`.

`codex-acp` exposes Codex as an ACP agent over stdio, with explicit concepts for:

- session creation and loading,
- prompt submission,
- progress notifications,
- permission requests,
- cancellation,
- and structured stop reasons.

This is much closer to the lifecycle that `operator` already wants from `AgentAdapter`.

## Decision

`operator` will adopt ACP as the primary and only planned integration boundary for Codex.

Concretely:

- the Codex adapter direction is `CodexAcpAgentAdapter`,
- that adapter will communicate with `codex-acp` as a subprocess over ACP stdio transport,
- `tmux` will be removed from the planned architecture rather than retained as a fallback,
- and Codex-specific protocol handling will be localized inside the ACP adapter.

The operator core will continue to depend only on the stable session-oriented `AgentAdapter` contract.

## Alternatives Considered

### Option A: Keep `tmux` as the main integration

Pros:

- simple spike path
- no additional protocol client work

Cons:

- terminal scraping is brittle
- weaker state semantics
- poorer observability and cancellation
- harder to test reliably

### Option B: Keep `tmux` as a fallback

Pros:

- offers a backup path if ACP is temporarily blocked

Cons:

- preserves a second architectural path we do not want to maintain
- encourages accidental coupling to a lower-quality integration
- adds code and testing burden before any release exists

### Option C: Adopt ACP and remove `tmux`

Pros:

- matches the session-oriented adapter model well
- gives structured progress and stop signals
- reduces terminal-specific brittleness
- aligns better with future extensibility

Cons:

- requires implementing an ACP client path in Python
- depends on `codex-acp` availability in the user environment

## Consequences

- `tmux` is no longer part of the Codex roadmap for this project.
- Documentation, config, and future adapter work should refer to ACP rather than terminal control.
- A future Codex adapter should model ACP sessions directly and normalize ACP notifications into `AgentProgress` and `AgentResult`.
- Claude Code remains separate and CLI-based until a comparably mature protocol surface exists for it.
