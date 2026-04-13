# ADR 0157: operator converse — NL dialogue surface

- Date: 2026-04-13

## Decision Status

Accepted

## Implementation Status

Not implemented

## Context

The CLI has structured inspection commands (`status`, `ask`, `attention`, `tasks`, `watch`)
but no conversational interface. Users who want to ask open-ended questions about an operation
or its current state must read raw output and interpret it themselves.

NL-UX-VISION.md defines `operator converse` as the primary entry point for interactive natural
language dialogue with the operator brain. The brain already holds the full operation context
at every planning cycle; `converse` makes that context available to the user interactively.

### Design principles (from NL-UX-VISION.md)

- **Read is always safe; write always previews.** NL queries about state need no confirmation.
  NL expressions that would change state always show the structured command and require explicit
  confirmation before execution.
- **Dangerous operations require structured confirmation.** For cancel, force-recover, or goal
  replacement, the system shows the structured command and does not execute unless the user
  confirms.
- **NL is distinct from `operator message`.** `operator message` injects durable context into
  the planning loop. `converse` is an ephemeral bidirectional session — questions, answers,
  goal adjustments — that routes writes through the same structured channels.

## Decision

Add `operator converse [OP]` as a new CLI command in
`src/agent_operator/cli/commands/operation_control.py`.

### CLI surface

```
operator converse [OP]
  [--project PROFILE]
  [--context full|brief]
```

- `OP` optional — when supplied, load that operation's context; when omitted, load
  fleet-level context (all active operations, open attentions).
- `--context full|brief` — controls how much operation history is assembled (default: `brief`
  for latency reasons).
- Opens a REPL-style terminal session (similar to Python's `>>>` prompt).

### Session loop

```
$ operator converse op-abc123

Operator › op-abc123 · RUNNING · iter 14/100 · 1 blocking attention
────────────────────────────────────────────────────────────────────
> <user types natural language>
```

Each turn:
1. User types a natural language expression.
2. The brain assembles current operation context + the conversation history so far.
3. Brain responds in natural language.
4. If the brain's response includes a proposed write action, the session surfaces it:

```
→ Proposed action: operator answer att-7f2a --text "use a branch"
   Execute? [y/N/edit]
```

- `y` — execute the structured command via the existing command delivery path.
- `N` — do not execute; continue the conversation.
- `edit` — open `$EDITOR` with the command pre-filled; run after edit.

The session ends with `Ctrl-D`, `exit`, or `quit`.

### Brain interface

`converse` does not add a new brain type. It reuses the existing operator brain (configured
in the operation's profile) with a modified prompt:

- system prompt describes the conversational role (question answering, intent interpretation),
- context payload includes operation state snapshot (goal, tasks, attention, recent decisions,
  memory entries),
- conversation history is maintained in-process for the duration of the session (ephemeral,
  not persisted to event log).

The brain is called synchronously per turn (no streaming in v1; streaming can be added later).

### Write action extraction

The brain is prompted to emit proposed write actions in a structured format that the session
loop can parse. The exact format (JSON in a code block, a delimiter-wrapped section, or a
structured tool call) is determined during implementation based on what the configured brain
model supports most reliably.

### Context assembly

The `--context full|brief` flag controls what is injected into the brain's context:

| Level | Contents |
|---|---|
| `brief` | Goal, current status, open attentions, last 5 iterations summary |
| `full` | + task graph, recent memory entries, last 20 iterations, recent event log |

### Fleet-level context (no OP supplied)

Brain loads: all non-terminal operations, their statuses, open attention counts, and
recent iteration counts. The user can ask "Which operation is furthest along?" or "Are
any blocked?" and get answers grounded in real state.

## Prerequisites for resolution

1. Design the brain prompt template for conversational mode.
2. Implement the REPL loop (`prompt_toolkit` or plain `input()` fallback).
3. Implement context assembly (brief and full).
4. Implement write-action extraction and preview/confirm flow.
5. Tests: read-only query returns an answer without executing commands; write proposal is
   surfaced and only executed on `y`; `N` continues the session; fleet-level mode loads
   when no OP is given.

## Non-goals

- Streaming responses (deferred to post-v1).
- Persisting conversation history across sessions.
- NL routing to background planning (separate from the live planning loop).
- TUI inline conversation panel (see ADR 0162).

## Consequences

- Users can interactively query operation state in natural language without reading raw output.
- Write operations remain safe: all mutations go through the existing structured command path.
- The NL layer is optional; users who prefer structured commands are unaffected.

## Related

- `src/agent_operator/cli/commands/operation_control.py` — target file for new command
- [NL-UX-VISION.md §CLI: operator converse](../NL-UX-VISION.md)
- [ADR 0149](./0149-nl-single-shot-query-surface.md) — `operator ask` (single-shot NL query)
