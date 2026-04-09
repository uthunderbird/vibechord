# TUI Display Family Red Team

## Status

Internal critique artifact.

This document records a red-team pass over the current TUI display candidates for:

- `Fleet`
- `Operation View`
- `Session View`

Its job is to stress the candidate set, reject weak routes, and identify the strongest target
display family to carry forward into canonical vision and implementation planning.

It is not itself the canonical TUI vision source. Canonical product roles remain defined in:

- [VISION.md](/Users/thunderbird/Projects/operator/design/VISION.md)
- [CLI-UX-VISION.md](/Users/thunderbird/Projects/operator/design/CLI-UX-VISION.md)
- [TUI-UX-VISION.md](/Users/thunderbird/Projects/operator/design/TUI-UX-VISION.md)

## Inputs reviewed

- [fleet-window-candidates-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/fleet-window-candidates-2026-04-09.md)
- [fleet-default-and-modes-decision-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/fleet-default-and-modes-decision-2026-04-09.md)
- [fleet-ui-contract-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/fleet-ui-contract-2026-04-09.md)
- [operation-view-candidates-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/operation-view-candidates-2026-04-09.md)
- [operation-view-default-and-modes-decision-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/operation-view-default-and-modes-decision-2026-04-09.md)
- [operation-view-ui-contract-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/operation-view-ui-contract-2026-04-09.md)
- [session-view-candidates-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/session-view-candidates-2026-04-09.md)
- [session-view-default-and-modes-decision-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/session-view-default-and-modes-decision-2026-04-09.md)

## Core question

What target display shape should the TUI adopt across the `Fleet -> Operation -> Session` zoom
chain?

The real fork is not "which single screen looks nicest?" It is:

- one repeated display pattern everywhere
- separate per-level winners with no family discipline
- a coherent display family with different local centers of gravity
- modes-heavy or configurable layouts as the main answer

## Red-team conclusion

The strongest route is:

- **not** one repeated visual pattern across all levels
- **not** a modes-heavy answer
- **not** a configurable screen system
- **but** a **coherent display family with different default anchors at each level**

That surviving family is:

- `Fleet`: calm-summary hybrid
- `Operation View`: task board + compact operation brief + selected-task panel
- `Session View`: split hybrid with recent timeline + compact session brief + selected event detail

## Why the strongest route survives

The surviving family works because it preserves **continuity without sameness**.

The levels answer different supervisory questions:

- `Fleet`: where should I look next?
- `Operation View`: what is happening in this operation, and which task matters now?
- `Session View`: what is this session doing right now, and should I intervene or open transcript?

Trying to make all three levels use the same repeated screen grammar would flatten the zoom chain
and blur those questions together.

At the same time, letting each level drift into a separate mini-application would destroy the
supervisory feel of the workbench.

The surviving route keeps the shared discipline:

- compact header
- left/right hierarchy
- stable zoom and action semantics
- brief sections only where they reduce inference cost
- explicit anti-sprawl rules

But it allows each level to keep its own **primary working object**:

- `Fleet`: selected operation
- `Operation View`: selected task
- `Session View`: selected event

## Major criticisms of rejected routes

### Rejected: one repeated display style everywhere

This route confuses consistency with sameness.

It over-optimizes for:

- easy documentation
- visible symmetry

And under-optimizes for:

- local task fit
- clear zoom identity
- distinct supervisory questions by level

Net result: a flatter, more repetitive UI that looks coherent but weakens the meaning of drill-down.

### Rejected: per-level winners with no family discipline

This route would maximize local optimization but risks:

- visual drift
- changing interaction rhythm at each zoom
- accidental duplication of information in incompatible shapes

It fails because the workbench must still feel like one system.

### Rejected: modes-heavy strategy as the main answer

This route is attractive because it appears to solve conflicting workflows without forcing hard
choices.

Under critique it failed for a simpler reason:

- most modes would be compensating for unresolved default design weaknesses

Modes can remain a secondary tool, but they should not replace choosing a strong default.

### Rejected: configurable screen family

This route is design avoidance masquerading as flexibility.

It degrades:

- documentation
- onboarding
- supportability
- stable visual grammar

And it does not solve the harder question of what the product should privilege by default.

## Family-level risks that remain

The chosen family still has real failure modes.

### Risk 1: summary creep

All three winners use some form of brief/detail layering.

That can improve comprehension, but it also creates a recurring temptation:

- keep adding "helpful" summary blocks
- weaken the actual working object
- make the right pane feel formulaic and repetitive

This is the single biggest design risk in the current direction.

### Risk 2: false richness

Operator-load, multi-agent counts, or advanced progress signals can make the screens feel more
intelligent than the current runtime truth actually supports.

If these cues are weakly grounded, they will reduce trust.

### Risk 3: level collapse near transcript

`Session View` is especially vulnerable here.

If it becomes too transcript-adjacent, it stops functioning as a supervisory live surface and turns
into an awkward halfway forensic browser.

### Risk 4: family neatness over liveliness

A too-neat workbench can become static.

If normalized summaries are overly canned, the TUI may become structurally elegant but operationally
lifeless.

## Minimal fix set

### P0

- Keep the primary working object dominant at each level:
  - selected operation in `Fleet`
  - selected task in `Operation View`
  - selected event in `Session View`
- Keep each brief compact, scoped, and local to its level.
- Do not let brief blocks duplicate the neighboring zoom level.
- Do not present speculative operator-load or multi-agent richness as always-on truth.
- Keep transcript as an explicit escalation path from `Session View`, not part of the default body.

### P1

- Add future modes only as explicit named modes with fixed semantics.
- Use modes to support genuinely distinct workloads, not to compensate for a weak default.
- Prefer density or attention bias as future mode axes over arbitrary pane composition.

## Surviving mode policy

Modes remain allowed only as a narrow extension policy.

Current acceptable future directions are:

- `Fleet`
  - `dense`
  - `attention`
- `Operation View`
  - `attention`
  - `session`
- `Session View`
  - at most one deferred `debug` mode

These are not part of the base answer.

They remain subordinate to the target display family defined above.

## Decision

Carry forward the following target display family:

- `Fleet`: calm-summary hybrid
- `Operation View`: task board + compact operation brief + selected-task panel
- `Session View`: split hybrid

And enforce the following interpretation rule:

- consistency comes from shared discipline and zoom grammar
- not from repeating the same pane recipe at every level

## Next steps

- Keep `Fleet` and `Operation View` contracts aligned to this critique.
- Create a `Session View` UI contract with the same anti-sprawl discipline.
- Sync [TUI-UX-VISION.md](/Users/thunderbird/Projects/operator/design/TUI-UX-VISION.md) so `Level 2`
  no longer uses the older timeline-only sketch.
- During implementation planning, explicitly reject any change that:
  - weakens the primary working object at a level
  - introduces transcript leakage into `Session View`
  - or uses modes to avoid fixing the default layout
