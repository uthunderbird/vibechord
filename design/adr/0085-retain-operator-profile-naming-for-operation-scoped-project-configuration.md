# ADR 0085: Retain operator-profile naming for operation-scoped project configuration

## Status

Accepted

## Context

[`RFC 0010`](../rfc/0010-async-runtime-lifecycles-and-session-ownership.md)
currently prefers `operation-profile` over `operator-profile` for configuration and policy that
shape one operation's behavior.

Repository truth does not match that preference:

- the repository already uses `operator-profile` naming in code, CLI behavior, tests, and docs
- no rename migration is currently planned or staged
- the repository is pre-release, but renaming still has repo-wide churn cost and documentation risk

The open question is whether the RFC should drive a rename, or whether the repository should retain
current naming and revise the RFC to match truth.

### Current truth

`operator-profile` is the existing repository term and filename surface. The repo does not currently
expose `operation-profile` as a parallel canonical contract.

## Decision

The repository retains `operator-profile` as the canonical name for operation-scoped project
configuration.

### Scope interpretation

Retaining the name does not widen the scope.

`operator-profile` remains operation-scoped in meaning when used to shape one operation's planning,
permissions, or runtime behavior.

### RFC correction

`RFC 0010` is revised alongside this ADR to remove the normative preference for
`operation-profile` and describe `operator-profile` as retained repository truth.

### Rename policy

A repository-wide rename from `operator-profile` to `operation-profile` is not part of the current
ADR batch and is explicitly not assumed as upcoming implementation work.

## Verification

- `verified`: repository truth uses `operator-profile` in CLI-facing behavior, runtime discovery,
  tests, and adjacent architecture docs.
- `verified`: no parallel canonical `operation-profile` contract exists in code or documentation.

## Closure notes

This ADR is accepted as a documentation-alignment decision, not as a code-migration ADR.

The repository already exposed `operator-profile` as canonical truth before this ADR wave. Closing
the ADR therefore required:

- confirming repository truth across code, tests, and docs
- revising `RFC 0010` to remove the now-false normative preference for `operation-profile`
- updating the roadmap so the naming boundary is no longer shown as open

## Consequences

- Repository truth and future runtime ADRs can proceed without carrying a speculative rename.
- The naming mismatch between RFC 0010 and current code/docs becomes explicit instead of lingering
  as silent debt.
- Future contributors do not need to guess whether `operator-profile` is transitional.

## This ADR does not decide

- the exact wording changes to RFC 0010
- whether a future superseding ADR may revive a rename for a different reason
- profile schema details or file layout

This ADR only fixes the naming boundary for the current architecture wave.

## Alternatives Considered

### Rename everything to `operation-profile`

Rejected. The repository does not currently need the churn, and the conceptual gain is too small to
justify a rename wave right now.

### Keep the mismatch implicit

Rejected. That leaves RFC truth and repository truth in conflict and makes later closure criteria
ambiguous.
