# v2 Cutover Governance Checklist

This document is the in-repo governance artifact for `ADR 0213`.

It does not claim that the final v2 cutover gate is satisfied today. It defines the checklist,
legacy inventory, removal order, rollback boundary, and rehearsal procedure that must be pinned to
one reviewed repository state before destructive v1 removal.

## Cutover Wave Record

Record these fields for the cutover wave under review:

- date
- repository `HEAD`
- reviewed branch or commit
- whether the worktree was clean
- operator data directory / target workspace
- verifier name
- result: `planned`, `rehearsed`, `blocked`, or `accepted`

## Gate Checklist

The final destructive removal of v1 load-bearing behavior may proceed only when all items below are
explicitly recorded as satisfied for one named wave.

### 1. Pinned Repository State

- record `git rev-parse HEAD`
- record `git status --short`
- record the exact branch or detached commit under review

### 2. Drain Or Explicit Terminal Disposition

For every running operation in scope, record one of:

- completed
- cancelled through the canonical control plane
- explicitly abandoned by policy

Capture at least:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator list --json
UV_CACHE_DIR=/tmp/uv-cache uv run operator status last --json
```

### 3. Canonical v2 Authority Preconditions

Before final cutover acceptance, the pinned repository state must already satisfy the accepted
closure conditions for `ADR 0203` through `ADR 0211`.

Minimum command set to record:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run pytest
UV_CACHE_DIR=/tmp/uv-cache uv run operator status last --json
UV_CACHE_DIR=/tmp/uv-cache uv run operator watch last --once --json
UV_CACHE_DIR=/tmp/uv-cache uv run operator debug inspect last --json --full
```

If one of those ADRs remains `Partial`, `Planned`, `Blocked`, or otherwise unverified, mark the
cutover wave `blocked` instead of inferring closure here.

### 4. Legacy Removal Inventory

Every remaining v1 surface must be classified as exactly one of:

- `removed`
- `retained temporarily as migration-only or forensic-only`
- `deferred with named blocker`

Use the inventory table in this document for the current repository truth.

### 5. Removal Order

Destructive removal must follow this order:

1. legacy authority paths
2. legacy control/query entrypoints
3. legacy public API exports
4. legacy tests and docs claims
5. dormant compatibility code with no named justification

### 6. Rollback Boundary

The cutover wave must say which rollback rule applies:

- not allowed after merge
- allowed only before destructive data cleanup
- allowed only through git history, not runtime compatibility

### 7. Rehearsal

Before final cutover acceptance, record one rehearsed run of this checklist with:

- exact commands
- operation ids
- observed success/failure criteria
- explicit blocker notes when the rehearsal does not pass

## Current Legacy Inventory

This table is the explicit remove/retain/defer inventory for the repository state reviewed with
this ADR slice.

| Surface | Current role | Classification | Evidence |
| --- | --- | --- | --- |
| Snapshot fallback loaders in `src/agent_operator/application/queries/operation_resolution.py` | Canonical read path tries replay first, then named snapshot fallback for mixed-mode and migration cases | retained temporarily as migration-only or forensic-only | `_load_snapshot_fallback()` remains explicit; see `ADR 0209` and `tests/test_operation_resolution.py` |
| Snapshot fallback loaders in `src/agent_operator/application/queries/operation_status_queries.py` | Status/read payloads prefer replay, then named snapshot fallback | retained temporarily as migration-only or forensic-only | `_load_snapshot_fallback()` remains explicit; see `ADR 0209` and `tests/test_operation_status_queries.py` |
| Snapshot fallback loaders in `src/agent_operator/application/commands/operation_delivery_commands.py` | Delivery commands still keep a named snapshot fallback when canonical state is absent | retained temporarily as migration-only or forensic-only | `ADR 0209` records the bounded fallback and tests it in `tests/test_operation_delivery_commands.py` |
| Top-level transitional CLI aliases such as `resume`, `recover`, `inspect`, `sessions`, `wakeups`, and `daemon` | Still published as transitional aliases to debug surfaces | deferred with named blocker | `docs/reference/cli-command-contracts.md`, `docs/reference/cli-command-inventory.md`, and `tests/test_cli_command_inventory.py` |
| Package-root exports other than `OperatorClient` | No longer part of the public root API | removed | `src/agent_operator/__init__.py`, `ADR 0215`, and `tests/test_client.py::test_agent_operator_package_root_exports_only_operator_client` |
| Direct `FileOperationStore.save_operation()` authority in guarded v2 mutation paths | Explicitly disallowed in covered v2 mutation paths | removed | `tests/test_application_structure.py::test_adr_0203_v2_mutation_paths_do_not_save_legacy_snapshots` |

## Rehearsal Procedure

This is the mandatory cutover rehearsal sequence. Running it once does not satisfy the final gate
by itself; it produces the evidence needed to decide whether the gate can close.

1. Pin the repository state:

   ```sh
   git rev-parse HEAD
   git status --short
   ```

2. Run the repository-wide baseline:

   ```sh
   UV_CACHE_DIR=/tmp/uv-cache uv run pytest
   ```

3. Capture one supervisory visibility set for the chosen operation:

   ```sh
   UV_CACHE_DIR=/tmp/uv-cache uv run operator status last --json
   UV_CACHE_DIR=/tmp/uv-cache uv run operator watch last --once --json
   UV_CACHE_DIR=/tmp/uv-cache uv run operator debug inspect last --json --full
   ```

4. Record whether any operation remained running, needed explicit cancel, or exposed a blocker.

5. Re-check the legacy inventory and mark each surface `removed`, `retained temporarily as
   migration-only or forensic-only`, or `deferred with named blocker`.

6. Name the rollback boundary for the wave before any destructive removal begins.

## Current Rollback Boundary

For the current repository state, rollback is allowed only through git history, not runtime
compatibility.

Reason: the repository is pre-release and follows the zero-fallback policy, but the final v1
removal wave has not happened yet. If a future wave removes the remaining legacy inputs, the
rollback decision must be re-recorded for that exact commit.
