# ADR 0219: CLI Surface Reduction And Command Family Consolidation

- Date: 2026-05-01

## Decision Status

Proposed

## Implementation Status

Partial

Implementation grounding on 2026-05-02:

- `implemented`: the intended ADR 0219 canonical root surface is now represented as a checked-in
  CLI inventory constant rather than only prose. Evidence:
  `src/agent_operator/cli/command_inventory.py`.
- `implemented`: the current stable root commands that should move behind grouped namespaces are
  represented as an explicit grouping backlog. Evidence:
  `src/agent_operator/cli/command_inventory.py`,
  `docs/reference/cli-command-inventory.md`.
- `implemented`: the edit/mutation family has a grouped stable namespace:
  `edit objective`, `edit harness`, `edit criteria`, `edit execution-profile`, and
  `edit involvement`. The previous root mutation paths remain callable while the migration
  proceeds; root patch paths are classified as transitional compatibility aliases.
  Evidence: `src/agent_operator/cli/commands/operation_control.py`,
  `src/agent_operator/cli/command_inventory.py`.
- `implemented`: operation-detail read surfaces now have a grouped stable `show ...` namespace for
  attention, tasks, memory, artifacts, report, dashboard, log, and session. The existing root read
  commands remain callable while the migration proceeds. Evidence:
  `src/agent_operator/cli/commands/operation_detail.py`,
  `src/agent_operator/cli/commands/operation_detail_log.py`,
  `src/agent_operator/cli/commands/operation_detail_session.py`.
- `implemented`: fleet inventory/read surfaces now have grouped stable paths:
  `fleet list`, `fleet history`, and `fleet agenda`. The existing root read commands remain
  callable but are now classified as transitional compatibility aliases. Evidence:
  `src/agent_operator/cli/commands/fleet.py`,
  `src/agent_operator/cli/command_inventory.py`.
- `verified`: command-inventory tests prove every registered stable root command is accounted for
  as either canonical root surface or grouping backlog, and prevent new stable root commands from
  bypassing ADR 0219 classification. Focused CLI tests cover the grouped edit commands delegating
  to the existing event-sourced command/control path, grouped show commands delegating to shared
  read payloads, grouped fleet commands delegating to the existing inventory/history/agenda read
  paths, and grouped edit-involvement delegating to the existing autonomy mutation path. Evidence:
  `tests/test_cli_command_inventory.py`, `tests/test_cli.py`.
- `planned`: natural-language grouping and operation-detail root-command migration remain open; no
  compatibility alias has been removed.

## Context

ADR 0210 closed the first CLI canon wave:

- every registered CLI path is now classified as `stable`, `transitional`, or `debug-only`;
- the repository has one checked-in command inventory and command-contract matrix;
- hidden alias debt is explicit instead of accidental.

That closure made one second-order problem easier to see:

- the CLI is contract-documented, but still too wide at the root;
- too many root-level stable commands answer adjacent user questions;
- transitional aliases still occupy top-level names even though their canonical homes already live
  under `debug`;
- several mutation and inspection families are flattened into sibling verbs instead of one
  coherent command family.

Current inventory truth on 2026-05-01:

- `83` total command paths
- `51` `stable`
- `11` `transitional`
- `21` `debug-only`

The main overlap families are:

1. **top-level transitional alias debt**
   - `resume`, `tick`, `daemon`, `recover`, `wakeups`, `sessions`, `inspect`, `context`,
     `trace`, `command`, `stop-turn`
2. **crowded root inspection/supervision surface**
   - `status`, `watch`, `dashboard`, `session`, `log`, `report`, `tasks`, `memory`,
     `artifacts`, `attention`, `list`, `agenda`, `history`
3. **flat edit/mutation trio**
   - `patch-objective`, `patch-harness`, `patch-criteria`
4. **overlapping natural-language interaction story**
   - `ask` and `converse`

The problem is no longer missing documentation. It is shell-shape complexity:

- there are too many peers at the same semantic level;
- too many root verbs compete as plausible answers to "what should I run next?";
- docs/help can hide some complexity, but cannot remove it while the root taxonomy stays flat.

## Decision

The CLI will move to a smaller canonical root surface and a more explicit command-family
taxonomy.

This decision has four parts:

1. **remove top-level transitional aliases from the public stable shell**
2. **keep only a small canonical root workflow surface**
3. **group secondary stable surfaces under explicit namespaces**
4. **treat migration aliases as temporary compatibility aids, not final taxonomy**

## Canonical Root Surface

The root command set should be intentionally small and answer only the primary workflow questions.

### Lifecycle and entry

- `operator` / `fleet`
- `run`
- `init`
- `clear`

### Primary operation interaction

- `status`
- `watch`
- `ask`
- `answer`
- `interrupt`
- `cancel`

### Essential operator control

- `message`
- `pause`
- `unpause`

### Stable administrative namespaces

- `project ...`
- `policy ...`
- `agent ...`
- `config ...`
- `mcp`

This root surface is the canonical user-facing shell story.

## Transitional Alias Removal

The following top-level paths should no longer remain part of the intended public shell:

- `resume`
- `tick`
- `daemon`
- `recover`
- `wakeups`
- `sessions`
- `inspect`
- `context`
- `trace`
- `command`
- `stop-turn`

Their canonical homes are already:

- `debug resume`
- `debug tick`
- `debug daemon`
- `debug recover`
- `debug wakeups`
- `debug sessions`
- `debug inspect`
- `debug context`
- `debug trace`
- `debug command`
- `interrupt`

If compatibility aliases remain temporarily, they must stay explicitly `transitional` and must not
be described as part of the final user-facing taxonomy.

## Secondary Stable Surfaces Must Be Grouped

Secondary stable surfaces remain useful, but should not all remain peer root verbs.

The intended direction is to group detailed inspection surfaces under one explicit family rather
than keep them flat at root.

Illustrative target families:

- operation-detail / show family
  - session
  - log
  - report
  - tasks
  - memory
  - artifacts
  - attention
- fleet/inventory family
  - list
  - agenda
  - history

The exact namespace names may be chosen during implementation, but the architectural rule is
stable:

> specialist read surfaces should be grouped by family, not exposed as a long flat list of root
> peers.

## Edit And Mutation Family Consolidation

The root patch family is too repetitive:

- `patch-objective`
- `patch-harness`
- `patch-criteria`

The intended direction is to collapse these into one explicit edit/mutation family instead of
three sibling root verbs.

Illustrative target shapes include:

- `edit objective`
- `edit harness`
- `edit criteria`

or another equivalent grouped form.

This ADR does not lock the exact spelling yet. It locks the requirement that the family be grouped.

## Natural-Language Surface Discipline

The repository should not keep two equally primary stable NL surfaces without a clear split.

The intended stable default is:

- `ask` as the canonical single-shot natural-language query surface

`converse` may remain as:

- an advanced interaction surface,
- a namespaced surface,
- or a later merged mode of `ask`,

but it should stop reading as a second equally primary default shell question-answer surface unless
implementation evidence justifies that distinction.

## Dashboard Demotion

The repository already has three live-supervision stories:

- `operator` / `fleet` as the flagship interactive supervision surface
- `watch` as the compact shell-native live follower
- `dashboard` as another richer live one-operation view

The intended direction is to demote `dashboard` from root-primary status.

This ADR does not require immediate deletion. It does require that:

- `dashboard` stop carrying root-level flagship semantics,
- docs/help stop presenting it as a co-equal primary live surface beside TUI and `watch`,
- and future CLI simplification evaluate whether it should migrate under a grouped detail family or
  be retired.

## Consequences

### Positive

- the root CLI story becomes smaller and easier to teach;
- help output aligns better with actual workflow priority;
- command discovery pressure moves from memorizing many sibling verbs to learning a few families;
- stable versus transitional versus debug-only boundaries become more meaningful in practice.

### Negative

- migration costs will touch docs, tests, examples, and some scripts;
- compatibility aliases may need one full transition wave;
- some power users will need to adjust muscle memory.

### Neutral

- this ADR does not by itself decide exact namespace spellings;
- this ADR does not require deleting useful capabilities, only reducing flat root exposure;
- project/policy/agent/config namespaces remain in scope but are not the primary simplification
  target.

## Implementation Plan

1. remove or hide top-level transitional aliases from the canonical shell story
2. define the grouped stable namespace(s) for detailed inspection
3. define the grouped stable namespace for objective/harness/criteria edits
4. migrate docs, examples, and tests to the grouped canonical paths
5. keep compatibility aliases only as explicit `transitional` aids during the migration window
6. retire compatibility aliases once the grouped paths are fully canonized and verified

## Verification Plan

- inventory regression proving the intended grouped canonical paths match the registered Typer tree
- contract-doc regression proving stable/transitional/debug classifications stayed truthful
- help-surface regression proving root help is materially smaller and keeps specialist/detail
  surfaces behind namespaces
- migration tests proving compatibility aliases, if retained temporarily, remain clearly
  transitional and do not re-enter the stable root set

## Related

- ADR 0093
- ADR 0204
- ADR 0210
- ADR 0212
