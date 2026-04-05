# ADR 0036: Live Constraint-Patching Command Slice

## Status

Accepted

## Context

The live-command architecture now supports deterministic control for:

- scheduler changes (`pause_operator`, `resume_operator`)
- one attached turn interruption (`stop_agent_turn`)
- involvement updates (`set_involvement_level`)
- goal edits (`patch_objective`, `patch_harness`, `patch_success_criteria`)
- attention handling and policy operations.

The next practical control gap is execution constraints that already steer operator behavior:

- which adapter keys may be used (`allowed_agents`)
- how many iterations may run (`max_iterations`)

These values currently require run restart or risky freeform messaging to change and are frequently
needed during active intervention.

## Decision

`operator` will add `patch_constraints` as a bounded deterministic command on the existing command
path.

The accepted command supports:

- `allowed_agents`: replaces the full persisted allowed-agent list
- `max_iterations`: replaces the persisted maximum iteration limit

Rules:

- at least one of the two fields must be present
- `allowed_agents` must be a non-empty list of non-empty strings when provided
- `max_iterations` must be a positive integer when provided
- accepted commands are marked `accepted_pending_replan`, replayed as part of normal command finalization,
  and surfaced through existing control-plane inspection surfaces (`context`, `inspect`, `dashboard`, `trace`)

## Alternatives Considered

- Option A: continue requiring restart or operator messages for constraint updates

Rejected because constraints are not advisory and should not depend on implicit interpretation.

- Option B: add one-shot "stop-and-reseed" control commands for each constraint type

Rejected because this fragmenting would add complexity without adding expressive power beyond a bounded
command envelope.

- Option C: general constraints JSON patch command

Rejected because this slice is intentionally bounded; generic JSON patching increases payload risk and
inspection ambiguity without improving operator ergonomics for the first release.

## Consequences

- execution constraints are now first-class, persistently mutable state during a live operation
- deterministic mutation path stays aligned with existing command acceptance/replanning behavior
- existing command and control surfaces automatically expose the updated constraints via the operation context payload
