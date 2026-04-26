# ADR 0216: Public Release Contract And Distribution Acceptance Gate

- Date: 2026-04-27

## Decision Status

Accepted

## Implementation Status

Partial

Current grounding on 2026-04-27:

- `implemented`: the repository already has a canonical package identity in
  [`pyproject.toml`](../../pyproject.toml) with `name = "agent-operator"`.
- `implemented`: the repository already has a canonical public Python API boundary under
  [`ADR 0215`](0215-public-python-api-v2-canonicalization-and-v1-shell-retirement.md).
- `implemented`: the repository already has explicit v2 verification and cutover governance gates
  under [`ADR 0211`](0211-v2-end-to-end-verification-matrix.md) and
  [`ADR 0213`](0213-v2-cutover-governance-and-legacy-removal-acceptance-gate.md).
- `implemented`: this ADR now records the accepted publication gate, and
  [`RFC 0015`](../rfc/0015-public-release-contract.md) plus
  [`docs/reference/public-release.md`](../../docs/reference/public-release.md) now provide the
  canonical release-contract and publication-checklist artifacts referenced by this gate.
- `verified`: static regression coverage now fails if the canonical package identity, CLI identity,
  Python API identity, or stability-boundary references drift away from current repository truth
  across package metadata, README/public docs, CLI contract docs, and SDK docs. Evidence:
  `tests/test_public_release_docs.py`.
- `partial`: the repository still does not have a recorded release-grade wheel/sdist build, public
  install smoke, CLI quickstart smoke from built artifacts, Python SDK quickstart smoke from built
  artifacts, or a versioned release-notes/changelog artifact tied to one pinned publication wave.

## Context

The late v2 closure tranche already covers internal release readiness in several important ways:

- [`ADR 0194`](0194-v2-migration-strategy-full-rewrite.md) records the no-long-lived-
  compatibility rewrite strategy.
- [`ADR 0211`](0211-v2-end-to-end-verification-matrix.md) records the verification evidence
  required for v2 acceptance.
- [`ADR 0213`](0213-v2-cutover-governance-and-legacy-removal-acceptance-gate.md) records the
  governance gate for final destructive cutover and legacy removal.
- [`ADR 0215`](0215-public-python-api-v2-canonicalization-and-v1-shell-retirement.md) records the
  canonical public Python entrypoint family.

That package is still not enough to make the repository honestly publishable as a public package
and CLI.

Public publication is a distinct decision surface from internal cutover:

- the repository needs one canonical public install story
- the repository needs one canonical CLI surface and one canonical Python API surface
- the repository must say what is stable versus experimental in public release claims
- the repository must name the minimum release artifacts and the minimum publication evidence
- the repository must block publication when those public-facing properties are not true, even if
  some internal v2 tranche evidence is otherwise green

Without an explicit publication ADR, the repository can reach a state where v2 is internally
cutover-ready while public installation, support boundaries, and shipped-surface claims remain
implicit or scattered across packaging metadata, README text, reference docs, and internal notes.

## Decision

The repository adopts an explicit public release contract and distribution acceptance gate.

Public publication of `operator` may proceed only when all of the following are true:

1. **v2 cutover gate is satisfied.**
   - The repository state under publication satisfies the required cutover and verification
     constraints from ADR 0211 and ADR 0213 for the scope of the release claims being made.

2. **Canonical public surfaces are explicit and accurate.**
   - The public install surface, public CLI surface, and public Python API surface are all named
     canonically and agree with shipped repository truth.

3. **Stable versus experimental boundaries are explicit.**
   - Public docs and release materials distinguish stable surfaces from experimental ones and do
     not present experimental paths as the default stable contract.

4. **Release artifact set is complete.**
   - The required release artifacts for the public release exist and are reviewable.

5. **Public-install and quickstart evidence exists.**
   - At least one publication-grade install and quickstart smoke proves that the released artifact
     set works for the canonical public entrypoints being claimed.

6. **Release evidence is pinned.**
   - The release evidence records exact commit or version, commands run, date, environment
     assumptions, and known exclusions.

## Canonical Public Surfaces

The public release contract covers at least these canonical surfaces:

1. **Package identity**
   - package name: `agent-operator`

2. **CLI identity**
   - command name: `operator`

3. **Python API identity**
   - package import surface: `agent_operator`
   - canonical high-level client entrypoint: `agent_operator.OperatorClient`

## Required Release Artifact Set

The minimum public release artifact set includes:

- a wheel
- an sdist
- one versioned changelog or release-notes entry
- public quickstart/install documentation aligned with the released version

This ADR does not decide the exact publishing toolchain. It decides the contract that the release
artifact set must satisfy.

## Required Public Claims Boundary

The public release must explicitly define:

- supported Python version range
- minimum supported runtime assumptions for the public install path
- which run modes are stable versus experimental
- which adapters are stable versus experimental
- what is explicitly out of scope for public support claims

## Required Verification For Publication

The publication gate requires, at minimum:

- one repository-wide test run tied to the release state
- one build verification for the release artifact set
- one install smoke from the release artifact set
- one CLI quickstart smoke against the public CLI surface
- one Python API quickstart smoke against the canonical SDK surface
- any required live/operator evidence inherited from ADR 0211 for the public claim scope

## Failure Conditions

Public publication is blocked if any of the following are true:

- the v2 cutover or verification gates remain open for the claims being made
- the public install smoke fails
- public docs claim unsupported behavior as stable
- experimental surfaces are presented as stable defaults
- the public CLI contract or public Python API contract disagrees with the shipped artifact truth
- the release evidence is not pinned tightly enough to support the public claims

## Required Properties

- Public publication has a repository-level meaning, not an oral tradition.
- Internal v2 readiness and public publishability are related but not conflated.
- One canonical public install, CLI, and Python API contract exists for each public release.
- Stable-versus-experimental boundaries are explicit at release time.
- Public claims are limited to what the repository can actually verify and support.

## Verification Plan

Promotion of this ADR should require:

- one companion contract document describing the enduring public release contract
- one publication-oriented reference procedure or checklist tied to the accepted contract
- one review proving that package metadata, README quickstart, CLI reference, Python SDK reference,
  and release notes agree on the released public surface
- one recorded release-grade install and quickstart smoke tied to the release artifact set

Current repository evidence for this slice:

- [`docs/reference/public-release.md`](../../docs/reference/public-release.md) records the current
  canonical public identity, public-doc alignment contract, stable-versus-experimental boundary,
  and a conservative publication checklist that distinguishes implemented documentation work from
  still-missing release evidence.
- `tests/test_public_release_docs.py` statically checks that the contract doc remains aligned with
  `pyproject.toml`, `README.md`, `docs/reference/cli.md`,
  `docs/reference/cli-command-contracts.md`, and `docs/reference/python-sdk.md`.

## Related

- ADR 0194
- ADR 0211
- ADR 0213
- ADR 0215
- RFC 0015
