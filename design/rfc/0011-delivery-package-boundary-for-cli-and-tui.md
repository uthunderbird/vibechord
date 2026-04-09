# RFC 0011: Delivery Package Boundary for CLI and TUI

## Status

Draft

## Purpose

Clarify the long-term package boundary for delivery surfaces after the current CLI decomposition
wave.

This RFC is not about product authority. That is already decided:

- CLI remains the authoritative shell-facing control surface
- TUI remains the preferred interactive supervision surface

This RFC is about code/package structure:

- should TUI stay under `agent_operator.cli`
- should it move to a top-level `agent_operator.tui`
- or should both CLI and TUI eventually live as sibling adapters under a common delivery package

## Current repository truth

Today the repository has:

- `agent_operator.cli.*` as the CLI package
- TUI implementation currently nested under `agent_operator.cli.tui*`

This is structurally understandable as a migration artifact:

- the TUI work started from CLI delivery code
- the current compatibility seams still run through CLI workflows
- the TUI is not yet fully separated as a sibling delivery adapter in package structure

## Problem

The current package shape and the current architecture story are slightly misaligned.

The architecture/design corpus already says:

- CLI and TUI are both delivery surfaces
- both are driving adapters over shared application-facing command/query contracts
- TUI must not invent separate control semantics

But the code/package shape still suggests:

- TUI is a sub-area inside CLI

That is acceptable as a transition, but weak as an enduring architecture signal.

At the same time, moving TUI directly to a top-level package like `agent_operator.tui` would also
be misleading.

It would imply stronger top-level symmetry than the product model intends and could blur the
repository’s “CLI authority, TUI supervision” split.

## Candidate routes

### Route A: Keep TUI permanently under `agent_operator.cli`

Shape:

- `agent_operator.cli.*`
- `agent_operator.cli.tui.*`

Strengths:

- lowest churn
- close proximity to current CLI workflows

Weaknesses:

- package structure understates that CLI and TUI are sibling delivery adapters
- bakes a migration artifact into the long-term architecture story

### Route B: Move TUI to top-level `agent_operator.tui`

Shape:

- `agent_operator.cli.*`
- `agent_operator.tui.*`

Strengths:

- immediately communicates that TUI is not “inside CLI”

Weaknesses:

- overstates top-level symmetry
- risks encouraging contributors to treat TUI as an independent authority surface rather than a
  sibling delivery adapter under the same product contract

### Route C: Introduce a common delivery package later

Shape:

- `agent_operator.delivery.cli.*`
- `agent_operator.delivery.tui.*`

Strengths:

- matches the architecture story directly
- keeps CLI and TUI as sibling delivery adapters
- avoids implying that TUI is either merely “part of CLI” or an equal top-level authority root

Weaknesses:

- requires a broader later migration rather than a one-off TUI move

## Recommendation

Route C is the best long-term architecture target.

That means:

- the current `agent_operator.cli.tui*` shape is acceptable as a transitional structure
- the repository should not treat it as the final architectural package boundary
- the repository should also not immediately move TUI to `agent_operator.tui` as a standalone
  top-level package

The correct future move is broader:

- introduce a `delivery/` package
- place `cli/` and `tui/` beneath it as sibling adapters

## Migration policy

### Near term

Continue current CLI package decomposition without forcing an immediate TUI move out of `cli/`.

This keeps churn proportional while the TUI still shares compatibility seams with CLI workflows.

### Medium term

Treat `cli/tui` as transitional in ADRs and implementation notes.

Avoid writing new design text that implies:

- `cli/tui` is the final target
- or `agent_operator.tui` is the next step by default

### Long term

When delivery packaging is revisited as a whole, prefer:

- `agent_operator.delivery.cli`
- `agent_operator.delivery.tui`

over:

- permanent `agent_operator.cli.tui`
- or top-level `agent_operator.tui`

## Architectural consequences

- package structure becomes more aligned with the existing delivery-layer model
- CLI authority remains a product/contract question, not a package-root question
- TUI remains a sibling supervisory adapter over shared command/query contracts

## Non-goals

This RFC does not:

- require an immediate code move
- change CLI/TUI product authority
- redesign TUI contracts
- create a new architectural layer between delivery and application

## Questions to resolve before implementation

1. whether `delivery/` should be introduced only when both CLI and TUI are moved together
2. how much compatibility-facade surface should be retained during such a migration
3. whether top-level `agent_operator.cli` should remain as a durable import facade even after the
   internal move to `delivery/cli`

## Related

- [ADR 0114](../adr/0114-cli-delivery-substrate-extraction-before-tui.md)
- [ADR 0123](../adr/0123-cli-package-submodules-and-subpackage-shape.md)
- [RFC 0012](./0012-delivery-package-migration-tranche.md)
