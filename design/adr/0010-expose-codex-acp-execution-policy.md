# ADR 0010: Expose Codex ACP Execution Policy Through Adapter Config

## Status

Accepted

## Context

`operator` uses `codex-acp` as the Codex integration boundary, but the first ACP adapter slice only exposed:

- command,
- model,
- reasoning effort,
- and working directory.

That was not sufficient for real long-lived work across project boundaries.

In practice, Codex turns could reach a point where they needed approval or broader sandbox access and the operator could only observe the blocker after the fact. We need a way to control Codex execution policy deliberately from `operator` rather than relying only on whatever happens to be in the user's global Codex config.

The installed `codex-acp` binary supports `-c/--config key=value` overrides for Codex runtime config, including sandbox and approval settings.

## Decision

Expose Codex execution policy through `operator`'s `codex_acp` adapter settings.

Concretely:

- add `approval_policy` to `codex_acp` settings,
- add `sandbox_mode` to `codex_acp` settings,
- and have `CodexAcpAgentAdapter` translate those settings into `codex-acp -c ...` overrides.

This keeps the operator core adapter-neutral while allowing Codex-specific runtime control to remain local to the Codex ACP adapter.

## Alternatives Considered

### Option A: Keep using only the global `~/.codex/config.toml`

Pros:

- no code changes
- minimal adapter surface

Cons:

- `operator` cannot make execution-policy choices explicitly
- live behavior depends on ambient machine config
- harder to test and reason about

### Option B: Add generic raw override strings only

Pros:

- maximum flexibility

Cons:

- weak typing
- poorer discoverability
- more likely to drift into opaque command construction

### Option C: Expose typed policy fields for the common case

Pros:

- keeps the public config contract explicit
- supports the real blocker we hit in live operation
- still allows the Codex-specific logic to stay inside the adapter

Cons:

- slightly widens the adapter config surface
- still does not model every possible Codex override

## Consequences

- `codex_acp` can now be configured for different approval and sandbox modes from `operator`.
- Live behavior becomes less dependent on ambient user config alone.
- Codex-specific execution policy remains adapter-local rather than leaking into the operator core.
- Additional Codex config overrides may still be needed later, but common execution-policy control is now first-class.
