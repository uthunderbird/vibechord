# ADR 0192: Attached-mode blocking attention inline wait

- Date: 2026-04-17

## Decision Status

Accepted

## Implementation Status

Verified

Implementation grounding on 2026-04-23:

- `implemented`: blocking attention creation sets `NEEDS_HUMAN` plus
  `FocusKind.ATTENTION_REQUEST`, which is the discriminator for an answerable attached-mode pause
- `implemented`: the attached drive loop now stays alive for
  `NEEDS_HUMAN + ATTENTION_REQUEST`, draining commands and sleeping in-process until the answer
  arrives
- `implemented`: answering the last blocking attention marks the operation back to `RUNNING` and
  clears the attention focus so the outer loop can continue
- `implemented`: live attached CLI output now prints an explicit `operator answer ... --text "..."`
  hint when blocking attention opens and prints `Answer received. Resuming...` when that command is
  applied
- `verified`: dedicated drive-loop, answer-resolution, legitimate-exit discriminator, and CLI
  regression tests cover the current repository truth
- `verified`: targeted closure tests passed on 2026-04-23:
  `tests/test_decision_execution_service.py::test_request_clarification_creates_blocking_attention_request`,
  `tests/test_operation_drive_service.py::test_attached_mode_inline_waits_on_blocking_attention_until_answered`,
  `tests/test_operation_command_service.py::test_answer_attention_request_seeds_snapshot_only_attention_before_answering`,
  `tests/test_agent_result_service.py::test_rate_limited_agent_blocks_operation_for_cooldown_without_retrying`,
  and `tests/test_cli.py::test_run_streams_blocking_attention_wait_and_resume_messages`
- `verified`: full `pytest -q` passed on 2026-04-23 at the repository state that accepts this ADR
  (`892 passed, 11 skipped`)

## Context

ADR 0008 defines attached mode as the preferred runtime model and says the process should stay
alive until the objective completes, fails, or reaches a real blocked state.

ADR 0057 applies that principle to background waits: when attached mode is blocked on a background
agent turn, the process does not exit. It stays alive, drains commands, sleeps, and resumes when
new evidence arrives.

Blocking attention requests need the same lifecycle treatment. A blocking attention request is a
transient human-answerable pause, not a terminal exit condition. The architectural problem is to
keep attached mode alive for answerable blocking attention while still allowing legitimate
`NEEDS_HUMAN` exits such as evaluation-stop or session cooldown/wakeup cases.

## Decision

In attached mode, when `state.status` becomes `NEEDS_HUMAN` and
`state.current_focus.kind` is `FocusKind.ATTENTION_REQUEST`, the attached drive loop does not
exit. It stays alive, drains the command inbox, sleeps for 1 second between polls, and re-enters
the main loop once the blocking attention has been answered.

### Discriminator for legitimate exit vs inline wait

| `state.status` | `current_focus.kind` | Correct behavior |
| --- | --- | --- |
| `NEEDS_HUMAN` | `ATTENTION_REQUEST` | Inline wait until answered |
| `NEEDS_HUMAN` | anything else (or `None`) | Exit |

### Repository implementation

- `src/agent_operator/application/decision_execution.py:239-250` marks blocking attention as
  `NEEDS_HUMAN` and sets `current_focus` to `FocusKind.ATTENTION_REQUEST`
- `src/agent_operator/application/drive/operation_drive.py:392-409` performs the attached-mode
  inline wait loop for `NEEDS_HUMAN + ATTENTION_REQUEST`
- `src/agent_operator/application/commands/operation_commands.py:856-875` appends the answered
  attention to `pending_attention_resolution_ids`, calls `mark_running(state)` when the last
  blocking attention is answered, and clears matching attention focus
- `src/agent_operator/cli/rendering/text.py:624-639` renders the attached live-output wait hint
  and the resume acknowledgement

### UX behavior

In current repository truth, attached CLI output:

1. prints `Attention needed: <title>. Run: operator answer <operation-id> <attention-id> --text "..."`
   when a blocking attention request opens
2. polls every 1 second, draining the command inbox
3. prints `Answer received. Resuming...` when `answer_attention_request` is applied
4. remains interruptible because the wait loop uses `anyio.sleep(1.0)` and does not swallow
   cancellation

### `operator resume` is not the answer

There is no IPC channel between a live attached process and a second `operator resume` invocation.
Running `operator resume` while an attached process is alive starts a concurrent drive loop
against the same state file, risking write conflicts. The correct command to unblock a waiting
attached process is `operator answer <operation-id> <attention-id> --text "..."`.

## Alternatives Considered

### Make `resume` signal the live process

Rejected: no IPC infrastructure exists, and `operator answer` already uses the command inbox that
the attached loop is polling.

### Exit and require manual resume

Rejected: this recreates the exact "keep resuming it" anti-pattern ADR 0008 was written to avoid.

## Consequences

- Positive: attached `operator run` now stays alive through blocking attention, matching the ADR
  0008 product contract
- Positive: background waits and blocking-attention waits now share the same
  `drain-commands + sleep` lifecycle pattern
- Positive: no new IPC layer is required; the command inbox remains the unblock mechanism
- Negative: `operator resume` remains unsafe against a live attached owner process and must not be
  used as the unblock path
- Follow-up implication: attached-loop `break` and early-return sites still need periodic audit so
  only terminal states, explicit interrupts, or genuinely unresolvable blocks can exit attached
  mode

## Closure Evidence Matrix

| ADR line / closure claim | Repository evidence | Verification |
| --- | --- | --- |
| Blocking attention must become `NEEDS_HUMAN + ATTENTION_REQUEST` | `src/agent_operator/application/decision_execution.py:239-250` | `tests/test_decision_execution_service.py::test_request_clarification_creates_blocking_attention_request` |
| Attached mode must inline-wait instead of exiting on blocking attention | `src/agent_operator/application/drive/operation_drive.py:392-409` | `tests/test_operation_drive_service.py::test_attached_mode_inline_waits_on_blocking_attention_until_answered` |
| Answering the blocking attention must unblock the loop and resolve the request | `src/agent_operator/application/commands/operation_commands.py:856-875`; `src/agent_operator/application/commands/operation_commands.py:504-552` | `tests/test_operation_command_service.py::test_answer_attention_request_seeds_snapshot_only_attention_before_answering` |
| Non-attention `NEEDS_HUMAN` remains a legitimate attached-mode exit | `src/agent_operator/application/drive/operation_drive.py:416-420` | `tests/test_agent_result_service.py::test_rate_limited_agent_blocks_operation_for_cooldown_without_retrying` |
| Attached CLI must show explicit wait/resume guidance | `src/agent_operator/cli/rendering/text.py:624-639` | `tests/test_cli.py::test_run_streams_blocking_attention_wait_and_resume_messages` |
| Current repository state is verified, not inferred | this ADR document plus the implementation above | `pytest -q tests/test_decision_execution_service.py -k test_request_clarification_creates_blocking_attention_request`; `pytest -q tests/test_operation_drive_service.py -k test_attached_mode_inline_waits_on_blocking_attention_until_answered`; `pytest -q tests/test_operation_command_service.py -k test_answer_attention_request_seeds_snapshot_only_attention_before_answering`; `pytest -q tests/test_agent_result_service.py -k test_rate_limited_agent_blocks_operation_for_cooldown_without_retrying`; `pytest -q tests/test_cli.py -k test_run_streams_blocking_attention_wait_and_resume_messages`; `pytest -q` |
