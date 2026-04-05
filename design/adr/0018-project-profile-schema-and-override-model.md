# ADR 0018: Project Profile Schema And Override Model

## Status

Accepted

## Context

The current direction of `operator` increases the amount of stable project-scoped configuration
that users repeatedly supply:

- working directory
- relevant target paths
- adapter roster
- adapter-specific defaults
- default harness instructions
- default success criteria
- default constraints
- default involvement level
- and monitoring or dashboard preferences

As the system evolves toward a true harness with:

- live control,
- attention handling,
- involvement levels,
- and richer monitoring surfaces,

repeated large CLI invocations become increasingly awkward and error-prone.

The project therefore needs a lighter project entrypoint.

But that does not justify hiding runtime truth inside opaque configuration.

The main architectural risk is creating a second persistence layer that quietly absorbs:

- live operation state
- transient tactical instructions
- or learned policy that should remain inspectable as runtime truth

The project needs a clear boundary for project profiles before implementing a profile-driven UX.

## Decision

`operator` will introduce explicit project profiles as declarative, reusable run defaults with a
clear override model.

The core decision is:

- project profiles are project-scoped defaults
- not live operation state
- not a hidden runtime store
- and not a substitute for persisted operation truth

Profiles should be:

- human-editable
- inspectable
- override-friendly
- and resolved into an explicit effective run configuration before start

The initial profile format should be YAML.

## Profile Purpose

A project profile should answer stable questions such as:

- where the operator works
- which agents are normally available
- which default harness instructions and success criteria apply
- what default constraints and involvement level apply
- which monitoring surfaces or dashboard preferences are preferred

A profile should not contain:

- live task state
- live session state
- live interventions
- live attention items
- or concrete operation history

Those belong to operation state, not project defaults.

## Initial Profile Shape

The first profile schema should remain small and bounded.

Likely fields:

- `name`
- `cwd`
- `paths`
- `default_agents`
- `adapter_settings`
- `default_harness_instructions`
- `default_success_criteria`
- `default_constraints`
- `default_involvement_level`
- `dashboard_prefs`
- `session_reuse_policy`

Optional later sections may include:

- named objective templates
- repo bootstrap defaults
- canonical-doc target locations
- or GitHub workflow defaults

But the first profile version should avoid becoming a giant nested configuration language.

## Boundary Rules

### Profile vs operation

Profile:

- reusable defaults
- stable project identity
- durable project-scoped preferences

Operation:

- concrete objective
- live state
- task and session history
- interventions
- outcomes
- and traceability artifacts

### Profile vs learned policy

Some preferences may be authored directly in the profile.
Some may be learned during operation runs.

These are related but not the same thing.

The profile is:

- hand-authored default configuration

Learned policy is:

- runtime-derived and provenance-bearing project memory

The system may later merge or layer these visibly, but they must not be collapsed into one
undifferentiated bucket.

### Profile vs adapter config

Profiles may select and parameterize adapters, but vendor-specific deep configuration should not
spill into random top-level keys.

Adapter-specific configuration should remain nested and bounded.

## Override Model

Profiles are only useful if overrides stay explicit and predictable.

The initial precedence model should be:

1. CLI or explicit caller override
2. project profile value
3. global default

The system should record:

- which profile was used
- which values were overridden
- and the fully resolved effective run configuration

For objective:

- `default_objective` in the profile is the resolved base objective when no CLI objective is provided;
- a CLI objective is recorded as an override only when it differs from the profile default objective.

This is required for transparency and reproducibility.

## Resolved Configuration Visibility

The operator should be able to show the fully resolved launch configuration before or after the
run begins.

This matters because profiles otherwise risk hiding:

- harness instructions
- success criteria
- active involvement level
- adapter settings
- or allowed agent lists

The user should not need to open YAML and mentally merge overrides to understand what will
happen.

## Recommended CLI Shape

The future CLI should support patterns like:

- `operator run --project femtobot "Close open cards"`
- `operator project list`
- `operator project inspect femtobot`
- `operator project resolve femtobot`

The exact CLI surface may evolve, but the profile concept should remain:

- explicit
- inspectable
- and overrideable

## Non-Goals

This ADR does not define:

- the full learned-policy storage model
- secret-management strategy
- whether profiles may also exist in user-level directories
- the full templating system for named operations
- or the final CLI ergonomics for profile authoring and editing

Those are follow-up decisions.

This ADR also does not require profiles to be the only way to run the operator.

Direct explicit CLI usage should remain possible.

## Minimum Requirements

The stronger guarantee of this ADR depends on several minimum rules:

- profiles must remain declarative and human-readable
- profile resolution must be inspectable
- override precedence must be explicit and stable
- profiles must not become a second store for live operation state
- effective run configuration must be recordable for reproducibility
- learned runtime policy must remain distinguishable from hand-authored profile defaults

## Alternatives Considered

### Option A: Keep using only explicit large CLI invocations

Rejected because:

- launch friction is already growing,
- repeated configuration is error-prone,
- and the system is becoming too project-shaped for this to remain ergonomic.

### Option B: Hide project defaults in ad hoc implicit config or runtime caches

Rejected because:

- it weakens transparency,
- makes behavior harder to inspect,
- and risks creating a hidden second source of truth.

### Option C: Introduce explicit YAML project profiles with a clear override model

Accepted because:

- it improves usability without sacrificing inspectability,
- keeps project defaults distinct from live operation state,
- and provides a clean foundation for future project-oriented UX.

## Consequences

### Positive

- Large repetitive run commands can become shorter and less error-prone.
- Project-scoped defaults gain an explicit, inspectable home.
- Effective run configuration becomes easier to reason about and reproduce.
- The future live harness UX gains a natural project entrypoint.

### Negative

- The project gains a new configuration surface that must remain disciplined.
- Users may be confused if profiles and learned policy are not clearly distinguished.
- Poorly bounded profile growth could turn YAML into a second programming language.

### Follow-Up Implications

- A follow-up ADR should define policy memory and promotion workflow separately from profiles.
- A follow-up ADR may define profile discovery locations and project-vs-user precedence.
- The implementation will likely need:
  - a `ProjectProfile` model
  - a resolved-run configuration model
  - and CLI surfaces for profile inspection and resolution
