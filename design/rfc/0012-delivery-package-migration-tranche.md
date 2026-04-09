# RFC 0012: Delivery Package Migration Tranche

## Status

Draft

## Purpose

Define the future migration tranche in which delivery adapters move from the current package shape
toward an explicit shared delivery family.

This RFC follows
[RFC 0011](./0011-delivery-package-boundary-for-cli-and-tui.md),
which established the preferred long-term delivery package boundary:

- `delivery/cli`
- `delivery/tui`

The remaining question is not the target, but the migration tranche:

- when should that move happen
- what should move together
- and what conditions must be true before the migration is worth the churn

## Current state

Today the repository is in an intermediate position:

- CLI decomposition is active and still settling
- TUI is packaged under `agent_operator.cli` as a transitional family
- shared command/query substrate extraction is still underway
- compatibility shims still exist for CLI/TUI execution glue

That means the repository does not yet have a stable enough delivery boundary to justify a broad
package migration.

## Problem

Without an explicit tranche definition, the repository risks two bad outcomes:

1. **premature move**
   - TUI gets moved out of `cli` too early
   - compatibility churn dominates
   - package structure changes faster than the underlying delivery contracts stabilize

2. **permanent transition**
   - `cli/tui` lingers indefinitely
   - the repository normalizes a migration artifact into the apparent architecture

The repository needs a way to say:

- not yet
- but also not forever

## Proposed tranche

The future package migration should be a deliberate `delivery/` tranche, not a one-off TUI move.

Target shape:

- `src/agent_operator/delivery/cli/...`
- `src/agent_operator/delivery/tui/...`

Compatibility facades may remain at:

- `src/agent_operator/cli/...`

for a transition period, but the internal implementation ownership would move under `delivery/`.

## Migration trigger conditions

The tranche should not start until all of the following are materially true:

1. **CLI package decomposition is stable**
   - the current `cli/` family split has landed and stopped churning structurally

2. **TUI package decomposition is stable**
   - TUI controller/model/rendering/io modules are stable enough that the move is mostly package
     relocation, not continued local redesign

3. **Shared delivery substrate is explicit**
   - command/use-case ports and query/projection services are already the reuse boundary
   - neither CLI nor TUI still depends on delivery-local logic from the other

4. **Compatibility seams are known**
   - the repository can enumerate which import paths and tests still depend on `agent_operator.cli`

If these conditions are not met, the migration should be deferred.

## Migration sequence

Recommended order:

1. create `delivery/`
2. introduce `delivery/cli/` and `delivery/tui/`
3. move internal implementation modules there
4. keep `agent_operator.cli` as a compatibility facade layer
5. migrate internal imports gradually
6. decide later whether public import aliases should remain permanently

This is intentionally a broader move than:

- “just move TUI out of `cli`”

because the architecture target is sibling delivery adapters, not isolated extraction of one side.

## Boundary rules during the tranche

The migration must preserve these invariants:

- CLI remains the authoritative shell-facing driving adapter
- TUI remains the supervisory interactive adapter
- both remain adapters over shared application-facing contracts
- package movement must not create a new orchestration layer between delivery and application
- package movement must not change public control semantics

## Explicit non-goals

This tranche does not require:

- changing command names
- changing TUI interaction contracts
- promoting TUI to a co-equal product authority
- immediate removal of `agent_operator.cli` compatibility facades
- application-layer refactors unrelated to delivery boundaries

## Risks

### 1. Churn without leverage

If the tranche starts before CLI/TUI package families stabilize, the move becomes directory churn
instead of architectural clarification.

### 2. False symmetry

If the migration is described badly, contributors may read `delivery/cli` and `delivery/tui` as a
product-authority statement rather than a package-boundary statement.

### 3. Compatibility drag

If `agent_operator.cli` compatibility paths are not managed explicitly, imports and tests may break
in scattered ways.

## Recommendation

Adopt this as a future-planning RFC only.

Do not start the tranche yet.

Near-term work should continue to:

- stabilize `cli/` package decomposition
- finish shared substrate extraction
- treat `cli/tui` as transitional

Then, when the trigger conditions are met, this RFC can be converted into an implementation-facing
ADR or tranche note.

## Related

- [RFC 0011](./0011-delivery-package-boundary-for-cli-and-tui.md)
- [ADR 0114](../adr/0114-cli-delivery-substrate-extraction-before-tui.md)
- [ADR 0123](../adr/0123-cli-package-submodules-and-subpackage-shape.md)
