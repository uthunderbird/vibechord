# ADR 0056: ACP SDK stdio reader limit

## Status

Accepted

## Context

Claude ACP background runs could fail during `session/prompt` with transport errors such as
`Separator is found, but chunk is longer than limit`.

The root cause was not in the operator session model. It was in the ACP Python SDK stdio transport:

- the SDK transport ultimately uses an `asyncio.StreamReader`,
- its stdio helper accepts a configurable `limit`,
- and the operator was not setting that limit, so large ACP payload lines could overflow the default
  reader bound.

For Claude ACP this was especially visible on large prompt or update payloads and could wrongly look
like a fatal agent/runtime failure.

## Decision

Set an explicit stdio reader limit for SDK-backed ACP subprocess transports and make it configurable
per ACP adapter.

The chosen default is:

- `stdio_limit_bytes = 1_048_576` (`1 MiB`)

The operator now:

- exposes `stdio_limit_bytes` on `claude_acp` and `codex_acp` adapter settings,
- passes that limit to `AcpSdkConnection`,
- and `AcpSdkConnection` forwards it to the ACP SDK `spawn_stdio_transport(..., limit=...)`.

This change applies only to the SDK-backed ACP substrate path. The bespoke subprocess ACP path is
unchanged.

## Alternatives Considered

- Keep the SDK transport on the default asyncio limit
- Hard-code a larger limit inside the SDK vendor package
- Increase the limit only for Claude ACP and not expose configuration
- Rewrite prompt/update framing instead of raising the reader limit

## Consequences

- Positive consequence: large ACP stdio chunks are much less likely to disconnect Claude ACP sessions
  for transport reasons alone.
- Positive consequence: the limit remains adjustable through adapter settings if `1 MiB` proves too
  small or unnecessarily large.
- Negative consequence: SDK-backed ACP transports can now buffer larger single chunks in memory.
- Negative consequence: this hardening does not fix every ACP disconnect class; it only addresses the
  reader-limit family.
