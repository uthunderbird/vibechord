# ADR 0031: Installed CLI Launch Mode And Local Project Profile Discovery

## Decision Status

Accepted

## Implementation Status

Implemented

Implementation grounding on 2026-04-13:

- `implemented`: local project discovery uses `operator-profile.yaml` in the launch directory
- `implemented`: installed CLI startup preserves the launch directory as the working-directory
  anchor unless explicitly overridden
- `implemented`: no-profile startup follows an explicit free-mode stub path rather than pretending
  the full interactive harness already exists
- `verified`: startup/profile-discovery behavior is covered in `tests/test_runtime.py` and
  `tests/test_cli.py`

## Context

`operator` already has:

- a Python package shape with a console script entrypoint,
- accepted bounded project profiles,
- and an attached-first runtime direction.

But the current launch model still assumes too much repository-local and operator-local context.

In particular:

- users should be able to install `operator` as a Python package and run `operator` from any directory,
- the default working directory should be the directory from which the user launched the CLI,
- the CLI should discover project defaults from a local profile file in that directory,
- and the system should still remain transparent about whether it is running with a project profile or in a profile-free mode.

The user also wants a future freeform mode where `operator` behaves more like a long-lived service with a TUI and direct user messages such as:

- “launch Codex and supervise it while it rewrites all tests under these rules ...”

However, that freeform service mode is lower priority than package-installed project mode.

The immediate decision is therefore not “design the full freeform harness now.”
It is:

- define how installed CLI startup works,
- define how local profile discovery works,
- define how working-directory defaults behave,
- and define what the initial free mode means before the true TUI service exists.

This ADR must fit the already accepted profile direction from ADR 0018 without collapsing project profiles into hidden runtime state.

## Decision

`operator` will support an installed CLI launch mode centered on the current shell directory and a local project profile file named `operator-profile.yaml`.

The initial launch semantics are:

1. The CLI is expected to be runnable as an installed console command: `operator`.
2. Unless the user explicitly overrides the working directory, the effective working directory is the current shell directory from which `operator` was launched.
3. On startup, the CLI looks for `operator-profile.yaml` in that launch directory.
4. If `operator-profile.yaml` exists, the run starts in project-profile mode using that local profile.
5. If no local profile exists, the run starts in free mode.
6. Initial free mode is intentionally a stub, not the final true-harness product surface.

### Local Profile Discovery

The local profile file is:

- `operator-profile.yaml`

The first discovery rule is intentionally narrow:

- check only the launch directory,
- do not walk parent directories yet,
- and do not silently merge multiple profile sources.

This keeps profile selection obvious and reproducible.

### Working Directory Default

Default working directory resolution is:

1. explicit CLI working-directory override
2. otherwise the launch directory

Local profile discovery does not change the discovery root.
The launch directory remains the default workspace anchor.

A local profile may still describe paths and other defaults relative to that project directory, but the CLI should not silently reinterpret “where the user launched the command from” as something else unless an explicit override path is supplied.

### Relationship To Existing Named Profiles

The existing named-profile system from ADR 0018 remains valid.

The new local profile mode is complementary:

- named profiles remain reusable operator-managed defaults,
- local `operator-profile.yaml` becomes the zero-friction project entrypoint for installed use.

The system should not require users to register every project globally before using `operator` in that project directory.

Named profiles remain available through explicit `--project`, but they are no longer part of implicit
local auto-discovery.

### Initial Free Mode

If no `operator-profile.yaml` exists, the CLI enters free mode.

But the first version of free mode is explicitly limited.

Initial free mode should:

- acknowledge that no local project profile was found,
- show that the effective working directory is the current directory,
- and exit through a clear stub path that explains the missing higher-level surface.

It should not pretend that the true interactive service/TUI already exists.

The user-facing message should make clear that:

- project mode is available today via `operator-profile.yaml`,
- and freeform live supervision mode is planned but not yet implemented.

### Future TUI Boundary

The intended long-term freeform product remains:

- a long-lived attached operator service,
- a TUI control surface,
- live user messages to the operator,
- and transparent monitoring plus intervention.

But that is a follow-up tranche.

This ADR explicitly does **not** require implementing the full TUI or message-driven service mode now.
The initial free-mode stub exists to reserve that product concept without faking completeness.

## Rationale

This decision wins because it gives the project a clean installed-package story without overcommitting to the full freeform harness in the same slice.

It optimizes for the high-priority path:

- package install,
- run from any folder,
- automatic local project discovery,
- and honest behavior when no project profile exists.

It also preserves transparency:

- users can tell whether they are in local-profile mode or free mode,
- the working directory default is predictable,
- and the CLI does not hide profile source selection behind parent walking or silent merging.

## Alternatives Considered

### Option A: Keep only explicit globally named profiles

Rejected because:

- it keeps first-run friction too high,
- it assumes operator-managed global configuration before project-local use,
- and it is weaker for the common workflow “cd into project, run operator.”

### Option B: Add local `operator-profile.yaml` discovery in the launch directory and keep free mode as a stub

Accepted because:

- it gives the package-installed CLI an immediate project-local UX,
- it keeps discovery simple and inspectable,
- and it does not require shipping the full freeform TUI in the same slice.

### Option C: Implement full freeform service + TUI first

Rejected for now because:

- it is materially larger than the packaging and launch problem,
- it would mix product-surface design with a simpler launch-mode decision,
- and it risks delaying the high-value project-profile path.

### Option D: Search parent directories for profiles from the start

Rejected for the first slice because:

- it adds ambiguity about which project root is active,
- it makes launch semantics less obvious,
- and it can be introduced later if the simple discovery rule proves too narrow.

## Consequences

### Positive

- `operator` gets a credible installed-package launch story.
- Project use becomes as simple as “install, cd into repo, run `operator`.”
- Local project onboarding friction drops.
- Users can distinguish clearly between profile-backed project mode and profile-free mode.
- The future freeform service/TUI concept is acknowledged without pretending it already exists.

### Negative

- There will be two profile entry paths:
  - explicit named profiles via `--project`,
  - and local `operator-profile.yaml`.
- The first free mode is intentionally incomplete and may feel abrupt.
- Some users will expect parent-directory discovery and not get it initially.
- Existing users of implicit local auto-discovery through `.operator/projects` will need to switch to
  either explicit `--project` or local `operator-profile.yaml`.

### Follow-Up Implications

- CLI startup needs an explicit launch-mode resolver.
- The profile loader needs a local-file code path in addition to named-profile lookup.
- The resolved run configuration should record whether it came from:
  - local profile,
  - named profile,
  - or free mode.
- Documentation should describe free mode honestly as a stub.
- A later ADR should define the true freeform attached service and TUI surface.

## Non-Goals

This ADR does not define:

- the full freeform TUI interaction model,
- parent-directory project-root discovery,
- profile merging between local and global sources,
- daemonization strategy,
- or the final operator-as-service lifecycle.

Those belong to later ADRs.
