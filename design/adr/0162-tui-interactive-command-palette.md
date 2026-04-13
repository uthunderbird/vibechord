# ADR 0162: TUI interactive command palette

- Date: 2026-04-13

## Decision Status

Accepted

## Implementation Status

Not implemented

## Context

The TUI (`src/agent_operator/cli/tui/controller.py`) currently supports keyboard-driven
navigation and a limited set of in-TUI actions:

- `a` — select oldest blocking attention for the current item
- `n` — **currently: select oldest non-blocking attention** (see conflict note below)
- `p` — pause/unpause
- `answer` flow — inline text entry for answering a selected attention request
- `/` — filter input

But several write commands cannot be issued from within the TUI:

- Sending an operator message
- Cancelling an operation
- Stopping an agent turn
- Invoking `operator converse` inline (NL dialogue)
- Patching the objective or harness

TUI-UX-VISION.md defines a command palette and NL conversation panel:

> **`:`** — Command palette: opens a one-line input bar at the bottom. The user types a
> structured command or intent. Tab-completion suggests available commands.
> **`n`** — Inline conversation panel: opens a right-pane NL session for the selected item
> (see NL-UX-VISION.md §TUI inline panel).

### Key binding conflict

`n` currently selects the oldest non-blocking attention. In TUI-UX-VISION.md, `n` is reserved
for the inline NL conversation panel. This conflict must be resolved:

- **Proposed resolution:** reassign non-blocking attention navigation to `N` (shift-n) or
  to `Tab` extended (e.g., second `Tab` press cycles through non-blocking attentions). Free
  `n` for the NL panel per the vision.

## Decision

Add an interactive command palette (`:` key) to the TUI and inline NL conversation panel
(`n` key), and reassign the current `n` binding.

### 1. Command palette (`:` key)

Pressing `:` at any TUI level opens a one-line command input bar at the bottom of the screen
(footer replaces itself with an input field):

```
: _
```

The user types a command or intent. Tab-completion shows available commands for the current
context. Commands are the same verbs as the CLI (`pause`, `unpause`, `cancel`, `answer`,
`message`, `interrupt`), with the operation ID pre-filled from the selected item.

Examples:
```
: cancel                 → confirm and cancel selected operation
: message "use a branch" → inject operator message into selected operation
: patch-objective "..."  → update goal of selected operation
: answer att-abc "yes"   → answer specific attention request
```

On Enter: the command is parsed, previewed in a confirmation bar, and executed on `y`.
On Escape: the palette closes without executing.

#### Completion
- The palette knows the current selected operation ID — commands that require an operation ID
  are pre-populated.
- Attention IDs are tab-completed from the open attention list of the selected operation.

### 2. Inline NL conversation panel (`n` key)

Pressing `n` opens the right pane as an NL conversation panel, backed by the same brain
session as `operator converse` (ADR 0157).

Context loaded based on current zoom level:
- Fleet View: fleet-level context
- Operation View: selected operation context
- Session View: selected task's session context

The panel is a scrollable chat view. The user types at the bottom prompt line. Write proposals
from the brain appear with a `→ Proposed:` line and `[y/N/edit]` confirmation.

The panel remains open until `Escape`, which returns to the previous right-pane content.

### 3. Key binding reassignment

| Old key | Old action | New key | Rationale |
|---|---|---|---|
| `n` | Select oldest non-blocking attention | `N` (shift) | Free `n` for NL panel per vision |

The `N` binding is backward-compatible with users who use shift — it replaces an absent binding.
The `n` binding changes are a deliberate breaking change in TUI ergonomics, justified by the
vision alignment.

### 4. Footer update

The footer line updates to show the palette key:

```
Enter open · Tab next-attn · a answer · : command · n converse · ? help
```

## Prerequisites for resolution

1. ADR 0157 (operator converse) implemented — the NL session logic is reused.
2. Reassign `n` → non-blocking attention navigation to `N`.
3. Implement `:` command palette: input bar, tab completion, preview-and-confirm flow.
4. Implement `n` NL panel: right-pane NL session view, brain call, write proposal flow.
5. Update footer bindings display.
6. Tests: `:` opens palette; Escape closes without executing; `n` opens panel; `N` selects
   non-blocking attention (regression test for old `n` behavior under new key).

## Non-goals

- Textual framework migration (the TUI remains Rich-based; this adds features to the existing
  controller structure).
- Full command-line syntax in the palette (the palette is for common operations; complex
  multi-flag commands should use the CLI).

## Consequences

- Users can perform all common write operations without leaving the TUI.
- The NL panel provides a context-aware conversational shortcut without switching to a separate
  terminal session.
- The `n` key binding change may surprise existing TUI users — document in changelog.

## Related

- `src/agent_operator/cli/tui/controller.py` — key handler target
- `src/agent_operator/cli/tui/rendering.py` — footer and pane rendering
- [TUI-UX-VISION.md](../TUI-UX-VISION.md)
- [NL-UX-VISION.md §TUI: Inline Conversation Panel](../NL-UX-VISION.md)
- [ADR 0157](./0157-operator-converse-nl-dialogue-surface.md)
