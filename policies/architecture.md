# Architecture Policy

## Architectural Biases

When in doubt, prefer:

- protocol-oriented design over inheritance trees;
- small explicit models over framework-heavy object graphs;
- event-backed transparency over hidden runtime state;
- application services over fat CLI commands;
- ADRs over undocumented architectural drift;
- shared delivery contracts over per-surface authority.

## Canonical Design Reading

The repository should remain understandable to a new contributor by reading:

1. [`../design/VISION.md`](../design/VISION.md)
2. [`../design/SDLC.md`](../design/SDLC.md)
3. [`../design/TESTING-RAILS.md`](../design/TESTING-RAILS.md)
4. [`../design/VERIFICATION-SCENARIOS.md`](../design/VERIFICATION-SCENARIOS.md)
5. [`../design/MOVING-PARTS.md`](../design/MOVING-PARTS.md)
6. [`../design/ARCHITECTURE.md`](../design/ARCHITECTURE.md)
7. relevant delivery vision docs
8. relevant [`../design/adr/`](../design/adr)

## ADR Practice

Write an ADR when a decision materially affects:

- public interfaces;
- protocol contracts;
- runtime behavior;
- persistence format;
- event schemas;
- adapter lifecycle;
- dependency direction;
- major tool and framework choices.

ADRs live under [`../design/adr/`](../design/adr).

## ADR Lifecycle

- ADRs must separate decision adoption from implementation completion.
- ADRs must expose both `Decision Status` and `Implementation Status` near the
  top of the document.
- Canonical `Decision Status` values: `Proposed`, `Accepted`, `Rejected`,
  `Superseded`, `Stale`.
- Canonical `Implementation Status` values: `Planned`, `Partial`,
  `Implemented`, `Verified`, `N/A`.
- Do not treat `Accepted` as a synonym for fully implemented.
