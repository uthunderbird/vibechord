# ADR 0154: patch_* command CLI surface

- Date: 2026-04-13

## Decision Status

Accepted

## Implementation Status

Verified

## Context

The domain already defines three goal-mutation command types in
`src/agent_operator/domain/enums.py`:

```python
class OperationCommandType(str, Enum):
    ...
    PATCH_OBJECTIVE = "patch_objective"
    PATCH_HARNESS = "patch_harness"
    PATCH_SUCCESS_CRITERIA = "patch_success_criteria"
```

The application layer in `operation_commands.py` handles these types in the command-dispatch
path. The CLI option infrastructure in `cli/options.py` already defines
`--success-criteria` and `--clear-success-criteria` option helpers.

However, no CLI commands expose `patch_objective`, `patch_harness`, or
`patch_success_criteria` to the user. The only way to issue a patch command today is through
the generic hidden `operator command` dev surface — which requires knowing the raw enum string
and payload format.

### Vision reference

VISION.md §Goal-patching commands:

> `patch_objective "..."` — replace the objective text while the operation is running.
> `patch_harness_instructions "..."` — update the harness instructions for the operator and
> agent path.
> `patch_success_criteria "..."` — revise the completion criteria.
>
> These are collectively referred to as `patch_*` commands. They route to the operation inbox,
> are accepted or rejected deterministically, and take effect at the next brain planning decision.

VISION.md §v2 Early Success Criteria item 2: "explicit pause / resume / stop semantics" — the
pause/resume/stop family is implemented; the patch family is the remaining gap in the live
command surface.

### Rejection conditions (from VISION.md)

A patch command must be rejected:
- with `operation_terminal` if the operation has already reached `TERMINAL` state,
- with `invalid_payload` if the payload is empty or structurally malformed,
- with `concurrent_patch_conflict` if a conflicting patch on the same field is already pending
  in the inbox.

## Decision

Expose the three patch command types as first-class CLI verbs in
`src/agent_operator/cli/commands/operation_control.py`:

```
operator patch-objective  <operation-ref> <text>
operator patch-harness    <operation-ref> <text>
operator patch-criteria   <operation-ref> [--criteria TEXT]... [--clear]
```

### CLI contract

All three commands:
- accept `operation-ref` (short or full UUID, same resolution as `operator ask`),
- submit the command via the existing delivery-command path,
- print the command acknowledgement (accepted / rejected-with-reason) to stdout,
- exit 0 on acceptance, exit 1 on rejection.

`patch-criteria` accepts `--criteria TEXT` (repeatable) to set one or more criteria strings
and `--clear` to empty the list. This reuses the existing `options.py` helpers.

### Domain events

No new event types are required. The existing `command.applied` event (emitted by the
command-dispatch path) covers patch commands. The brain reads the updated objective/harness/
criteria at its next planning cycle from the projected state.

### Rejection responses

The CLI must surface the rejection reason clearly:

```
Error: patch rejected — operation_terminal (operation has already completed)
```

## Consequences

- Users can live-patch the objective, harness, or success criteria of a running operation
  without restarting it.
- The v2 live control surface is complete: pause, resume, stop, answer, message, and patch
  are all first-class CLI verbs.
- No domain or application changes are required — only a CLI layer addition.

## Prerequisites for resolution

1. Verify that `operation_commands.py` correctly applies `PATCH_OBJECTIVE`, `PATCH_HARNESS`,
   and `PATCH_SUCCESS_CRITERIA` payloads to `OperationState` (read and confirm, do not assume).
2. Add CLI commands to `operation_control.py`.
3. Add tests for acceptance and each rejection condition
   (`operation_terminal`, `invalid_payload`, `concurrent_patch_conflict`).

## Related

- `src/agent_operator/domain/enums.py` — `OperationCommandType`
- `src/agent_operator/application/commands/operation_commands.py` — patch dispatch
- `src/agent_operator/cli/commands/operation_control.py` — target for new CLI verbs
- `src/agent_operator/cli/options.py` — reusable criteria option helpers
- [VISION.md §Goal-patching commands](../VISION.md)
