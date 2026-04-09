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
- `Accepted` records decision authority, not automatic delivery closure.
- If implementation is still incomplete, the ADR must say so explicitly through an implementation
  status and must not rely on `Accepted` alone to imply completion.
- If the repository is not yet ready to anchor even the accepted direction in git, keep the ADR at
  `Proposed` instead of prematurely marking it `Accepted`.

## ADR Lifecycle Semantics

- ADRs must separate decision adoption from implementation completion.
- Use a decision-status field such as `Proposed`, `Accepted`, `Rejected`, `Superseded`, or
  `Stale`.
- Use a distinct implementation-status field such as `Planned`, `Partial`, `Implemented`,
  `Verified`, or `N/A`.
- Do not treat `Accepted` as a synonym for "fully done".
- Migration and tranche ADRs with partial implementation must link a canonical remaining-work
  artifact such as a tranche ADR, backlog note, checklist, or status document.
