# ADR 0174: No Separate Context-Read Events And Memory-Freshness ADR

## Decision Status

Rejected

## Implementation Status

N/A

Skim-safe status on 2026-04-15:

- `implemented`: the repository already implements the relevant behavior for brain file reads,
  `operator.context_read` trace events, `MemoryEntry` freshness, and project-scope memory
  through earlier ADRs and their corresponding code paths
- `verified`: current repository tests cover the concrete behavior that a hypothetical separate
  ADR 0174 would have needed to justify
- `current repository truth`: there was no standalone `design/adr/0174-*.md` file in the tree;
  this record exists only to close that documentation gap and route future readers to the
  canonical earlier ADRs

## Context

An audit request on 2026-04-15 asked for line-by-line verification of "ADR 0174" against the
repository.

Current repository truth at the start of that audit:

- there was no `design/adr/0174-*.md` file
- there were no repository references to `ADR 0174`
- the implementation surface implied by the request was already split across accepted earlier
  ADRs:
  - [ADR 0006: Memory Entry Freshness And Invalidation](./0006-memory-entry-freshness-and-invalidations.md)
  - [ADR 0059: Brain — project file system boundary](./0059-brain-project-file-system-boundary.md)
  - [ADR 0060: Project-scope MemoryEntry](./0060-project-scope-memory-entry.md)
  - [ADR 0064: Memory strata and scope model](./0064-memory-strata-and-scope-model.md)

Creating a new architectural decision that re-decides those semantics would add parallel truth
instead of clarifying repository authority.

## Decision

Do not create a new normative architecture decision for this topic.

`ADR 0174` is reserved as a bookkeeping record only:

- to state that no separate ADR existed at current repository truth
- to prevent future readers from assuming a missing-but-normative decision record
- to redirect citations to the existing accepted ADRs that already carry the authority

Future documentation and implementation work should cite the earlier ADRs directly rather than
using `ADR 0174` as a behavioral authority.

## Repository Evidence

### Brain file-read and `operator.context_read` behavior

- Provider-side file-context tool contract:
  [src/agent_operator/protocols/providers.py](/Users/thunderbird/Projects/operator/src/agent_operator/protocols/providers.py:61)
- File tool names and DTOs:
  [src/agent_operator/dtos/brain.py](/Users/thunderbird/Projects/operator/src/agent_operator/dtos/brain.py:153)
- OpenAI provider file-context decision path:
  [src/agent_operator/providers/openai_responses.py](/Users/thunderbird/Projects/operator/src/agent_operator/providers/openai_responses.py:158)

### Memory freshness and supersession semantics

- `MemoryEntry` carries `freshness` and `superseded_by`:
  [src/agent_operator/domain/operation.py](/Users/thunderbird/Projects/operator/src/agent_operator/domain/operation.py:299)
- Freshness enum:
  [src/agent_operator/domain/enums.py](/Users/thunderbird/Projects/operator/src/agent_operator/domain/enums.py:124)
- Task-memory supersession on refresh:
  [src/agent_operator/application/agent_results.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/agent_results.py:516)
- Loaded-operation stale-marking on task regression:
  [src/agent_operator/application/loaded_operation.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/loaded_operation.py:389)

### Project-scope memory persistence and loading boundary

- Project-memory store protocol:
  [src/agent_operator/protocols/runtime.py](/Users/thunderbird/Projects/operator/src/agent_operator/protocols/runtime.py:151)
- File-backed implementation:
  [src/agent_operator/runtime/project_memory.py](/Users/thunderbird/Projects/operator/src/agent_operator/runtime/project_memory.py:9)
- Composition-root wiring:
  [src/agent_operator/bootstrap.py](/Users/thunderbird/Projects/operator/src/agent_operator/bootstrap.py:125)

### Query/CLI surfaces that expose current memory truth

- Projection helper excludes non-current entries by default:
  [src/agent_operator/application/queries/operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/queries/operation_projections.py:312)
- CLI memory rendering helper excludes non-current entries by default:
  [src/agent_operator/cli/helpers/rendering.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/helpers/rendering.py:418)

## Verification

Evidence inspected during this audit:

- `tests/test_cli.py` covers machine-readable memory output and project-memory filesystem behavior:
  [tests/test_cli.py](/Users/thunderbird/Projects/operator/tests/test_cli.py:1955)
- `tests/test_operation_projections.py` covers explicit memory payload derivation and freshness
  handling:
  [tests/test_operation_projections.py](/Users/thunderbird/Projects/operator/tests/test_operation_projections.py:114)
- `tests/test_operation_dashboard_queries.py` covers dashboard payload handling of current memory:
  [tests/test_operation_dashboard_queries.py](/Users/thunderbird/Projects/operator/tests/test_operation_dashboard_queries.py:94)
- full repository verification for this slice is `uv run pytest`

## Consequences

- Future requests for "ADR 0174" should be answered by citing ADR 0006, ADR 0059, ADR 0060, and
  ADR 0064, plus the concrete code/test evidence above.
- No implementation work is tracked under ADR 0174 itself.
