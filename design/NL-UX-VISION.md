# NL UX Vision

## Purpose

This document specifies the design of natural language interaction with `operator`. It covers the conversational model, the operator-as-agent interface, the boundary between natural language and structured commands, ambient proactive surfacing, voice scope, and how NL interaction fits within the existing CLI and TUI surfaces.

This document is a companion to CLI-UX-VISION.md, TUI-UX-VISION.md, and WORKFLOW-UX-VISION.md. NL interaction is not a separate surface — it is an affordance layer built into and accessible from those surfaces.

This is a design specification, not an implementation guide. NL parsing mechanics, model selection, and latency handling are noted but not adjudicated here.

---

## Design Principles

**P1 — Conversation-in-context, not command parsing.**
The operator already has a brain that holds the current state of the work: the task graph, attention requests, recent decisions, operation history, and project-scope memory. When the user opens a conversation, they are talking to something that already knows what is happening. The mental model is a check-in with a project lead who has been managing the work, not issuing commands into a void.

**P2 — NL is an input method; the structured form is the contract.**
For any write operation, the system shows the exact structured command it will execute before executing it. Natural language is how the user expresses intent. The structured form is the verifiable contract. The user never needs to trust the interpretation — they can read and confirm or cancel.

**P3 — Read is always safe; write always previews.**
Natural language queries about system state require no confirmation. Natural language expressions that would change system state always require showing the structured form and receiving explicit confirmation. This boundary is inviolable.

**P4 — Dangerous operations require structured confirmation.**
For irreversible or high-impact operations (cancel, force-recover, goal replacement), natural language input is accepted for expression but a structured confirmation is required. The system says: "I understood you want to cancel op-abc123. To confirm, run: `operator cancel op-abc123`" — and does not execute unless the structured command is issued or the user types the operation ID.

**P5 — Ambient without noise.**
The operator brain may surface low-urgency observations to the user without blocking progress. These ambient observations are subject to a high threshold: only surfaced when confidence is high and the observation is operationally relevant. The brain does not narrate its internal state. Ambient observations are distinct from typed attention requests (`AttentionRequest` with `AttentionType`) — they do not require user action and are not stored as `AttentionRequest` records.

**P6 — NL does not replace transparency.**
A user who prefers structured commands can ignore the NL layer entirely. Every NL interaction has an equivalent structured CLI command. The NL layer adds convenience and expressiveness; it does not create a separate path to system state that bypasses CLI observability.

---

## Mental Model: Talking to the Operator

The operator has an LLM brain. That brain is used for planning, decomposition, delegation, evaluation, and deciding the next move. The same brain can respond to user questions and interpret user intent — not as a secondary chatbot bolted on top, but as a first-class use of the brain's existing context.

When the user initiates a conversation with the operator, the brain loads:
- the current operation's goal and task graph,
- active and recent attention requests,
- the operator's most recent planning decisions,
- project-scope and operation-scope memory entries,
- and recent operation history from the ledger.

With that context loaded, the brain can answer questions like:
- "What are you currently working on?"
- "Why did you assign the auth task to Codex instead of Claude?"
- "What would you do next if you weren't blocked?"
- "Have you seen this kind of decision before in this project?"

The brain can also interpret expressions of intent:
- "Use a branch for that" → resolves to a specific attention answer
- "Stop the codex task and give it a different goal" → resolves to an interrupt + message sequence, shown for confirmation

This is the operator-as-agent model: the user and the operator brain are in dialogue about the work, not the user issuing commands and the system executing them silently.

---

## What `operator message` Is and Is Not

`operator message OP TEXT` (from CLI-UX-VISION.md) injects a durable message into the operation's brain context. It persists for the configured message window. It is a one-way channel: user → operation.

Conversational NL is a different channel with different semantics:

| Channel | Direction | Persistence | Use |
|---------|-----------|-------------|-----|
| `operator message OP TEXT` | User → operation | Durable (survives turns) | Injecting standing guidance into the brain's planning context |
| Conversational NL | Bidirectional | Ephemeral (session only) | Interactive dialogue — questions, attention responses, goal adjustments |

These are not substitutes. A user who wants the operator to remember something across planning cycles uses `operator message`. A user who wants to discuss the current state and potentially act on it uses the conversational interface.

When a conversational NL exchange results in a write action (an attention answer, a goal adjustment, a pause), the action is injected through the same structured channels as the equivalent CLI command — the NL session is a front-end, not a separate execution path.

---

## Entry Points

### CLI: `operator converse [OP]`

```
operator converse [OP]
  [--project PROFILE]
  [--context full|brief]
```

Opens an interactive conversational session with the operator brain. When `OP` is supplied, the brain loads that operation's full context. Without `OP`, the brain loads fleet-level context: all active operations, their current states, and any open attentions.

The session is a REPL-style interface: the user types in natural language, the brain responds in natural language, and write operations surface the structured preview before executing.

```
$ operator converse op-abc123

Operator › op-abc123 · RUNNING · iter 14/100 · 1 blocking attention
────────────────────────────────────────────────────────────────────
> What are you stuck on?

The codex task is waiting on a policy decision: whether to commit
changes directly to main or use a feature branch. I've asked before
for similar operations and you said to use a branch (see policy
p-7f3a from 2026-03-28). Should I apply that same policy here?

→ Proposed action: operator answer att-7f2a --text "use a branch"
   Execute? [y/N/edit] _
```

The session shows an `→ Proposed action:` line for any write operation before executing. The user may:
- `y` — execute as shown
- `N` — cancel
- `edit` — open `$EDITOR` to modify the structured command before execution

The session ends with `Ctrl-D`, `quit`, or `exit`.

### TUI: `n` key — Inline Conversation Panel

At any level of the TUI (Fleet View, Operation View, Session View), pressing `n` opens an inline conversation panel in the right pane. The panel loads context for the currently selected item:

- Fleet View: fleet-level context (all active operations)
- Operation View: the selected operation's context
- Session View: the selected task's session context

The panel replaces the current right-pane content; pressing `n` again or `Esc` closes it and restores the previous view.

```
┌─ breadcrumb ──────────────────────────────────────────────────────────┐
│ fleet > op-codex-1                                                     │
├─ left pane (30 cols) ─┬─ right pane ───────────────────────────────────┤
│                       │ ┌─ conversation ──────────────────────────────┐ │
│  [RUNNING]            │ │ > why is the integration test blocked?      │ │
│  ▶ auth session  [!!] │ │                                             │ │
│  ▶ unit tests         │ │ The integration test (task-2c8a5f) depends  │ │
│                       │ │ on the auth session runner (task-3a7f) and  │ │
│  [READY]              │ │ the codex adapter (task-7b3f). Neither is   │ │
│  ○ codex adapter      │ │ complete yet.                               │ │
│                       │ │                                             │ │
│  [BLOCKED]            │ │ > _                                         │ │
│  ◐ integration tests  │ └─────────────────────────────────────────────┘ │
│     ↳ 3a7f2b, 7b3f1e  │                                               │
└───────────────────────┴───────────────────────────────────────────────┘
│ n: close conversation · y/N: confirm action if proposed               │
```

---

## The NL / Structured Command Boundary

### The Rule

The boundary is defined by **confirmation semantics**, not by action type:

| Operation type | NL handling | Confirmation required |
|----------------|-------------|----------------------|
| Read / query | NL with no confirmation | None — brain answers directly |
| Write with canonical structured form | NL with structured preview | Show exact command; require `y` |
| Write without canonical form (novel state change) | NL with structured preview of proposed change | Show proposed state diff; require `y` |
| Irreversible / dangerous | NL accepted for expression; structured required for execution | User must issue structured command or type operation ID |

### Ambiguous NL

When the user's NL expression maps to more than one plausible structured command, the brain presents options — numbered, each with the full structured form — and waits for the user to select:

```
> stop the failing task

I found two tasks that might be failing:
  1. operator interrupt op-abc123 --task task-3a7f  (auth session, currently blocked)
  2. operator interrupt op-abc123 --task task-9e1c  (unit tests, exit code 1)

Which did you mean? [1/2/cancel] _
```

The brain does not pick silently when ambiguous.

**TUI disambiguation:** In the TUI inline conversation panel, numbered disambiguation lists accept digit keys (`1`, `2`, …) for selection. The key binding bar shows `[1–N: select] [Esc: cancel]` when a disambiguation list is active. Pressing `Esc` cancels without selecting.

### Compound NL Commands

When the user's NL expression requires multiple structured commands in sequence, the brain shows all of them in order before executing:

```
> stop the codex task and give it a goal about error handling instead

→ Proposed sequence:
  1. operator interrupt op-abc123 --task task-3a7f
  2. operator message op-abc123 "New goal for task-3a7f: focus on error handling in the auth session runner"

Execute all? [y/N/step-by-step] _
```

`step-by-step` walks through each command individually, pausing for confirmation at each step. *Note: `step-by-step` mode is available only in `operator converse` (CLI REPL). The TUI conversation panel supports only `y` (execute all) and `N` (cancel all) for compound command sequences.*

### Where NL Goes Far Enough

The following NL expressions are fully supported in scope:

- `use a branch` (in conversation about a policy_gap attention)
- `pause the operation` → `operator pause op-abc123`
- `what's blocking this?` → query, no action
- `run a quick check on the auth module` → `operator run "check the auth module" --project default`
- `cancel it` (in conversation about a specific operation) → requires type-to-confirm (see P4)

### Where NL Stops

Natural language is not accepted as the sole input for:
- `operator cancel OP` — user must confirm with the operation ID
- `operator debug recover OP` — structured command required, NL can explain but not execute
- policy revocation — NL may explain the intent but `operator policy revoke POLICY-ID` must be issued

These limits exist because the structured form's specificity is the safety mechanism, not just a convenience convention.

**PM system writes:** Mid-operation PM ticket updates (e.g., "update the Linear ticket to say we're making progress") are not supported via natural language. Per WORKFLOW-UX-VISION.md Design Principle 1, operator writes to PM systems only on terminal state. Natural language requests to update tickets mid-operation are declined with an explanation: *"I can only post to the ticket when the operation completes. Use `operator message` to inject context for the brain's next planning cycle instead."*

---

## Operator Proactive Surfacing — Ambient Tier

### Three-Tier Signal Model

The existing attention system has two tiers (from TUI-UX-VISION.md):
- `[!!N]` — blocking: operation cannot proceed without user input
- `[!N]` — non-blocking: informational, operation continues

Natural language interaction introduces a third tier:
- `[~N]` — ambient observation: low-urgency brain observation, no action required

**Naming note:** The `[~N]` tier is called an *ambient observation*, not an "ambient attention." It is distinct from the typed `AttentionRequest` model (`AttentionType.POLICY_GAP`, `AttentionType.DOCUMENT_UPDATE_PROPOSAL`, etc.). Ambient observations do not have an `AttentionType`, are not stored as `AttentionRequest` records, and do not require a response. They require a separate lightweight domain model (e.g., `AmbientObservation` with `text`, `operation_id`, `created_at`, `dismissed: bool`). Existing typed attention requests such as `document_update_proposal` are non-blocking (`[!N]`) — not ambient (`[~N]`).

### Ambient Observation

An ambient observation is a brain-generated informational entry that meets all three criteria:
1. **High confidence** — the brain is not guessing; it has a specific, grounded observation
2. **Operationally relevant** — the observation bears on the current goal or user intent
3. **Not yet surfaced** — the same observation has not been surfaced in this operation

Examples of valid ambient observations:
- "The same file I'm relying on for context was significantly changed since I last read it"
- "This pattern of iteration looks similar to op-def456 which hit iteration limit — you may want to check in"
- "A policy from a previous operation may apply here: [policy X]. I haven't applied it automatically."

Examples that do not meet threshold (not surfaced):
- Commentary on the brain's current reasoning process
- Confidence updates ("I'm 70% sure this approach is right")
- Questions the user hasn't asked

Ambient observations are displayed in the TUI as a `[~N]` badge (dim, neutral style — distinct from `[!N]` yellow and `[!!N]` red). They are visible in the right pane of the selected item at Operation View level. They do not interrupt the flow. The user can dismiss or ignore them — no response is required.

In the CLI, `operator status OP` shows ambient observations in a dedicated section below blocking and non-blocking attentions.

### Who Initiates

Both directions are supported:

**User-initiated:** The user opens a conversation at any time with `operator converse` or the TUI `n` key. The brain is always ready to respond.

**Operator-initiated:** The brain surfaces ambient observations autonomously when the threshold criteria above are met. Ambient observations are lower urgency than non-blocking attentions — they carry no badge propagation to ancestors in the TUI (they are visible only at the operation level, not at the fleet level).

The distinction matters: blocking and non-blocking attentions propagate upward (fleet view shows them). Ambient observations do not propagate — the user sees them when they zoom into the operation, not from fleet level. This prevents ambient observations from polluting the fleet-level signal.

**Transparency trade-off:** VISION.md §Transparency Principle 5 requires that users can see "what the operator decided." Ambient observations intentionally do not propagate to the fleet level — a user monitoring only at fleet level will not see them. This is a deliberate trade-off: high-volume ambient observations at fleet level would degrade the clarity of the fleet signal. Users who want full transparency can monitor at operation level or use `operator ask` to query the brain directly. This is an acknowledged partial relaxation of Principle 5 for the ambient tier specifically.

---

## Relationship to CLI and TUI

NL interaction is not a third surface. It is an affordance built into the existing surfaces:

| Surface | NL entry point | Scope |
|---------|---------------|-------|
| CLI | `operator converse [OP]` | Operation or fleet context; REPL session |
| CLI | `operator ask OP "QUESTION"` | Single-shot query; no write operations |
| TUI | `n` key (any level) | Context of currently selected item |

`operator ask OP "QUESTION"` is the non-interactive form — useful in scripts or quick terminal use. It runs a single query against the brain and prints the response. It is read-only by design: no write operations are available in `ask` mode.

**Note on `OP` requirement:** Unlike `operator converse [OP]` where `OP` is optional (omitting it loads fleet-level context), `operator ask` requires a specific operation ID. Fleet-level single-shot queries are not supported via `operator ask` — use `operator converse` (interactive, supports fleet context) or `operator status` / `operator fleet` for structured fleet output. If `ask` is used frequently for fleet queries without an operation context, a `operator ask --fleet "question"` form may be warranted as a follow-on.

```
$ operator ask last "what was the last decision the brain made?"
Planning cycle 14: decided to continue the auth session runner task.
Codex had partial progress; estimated completion within 1–2 more cycles.
Confidence: high. No reallocation warranted.
```

### Key Binding Summary

| Surface | Key / Command | Action |
|---------|---------------|--------|
| CLI | `operator converse [OP]` | Open interactive NL session |
| CLI | `operator ask OP "..."` | Single-shot NL query (read-only) |
| TUI (any level) | `n` | Open inline conversation panel |
| TUI (any level) | `n` again or `Esc` | Close conversation panel |
| TUI conversation | `y` | Confirm proposed action (or execute all in a compound sequence) |
| TUI conversation | `N` | Cancel proposed action (or cancel all in a compound sequence) |
| TUI conversation | `1`–`9` | Select from numbered disambiguation list (when ambiguous NL) |
| TUI conversation | `Esc` | Cancel disambiguation selection |

### What Changes in the Existing CLI

`operator converse` and `operator ask` are new primary commands. They appear in the primary commands section of `--help`:

```
operator converse [OP]    Talk to the operator brain about the current state
operator ask OP "..."     Single query to the brain (read-only, non-interactive)
```

No existing CLI commands change semantics. NL interaction is additive.

### Additions Required in CLI-UX-VISION.md

The following additions to `CLI-UX-VISION.md` follow from this document:

| Addition | Section in CLI-UX-VISION.md |
|----------|-----------------------------|
| `operator converse [OP]` as a primary command | Primary commands |
| `operator ask OP "..."` as a primary command | Primary commands |
| Ambient observation `[~N]` tier in `operator status` output | `operator status OP` specification |
| `operator converse` and `operator ask` as Known Open Items | Known Open Items |

---

## Conversational Session Properties

### Ephemeral by Default

A conversational session does not persist as an operation artifact. The user's questions and the brain's responses are not written to the event log or the history ledger. The session is a read-and-interpret layer over the existing persistent state.

**Exception:** when a conversational session results in a write operation (an attention answer, a message, a pause), the write is persisted through the normal operation channels — the attention answer appears in the event log, the message is durably injected. The NL session is the input method; the structured operation is the durable record.

### Context Loading

The brain loads context for a conversational session from:
- Current operation state (task graph, attention requests, scheduler state)
- Operation-scope and project-scope memory entries
- Recent domain events (last N events from the event log)
- Operation history ledger entries for this project (recent N operations)

The context is loaded at session start and refreshed between exchanges if the operation state changes (e.g., a blocking attention is answered mid-conversation). The brain is aware of state changes during the session.

### Response Character

The brain's responses in conversation are:
- **Grounded in current state** — the brain answers from what it knows, not what it imagines
- **Brief by default** — conversational responses are concise; the user can ask follow-up questions
- **Explicit about uncertainty** — when the brain doesn't know, it says so rather than inventing
- **Actionable when relevant** — if the user's question implies a possible action, the brain proposes it with a structured preview

---

## Voice

The conversational model is voice-compatible by construction. The brain's responses are already natural language; rendering them as speech is a transport-layer change, not a model change. The attention answer workflow maps to: hear the question, say your answer, confirm by voice or `y`.

Voice implementation specifics — speech-to-text, text-to-speech, wake-word model, push-to-talk vs. always-on microphone, latency handling for long responses — are out of scope for this document and are deferred to a future Voice-UX addendum.

This document does not preclude voice. Nothing in the model requires a keyboard.

---

## Relationship to Existing Documents

| Concern | Document |
|---------|----------|
| Structured CLI commands | CLI-UX-VISION.md |
| TUI views, badge system, key bindings | TUI-UX-VISION.md |
| Project/workspace model, history ledger, PM integration | WORKFLOW-UX-VISION.md |
| Conversational NL, operator-as-agent, NL/structured boundary | This document |

The four documents are non-overlapping by design. NL-UX-VISION.md does not respecify CLI commands or TUI layout — it specifies the NL affordances that sit on top of those surfaces.

---

## Known Open Items

- `operator converse [OP]` — new CLI command implementation; REPL loop, context loading, structured preview rendering
- `operator ask OP "..."` — single-shot NL query command; read-only; print response and exit
- TUI `n` key — inline conversation panel; right pane replacement; context-scoped to selected item
- Ambient observation tier `[~N]` — new lightweight domain model (`AmbientObservation`); display in TUI at operation level only (no fleet-level badge propagation); dismiss mechanism required
- Confirmation fatigue mitigation — for dangerous operations (cancel, force-recover), require user to type the operation ID rather than `y`; document this in the confirmation UX spec
- Ambiguity resolution protocol — when NL expression maps to N > 1 structured commands; numbered list with full structured forms; no silent disambiguation
- Brain context loading spec — what exactly is loaded for a conversational session; interface contract between the NL session handler and the brain; particularly: which memory scopes, how many history entries, refresh interval during session
- Compound command sequencing — `step-by-step` mode for multi-step NL commands; implementation in REPL loop
- `[~N]` badge rendering — TUI badge system extension; ambient badge style (dim, neutral) to distinguish from `[!N]` (yellow) and `[!!N]` (red)
