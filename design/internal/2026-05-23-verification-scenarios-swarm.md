# Verification Scenario Coverage Swarm

Status: `complete`

## Phase 1: Problem Definition

Core problem: determine whether the design corpus covers every planned
behavioral and architectural obligation with verification scenarios.

Scope: design-time verification coverage in `../vibechord`. Runtime test
implementation is out of scope because runtime code does not exist yet.

Success criteria:

- each major product surface has concrete planned verification scenarios;
- ADR verification plans map to scenario families;
- implementation plans reference scenario families;
- unresolved verification-critical decisions are either specified or left in
  backlog with a clear reason.

## Phase 2: Expert Assembly

- Martin Fowler: critic, architecture fitness and test strategy.
- Barbara Liskov: critic, protocol contracts and substitutability.
- Leslie Lamport: critic, ordering/replay/failure semantics.
- Kent Beck: evangelist, smallest useful local verification loops.
- Charity Majors: balanced, observability and operable evidence.

Evidence boundary: local repository files only.

## Phase 3: Round-Robin Findings

Fowler: the rails are structurally sound, but implementation teams need a
scenario catalog so feature plans can cite stable scenario IDs rather than
rephrase the test mesh.

Liskov: protocol conformance is present, but REST/CLI/TUI-specific contracts
need named scenarios because delivery-surface parity is otherwise too broad to
enforce.

Lamport: event ordering and replay are covered, but REST cursor semantics,
idempotency, and audit events need explicit scenario coverage because they are
failure-boundary issues.

Beck: the fast/focused/full rails are useful, but the design should say what
evidence the fake harness emits so local agents can inspect failures without
manual archaeology.

Majors: release confidence needs docs-claim and operational evidence scenarios,
especially for REST exposure safety and TUI manual verification notes.

## Route Update

Route: verification coverage audit.

Prior state: broad rails existed, but some coverage was distributed across
vision, ADR, and plan documents.

New state: `VERIFICATION-SCENARIOS.md` is the scenario catalog; plans and
reading order now reference it.

Justification: every major surface and architectural obligation now maps to a
named planned scenario family.
