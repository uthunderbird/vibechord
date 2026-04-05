# ADR 0043: Claude ACP Effort Via Thinking Token Env

## Status

Accepted

## Context

`operator` already exposed named `effort` levels for the `claude_code` adapter, but `claude_acp` only supported model and permission mode.

The locally installed `@zed-industries/claude-code-acp` adapter does not expose a named ACP RPC for effort. Instead, it reads `MAX_THINKING_TOKENS` from the subprocess environment and passes that through to Claude Code options as `maxThinkingTokens`.

We still want a consistent operator-facing knob for Claude ACP runs, especially for long research loops where users already think in terms of `low` / `medium` / `high` / `max`.

## Decision

Expose `claude_acp.effort` in operator settings and map it inside the adapter to subprocess env `MAX_THINKING_TOKENS`.

The mapping is an operator-local heuristic:

- `none` -> `0`
- `low` -> `1024`
- `medium` -> `4096`
- `high` -> `16384`
- `max` -> `32768`

This is explicitly not a claim that Claude ACP has a native named effort setting. The named effort is translated by `operator` into a thinking-token budget before the ACP subprocess starts.
Leaving `effort` unset still means "do not set `MAX_THINKING_TOKENS` at all"; this is different from `effort=none`, which explicitly requests zero thinking tokens.

## Alternatives Considered

- Do not support effort for `claude_acp` at all.
- Require users to set `MAX_THINKING_TOKENS` manually outside operator.
- Invent a non-existent ACP RPC such as `session/set_effort`.

## Consequences

- Positive: users can request `claude_acp` effort levels through the same operator surface they already use for other adapters.
- Positive: implementation stays grounded in the actual `claude-code-acp` behavior we observed locally.
- Negative: the mapping is heuristic and may need retuning if upstream Claude ACP or Claude Code changes its thinking-token behavior.
- Negative: `claude_acp` effort remains less semantically direct than `claude_code --effort`, so docs and code should avoid overclaiming equivalence.
