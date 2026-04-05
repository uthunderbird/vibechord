# ADR 0106: Public documentation surface and committed design corpus separation

## Status

Accepted

## Context

The repository previously had no real public documentation surface.

Current truth:

- `verified`: there was no root `README.md`
- `verified`: there was no public quickstart
- `verified`: there was no contributor-facing `CONTRIBUTING.md`
- `verified`: `pyproject.toml` pointed `readme` at the design corpus rather than a public package
  front door
- `verified`: the old `docs/` tree was dominated by design and process artifacts rather than user
  documentation

The old `docs/` tree mixed several distinct document classes:

- design authority:
  - `VISION.md`
  - `ARCHITECTURE.md`
  - `*-UX-VISION.md`
- architectural decision and design history:
  - `design/adr/`
  - `design/rfc/`
  - `design/RFC-ADR-ROADMAP.md`
- process artifacts:
  - critiques
  - brainstorm notes
  - internal red-team documents
- implementation planning artifacts

This creates a documentation UX problem:

- evaluators do not get a clean front door
- first-time users do not get a quick path to first success
- integrators do not get a clearly separated contract/reference surface
- contributors must infer which documents are canonical design authority and which are process
  history

At the same time, the current `docs/` tree is not junk:

- `verified`: `AGENTS.md` treated `VISION.md`, `ARCHITECTURE.md`, `STACK.md`, and ADRs as
  canonical contributor reading
- `verified`: many ADRs, RFCs, and design docs cross-reference one another

So the real problem is not that the design corpus exists. The real problem is that the repository
does not separate:

- public product documentation
- committed design authority
- committed design/process history

## Decision

The repository should separate the public documentation surface from the committed design corpus.

### Namespace ownership

- root `README.md` should be the evaluator-facing front door
- `docs/` should become the public product documentation namespace
- the current design-heavy `docs/` corpus should move under `design/`
- canonical repository-operational instructions should live under `policies/`

`design/` should remain committed to git.

It should not be added to `.gitignore`.

### Why `design/`

The existing `docs/` content is not primarily user documentation.

It is a mix of:

- design authority
- ADR and RFC history
- critiques
- brainstorms
- implementation plans

That corpus is valuable, but its correct meaning is design knowledge and design history, not the
public documentation surface of the product.

`design/` is therefore a more honest namespace than `docs/`.

### Public documentation model

The new public documentation surface should stay small and audience-routed.

Minimum intended structure:

- root `README.md`
- `docs/README.md`
- `docs/quickstart.md`
- a small `docs/how-to/` set for concrete tasks
- a small `docs/reference/` set for stable user/integrator surfaces
- an integration entry document such as `docs/integrations.md` or `docs/agent-api.md`

### Design corpus model

The committed design corpus under `design/` should contain:

- `VISION.md`
- `ARCHITECTURE.md`
- `*-UX-VISION.md`
- `adr/`
- `rfc/`
- critiques
- brainstorms
- internal design notes
- implementation plans

This corpus is public project history and contributor-facing design material, not local scratch.

## Alternatives Considered

### Keep the current `docs/` tree and only add an index

Rejected.

That would reduce confusion somewhat, but it would still assign the strongest documentation
namespace in the repository to a tree that is primarily design authority and design/process
history.

The result would remain semantically misleading for evaluators and users.

### Rename the current tree to `design_docs/`

Rejected.

This would be structurally workable, but `design/` is shorter, cleaner, and better reflects that
the corpus includes more than just polished documents. It includes design history and process
artifacts as well.

### Rename the current tree and add it to `.gitignore`

Rejected.

The design corpus is not machine-local scratch.

It is committed project knowledge used by contributors and referenced by repository guidance and
architectural records. `.gitignore` is the wrong mechanism for that material.

### Treat the current `docs/` tree as the public documentation surface

Rejected.

The current tree does not provide the documentation modes a normal user expects:

- evaluator overview
- quickstart
- task-oriented how-to guidance
- stable public reference

It is explanation-heavy and design-history-heavy instead.

## Consequences

- The repository will gain a clean public documentation front door.
- The meaning of `docs/` will align with common open-source expectations.
- The existing design corpus can stay public and committed without pretending to be end-user docs.
- Contributors will still have access to the full design and ADR history under a more honest
  namespace.
- The migration will require link rewiring across `AGENTS.md`, `STACK.md`, ADRs, RFCs, and other
  documents that currently point into `docs/`.
- `implemented`: root `README.md`, `CONTRIBUTING.md`, public `docs/`, committed `design/`, and
  committed `policies/` now exist.
- `implemented`: `pyproject.toml` now points `readme` at `README.md`.
- `implemented`: the old design-heavy `docs/` corpus has moved under `design/`.
- `implemented`: the public docs surface now has a minimal quickstart/how-to/reference structure.
- `partial`: some historical design-process artifacts still mention old `docs/` paths in prose,
  but active repository guidance has been rewired to the new structure.
