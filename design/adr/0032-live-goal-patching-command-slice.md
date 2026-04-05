# ADR 0032: Live Goal-Patching Command Slice

## Status

Accepted

## Context

The accepted command inbox and deterministic command reducer already give the operator a durable
live-control path for:

- pause and resume,
- stopping the active attached turn,
- involvement changes,
- human answers,
- policy promotion,
- and freeform operator messages.

But the current product still leaves one high-value control-plane gap.

When a running operation needs a corrected objective or updated definition of success, the user
can currently:

- cancel and restart the run,
- inject a freeform operator message and hope the next plan interprets it correctly,
- or patch only the harness instructions.

That is weaker than the rest of the persisted control plane because the operator's core business
target remains partly implicit instead of being authoritatively editable.

The repo also already treats objective, harness instructions, and success criteria as distinct
persisted fields in operation state and prompt construction.

## Decision

`operator` will ship a bounded live goal-patching slice through the existing command inbox.

The accepted first slice adds deterministic command support for:

- `patch_objective`
- `patch_harness`
- `patch_success_criteria`

Semantics:

- `patch_objective` replaces the persisted objective text for the operation.
- `patch_harness` replaces the persisted harness instructions.
- `patch_success_criteria` replaces the entire persisted success-criteria list.
- an empty `patch_success_criteria` payload explicitly clears the list.
- each accepted patch is recorded deterministically, marks the command
  `accepted_pending_replan`, and becomes `applied` once a new operator decision incorporates the
  changed goal state.

The same bounded slice also adds a `run --success-criterion ...` CLI override so launch-time goal
truth and live goal-edit truth use the same explicit fields.

This slice does not add arbitrary constraint editing.

## Alternatives Considered

- Option A: rely on `inject_operator_message` for all live goal corrections
- Option B: add bounded deterministic goal-patching commands
- Option C: broaden immediately to generic `patch_constraints`

Option A was rejected because it leaves the business target interpretive instead of authoritative.

Option B was accepted because it closes the most important product gap without widening the command
surface beyond what the current runtime can explain and test cleanly.

Option C was rejected because generic constraint mutation introduces a larger payload design and
validation problem than this slice needs.

## Consequences

- Running operations gain an explicit way to correct what the operator is trying to achieve.
- Goal edits remain visible in the same command, inspect, trace, watch, and dashboard surfaces as
  other control-plane actions.
- Success criteria now have one consistent explicit shape at launch time and at live-edit time.
- Arbitrary constraint patching remains follow-up work and should get its own ADR if pursued.
