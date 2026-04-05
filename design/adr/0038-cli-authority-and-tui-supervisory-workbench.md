# ADR 0038: CLI Authority And TUI Supervisory Workbench

## Status

Accepted

## Context

`operator` now has enough direct usage experience to evaluate its product UX shape from real
operation rather than from abstraction alone.

The current architecture and accepted ADRs already establish several important facts:

- the project is explicitly CLI-first,
- installed project-local use via `operator-profile.yaml` is the preferred near-term entry path,
- one-operation and cross-operation live views already exist as CLI surfaces,
- and future TUI work is expected to reuse persisted runtime truth rather than invent a second
  control model.

At the same time, the product surface has grown:

- `run`
- `watch`
- `agenda`
- `fleet`
- `dashboard`
- `context`
- `inspect`
- `report`
- task/memory/artifact inspection
- project and policy commands
- explicit live controls such as pause, stop-turn, stop-operation, and answer routing

This creates a product question that code alone does not settle:

- is the CLI the authoritative control plane, with TUI as a later supervisory workbench,
- or should CLI and TUI be treated as co-equal primary operating surfaces?

That choice materially affects:

- documentation,
- command organization,
- future TUI scope,
- user onboarding,
- and the boundary between deterministic command semantics and live visual workbenches.

## Decision

`operator` will treat the CLI as the authoritative control surface and a future TUI as a
supervisory workbench layered over the same persisted truth.

The product split is:

1. **CLI is preferred for**
   - starting work,
   - explicit control actions,
   - scripting and automation,
   - CI and non-interactive execution,
   - deterministic inspection,
   - and any workflow that must be reproducible, copyable, or shell-native.

2. **TUI is preferred for**
   - persistent live supervision,
   - cross-operation monitoring,
   - attention triage,
   - fast drill-down between operations,
   - and low-friction intervention during active supervision sessions.

3. **TUI must not invent new control semantics.**
   Any meaningful control exposed by the TUI must map to the same underlying command and
   persisted runtime truth already used by the CLI.

4. **CLI remains the product’s first successful-user path.**
   A user should be able to install `operator`, enter a project directory, and complete core
   workflows without needing the TUI.

## UX Model

The product should be explained through three recurring user moments:

1. **Start an operation**
2. **Stay oriented while it runs**
3. **Intervene or review afterward**

The CLI owns all three moments.
The TUI is a later optimization for the second and parts of the third.

### CLI UX Shape

The CLI should be organized by user intent rather than by internal storage objects.

Primary intent groups:

- **start work**
  - `run`
  - project/profile resolution and setup
- **monitor and control one operation**
  - `watch`
  - `dashboard`
  - `context`
  - live control commands
- **supervise many operations**
  - `agenda`
  - `fleet`
  - project-scoped dashboard variants
- **inspect durable truth**
  - `report`
  - `inspect`
  - `trace`
  - `tasks`
  - `memory`
  - `artifacts`
- **manage project defaults and policy**
  - project commands
  - policy commands

### TUI UX Shape

The future TUI should be a persistent operator cockpit built from the same read models already
used by:

- `agenda`
- `fleet`
- `dashboard`
- `context`
- `watch`

Its core jobs are:

- fleet glanceability,
- one-operation drill-down,
- attention triage,
- low-friction intervention,
- and fast navigation across active work.

It should not become a second architecture or a replacement for explicit CLI control.

## Alternatives Considered

### Option A: Treat CLI and TUI as co-equal primary surfaces

Rejected because:

- it creates ambiguity about which surface defines authoritative control behavior,
- it invites TUI-only semantics,
- and it weakens the current installed-package and shell-native story.

### Option B: Keep focusing only on CLI and defer TUI product thinking entirely

Rejected because:

- the architecture already anticipates future TUI work,
- the dashboard and fleet slices already imply a future cockpit direction,
- and ignoring that split now would increase drift later.

### Option C: CLI as authoritative control surface, TUI as supervisory workbench

Accepted because:

- it matches the current architecture,
- preserves reproducibility and automation,
- gives the TUI a concrete job instead of vague parity,
- and keeps all product surfaces grounded in one runtime truth model.

## Consequences

- Documentation should present CLI as the default entry and authority surface.
- Future TUI work should be evaluated by whether it materially improves supervision rather than
  whether it duplicates CLI coverage.
- CLI commands should be documented and organized around user workflows, not just implementation
  nouns.
- The product can support richer live experiences without weakening shell-native reliability.
- A companion product document should capture user stories and surface preferences explicitly.
