# TUI UX Vision

## Purpose

This document specifies the design of the `operator` multi-operation terminal user interface (TUI). It covers the view hierarchy, information shown at each level, navigation model, key bindings, the signal system, and the extension path for nested operator hierarchies (`operator_acp`).

This is a design specification, not an implementation guide. Implementation technology choices (Rich vs Textual, rendering details) are noted but not adjudicated here.

---

## Design Principles

1. **Zoom is navigation** — the interface is the same at every level; what changes is what you are supervising. Whether you are looking at operations, tasks, agent sessions, or sub-operators, the structure is: left pane (items at current level) + right pane (detail of selected item).

2. **Badge propagation is the signal system** — an action required anywhere in the tree surfaces upward to every ancestor, all the way to the fleet level. The user always knows where attention is needed without exploring the tree.

3. **Left pane never disappears** — the navigation anchor is always visible. No full-screen modals that cut the user off from the fleet.

4. **Action available without full drill-down** — the user can answer a blocking attention request from Fleet View without entering Operation View. They never have to navigate three levels deep just to type a response.

5. **Forensic depth is available but not imposed** — raw transcripts (Level 3) require explicit navigation. They never appear unsolicited.

---

## View Hierarchy

```
Level 0  Fleet View          ← startup; all operations; top-level triage
  │
  └── Level 1  Operation View    ← one operation's task board + agent status
        │
        └── Level 2  Session View    ← one task's agent session timeline
              │
              └── Level 3  Raw Transcript  ← forensic; full-screen; q to exit
```

For `operator_acp`, sub-operators nest in the left pane under their parent operation. Navigating into a sub-operator opens its Operation View — same structure, one level deeper in the breadcrumb.

---

## Screen Structure

```
┌─ breadcrumb ──────────────────────────────────────────────────────────┐
│ fleet > op-codex-1 > task-3a7f2b1c                                    │
├─ left pane (30 cols) ─┬─ right pane (remaining) ──────────────────────┤
│                       │                                               │
│  Navigation context   │  Detail for selected item                     │
│  (items at current    │                                               │
│   zoom level)         │                                               │
│                       │                                               │
├───────────────────────┴───────────────────────────────────────────────┤
│ status bar: 5 ops · [!!2] blocking · [!3] non-blocking · [?] help     │
└───────────────────────────────────────────────────────────────────────┘
```

**Breadcrumb** — single line, always visible, shows the full zoom path from fleet to current level.

**Status bar** — single line, always visible: total operations, total blocking attention count, total non-blocking count, current key bindings hint.

---

## Signal System

Two badge tiers prevent alert fatigue:

- `[!!N]` — **blocking attention** (bold, red) — requires user action before the operation or task can proceed. The operation is in `NEEDS_HUMAN` state.
- `[!N]` — **non-blocking attention** (dim, yellow) — informational; the operation continues without user action.

Badge propagation: every ancestor of an item with open attention requests shows an aggregate badge count. The user starts at fleet level; the badges show them a path to wherever action is needed.

```
fleet > op-root [!!3]
  └─ oper-A [!!2]
       └─ oper-B [!!2]
            └─ task-xyz [!!2]  ← 2 blocking attentions here
```

`Tab` at any level jumps to the next item with a `[!!]` blocking badge, allowing the user to triage all blocking attentions without visiting every operation.

**Auto-selection ordering:** when `a` is pressed and multiple blocking attentions exist, the oldest is selected first (creation time ascending). If multiple blocking attentions remain after answering, the next-oldest is shown. The count of remaining blocking attentions is displayed after each answer.

---

## Level 0 — Fleet View

**Entry:** startup, or `Esc` from any deeper level.
**Breadcrumb:** `fleet`

### Empty state

When no operations are active (fleet is empty, or all operations have reached terminal state), the fleet view shows:

- Left pane: `No active operations. Run 'operator run [goal]' to start.`
- Right pane: blank
- Breadcrumb: `fleet`
- `q` quits; all other navigation keys are no-ops.

### Left pane — Operations list

```
 ● op-codex-1    [!!1][!1]  RUNNING
     └─ oper-sub [!!1]      RUNNING
 ◐ op-claude-2              RUNNING
 ⚫ op-arch-3    [!!1]      NEEDS_HUMAN
 ✓ op-docs-4                COMPLETED
 ✗ op-auth-6                FAILED
 ⊘ op-test-7                CANCELLED
 ○ op-test-5                RUNNING
```

Each line: status glyph + operation name + badges (if any) + macro-status.

Sub-operators are indented with `└─` under their parent operation.

**Status glyphs:**

| Glyph | Meaning |
|-------|---------|
| `●` | running (attached) |
| `◐` | running (background / resumable) |
| `⚫` | needs_human — blocking attention open |
| `✓` | completed |
| `✗` | failed |
| `⊘` | cancelled |
| `○` | running (low activity / waiting) |

### Right pane — OperationBrief of selected item

```
op-codex-1  ·  RUNNING
Objective:  Refactor auth module and add test coverage
Progress:   iter 14/100  ·  started 2h 14m ago
Tasks:      2 running  ·  3 ready  ·  1 blocked  ·  4 completed
Agent:      codex-acp  →  task-3a7f2b1c "auth session runner"

Blocking attention [!!1]:
  policy_gap: "Should I commit directly to main?"
  → operator answer op-codex-1 att-7f2a --text "use a branch"

Non-blocking [!1]:
  novel_strategic_fork: "Add OAuth2 or keep JWT?"
```

For terminal-state operations (failed or cancelled), the right pane shows the outcome summary instead:

```
op-auth-6  ·  FAILED
Objective:  Refactor auth module and add test coverage
Stop reason:  iteration_limit_exhausted  ·  ended 3h 12m ago
Iterations:   100/100 completed
Tasks:        2 completed  ·  1 failed  ·  3 not started
```

```
op-test-7  ·  CANCELLED
Objective:  Add integration test suite
Stop reason:  user_cancelled  ·  ended 1h 05m ago
Iterations:   14/100 completed
Tasks:        1 completed  ·  4 not started
```

### Key bindings — Fleet View

| Key | Action |
|-----|--------|
| `↑` `↓` | move selection |
| `Enter` | zoom into selected operation (Level 1) |
| `Tab` | jump to next item with `[!!]` blocking attention |
| `a` | answer oldest blocking attention of selected operation (creation time ascending) |
| `p` / `u` | pause / unpause selected operation |
| `c` | cancel selected operation |
| `/` | filter by name, status, or agent |
| `?` | show help overlay |
| `q` | quit |

### Confirmation behavior for destructive actions

Pressing `c` (cancel) at Fleet View opens an inline confirmation bar at the bottom of the screen:

```
Cancel op-arch-3 (auth module refactor)? [y/n]  _
```

Pressing `y` executes the cancel. Pressing any other key (including `n` or `Esc`) aborts without action. This is consistent with CLI P7 (destructive commands confirm).

---

## Level 1 — Operation View

**Entry:** `Enter` from Fleet View on an operation.
**Breadcrumb:** `fleet > op-codex-1`

### Left pane — Task board

Tasks grouped by status. `[BLOCKED]` is a display alias for `PENDING` tasks that have at least one dependency not yet completed — it is a presentation grouping, not a distinct lifecycle state. Note: `[BLOCKED]` refers to task dependency blocking, distinct from `OperationStatus.NEEDS_HUMAN` (operation-level blocking awaiting human response to an attention request).

```
[RUNNING]
 ▶ 3a7f2b1c [!!1]  auth session runner
 ▶ 9e1c4d2a        auth unit tests

[READY]
 ○ 7b3f1e9d        codex adapter

[BLOCKED]
 ◐ 2c8a5f3b        integration tests
     ↳ 3a7f2b1c, 7b3f1e9d

[COMPLETED]
 ✓ a1d4e7c2        domain model setup
```

### Right pane — Task detail of selected task

```
task-3a7f2b1c  ·  auth session runner
Agent:   codex-acp  ·  sess-8f2a
Status:  RUNNING  ·  iter 14  ·  started 40m ago
Goal:    Implement the ACP session runner for auth tokens

Latest:  "Writing the token refresh handler. ~15min to go."

Blocking attention [!!1]:
  policy_gap — "Should I commit directly to main?"
  → operator answer op-codex-1 att-7f2a --text "use a branch"
```

The right pane can be switched to alternate views with single keys while keeping the task selected in the left pane:

- default: task detail (as above)
- `d`: latest DecisionMemo — the brain's reasoning for the most recent planning cycle
- `t`: event log — recent events in chronological order (simplified timeline)
- `m`: memory entries for this task

### Key bindings — Operation View

| Key | Action |
|-----|--------|
| `↑` `↓` | move task selection |
| `Enter` | zoom into agent session (Level 2) |
| `Tab` | jump to next task with `[!!]` blocking attention |
| `a` | answer oldest blocking attention for selected task (creation time ascending) |
| `p` / `u` | pause / unpause operation |
| `s` | interrupt current agent turn for selected task |
| `d` | show DecisionMemo in right pane |
| `t` | show event log in right pane |
| `m` | show memory entries in right pane |
| `Esc` | zoom out to Fleet View |
| `?` | help overlay |
| `q` | quit |

---

## Level 2 — Session View

**Entry:** `Enter` from Operation View on a running task.
**Breadcrumb:** `fleet > op-codex-1 > task-3a7f2b1c`

### Left pane — Recent session events (newest first)

```
 14:32  ▸ agent output (partial)
 14:31  ● brain decision: continue
 14:28  ▸ agent output (partial)
 14:20  ⚠ attention opened: policy_gap
 14:15  → agent started: codex-acp
 14:00  ◆ task assigned
```

**Event glyphs:**

| Glyph | Meaning |
|-------|---------|
| `▸` | agent event (output, progress) |
| `●` | brain decision |
| `⚠` | attention request |
| `→` | session lifecycle (start, stop, recover) |
| `◆` | task lifecycle (assigned, completed, failed) |

### Right pane — Event detail of selected event

```
[14:32]  agent output (partial)
codex-acp  ·  sess-8f2a

"I've implemented the token refresh handler.
 auth/session.py updated. Moving to validation."

Changes (cumulative):
  auth/session.py   +120  -8
  tests/test_auth.py  +45

Artifacts: none yet
```

### Key bindings — Session View

| Key | Action |
|-----|--------|
| `↑` `↓` | move event selection |
| `Enter` | expand event detail in right pane |
| `r` | open raw transcript (Level 3) |
| `Esc` | zoom out to Operation View |
| `?` | help overlay |
| `q` | quit |

---

## Level 3 — Raw Transcript

**Entry:** `r` from Session View.
**Breadcrumb:** `fleet > op-codex-1 > task-3a7f2b1c > sess-8f2a [raw]`

Full-screen scrollable log of raw agent transcript. Content: same as `claude-log op-id` / `codex-log op-id`. `q` or `Esc` returns to Session View.

---

## operator_acp — Hierarchy Extension

A sub-operator is an item in the left pane indented under its parent operation. It uses the same glyph set as an operation. It is navigated with the same `Enter` / `Esc` zoom model. No new paradigm is required.

### Left pane with sub-operator

```
 ● op-root     [!!3]  RUNNING
     └─ oper-A [!!2]  RUNNING
 ◐ op-other          RUNNING
```

Navigating into `oper-A` opens its Operation View:

```
breadcrumb: fleet > op-root > oper-A
left pane:  oper-A's task board
right pane: selected task detail
```

### Depth cap

At 3+ levels of nested operators, the left pane shows only the direct children of the current zoom level — not the full subtree. The breadcrumb carries the full path. Ancestors are accessible via repeated `Esc`.

**Example at depth 4:**

```
breadcrumb: fleet > op-root > oper-A > oper-B > task-xyz
left pane:  tasks of oper-B  (oper-B's task board)
right pane: detail of task-xyz
```

The user is never "lost" because the breadcrumb always shows the full path and `Esc` always moves one level up.

### Badge propagation through operators

A blocking attention anywhere in the subtree of a sub-operator propagates up through every ancestor to the fleet level. The user at fleet level sees the aggregate — they do not need to know which sub-operator it came from to know that the operation needs attention.

---

## Consolidated Key Binding Map

| Key | Fleet | Operation | Session |
|-----|-------|-----------|---------|
| `↑` `↓` | move selection | move selection | move event |
| `Enter` | zoom in | zoom in | expand event |
| `Esc` | — (already root) | zoom out → Fleet | zoom out → Operation |
| `Tab` | next `[!!]` item | next `[!!]` task | — |
| `a` | answer blocking att | answer for selected task | — |
| `p` / `u` | pause / unpause | pause / unpause | — |
| `c` | cancel op | — | — |
| `s` | — | interrupt agent turn for task | — |
| `d` | — | DecisionMemo in right | — |
| `t` | — | event log in right | — |
| `m` | — | memory entries in right | — |
| `r` | — | — | raw transcript |
| `/` | filter | filter | — |
| `?` | help overlay | help overlay | help overlay |
| `q` | quit | quit | quit |

No binding conflicts. All action keys are named by user intent.

---

## Relationship to Existing CLI Commands

The TUI is an interactive shell over the same application layer. All actions route through the same `_enqueue_command_async` and service paths as the existing CLI commands.

| Existing command | TUI equivalent |
|---|---|
| `watch op-id` | Level 1 Operation View (live) |
| `fleet` | Level 0 Fleet View |
| `dashboard op-id` | Level 1 right pane (rich variant) |
| `tasks op-id` | Level 1 left pane task board |
| `trace op-id` | `t` key at Level 1 (event log); full trace at Level 2 |
| `claude-log` / `codex-log op-id` | Level 3 Raw Transcript |
| `answer att-id "..."` | `a` key at Fleet or Operation level |
| `interrupt op-id [--task TASK]` | `s` key at Level 1 |
| `pause` / `unpause op-id` | `p` / `u` at Fleet or Operation level |

---

## Live Refresh Model

- **Mechanism:** polling loop at 500ms default (`--poll-interval` flag), reading operation state files — consistent with the existing `watch` and `fleet` implementations
- **Multi-op cost:** one file-read pass per cycle across all N operations; at N=8 and 500ms, ≤8 reads per cycle — acceptable
- **Framework path:** the existing `rich.live.Live` foundation supports the TUI. The recommended upgrade path for full keyboard focus management and reactive widget layout is **Textual** (Rich-based), which retains compatibility with the existing rendering code
- **Event-driven future:** when the `WakeupInbox` / `asyncio.Event` model is exposed to the CLI layer, the refresh cycle can be event-triggered instead of polled, eliminating unnecessary cycles

---

## Known Open Items

- **`[BLOCKED]` display alias** — specified here as a group header in the Level 1 left pane; the existing `tasks` CLI currently shows raw `[pending]` status. This spec is the design target; the implementation gap is tracked separately.
- **`watch` TTY format** — the existing `watch` output (`state: running | scheduler=active | ...`) does not match this spec's primary view format. This TUI replaces `watch` as the preferred live surface; the existing command remains for non-TTY and pipe use.
- **Textual migration** — the current CLI uses Rich directly. Migrating to Textual is required for keyboard focus management between left and right panes. This is an implementation prerequisite, not a design question.
- **`n` key (inline conversation panel)** — NL conversation affordance specified in NL-UX-VISION.md; requires adding `n` to all key binding tables and implementing the right-pane panel replacement.
- **`[~N]` ambient observation badge** — a third badge tier introduced in NL-UX-VISION.md (dim, neutral style); visible at operation level only, does not propagate to fleet level. Requires TUI badge rendering extension.

## Roadmap

The following features are designed but depend on architecture not yet implemented:

- **`operator_acp` hierarchy** — sub-operators nested in the fleet view left pane, cross-hierarchy badge propagation, depth-capped navigation. Depends on the `operator_acp` architecture (operator-as-sub-operator). The design is specified in this document; implementation waits on `operator_acp`.
