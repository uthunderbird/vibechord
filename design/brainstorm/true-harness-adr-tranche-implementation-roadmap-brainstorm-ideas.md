# True Harness ADR Tranche Implementation Roadmap Brainstorm Ideas

## Status

Brainstorm only. Not implementation truth.

## Scope

This note turns the current proposed ADR tranche into an implementation order:

- ADR 0013
- ADR 0014
- ADR 0015
- ADR 0016
- ADR 0017
- ADR 0018
- ADR 0019

The goal is to identify the order that preserves honest runtime behavior and avoids building a
polished UI on top of missing control semantics.

## Guiding Rule

Build control-plane substrate before high-level surfaces.

In practice, that means:

- command truth before TUI commands
- scheduler state before pause UI
- attention objects before attention dashboards
- profile resolution before project UX polish
- and policy memory after attention + involvement semantics exist

## Recommended Implementation Order

### Phase 1: command substrate

Implement:

- `OperationCommand`
- `OperationCommandType`
- `CommandTargetScope`
- `CommandStatus`
- file-backed `OperationCommandInbox`
- CLI submission path for a very small command set

Target ADRs:

- ADR 0013
- enough of ADR 0014 to make reducer boundaries real

Recommended first commands:

- `pause_operator`
- `resume_operator`
- `stop_operation`
- `patch_harness`
- `inject_operator_message`

Why first:

- this creates the real live intervention substrate
- and gives attached mode something to drain

### Phase 2: deterministic reducer boundary

Implement:

- explicit reducer-shaped command application path
- command acceptance / rejection / `accepted_pending_replan`
- provenance in `inspect` and `trace`

Target ADR:

- ADR 0014

Why now:

- without it, command inbox remains only a storage idea

### Phase 3: scheduler state and attached pause

Implement:

- scheduler-state field on operation truth
- `active`
- `pause_requested`
- `paused`
- `draining`
- command draining during `_collect_attached_turn(...)`
- honest live surfaces for pause status

Target ADR:

- ADR 0015

Why before attention and TUI:

- because pause semantics are the first real proof that the harness is live-controllable

### Phase 4: attention model and answer routing

Implement:

- `AttentionRequest`
- `AttentionType`
- `AttentionStatus`
- blocking vs non-blocking flag
- `answer_attention_request`
- explicit link from `BLOCKED` to open attention ids

Target ADR:

- ADR 0016

Why here:

- now the operator can both receive commands and ask for help in a typed way

### Phase 5: involvement levels

Implement:

- `InvolvementLevel`
- runtime field on operation state
- reducer support for `set_involvement_level`
- first control-plane behaviors for:
  - `unattended`
  - `auto`
  - `collaborative`
  - `approval_heavy`

Target ADR:

- ADR 0017

Why after attention:

- because involvement policy needs a real attention model to act on

### Phase 6: project profiles

Implement:

- `ProjectProfile`
- YAML profile discovery/loading
- resolved effective run configuration model
- `--project` / `project inspect` / `project resolve`

Target ADR:

- ADR 0018

Why after live-control substrate:

- profiles are valuable, but they do not fix runtime truth problems

### Phase 7: policy memory

Implement:

- `PolicyEntry`
- explicit promotion workflow
- links from resolved attention items or commands to policy provenance
- revocation / supersession basics

Target ADR:

- ADR 0019

Why last in this tranche:

- because policy memory depends on real attention, answers, and involvement semantics
- otherwise it becomes vague prompt sludge or accidental persistence

## What Should Wait Until After This Tranche

These should not lead the implementation order:

- rich TUI/dashboard work
- branch-aware multi-session live surgery
- complex project templating
- broad policy-matching automation

They depend on the substrate above.

## Minimal Strong Milestone

The smallest milestone that would prove the tranche is real looks like:

1. start attached run
2. send `pause_operator` while an attached turn is active
3. see `pause_requested` in `inspect`
4. send `inject_operator_message`
5. see it acknowledged and later reflected in replanning
6. operator raises typed `AttentionRequest`
7. user answers via `answer_attention_request`
8. operator replans from explicit answer truth

If that works, the harness is no longer just a loop with nicer logs.

## Working Conclusion

The correct order is:

1. command inbox
2. command reducer boundary
3. scheduler state and pause
4. attention requests and answer routing
5. involvement levels
6. project profiles
7. policy memory

That order preserves the architectural rule that product surfaces should follow control-plane
truth, not invent it.
