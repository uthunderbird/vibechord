# ADR 0025: Add A Project Profile Init CLI Surface

## Status

Accepted

## Context

ADR 0018 established project profiles as the bounded declarative default layer for repeated work.

The current repo already implements:

- YAML-backed project profiles
- `operator project list`
- `operator project inspect`
- `operator project resolve`
- and `operator run --project ...`

That leaves one practical gap.

Users can resolve and inspect profiles, but they still need to hand-author YAML files from
scratch before the profile workflow becomes useful.

For a feature that is supposed to become the ergonomic entrypoint for repeated work, that is too
much friction.

At the same time, the fix should not introduce:

- hidden mutable profile state
- an interactive wizard with opaque defaults
- or a second runtime store that blurs profile defaults with live operation truth

## Decision

`operator` will expose an explicit `operator project init` command that writes a bounded YAML
project profile file.

The initial command shape is intentionally narrow:

- it writes the existing `ProjectProfile` schema
- it accepts only stable top-level defaults already supported by the profile model
- it overwrites only when `--force` is given
- and advanced or uncommon fields may still be edited manually in YAML afterward

The command is a scaffolding surface, not a hidden profile manager.

## Alternatives Considered

- Option A: keep profile authoring fully manual
- Option B: add an explicit `project init` scaffolding command
- Option C: build an interactive profile editor

Option A was rejected because it leaves the project-profile workflow awkward at the exact point
where it should become ergonomic.

Option B was accepted because it improves profile adoption while preserving explicit,
inspectable YAML as the source of truth.

Option C was rejected because it adds delivery complexity and stronger UX commitments before the
bounded profile model is proven.

## Consequences

- Project profiles become easier to adopt without changing their declarative YAML source of truth.
- The CLI grows a small authoring surface while keeping advanced editing manual and transparent.
- Future profile editing or discovery features can build on this command instead of assuming
  users always start from a hand-written file.
