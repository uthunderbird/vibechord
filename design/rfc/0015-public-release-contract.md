# RFC 0015: Public Release Contract

## Status

Accepted

## Implementation Status

Partial

Current grounding on 2026-04-27:

- `implemented`: the repository already has a canonical package identity in
  [`pyproject.toml`](../../pyproject.toml) and a canonical public Python API boundary in
  [`ADR 0215`](../adr/0215-public-python-api-v2-canonicalization-and-v1-shell-retirement.md).
- `implemented`: the repository already has accepted v2 verification and cutover governance ADRs
  that public publication must depend on rather than replace.
- `implemented`: this RFC now serves as the accepted enduring publication contract, and
  [`docs/reference/public-release.md`](../../docs/reference/public-release.md) now provides the
  canonical public-facing reference/checklist artifact that executes the contract.
- `verified`: static regression coverage now fails if the public contract drifts away from current
  repository truth across package metadata, README/public docs, CLI contract docs, and SDK docs.
  Evidence: `tests/test_public_release_docs.py`.
- `partial`: the repository still lacks pinned release-notes/changelog evidence plus build/install
  smoke tied to one publication-grade wheel/sdist artifact set, so this RFC is not closed as
  `Implemented` or `Verified`.

## Purpose

Define one canonical public release contract for `operator`.

This RFC exists so that public publication truth does not remain fragmented across:

- package metadata
- README quickstart text
- CLI reference docs
- Python SDK reference docs
- internal strategy notes
- release-specific tribal knowledge

[`ADR 0216`](../adr/0216-public-release-contract-and-distribution-acceptance-gate.md) accepts the
publication gate. This RFC records the enduring contract that gate is meant to protect.

## Scope

In scope:

- canonical public identity
- canonical install surface
- canonical CLI surface
- canonical Python API surface
- release artifact expectations
- stable-versus-experimental boundaries
- documentation alignment requirements for public publication

Out of scope:

- step-by-step internal release procedure
- marketing or announcement strategy
- internal migration history
- low-level packaging tool choice unless it changes the public contract

## Canonical Public Identity

The public release contract for this repository is:

- project and CLI concept: `operator`
- pip package name: `agent-operator`
- CLI command: `operator`
- Python import package: `agent_operator`
- canonical high-level client entrypoint: `agent_operator.OperatorClient`

The public contract may describe additional import paths or advanced surfaces, but those must not
compete with this canonical identity.

## Canonical Release Artifacts

Each public release is expected to provide:

- a wheel
- an sdist
- versioned release notes or changelog entry
- public install and quickstart documentation aligned with the released version

If future releases add more artifacts, those artifacts extend rather than replace this minimum set
unless a later accepted decision changes the contract.

Current repository truth on 2026-04-27:

- public install and quickstart docs exist in `README.md` and `docs/quickstart.md`
- CLI and SDK reference docs exist in `docs/reference/cli.md`,
  `docs/reference/cli-command-contracts.md`, and `docs/reference/python-sdk.md`
- the repository does not yet expose a committed public release-notes/changelog artifact
- no publication-grade build/install smoke is recorded in this RFC slice

## Public Install Contract

The public install contract must define:

- the canonical installation command
- supported Python version range
- minimum environment assumptions for installation and first run
- what a user should expect to work immediately after install

The install contract must not rely on undocumented repository-local setup knowledge.

## Public CLI Contract

The public CLI contract must define:

- the canonical command family intended for public use
- which command families are stable
- which command families are transitional, debug-only, or otherwise non-public by default
- expectations for `--json` stability on the public command set

The public CLI contract must not silently treat internal or forensic-only surfaces as part of the
default stable release story.

## Public Python API Contract

The public Python API contract must define:

- the canonical stable entrypoint family
- the intended high-level machine-facing SDK surface
- which import paths remain internal even if technically importable
- the compatibility expectation for stable public imports

The public Python API contract extends, rather than reopens, the canonical boundary accepted under
ADR 0215.

## Experimental Surface Policy

Public publication must distinguish stable surfaces from experimental ones.

At minimum, the contract must define:

- how experimental adapters are labeled
- how experimental run modes are labeled
- where that experimental status must be visible
- that experimental paths are not presented as the default stable contract

## Documentation Alignment Contract

At publication time, the following must agree on the released public surface:

- package metadata
- README quickstart
- CLI reference docs
- Python SDK reference docs
- release notes or changelog entry
- any stability or experimental labels attached to the release

If these surfaces disagree, the release is not publication-ready by this contract.

For the current repository state before public publication, the canonical alignment checkpoint is
[`docs/reference/public-release.md`](../../docs/reference/public-release.md). That reference may
state that required publication artifacts or evidence are still missing, but it must not claim they
already exist when they do not.

## Release Claim Boundaries

The repository may publicly claim only what is supported by:

- accepted repository decisions
- verified tests or recorded verification evidence
- shipped documentation aligned with released artifact truth

The contract therefore forbids overclaiming experimental, partial, or unverified behavior as part
of the stable public release story.

## Relationship To ADR 0216

- ADR 0216 accepts the public publication gate and decision boundary.
- This RFC records the enduring release contract that public docs, artifacts, and release evidence
  must agree with.

## Follow-Up Artifacts

This RFC is now executed in part by:

- [`docs/reference/public-release.md`](../../docs/reference/public-release.md) as the canonical
  public release reference/checklist artifact
- `tests/test_public_release_docs.py` as the static regression anchoring that artifact to current
  repository truth

Remaining follow-up work still needed before public publication:

- one versioned release-notes/changelog artifact
- one release evidence template or recorded release report format
- one pinned build/install/quickstart evidence bundle tied to a publication wave
