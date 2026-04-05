# Contributing

## Start Here

For a new contributor, the canonical reading order is:

1. [README.md](README.md)
2. [policies/README.md](policies/README.md)
3. [design/VISION.md](design/VISION.md)
4. [design/ARCHITECTURE.md](design/ARCHITECTURE.md)
5. [STACK.md](STACK.md)
6. relevant [design/adr/](design/adr/)

## Development Setup

```sh
uv sync --extra dev
uv run pre-commit install
```

Install the pre-commit hook locally. It is part of the expected contributor setup and runs `ruff`
plus `mypy` on changed Python files and the full `pytest -q` suite before each commit.

`mkdocs build --strict` is intentionally not part of the pre-commit hook. Run it manually when your
change touches public docs, MkDocs configuration, generated reference pages, or documentation
navigation.

Manual checks when you need to debug or run them outside the hook:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q
uv run mkdocs build --strict
```

Pre-commit runs `ruff` and `mypy` on changed Python files plus the full test suite.

Examples for manual targeted typechecks:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run mypy --follow-imports=silent src/agent_operator/bootstrap.py
UV_CACHE_DIR=/tmp/uv-cache uv run mypy --follow-imports=silent tests/test_service.py
```

Full repository-wide `mypy` coverage remains `planned`.

## Documentation Placement

- Public user and integrator docs go in [`docs/`](docs/).
- Design authority and design history go in [`design/`](design/).
- Repository-operational rules for agents and contributors go in [`policies/`](policies/).
- Architectural decisions go in [`design/adr/`](design/adr/).
- RFCs go in [`design/rfc/`](design/rfc/).
- Brainstorms, critiques, and internal design notes go in [`design/brainstorm/`](design/brainstorm/)
  or [`design/internal/`](design/internal/).

Do not put end-user quickstarts or how-to guides into `design/`. Do not put brainstorms,
implementation plans, or critiques into `docs/`.

## Design And Architecture Changes

When architecture changes:

- update `design/VISION.md` only if the product or philosophy changed
- update `design/ARCHITECTURE.md` if boundaries, protocols, or runtime shape changed
- update `STACK.md` if tooling or dependency choices changed
- add or update an ADR under `design/adr/` when the change is decision-worthy

ADR status discipline:

- do not move an ADR to `Accepted` without making a commit in the same work wave
- if the code and docs are not yet ready to anchor that decision in git, keep the ADR `Proposed`
  until the repository state catches up

## Agent Policies

Repository-operational instructions are intentionally split:

- quick entrypoint: [AGENTS.md](AGENTS.md)
- canonical detailed rules: [policies/README.md](policies/README.md)

## Verification Expectations

Prefer matching tests for behavior changes. For nontrivial claims in docs or reports, distinguish:

- `implemented`
- `verified`
- `partial`
- `planned`
- `blocked`
