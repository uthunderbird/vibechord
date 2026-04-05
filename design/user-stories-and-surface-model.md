# User Stories And Surface Model

## Purpose

This document captures the current product-facing UX model for `operator`:

- who the main users are,
- which stories matter most,
- how CLI and future TUI should differ,
- and when each surface should be preferred.

This document is a product companion to:

- [VISION.md](/Users/thunderbird/Projects/operator/design/VISION.md)
- [ARCHITECTURE.md](/Users/thunderbird/Projects/operator/design/ARCHITECTURE.md)
- [ADR 0031](/Users/thunderbird/Projects/operator/design/adr/0031-installed-cli-launch-mode-and-local-project-profile-discovery.md)
- [ADR 0038](/Users/thunderbird/Projects/operator/design/adr/0038-cli-authority-and-tui-supervisory-workbench.md)

## User Archetypes

### 1. Repo-Scoped Developer

Works inside one project repository and wants to launch and supervise work with minimal setup.

Primary values:

- fast startup
- predictable defaults
- shell-native workflows
- honest visibility into what the operator is doing

### 2. Power User / Automation-Oriented Developer

Uses `operator` as part of scripts, repeatable flows, and explicit control loops.

Primary values:

- reproducibility
- composability
- machine-readable output
- stable command semantics

### 3. Human Supervisor / Operator

Monitors one or many active operations, answers attention requests, and redirects work in
real time.

Primary values:

- live situational awareness
- quick triage
- low-friction intervention
- fast switching across active operations

### 4. Newcomer

Has not internalized the command set and needs a small number of obvious workflows.

Primary values:

- low cognitive load
- memorable entrypoints
- clear distinction between “start”, “watch”, and “inspect”

## Top-Level User Stories

### Project Entry

- As a repo-scoped developer, I want to `cd` into a project and run `operator` without
  registering global config first.
- As a user, I want the system to tell me whether it is running from a local profile or not.
- As a user, I want project defaults to stay inspectable and file-backed.

### Starting Work

- As a developer, I want to start an operation from the CLI with an explicit objective.
- As a developer, I want to constrain which agents may be used.
- As a developer, I want reproducible launch semantics that can be copied into scripts or CI.

### One-Operation Live Supervision

- As a developer, I want to see what one operation is doing while it runs.
- As a supervisor, I want to understand active focus, session state, attention, and recent
  events without reconstructing them manually.
- As a supervisor, I want to intervene with explicit controls such as pause, stop-turn,
  stop-operation, answer, or message.

### Cross-Operation Supervision

- As a supervisor, I want to know which operations need attention now.
- As a supervisor, I want a fleet-level view of health, blockage, and recent outcomes.
- As a supervisor, I want to jump quickly from fleet-level overview to one-operation detail.

### After-The-Fact Inspection

- As a developer, I want a concise handoff summary after a run.
- As a developer, I want to inspect why the operator made certain decisions.
- As a power user, I want direct access to durable task, memory, and artifact state.

## Surface Model

## CLI

The CLI is the authoritative control surface.

It should be preferred when the user needs:

- an explicit action,
- a reproducible workflow,
- shell-native use,
- scripting or automation,
- precise inspection,
- or a command that must exist independently of any live UI.

The CLI should feel organized around a small number of workflow groups:

- **start work**
  - `run`
- **watch and control one operation**
  - `watch`
  - `dashboard`
  - `context`
  - live control commands
- **supervise many operations**
  - `agenda`
  - `fleet`
- **inspect durable truth**
  - `report`
  - `inspect`
  - `trace`
  - `tasks`
  - `memory`
  - `artifacts`
- **manage defaults**
  - `project ...`
  - `policy ...`

### CLI Preference Rules

Prefer the CLI when:

- the user is starting work,
- the action should be copyable into docs or scripts,
- the user is operating in CI or remote shell environments,
- the user needs exact and auditable control,
- or the interaction is one-shot rather than persistent.

## TUI

The future TUI is a persistent supervisory workbench, not a second control architecture.

It should be preferred when the user needs:

- continuous awareness over time,
- a fleet-level cockpit,
- fast switching across many operations,
- attention triage,
- or repeated live drill-down and intervention during an active supervision session.

### TUI Preference Rules

Prefer the TUI when:

- the user is supervising for an extended period,
- several operations are live at once,
- the main problem is orientation rather than command recall,
- or fast navigation between monitoring and intervention matters more than shell copyability.

### TUI Boundaries

The TUI should:

- reuse the same persisted truth as CLI surfaces,
- expose the same underlying control actions,
- and avoid TUI-only semantics.

The TUI should not:

- become the only place to perform important actions,
- hide the authoritative command path,
- or require a user to adopt a full-screen interface for basic success.

## Recommended Default Journey

For most users, the preferred journey should be:

1. install `operator`
2. `cd` into a repo
3. rely on local `operator-profile.yaml` when present
4. start work from the CLI
5. use CLI live surfaces for one-run monitoring
6. graduate to a TUI later only when persistent supervision becomes valuable

## Implications For Future Design

- The CLI should keep first-run success simple and memorable.
- Surface overlap should be reduced by documenting each command by job, not by internal data.
- Future TUI work should optimize for supervision speed, not parity for parity’s sake.
- Every major TUI panel should have a clear lineage back to existing CLI read models such as
  `agenda`, `fleet`, `dashboard`, `watch`, and `context`.
