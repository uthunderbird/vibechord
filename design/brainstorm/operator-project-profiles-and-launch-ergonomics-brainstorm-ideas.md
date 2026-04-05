# Operator Project Profiles And Launch Ergonomics Brainstorm Ideas

## Status

Brainstorm only. Not a source-of-truth architecture document.

## Core Thesis

Operator runs are becoming too configuration-heavy to express cleanly as repeated large CLI invocations.
That does not mean runtime truth should disappear into opaque config.
It means the project needs explicit project profiles:

- reusable,
- inspectable,
- override-friendly,
- and clearly separated from per-run state.

## Profile Purpose

A project profile should answer:

- where the operator works
- which agents are available
- which default objective/harness components exist
- what constraints and policies normally apply
- what dashboards or delivery surfaces should open
- what user involvement default is expected

It should not contain live operation state.

## Candidate Profile Contents

Likely YAML fields:

- `name`
- `cwd`
- `paths`
- `default_agents`
- `adapter_settings`
- `default_harness_instructions`
- `default_success_criteria`
- `default_constraints`
- `default_involvement_level`
- `project_policies`
- `dashboard_prefs`
- `session_reuse_policy`

Possible optional sections:

- named operations/templates
- repo bootstrap settings
- GitHub/release workflow defaults
- canonical docs / target directories

## Boundary Rules

### Profile vs operation

Profile:

- reusable defaults
- project identity
- stable paths and policies

Operation:

- concrete objective
- live state
- task/session history
- interventions
- outcomes

### Profile vs adapter config

Project profile can select or parameterize adapters, but vendor-specific deep config should not sprawl into random top-level keys.
It likely needs nested adapter sections.

### Profile vs learned policy

Some policy may start in a hand-authored profile.
Some will be learned during operations.
The system needs a way to merge them visibly without confusion.

## Override Model

Profiles are only useful if overrides stay simple.
The CLI should support:

- use profile defaults
- override objective
- append/replace harness instructions
- override involvement level
- override allowed agents

The user should be able to see the fully resolved run config before start.

## Ergonomic Direction

Likely commands:

- `operator project list`
- `operator project inspect <name>`
- `operator run --project femtobot "objective..."`

Potentially later:

- `operator project init`
- `operator project edit`
- `operator project resolve <name>`

## Risks

### Risk: config becomes a second programming language

Keep profiles declarative and bounded.

### Risk: hiding too much

If users cannot see the resolved harness, constraints, and agents, profiles will make behavior less transparent.

### Risk: conflating project policy with one run's tactical instructions

Profiles should hold defaults and durable preferences, not transient decisions.

## Candidate ADR Topics

1. Project profile schema and scope boundaries
2. Resolved-run configuration model and override semantics
3. Merge rules for profile defaults vs learned policy vs per-run overrides
4. Adapter configuration embedding inside project profiles
5. CLI project-surface design

## Open Questions

- Should profiles live only in the repo, or also in a user-level directory?
- How should profiles reference secrets or tokens without becoming unsafe?
- Should one repo have one profile or many named profiles?
- How much profile data belongs in YAML vs generated runtime state?
