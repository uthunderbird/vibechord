# ADR 0074: Bridge-slice cleanup after process-manager and planning-trigger integration

## Status

Accepted

## Context

[`ADR 0072`](./0072-process-manager-policy-boundary-and-builder-assembly.md) and
[`ADR 0073`](./0073-command-bus-and-planning-trigger-semantics.md) were implemented as a deliberate
bridge slice on top of the current snapshot-based `OperatorService`.

That implementation landed the intended architectural direction:

- process-manager behavior is now code-assembled and policy-bounded
- planning triggers are durable and inspectable
- `accepted_pending_replan` and `pending_replan_command_ids` were removed from current runtime
  truth

At the same time, the bridge exposed and partly increased several kinds of technical debt that
should not remain implicit.

### Observed debt classes

1. **Bridge-only seams inside `OperatorService`**

   The current service now contains an internal `ProcessManagerSignal` bridge model and planning
   trigger draining logic, but the overall runtime is still snapshot-first rather than fully
   event-sourced.

   This is intentional for the bridge slice, but it means some code paths now mix:

   - snapshot mutation
   - bridge signals
   - planning-trigger bus usage
   - partial future-facing boundaries from RFC 0009

2. **Legacy compatibility aliases still present in runtime models**

   To keep the service running while landing the bridge, compatibility shims remain, for example:

   - legacy-style session/background fields mapped onto newer session/execution state
   - service assumptions translated through aliases rather than fully removed

   These shims are useful only as temporary migration aids. Leaving them in place too long would
   blur the actual state model.

3. **Unrelated pre-existing service drift surfaced during the bridge**

   The implementation work uncovered older inconsistencies that are not conceptually part of
   `ADR 0072` or `ADR 0073`, but currently live in the same service layer, for example:

   - status-name drift such as `BLOCKED` vs `NEEDS_HUMAN`
   - runtime-option drift such as older `supports_background_waits` assumptions vs
     `background_runtime_mode`
   - trace event emission paths that relied on outdated event-shape assumptions

4. **Verification is strong for the new slice, but not yet repository-wide**

   The bridge slice is covered by targeted tests and type/lint checks, but that is not the same as
   saying the full repository is now cleanly aligned.

   Current truth:

   - `implemented`: the new bus/process-manager/planning-trigger slice exists
   - `verified`: the new slice has dedicated tests and checks
   - `partial`: full-repository cleanup and full-suite convergence are not yet complete

### Why this needs its own ADR

Without an ADR, this debt can be hand-waved as "temporary" indefinitely.

That would be dangerous because:

- bridge seams tend to fossilize
- compatibility aliases tend to become invisible dependencies
- unrelated service drift tends to stay bundled into future feature work instead of being retired
  explicitly

This ADR therefore records the cleanup obligation as a real architectural follow-up rather than an
informal intention.

## Decision

The repository will treat the post-`0072`/`0073` bridge debt as a first-class cleanup program with
its own closure criteria.

### Cleanup goals

The cleanup work should:

- remove temporary compatibility aliases introduced or retained only to land the bridge slice
- reduce bridge-only logic inside `OperatorService` where a lower-level contract already exists
- align current runtime terminology and status handling with the accepted ADR/RFC set
- raise verification from targeted-slice confidence to repository-wide confidence where practical
- keep bridge-only artifacts out of domain public exports and package-level API

### Specific cleanup targets

#### 1. Retire temporary runtime aliases

Examples:

- remove legacy session/background lifecycle aliases once the service fully speaks in
  session/execution terms
- avoid keeping compatibility properties that only preserve older service assumptions

#### 2. Normalize service terminology and status handling

Examples:

- no remaining `BLOCKED` vs `NEEDS_HUMAN` drift
- no remaining older runtime flag semantics when a newer canonical option already exists
- no event-emission paths that depend on outdated event schema assumptions

#### 3. Make bridge boundaries easier to remove later

Examples:

- `ProcessManagerSignal` moved to `agent_operator.application.process_signals` and removed from `agent_operator.domain` public export surface
- avoid letting bridge constructs become quasi-domain models
- keep planning-trigger handling isolated enough that later migration to canonical domain-event
  inputs is straightforward

#### 4. Expand verification before calling the bridge fully stable

Required direction:

- full repository tests should pass before declaring this cleanup program complete
- targeted bridge tests are necessary but not sufficient

### Non-goal

This ADR does **not** reopen `ADR 0072` or `ADR 0073`.

It does not question:

- process-manager policy boundaries
- planning-trigger semantics
- the shared control-intent bus

Those decisions remain accepted.

This ADR is only about retiring the transitional debt left around them.

## Consequences

- The repository has an explicit record that the current bridge is not the desired final shape.
- Future contributors can distinguish accepted architectural direction from temporary transitional
  compromises.
- Cleanup work can be tracked to completion and then this ADR can move to `Accepted`.
- If the bridge debt is not retired, the repo risks re-creating a god-object service under a newer
  vocabulary.

## Closure Notes

- Legacy command enqueue compatibility for command-shell expectations (`tmp/commands/*.json` containing
  `command_type`, `command_id`, and command payload fields) was preserved while the new durable control
  intent bus remains authoritative for service processing.
- `FileOperationCommandInbox` and bootstrap wiring now keep command writes and planning-trigger writes
  in separate durable roots (`commands` and `control_intents` respectively), removing the implicit coupling
  introduced by the bridge integration.
- Full repository tests are now passing:
  - `274 passed`
  - `11 skipped`

## Alternatives Considered

### Treat the debt as ordinary backlog with no ADR

Rejected. The debt affects runtime boundaries and architectural truth, not just implementation
polish.

### Reopen ADR 0072 and ADR 0073 instead

Rejected. The accepted decisions themselves are not the problem; the remaining transitional seams
around their implementation are.

### Ignore the debt until RFC 0009 is fully implemented end-to-end

Rejected. That would allow temporary bridge mechanics to harden into permanent architecture.
