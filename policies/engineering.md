# Engineering Policy

## Working Style

- Prefer small, explicit abstractions over framework-heavy designs.
- Keep the operator loop central.
- Keep vendor-specific behavior inside adapters.
- Use `typing.Protocol` for core contracts.
- Preserve transparency and observability in CLI-facing behavior.
- Prefer deterministic guardrails around LLM-driven decisions.
- Follow the boy scout rule: leave the codebase cleaner than you found it.
- Follow `Keep it simple, stupid`.
- Follow `Let it fail`: prefer explicit failure over hidden fallback behavior when the failure
  reveals a real integration or design problem.

## Pre-Release Compatibility Policy

`operator` is still pre-release. We do not currently optimize for backward compatibility.

This means:

- do not add fallback paths just to preserve older behavior
- do not keep legacy compatibility shims longer than needed without a clear active migration reason
- do not introduce parallel old/new code paths when one direct replacement is sufficient

The current policy is zero-fallback by default.

## Code Authoring Policy

For all new code added to this repository:

- write docstrings in Google style
- add concrete examples in docstrings for non-trivial public classes, public functions, and public
  methods
- keep type annotations explicit and strict
- prefer precise concrete types over `Any`
- avoid untyped containers in signatures when a more precise type is known
- do not add local imports inside functions or methods unless a documented third-party constraint
  makes that unavoidable

## Typing Expectations

- New protocols, dataclasses, Pydantic models, and service-layer functions should have complete
  type signatures.
- Prefer repository-wide consistency with strict static analysis rather than relying on dynamic
  runtime behavior alone.
- If a boundary is intentionally dynamic, document that looseness explicitly in a docstring or
  adjacent code comment.

## Engineering Hygiene

When you notice a real issue while already working nearby:

- if it is small and quick, fix it
- if it is real but not quick, document it in
  [`../design/BACKLOG.md`](../design/BACKLOG.md)
