# ADR 0132: Workspace shell and lifecycle commands

- Date: 2026-04-10

## Status

Accepted

## Implementation Status

Partial

Skim-safe current truth on 2026-04-10:

- `implemented`: `operator`, `run`, `init`, and `clear` already exist as the workspace shell and
  lifecycle command family
- `implemented`: default CLI help and reference docs now teach these commands as one coherent
  workspace lifecycle
- `verified`: focused CLI help coverage now asserts the lifecycle framing and command descriptions
- `partial`: this ADR still does not close broader RFC 0014 shell-output examples or any future
  workspace-lifecycle UX refinements beyond help and docs

## Commands Covered

- `operator`
- `operator run`
- `operator init`
- `operator clear`

## Not Covered Here

- cross-operation supervisory snapshot rendering details
- project subgroup read/write commands
- one-operation control commands

## Context

The CLI already has accepted decisions for:

- fleet-first no-arg entry behavior
- project-backed run/init/profile workflow
- project-local runtime-state clearing

Those decisions were made in narrower slices and before RFC 0014 assembled the CLI as one coherent
shell.

The current vision now wants the CLI to feel like a lifecycle-coherent operator shell across:

- first run
- normal repeated work
- and workspace reset

Without a consolidating ADR, the shell-level commands risk feeling like unrelated utilities:

- `operator` as an entrypoint
- `run` as a launcher
- `init` as setup
- `clear` as cleanup

## Decision

The CLI should treat these commands as one workspace shell and lifecycle family.

### Shell entry

No-arg `operator` remains the primary shell entry.

Its role inside this ADR is not output grammar, but lifecycle posture:

- enter supervision when work exists
- orient the user when no work exists
- anchor the shell around the current workspace

### Start workflow

`run` remains the canonical start command for new work.

It should remain clearly distinct from:

- `init`, which prepares workspace configuration
- `clear`, which removes runtime state

### Setup workflow

`init` remains the first-run setup command for the workspace.

It owns project/operator initialization rather than operation launching.

### Reset workflow

`clear` remains the destructive workspace reset command.

It should continue to be treated as:

- project-local
- destructive
- confirmation-gated
- and explicitly separate from project profile configuration

## Lifecycle Model

The shell should present one coherent lifecycle:

1. prepare the workspace with `init`
2. start work with `run`
3. supervise work through `operator` / `fleet` / operation commands
4. reset stale local runtime state with `clear` when needed

This ADR does not require introducing a new subgroup for these commands.

The accepted model is lifecycle cohesion without additional naming hierarchy.

## Discoverability Rule

Help and docs should be able to explain these commands as one lifecycle family even though the
command names remain flat.

In particular:

- `init` should be taught as first-run setup
- `run` should be taught as start/resume user intent
- `clear` should be taught as workspace reset, not cache cleanup
- no-arg `operator` should be taught as default shell entry

## Consequences

Positive:

- shell entry, setup, launch, and reset are teachable as one lifecycle
- RFC 0014 lifecycle examples get an explicit ADR home
- future help/discoverability work can reference one shell-family authority

Tradeoffs:

- this ADR must reference several older slices rather than redefine them from scratch
- shell cohesion becomes an explicit product commitment rather than an incidental pattern

## Verification

Current evidence for the landed slice:

- `verified`: top-level `operator --help` now frames the workspace lifecycle explicitly and shows
  lifecycle-specific summaries for `run`, `init`, and `clear`
- `verified`: CLI reference now teaches `operator`, `run`, `init`, and `clear` as one workspace
  lifecycle family

The repository should preserve these conditions:

- `operator`, `run`, `init`, and `clear` are explainable as one workspace lifecycle
- `clear` remains confirmation-gated and refuses live/recoverable state without explicit escape
- shell/help surfaces do not frame `clear` as a generic cache cleaner

## Related

- [ADR 0093](./0093-cli-command-taxonomy-visibility-tiers-and-default-operator-entry-behavior.md)
- [ADR 0094](./0094-run-init-project-create-workflow-and-project-profile-lifecycle.md)
- [ADR 0122](./0122-project-operator-state-clear-command.md)
- [RFC 0014](../rfc/0014-cli-output-contract-and-example-corpus.md)
