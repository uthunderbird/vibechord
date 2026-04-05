# Architecture Policy

## Architectural Biases

When in doubt, prefer:

- protocol-oriented design over inheritance trees
- small explicit Pydantic models over bloated framework-heavy object graphs
- file-backed transparency over hidden runtime state
- application services over fat CLI commands
- ADRs over undocumented architectural drift

## Canonical Design Reading

The repository should remain understandable to a new contributor by reading:

1. [`../design/VISION.md`](../design/VISION.md)
2. [`../design/ARCHITECTURE.md`](../design/ARCHITECTURE.md)
3. [`../STACK.md`](../STACK.md)
4. relevant [`../design/adr/`](../design/adr/)

## ADR Practice

Write an ADR when a decision materially affects:

- public interfaces
- protocol contracts
- runtime behavior
- persistence format
- event schemas
- adapter lifecycle
- dependency direction
- major tool and framework choices

Store ADRs under [`../design/adr/`](../design/adr/).

## ADR Acceptance And Commit Rule

- Do not flip an ADR to `Accepted` and leave the repository uncommitted afterward.
- Once an ADR is moved to `Accepted`, make a commit in the same work wave so the accepted decision
  is anchored to a concrete repository state.
- If implementation is still incomplete or not ready to anchor in git, keep the ADR at `Proposed`
  or `partial` truth in related docs instead of prematurely marking it `Accepted`.
