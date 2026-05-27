# Engineering Policy

## Working Style

- Keep the operation loop central.
- Prefer small explicit abstractions over framework-heavy designs.
- Keep vendor-specific behavior inside adapters.
- Use `typing.Protocol` for core contracts when implementation begins.
- Preserve transparency and observability in user-facing behavior.
- Prefer deterministic guardrails around LLM-driven decisions.
- Prefer explicit failure over hidden fallback behavior.
- Leave the codebase cleaner than you found it.

## Pre-Release Compatibility Policy

`vibechord` is pre-implementation and pre-release. Optimize for correctness and
clarity over compatibility.

This means:

- do not add fallback paths to preserve abandoned behavior;
- do not keep legacy compatibility shims without a documented migration need;
- do not introduce parallel old/new code paths when one direct replacement is
  sufficient.

## Code Authoring Policy

For new code added to this repository:

- write docstrings in Google style;
- add concrete examples in docstrings for non-trivial public APIs;
- keep type annotations explicit and strict;
- prefer precise concrete types over `Any`;
- avoid untyped containers in signatures when a more precise type is known;
- do not add local imports inside functions unless a documented dependency
  constraint requires it.

## Engineering Hygiene

When you notice a real issue while working nearby:

- if it is small and quick, fix it;
- if it is real but not quick, document it in
  [`../design/BACKLOG.md`](../design/BACKLOG.md).
