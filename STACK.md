# Planned Stack

## Packaging And Tooling

- Python `3.13`
- `uv` for environment management, dependency management, locking, and task execution
- `pyproject.toml` as the single project entrypoint

## CLI

- `typer` for the command-line interface
- `rich` for transparent terminal rendering, live status, and event presentation

The CLI should share the same application layer as the Python library. No separate command-only business logic.

## Core Typing And Contracts

- `typing.Protocol` for primary interfaces
- `pydantic` for domain models, DTOs, config, and event schemas
- explicit DTO and mapper layers for provider-facing structured outputs

The core should still prefer small, explicit models over framework-heavy inheritance trees. Pydantic is the chosen model layer, not an excuse to blur domain objects and provider payloads together.

## Dependency Injection

- `dishka`

Current truth:

- `partial`: composition-root assembly in [bootstrap.py](/Users/thunderbird/Projects/operator/src/agent_operator/bootstrap.py)
  now uses `dishka`
- `implemented`: the bootstrap container graph is already split into semantic provider slices
- `implemented`: test-facing operator-service assembly can also use a dedicated `dishka`-backed
  support provider
- `partial`: application and domain constructors still remain explicit by design; `dishka` is not
  used inside the core

Planned direction:

- `dishka` is the intended DI framework for wiring providers, adapters, runtime services, and the
  CLI composition root

The domain and application layers should continue to avoid direct dependency on `dishka` types.

## LLM Integration

- Internal operator brain behind an `OperatorBrain` protocol
- Initial OpenAI-compatible client support for the operator brain
- Architecture should allow Anthropic, OpenAI, local, or custom providers without changing the operator loop
- Provider implementations should return structured DTOs that are mapped into domain decisions and evaluations

The operator brain is an internal service, distinct from external agent adapters.

## Agent Adapters

- `Claude ACP` via `@agentclientprotocol/claude-agent-acp`
- `Codex` via `codex-acp` over ACP stdio
- ACP-backed adapters normalized behind an operator-owned ACP substrate seam
- ACP-backed adapters share a session-runner layer above that substrate and below vendor policy
- ACP-side permission handling normalized through a shared operator-owned permission policy layer
- ACP Python SDK as the default substrate for ACP-backed adapters that have direct runtime evidence
- adapter system designed for future hosted, local, or API-driven agents

Each adapter should implement a shared protocol-oriented contract and hide vendor-specific mechanics.

## Terminal / Process Control

- subprocess stdio transport for ACP-compatible agents such as `codex-acp`
- `anyio` for structured async concurrency, cancellation, and timeouts
- `agent-client-protocol` Python SDK for ACP session/client lifecycle and canonical ACP models

The exact ACP backend may be bespoke or SDK-backed during migration, but the public adapter contract must not depend on that choice.

## Observability

- structured event model owned by the project
- `rich` for human-facing CLI output
- JSONL event logs for machine-readable traceability
- standard library `logging` or `structlog` for internal diagnostics

Preference: start with stdlib `logging` unless `structlog` buys a clear advantage early.

## Persistence

- Start simple with file-backed run artifacts and logs
- Keep storage behind a protocol so SQLite or other stores can be introduced later

## Testing

- `pytest`
- `pytest-asyncio` or `anyio` test support
- adapter contract tests
- golden-style CLI output tests where helpful

## Quality Tools

- `ruff` for linting and formatting
- `mypy` for static typing

## Documentation

- `README.md` for evaluator-facing project entry
- `docs/` for public product and integration documentation
- `design/VISION.md` and `design/ARCHITECTURE.md` for design authority
- `design/adr/` for architectural decisions and provenance
- `policies/` for repository-operational contributor and agent instructions
- `STACK.md` for stack and technology choices

## Biases

- Prefer modern, transparent CLI tooling over hidden framework magic
- Prefer protocols over inheritance-heavy extension trees
- Prefer a small core with explicit boundaries over many abstract layers
- Prefer deterministic guardrails around an LLM-driven operator loop
