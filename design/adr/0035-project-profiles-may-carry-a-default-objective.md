# ADR 0035: Project Profiles May Carry A Default Objective

## Status

Accepted

## Context

Project profiles already carry stable run defaults such as:

- `cwd`
- default agents
- default harness instructions
- default success criteria
- default involvement level

But repeated research projects also need a stable default objective.

Without that field:

- local `operator-profile.yaml` can only describe workspace policy, not the actual task,
- problem-scoped projects still require the user to restate the main objective on every run,
- and profile-backed runs cannot honestly distinguish between the objective and the harness.

This is especially awkward for research workspaces such as one-problem subprojects where the
problem itself is the stable default objective.

## Decision

Project profiles may carry a first-class `default_objective`.

Semantics:

- `default_objective` is the stable default task statement for runs launched from that profile
- CLI-provided objective text still overrides the profile value
- if neither an explicit objective nor a `default_objective` is available, `operator run` should
  fail clearly instead of inventing one

This field is distinct from:

- harness instructions, which describe operator protocol and policy
- success criteria, which describe the bar for completion

## Alternatives Considered

### Option A: Keep the objective outside profiles entirely

Rejected because repeated project work still has a stable task identity and forcing users to restate
 it every run adds noise while encouraging objective text to leak into harness fields.

### Option B: Encode the objective indirectly inside harness instructions

Rejected because it blurs the boundary between:

- what the operator is trying to achieve
- and how the operator should behave while trying to achieve it

### Option C: Add a first-class `default_objective`

Accepted because it preserves the objective/harness distinction while making profile-backed project
launches complete enough to stand on their own.

## Consequences

- Project profile schema grows one public field: `default_objective`
- `operator run` can be launched without an explicit objective when a profile supplies one
- local `operator-profile.yaml` files become usable as true project entrypoints for stable
  long-lived research tasks
- profile tooling, tests, and documentation must keep the objective/harness distinction explicit
