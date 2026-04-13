# AGENTS

## Purpose

This repository builds `operator`: a minimalist Python library and CLI that acts as an operator
for other agents.

## Start Here

Agents working in this repository should start with:

1. [README.md](/Users/thunderbird/Projects/operator/README.md)
2. [policies/README.md](/Users/thunderbird/Projects/operator/policies/README.md)
3. [design/VISION.md](/Users/thunderbird/Projects/operator/design/VISION.md)
4. [design/ARCHITECTURE.md](/Users/thunderbird/Projects/operator/design/ARCHITECTURE.md)
5. [STACK.md](/Users/thunderbird/Projects/operator/STACK.md)
6. relevant [design/adr/](/Users/thunderbird/Projects/operator/design/adr)

## Non-Negotiables

- Keep the operator loop central.
- Prefer small, explicit abstractions over framework-heavy designs.
- Keep vendor-specific behavior inside adapters.
- Use `typing.Protocol` for core contracts.
- Prefer deterministic guardrails around LLM-driven decisions.
- Follow the zero-fallback pre-release policy unless a real migration need is documented.
- Do not overclaim; distinguish `implemented`, `verified`, `partial`, `planned`, and `blocked`.
- Keep public docs self-contained and aligned with repository truth.

## Canonical Policy Locations

- Engineering and code-authoring rules:
  [policies/engineering.md](/Users/thunderbird/Projects/operator/policies/engineering.md)
- Documentation, claim discipline, and docs placement:
  [policies/documentation.md](/Users/thunderbird/Projects/operator/policies/documentation.md)
- Architecture and ADR expectations:
  [policies/architecture.md](/Users/thunderbird/Projects/operator/policies/architecture.md)
- Verification and evidence requirements:
  [policies/verification.md](/Users/thunderbird/Projects/operator/policies/verification.md)

## Placement Rules

- End-user and integrator docs live in [docs/](/Users/thunderbird/Projects/operator/docs).
- Design authority and design history live in [design/](/Users/thunderbird/Projects/operator/design).
- Repository-operational agent and contributor rules live in
  [policies/](/Users/thunderbird/Projects/operator/policies).
- Architectural decisions live in [design/adr/](/Users/thunderbird/Projects/operator/design/adr).
- Brainstorms, critiques, and design-process artifacts live under
  [design/brainstorm/](/Users/thunderbird/Projects/operator/design/brainstorm) or
  [design/internal/](/Users/thunderbird/Projects/operator/design/internal).

## Backlog Rule

If you notice a real issue while working nearby and it cannot be fixed quickly, document it in
[design/BACKLOG.md](/Users/thunderbird/Projects/operator/design/BACKLOG.md).

## Canonical Codex Launch

When starting `operator` against a project with `codex_acp`, use the explicit command override so
the worker does not fall back to the missing default `codex-acp` executable:

```sh
env OPERATOR_CODEX_ACP__COMMAND='npx @zed-industries/codex-acp --' \
    OPERATOR_CODEX_ACP__MODEL='gpt-5.4' \
    OPERATOR_CODEX_ACP__EFFORT='low' \
    UV_CACHE_DIR=/tmp/uv-cache \
    uv run operator run --mode attached --agent codex_acp --max-iterations 100 "<objective>"
```
