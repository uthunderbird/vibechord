# ADR 0103: Dishka composition-root migration

## Status

Accepted

## Context

The repository already declares `dishka` in the dependency set and in the planned stack.

At the same time, current implementation truth is different:

- `bootstrap.py` now uses `dishka` for composition-root assembly
- `OperatorService` no longer acts as a fallback constructor assembler for peer collaborator graph
- application and domain collaborators are passed through explicit constructor wiring rather than a
  DI container

This is not inherently wrong.

Manual wiring has been useful during the recent architecture waves because it kept boundaries
explicit while:

- `OperatorService` was being thinned into a shell
- `LoadedOperation` was being introduced as the one-operation boundary
- workflow-authority services and local execution collaborators were still moving

But after those waves, the remaining manual composition cost is now clearer:

- previously large bootstrap assembly
- test and manual composition now use dedicated outer assembly paths instead of shell-local
  fallback graph construction
- repeated environment-specific wiring logic for CLI, tests, and runtime variants
- documentation drift, because the repository has long described `dishka` as the intended DI tool
  while current code still uses manual composition

The architectural question is therefore no longer whether the repository should adopt a pervasive
framework-driven object model.

The narrower question is:

- should `dishka` be adopted at the composition root while preserving constructor-based boundaries
  inside the application and domain layers?

## Decision

`operator` should migrate to `dishka` at the composition root and bootstrap boundary only.

`dishka` is an assembly tool for infrastructure and top-level application graph wiring.

It is not the repository's primary architectural abstraction.

### Where `dishka` should be used

`dishka` should own:

- bootstrap/container assembly
- provider selection and provider-specific infrastructure wiring
- runtime binding assembly
- store / event sink / inbox / supervisor / history-ledger wiring
- CLI-facing composition root construction
- test or smoke-run composition variants where containerized wiring reduces duplication

### Where `dishka` should not be used

`dishka` should not become part of:

- domain models
- application-service contracts
- `LoadedOperation`
- workflow-authority service logic
- decision or drive execution logic
- protocol contracts

Those layers should remain explicit constructor- and protocol-oriented Python code.

### Migration rule

The repository should prefer:

- `dishka` at the outer composition boundary
- plain typed constructors inside the application graph

This keeps dependency direction clean:

- `dishka` stays outside the core
- the core does not depend on container types or injection magic

### Constructor ownership rule

The repository should not adopt a blanket "inject everything" policy.

Instead:

- inject collaborators that cross an architectural boundary
- inject peer authorities, external boundaries, and independently swappable capabilities
- keep locally constructed helpers when they are private implementation mechanics fully owned by
  the enclosing abstraction

This means constructor-level `new` remains acceptable for:

- adapter-private runners and hooks
- runtime-private registries and helper objects
- other local mechanisms that do not represent separate architectural authority

It remains undesirable when a top-level shell or service constructor becomes an implicit
composition root for multiple peer collaborators.

## Alternatives Considered

### Keep manual wiring permanently

Rejected.

This remains a viable implementation technique in small systems, but the repository has already
grown past the point where manual assembly is the clearest long-term default.

It leaves the project with:

- large bootstrap assembly
- shell constructor bloat
- repeated top-level wiring logic
- and ongoing drift between stack/docs and actual composition practice

### Use `dishka` throughout the application and domain layers

Rejected.

That would push a DI framework into places where the repository currently benefits from:

- explicit protocols
- explicit collaborators
- transparent constructor signatures

It would increase framework coupling without solving a real internal-core problem.

### Introduce a custom builder/factory layer instead of `dishka`

Rejected as the default route.

The repository already carries `dishka` as the planned DI tool, and the missing need is standard
composition-root wiring rather than a novel custom container abstraction.

A builder/factory layer may still exist locally where it clarifies one bounded assembly problem,
but it should not replace the broader composition-root migration decision.

## Consequences

- The repository can align current implementation direction with the declared planned stack.
- `OperatorService` can continue shrinking toward a true shell because part of today's constructor
  burden will move outward into the composition root.
- Bootstrap and CLI wiring can become more structured without forcing `dishka` into the core
  architecture.
- The migration must be done carefully so that `dishka` remains an outer assembly concern rather
  than becoming ambient framework magic throughout the codebase.
- Current truth is now `partial`: `dishka` is live in `bootstrap.py` for composition-root assembly,
  and the bootstrap graph is already split into semantic provider slices rather than one monolithic
  provider.
- Current truth is now also `implemented`: the production bootstrap path injects most peer
  application collaborators into `OperatorService` rather than relying on shell-local default
  construction.
- Current truth is now also `implemented`: test-friendly service assembly can use a dedicated
  `dishka`-backed support provider instead of relying on shell-local fallback construction.
- Current truth is still `partial`: `dishka` is not used everywhere, by design. Application and
  domain constructors remain explicit, and local private mechanism creation is still allowed under
  the ownership-based rule.
- The migration therefore rejects blanket constructor-purity rules in favor of an ownership-based
  distinction between composition leakage and legitimate local mechanism creation.
- The migration remains intentionally bounded: `dishka` is still an outer assembly concern rather
  than an application-core dependency.

## Implementation Status

Implemented

Skim-safe current truth on 2026-04-12:

- `implemented`: `dishka` is the composition root; `bootstrap.py` owns `AsyncContainer` construction
- `implemented`: CLI workflows resolve dependencies through dishka; no manual construction leaking
- `implemented`: `dishka` remains an outer assembly concern — not an application-core dependency
- `verified`: `tests/test_bootstrap.py` confirms the container assembles cleanly
