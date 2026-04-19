# ADR 0192: Attached-mode blocking attention inline wait

- Date: 2026-04-17

## Decision Status

Proposed

## Implementation Status

Planned

## Context

ADR 0008 defines the attached run as the preferred runtime mode and says the process should stay
alive until the objective is complete, failed, or "a real blocked state" is reached.

ADR 0057 extends this for background-run waits: when the attached loop is blocked on a background
agent turn, it does not exit — it polls via a `drain-commands + sleep` loop until the turn
completes.

A symmetrical gap exists for blocking attention requests.

When a blocking attention request fires (e.g. the permission evaluator escalates, the brain opens
an `APPROVAL_REQUEST`, or an agent result returns `agent_waiting_input`), the current code at
`operation_drive.py:388-392` breaks the attached loop unconditionally and returns. The attached
process exits. The user is left with no running process and must manually run `operator resume`
to continue — the exact "keep resuming it" anti-pattern ADR 0008 was written to prevent.

This is a UX regression from the intended contract. Blocking attention in attached mode is a
transient human-answerable pause, not a terminal exit condition.

### Evidence

- `operation_drive.py:388-392`: unconditional `break` on `NEEDS_HUMAN` regardless of run mode
- `operation_commands.py:880-886`: `_apply_answer_attention_request` calls
  `mark_running(state)` when the last blocking attention is answered — the polling loop can use
  this to detect unblock
- `decision_execution.py:239`: blocking attention always sets `current_focus` to
  `FocusKind.ATTENTION_REQUEST` — this discriminates the blocking-attention case from the
  evaluation-stop case
- `drive.py:415`: `mark_needs_human` from evaluation does not set an attention request or
  `ATTENTION_REQUEST` focus — this case IS a legitimate exit

## Decision

In attached mode, when `state.status` becomes `NEEDS_HUMAN` and `state.current_focus.kind` is
`FocusKind.ATTENTION_REQUEST`, the attached drive loop does not exit. It enters a `drain-commands
+ sleep` polling loop, identical in structure to the background-run wait loop at
`operation_drive.py:273-278`.

The loop exits when `_drain_commands` processes an `ANSWER_ATTENTION_REQUEST` command, which
calls `mark_running(state)` and flips `state.status` back to RUNNING. The outer loop then
re-enters via `continue`.

### Discriminator for legitimate exit vs inline wait

| `state.status` | `current_focus.kind` | Correct behavior |
|---|---|---|
| `NEEDS_HUMAN` | `ATTENTION_REQUEST` | Inline wait (poll until answered) |
| `NEEDS_HUMAN` | anything else (or None) | Exit (evaluation-stop or disconnect-recovery path) |

### Implementation sketch

```python
# operation_drive.py, replacing lines 388-392
if state.status is OperationStatus.NEEDS_HUMAN:
    await self._trace._record_iteration_brief(state, iteration, task)
    await self._trace._sync_traceability_artifacts(state)
    await self._advance_checkpoint(state)
    if (
        options.run_mode is RunMode.ATTACHED
        and state.current_focus is not None
        and state.current_focus.kind is FocusKind.ATTENTION_REQUEST
    ):
        # Stay alive and poll — operator answer will arrive via command inbox
        while state.status is OperationStatus.NEEDS_HUMAN:
            await self._control._drain_commands(state)
            if state.status is not OperationStatus.NEEDS_HUMAN:
                break
            await self._advance_checkpoint(state)
            await anyio.sleep(1.0)
        continue  # re-enter main loop
    break
```

The polling loop must remain interruptible — AnyIO cancellation propagates through `anyio.sleep`.

### UX behavior

When the attached loop enters the blocking-attention wait, the CLI should:

1. Print an inline message: `"Attention needed: [title]. Run: operator answer <id> \"...\""`
2. Poll every 1 second, draining the command inbox
3. On answer arrival: print "Answer received. Resuming..." and continue
4. Ctrl-C exits normally at any time

### `operator resume` is not the answer

There is no IPC channel between a live attached process and a second `operator resume` invocation.
Running `operator resume` while an attached process is alive starts a concurrent drive loop
against the same state file, risking write conflicts. The correct command to unblock a waiting
attached process is `operator answer <attention-id> "..."`.

## Alternatives Considered

### Make `resume` send a signal to the live process

Rejected: no IPC infrastructure exists. Building it would add significant complexity for a use
case already covered by `operator answer`. The answer command already enqueues into the command
inbox; the polling loop reads from that same inbox.

### Exit and require manual resume (current behavior)

Rejected: this violates the ADR 0008 contract and creates the exact "keep resuming it" pattern
that attached mode was designed to prevent.

## Consequences

- Positive: `operator run` in attached mode now stays alive through blocking attention — the
  intended user experience from ADR 0008.
- Positive: the `drain-commands + sleep` pattern is consistent across background-run waits and
  blocking-attention waits.
- Positive: no new IPC infrastructure required; the existing command inbox is sufficient.
- Negative: `operator resume` must not be run concurrently with a live attached process; this
  constraint must be documented and ideally enforced or warned.
- Follow-up implication: all `break` and early-return points in the attached drive loop should be
  audited to confirm they fall into a legitimate exit category (terminal state, user interrupt,
  or genuinely unresolvable block). Any break that fires on a state resolvable by human command
  input is a UX regression.
- Follow-up implication: a progress indicator or periodic refresh should be added to the wait
  loop so users can confirm the attached process is still alive.
