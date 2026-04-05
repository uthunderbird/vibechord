# ADR 0034: Standard Coding Agent Tool Capabilities

## Status

Accepted

## Context

`operator` already treats adapters as capability-bearing targets, but current adapter descriptors
only expose coarse transport facts such as `acp`, `follow_up`, or `headless`.

That is too weak for coding-agent orchestration. The operator brain needs a stable, adapter-agnostic
way to reason about the practical tool surface of a coding agent, especially when choosing between
Codex- and Claude-based integrations for repository work.

Without a shared tool vocabulary:

- the brain has to infer coding power from adapter names,
- prompts cannot state tool availability explicitly,
- and adapter capability declarations remain too vague to guide routing.

## Decision

Adopt a small standard coding-agent tool capability taxonomy and expose it through
`AgentDescriptor.capabilities`.

The first standard coding tool set is:

- `read_files`
- `write_files`
- `edit_files`
- `grep_search`
- `glob_search`
- `run_shell_commands`

Coding-oriented adapters should declare this standard set in `describe()`, alongside any
adapter-specific capabilities such as `acp`, `follow_up`, or `headless`.

The operator runtime should also surface the available agent descriptors as persisted operation
context so both the brain prompt and CLI control views can reason from declared tool truth instead
of adapter-name folklore.

## Alternatives Considered

- Keep only coarse adapter capabilities like `acp` and `headless`.
- Infer tool availability from adapter key names inside the prompt.
- Add a richer typed tool schema with categories and argument contracts immediately.

## Consequences

- Positive: the brain receives a stable, adapter-agnostic description of coding tools.
- Positive: routing can depend on declared capabilities instead of hard-coded agent names.
- Positive: `context` and `dashboard` can expose the same capability truth the brain sees.
- Positive: future adapters can conform by mapping into the same standard vocabulary.
- Negative: capability declarations remain descriptive, not enforced tool contracts.
- Negative: the first taxonomy is intentionally narrow and may need extension later.
