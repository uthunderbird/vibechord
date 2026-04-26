# Public Release Reference

This document is the canonical public-release reference and conservative publication checklist for
`operator`.

It executes the contract accepted by
[`ADR 0216`](../../design/adr/0216-public-release-contract-and-distribution-acceptance-gate.md)
and
[`RFC 0015`](../../design/rfc/0015-public-release-contract.md).

It is intentionally grounded in current repository truth on 2026-04-27. It does **not** claim that
the repository is already publication-ready.

## Canonical Public Identity

- project concept: `operator`
- pip package name: `agent-operator`
- CLI command: `operator`
- Python import package: `agent_operator`
- canonical stable SDK entrypoint: `agent_operator.OperatorClient`

These identities must agree with:

- `pyproject.toml`
- `README.md`
- `docs/quickstart.md`
- `docs/reference/cli.md`
- `docs/reference/cli-command-contracts.md`
- `docs/reference/python-sdk.md`

## Current Public Install Surface

Current repository truth documents a source-oriented install path, not a released PyPI install
path:

- local development install: `uv sync --extra dev`
- local CLI invocation: `UV_CACHE_DIR=/tmp/uv-cache uv run operator ...`
- documented first-run workspace bootstrap: `UV_CACHE_DIR=/tmp/uv-cache uv run operator init`

Current prerequisites stated in public docs:

- Python `>=3.13` from `pyproject.toml`
- `uv`
- an available agent backend such as `codex_acp`

Public-release implication:

- this repository already documents a coherent source checkout quickstart
- this repository does **not** yet document a verified wheel/sdist installation command for public
  release consumers

## Current CLI Contract Boundary

The canonical CLI references are:

- overview/reference: `docs/reference/cli.md`
- stability and exit/error contract matrix: `docs/reference/cli-command-contracts.md`
- machine-readable payload schema reference: `docs/reference/cli-json-schemas.md`

Current stable CLI surface is the command set marked `stable` in
`docs/reference/cli-command-contracts.md`.

Current non-stable public boundary:

- commands marked `transitional` are callable compatibility aliases, not the default stable public
  contract
- commands marked `debug-only` are verification or forensic surfaces, not the default stable public
  contract

In particular, the transitional alias `operator inspect` must not be presented as part of the
default stable CLI story while `operator debug inspect` remains its canonical home.

## Current Python SDK Contract Boundary

The canonical SDK reference is `docs/reference/python-sdk.md`.

Current stable SDK truth:

- package-root import: `from agent_operator import OperatorClient`
- package-root export set: only `OperatorClient`
- canonical stable entrypoint family: `agent_operator.OperatorClient`

Current non-stable SDK boundary:

- internal or advanced module-path imports may exist
- those import paths are not part of the stable package-root contract unless public docs promote
  them explicitly

## Required Release Artifact Set

For a public release, the minimum artifact set remains:

- a wheel
- an sdist
- versioned release notes or changelog entry
- public install and quickstart docs aligned with the released version

Current repository truth on 2026-04-27:

- install and quickstart docs exist
- CLI reference docs exist
- Python SDK reference docs exist
- no committed release-notes or changelog artifact is present in this repository slice
- no release-grade wheel/sdist evidence is recorded in this repository slice

## Publication Checklist

Mark an item complete only when repository evidence exists for the exact release wave.

### Decision And Governance

- [ ] ADR 0211 evidence requirements are satisfied for the public claims being made
- [ ] ADR 0213 cutover-governance requirements are satisfied for the public claims being made
- [ ] the exact commit or version under publication is pinned

### Public Surface Alignment

- [x] `pyproject.toml` names the package `agent-operator`
- [x] `pyproject.toml` exposes the `operator` CLI entrypoint
- [x] package-root public SDK export is `agent_operator.OperatorClient`
- [x] `README.md` and `docs/quickstart.md` describe the same source-oriented quickstart shape
- [x] `docs/reference/cli.md` and `docs/reference/cli-command-contracts.md` publish the CLI
      surface boundary
- [x] `docs/reference/python-sdk.md` publishes `agent_operator.OperatorClient` as the stable SDK
      surface
- [x] stable versus transitional/debug CLI boundaries are explicit in the CLI contract docs

### Missing Before Public Publication

- [ ] wheel build recorded for the release state
- [ ] sdist build recorded for the release state
- [ ] versioned release notes or changelog entry added
- [ ] install smoke from built artifacts recorded
- [ ] CLI quickstart smoke from built artifacts recorded
- [ ] Python SDK quickstart smoke from built artifacts recorded
- [ ] release evidence bundle records date, commands, environment, commit/version, and exclusions

## Status Reporting Rules

Use the following conservative language:

- `implemented` for documentation or repository surfaces that already exist
- `partial` when the contract artifact exists but release evidence is incomplete
- `verified` only when the relevant regression tests or recorded release evidence actually exist
- do not claim public-release readiness until the missing publication items above are closed
