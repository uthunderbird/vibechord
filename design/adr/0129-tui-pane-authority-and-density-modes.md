# ADR 0129: TUI pane authority and density modes

- Date: 2026-04-10

## Decision Status

Accepted

## Implementation Status

Planned

## Context

The next TUI wave wants richer live summaries and stronger supervisory readability, especially in
`fleet`.

Recent design exploration converged on a stable product instinct:

- one canonical default layout
- optionally a very small number of named modes
- no arbitrary user-built screen composition

Without an ADR, pane structure and density can drift through feature accretion:

- the right pane absorbs unrelated status blocks
- "verbose" means different things in different views
- optional modes become pseudo-configurability without durable semantics

## Decision

The TUI should have explicit pane authority and tightly constrained density modes.

The governing rule is:

- one canonical default layout per major supervisory level
- optionally a small number of named modes with fixed semantics
- no arbitrary pane selection or freeform layout composition

## Pane Authority Rule

Each major level should define:

- which panes are always visible
- which sections are contextual
- which information belongs in compact header/footer vs body panes

Pane authority must be documented before a new summary block becomes canonical.

No view should grow by casually appending status sections until the layout becomes accidental.

## Density Rule

`verbose`, `compact`, or named mode variants are allowed only when they have crisp semantics.

Allowed direction:

- one canonical default
- one dense mode for higher-throughput scanning
- one attention-focused mode if intervention-heavy work proves materially different

Disallowed direction:

- arbitrary field toggles
- arbitrary pane on/off composition
- mode names that merely mean "show more stuff"

## Default-First Rule

The default mode must remain the primary documented and tested product surface.

Optional modes are secondary.

They should not:

- become the only place where important truth is visible
- require separate undocumented semantics
- undermine the canonical visual grammar of the product

## Verbose Rule

If a `verbose`-style rendering exists, it should mean one of:

- more explanatory lines within the same conceptual layout
- slightly expanded section content under the same authority rules

It should not mean:

- a second ad hoc product with different information architecture
- dumping raw internal state into supervisory panes

## Consequences

Positive:

- the TUI keeps a canonical reading grammar
- richer summaries can be added without layout sprawl
- limited named modes remain testable and documentable

Tradeoffs:

- some customization desires are intentionally rejected
- every new pane/section proposal must justify its authority
- mode count must remain small, which constrains experimentation

## Verification

When implemented, the repository should preserve these conditions:

- each supervisory level has a canonical documented layout
- optional modes have fixed and documented semantics
- arbitrary configurable screen composition is absent
- tests and docs target the default mode first

## Related

- [ADR 0110](./0110-tui-view-hierarchy-and-zoom-contract.md)
- [ADR 0126](./0126-supervisory-activity-summary-contract.md)
- [ADR 0128](./0128-tui-information-architecture-beyond-classic-zoom.md)
