# Project Profiles And Launch Ergonomics Brainstorm Ideas

## Status

Brainstorm only. Not architecture truth.

## Context

Current launch commands are getting large and repetitive. In practice, the operator often already knows stable project facts:

- working directory,
- writable roots,
- agent roster,
- default harness instructions,
- success criteria defaults,
- involvement mode,
- and likely dashboard preferences.

This points toward project profiles.

## Core Thesis

Project profiles should be lightweight declarative presets for operator runs, not a hidden runtime state store.

Their job is to make launches short and consistent while keeping the actual operation state transparent and inspectable.

## Main Design Axes

### 1. Profile vs operation

Profiles are defaults.
Operations are instantiated runs.

Do not merge them conceptually.

### 2. Static config vs learned policy

Separate:

- declarative project config in profile YAML,
- from learned or approved policy memory generated during runs.

Both may be project-scoped, but they should not live in one bucket.

### 3. Human-editable simplicity

Profiles should stay small, readable, and friendly to hand editing.

That argues for a constrained YAML schema rather than a giant nested config tree.

### 4. Reproducibility

A run should record:

- which profile it used,
- which values were overridden,
- and the fully materialized config snapshot.

## Likely Architecture Direction

### Suggested profile contents

- project key / display name
- primary `cwd`
- additional writable or target roots
- default adapters and per-adapter settings
- default objective template or reusable harness fragments
- default success criteria
- involvement mode
- monitoring preferences
- trusted repos or target paths

### CLI shape

Examples:

- `operator run --profile femtobot "Close open cards"`
- `operator tui --profile femtobot`
- `operator inspect <id>`

### Composition rule

Precedence should be explicit:

1. CLI override
2. profile value
3. global default

## Risks And Tradeoffs

### Positive

- shorter commands,
- fewer accidental launch mistakes,
- better repeatability,
- cleaner project onboarding.

### Risks

- profile sprawl,
- hidden coupling between profile values and runtime truth,
- temptation to stuff dynamic policy or memory into static YAML.

### Design warning

A profile should not become a second persistence layer for live operation state.

## Recommended ADR Topics

1. `project profile yaml schema and precedence rules`
2. `profile vs learned policy boundary`
3. `recording effective run configuration for reproducibility`
4. `multi-root working context and project target paths`
