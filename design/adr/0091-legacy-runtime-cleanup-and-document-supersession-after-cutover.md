# ADR 0091: Legacy runtime cleanup and document supersession after cutover

## Status

Accepted

## Context

The repository now has two layers of runtime truth:

- accepted foundation ADRs for the event-sourced and runtime-contract direction
- active legacy codepaths and documents that still describe snapshot-first and `AgentAdapter`-era
  behavior

Per repository policy, an ADR wave is not fully closed until consciously deferred leftovers are
captured explicitly. For the RFC 0009/0010 closure wave, those leftovers are not optional polish.
They are mandatory cleanup obligations required to make repository truth coherent.

### Current truth

Even after implementing the foundation ADRs, the repository still contains legacy runtime surfaces
in code, tests, and docs that would continue to imply the old architecture unless removed or
annotated.

### Implementation notes

The cleanup wave has now landed in documentation and protocol labeling:

- `VISION.md` and `ARCHITECTURE.md` no longer describe `AgentAdapter` as the canonical runtime
  contract
- the active public runtime truth is documented as `AdapterRuntime`, `AgentSessionRuntime`, and
  `OperationRuntime`
- the old `AgentAdapter` protocol module has been removed from active repository code
- attached execution no longer depends on `attached_registry.py`; canonical attached mode now uses
  `AttachedSessionRuntimeRegistry`
- historical RFC/ADR documents that centered `AgentAdapter` are now annotated or superseded
- file-based worker hosting has been removed from active code
- CLI background-run inspection now uses a read-only inspection store rather than an execution
  supervisor

The remaining closure tail is now event-sourced runtime cutover under RFC 0009, not legacy runtime
truth under RFC 0010.

## Decision

The RFC 0009/0010 closure wave must end with explicit removal or supersession of legacy runtime
truth.

### Cleanup obligations

Once `ADR 0086` through `ADR 0090` are implemented and verified, the repository must remove or
supersede:

- `AgentAdapter` as active public protocol truth
- snapshot-first live runtime entrypaths
- background-worker-era canonical execution paths
- tests that assert poll/collect-era architecture as current truth
- docs that still describe `AgentAdapter` or snapshot-first runtime as the intended steady state

### Documentation obligations

The closure implementation must review and update the older documents that currently encode legacy
truth, especially where they still present:

- ACP integration beneath `AgentAdapter`
- snapshot-first operation execution as active architecture
- worker-process execution as canonical runtime behavior

If a document remains historically useful, it should be annotated, superseded, or scoped
explicitly rather than left silently misleading.

## Consequences

- The repository can move `RFC 0009` and `RFC 0010` to closed lifecycle states without hidden
  contradictions.
- Future contributors will not need to reverse-engineer which legacy documents still matter.
- Cleanup becomes a first-class acceptance criterion rather than optional aftercare.

## Verification

- `verified`: `design/VISION.md` now describes runtime-contract truth in terms of
  `AdapterRuntime`, `AgentSessionRuntime`, and `OperationRuntime`.
- `verified`: `design/ARCHITECTURE.md` now marks `AgentAdapter` as transitional rather than
  canonical.
- `verified`: the old `AgentAdapter` protocol module has been removed from active repository code.
- `verified`: the old attached-runtime compatibility boundary has been removed from active code.
- `verified`: historical RFC/ADR documents that still mention `AgentAdapter` as active truth are
  now explicitly annotated or superseded.
- `verified`: the old worker-process runtime path has been removed from active repository code.

## This ADR does not decide

- the exact implementation order of the cutover ADRs
- whether historical documents are rewritten in place or superseded by newer records
- unrelated cleanup outside the RFC 0009/0010 closure wave

## Alternatives Considered

### Treat cleanup as implicit and leave old docs/code to be trimmed opportunistically later

Rejected. That repeatedly leaves architecture waves half-closed in practice.

### Keep legacy docs untouched as historical archive without annotations

Rejected. Unannotated legacy architecture docs look like active truth to new contributors.
