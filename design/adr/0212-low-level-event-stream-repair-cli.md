# ADR 0212: Low-level event stream repair CLI

- Date: 2026-04-23

## Decision Status

Accepted

## Implementation Status

Verified

Implementation grounding on 2026-04-24:

- `implemented`: the debug namespace now exposes `operator debug event append` through
  `src/agent_operator/cli/commands/debug.py`
- `implemented`: `EventStreamRepairService` in
  `src/agent_operator/application/event_sourcing/event_stream_repair.py` appends allowlisted
  repair events through the canonical event store, replay service, and checkpoint materialization
  path rather than writing JSONL files directly
- `implemented`: repair appends default to dry-run, support optimistic
  `--expected-last-sequence`, require `--reason` for non-dry-run writes, and store the repair
  reason in persisted event metadata
- `implemented`: the initial allowlist is constrained to `operation.status.changed`,
  `session.observed_state.changed`, `scheduler.state.changed`, and `attention.request.answered`
- `verified`: CLI regression coverage exists in `tests/test_cli.py` for dry-run preview,
  canonical append, invalid JSON rejection, missing-reason rejection, unsupported-event rejection,
  and post-append status visibility
- `verified`: the full repository suite passed via `uv run pytest` at the repository state that
  closes this ADR

## Context

`operator` v2 uses `.operator/operation_events/<operation_id>.jsonl` as canonical operation
truth, with checkpoints as derived replay acceleration. This is already established by ADR 0069
and the current event-sourced command/replay services.

During operator-on-operator v2 verification, the normal CLI could not stop a v2 operation because
`operator cancel` still routed through the legacy snapshot cancellation path and failed with:

```text
RuntimeError: Operation 'cad0a556-5eeb-4d26-a2dc-86aaddb091d6' was not found.
```

The operation could be stopped only by running an ad hoc Python snippet that used
`EventSourcedCommandApplicationService.append_domain_events()` to append:

- `session.observed_state.changed` with `terminal_state=cancelled`
- `operation.status.changed` with `status=cancelled`

That repair correctly updated the canonical stream and checkpoint, but the workflow was not a
supported operator interface. It required import knowledge, shell quoting, and direct construction
of application services. That is operationally fragile during exactly the incidents where a repair
tool is needed.

At the same time, an unrestricted "append arbitrary event" CLI would be dangerous:

- it can bypass domain command validation
- it can create event streams that no reducer/projector can replay
- it can fabricate causal history
- it can hide product bugs that should instead be fixed in normal command surfaces
- it can desynchronize related derived stores such as command intent status unless the command owns
  its repair semantics explicitly

## Decision

Add a low-level, debug-only event stream repair CLI for v2 operations.

The command is not a normal user control surface. It is an operator-maintainer escape hatch for
repairing canonical v2 state when a higher-level command path is missing, broken, or intentionally
not yet implemented.

The initial surface should live under the debug namespace, for example:

```sh
operator debug event append <operation-ref> --event-type operation.status.changed \
  --payload-json '{"status":"cancelled","final_summary":"Operation cancelled by user request."}' \
  --reason "manual v2 repair: legacy cancel path cannot address event-sourced operation"
```

Exact command naming is implementation detail, but the surface must clearly communicate that it is
debug/repair tooling, not a primary lifecycle API.

## Required Semantics

### Append through application services

The CLI must append through an application service that:

1. resolves the operation reference using the same v2-aware resolver as status/inspect
2. loads the current replay state
3. appends with optimistic expected-sequence checking
4. folds the appended events
5. materializes the updated checkpoint
6. returns the stored events and resulting checkpoint summary

The CLI must not write JSONL files directly.

### Dry-run first

The command must support `--dry-run` and should default to dry-run unless `--yes` is passed.

Dry-run output must include:

- resolved operation id
- current last sequence
- proposed event drafts
- whether every event type is recognized by the projector
- projected status after applying the draft events
- warnings for event families known to have related derived stores

### Reason is required

Every non-dry-run append requires a non-empty `--reason`.

The reason is stored in event metadata, preferably as causation/correlation metadata or an explicit
repair event wrapper field if the event store format evolves to support it.

### Allowlist before arbitrary mode

The first implementation must not expose unconstrained arbitrary event append by default.

It should support a narrow allowlist of repair-safe event families first:

- `operation.status.changed`
- `session.observed_state.changed`
- `scheduler.state.changed`
- `attention.request.answered`

Additional event types require adding tests that prove replay remains valid and that downstream
read models show the intended result.

An arbitrary `--unsafe-raw` mode may exist only if it is hidden, requires `--yes`, requires
`--reason`, prints a destructive-operation warning, and is covered by explicit tests. It must still
append through the event store and materialize checkpoint; direct file writes remain forbidden.

### No self-healing of product bugs

Using this command during development must create or reference a bug/ADR/backlog item when it works
around a broken higher-level command path.

For example, using it because `operator cancel` cannot address v2 operations must be paired with a
follow-up item for v2 command/control-plane canonicalization.

## Non-goals

- This ADR does not make low-level event append part of the stable end-user CLI.
- This ADR does not replace `operator cancel`, `operator answer`, `operator pause`, or other normal
  command surfaces.
- This ADR does not permit direct mutation of `.operator/operation_events/*.jsonl`.
- This ADR does not standardize every domain event payload.
- This ADR does not solve command-inbox status synchronization; it only makes manual canonical
  repairs safer and auditable.

## Consequences

Positive:

- Maintainers get a repeatable repair path for v2 operations when legacy delivery paths fail.
- Repairs update both canonical event stream and checkpoint instead of editing files by hand.
- Incident response becomes auditable: reason, event drafts, resulting sequence, and projected
  state are visible.
- The tool reinforces event-store authority rather than resurrecting snapshot mutation.

Negative:

- A repair CLI increases the risk that maintainers bypass missing proper command implementations.
- Event payload validation must be kept tight, or the command becomes a stream-corruption tool.
- The command may be mistaken for a stable API unless it is clearly documented as debug-only.

Neutral:

- This command is a bridge tool. If v2 command/control-plane canonicalization becomes complete, its
  use should become rare, but it remains useful for incident repair and development forensics.

## Verification Plan

Implementation is accepted only when tests cover:

- appending an allowlisted event through the CLI updates the event stream and checkpoint
- dry-run performs projection without writing an event
- stale expected-sequence conflict is reported without partial writes
- invalid JSON payload is rejected
- unsupported event type is rejected by default
- `--reason` is required for non-dry-run append
- status/inspect after append show the projected state
- no direct write to `.operator/operation_events/*.jsonl` exists in the CLI path

For the cancellation repair case, a regression should prove:

1. seed a v2 operation with a waiting session
2. invoke the repair CLI to append terminal session + cancelled operation events
3. `operator status <id> --json` returns `status=cancelled`
4. replay from scratch yields the same checkpoint status

## Related

- ADR 0069: Operation event store and checkpoint store contracts
- ADR 0078: Command application and single-writer domain event append boundary
- ADR 0144: Event-sourcing write path contract and RFC 0009 closure
- ADR 0193: OperationAggregate v2 domain boundary
- ADR 0194: v2 migration strategy
- ADR 0205: Event-Sourced Command and Control Plane
