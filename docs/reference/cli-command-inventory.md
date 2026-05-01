# CLI Command Inventory

This page is the canonical command inventory for ADR 0210. It records whether each public CLI path
is currently treated as `stable`, `transitional`, or `debug-only`.

`stable` means the command is part of the intended user-facing or machine-facing surface.
`transitional` means the command still exists, but the repository does not want new workflows to
depend on it as the long-term shell contract.
`debug-only` means the command is intentionally scoped to debug, repair, or verification work.

## Stable commands

ADR 0219 splits stable root commands into two sets:

- canonical root commands: the intended small root workflow surface;
- grouping backlog commands: still stable and callable, but intended to move behind grouped
  namespaces before the final CLI shape is claimed.

### Lifecycle

- `run`
- `init`
- `clear`
- `fleet`

### Control

- `answer`
- `cancel`
- `converse`
- `edit`
- `edit criteria`
- `edit execution-profile`
- `edit harness`
- `edit involvement`
- `edit objective`
- `interrupt`
- `message`
- `pause`
- `unpause`

### Read / supervision

- `ask`
- `fleet agenda`
- `fleet history`
- `fleet list`
- `show`
- `show artifacts`
- `show attention`
- `show dashboard`
- `show log`
- `show memory`
- `show report`
- `show session`
- `show tasks`
- `status`
- `watch`

### Project / policy / admin / integration

- `agent`
- `agent list`
- `agent show`
- `config`
- `config edit`
- `config set-root`
- `config show`
- `mcp`
- `policy`
- `policy explain`
- `policy inspect`
- `policy list`
- `policy projects`
- `policy record`
- `policy revoke`
- `project`
- `project create`
- `project dashboard`
- `project inspect`
- `project list`
- `project resolve`

## ADR 0219 canonical root surface

- `agent`
- `answer`
- `ask`
- `cancel`
- `clear`
- `config`
- `edit`
- `fleet`
- `init`
- `interrupt`
- `mcp`
- `message`
- `pause`
- `policy`
- `project`
- `run`
- `show`
- `status`
- `unpause`
- `watch`

## ADR 0219 grouping backlog

### Other grouping candidates

- `converse`

## Transitional commands

These paths remain callable, but the canonical homes are under `operator debug` or other stable
surfaces.

- `daemon` -> use `debug daemon`
- `agenda` -> use `fleet agenda`
- `artifacts` -> use `show artifacts`
- `attention` -> use `show attention`
- `command` -> use `debug command`
- `context` -> use `debug context`
- `dashboard` -> use `show dashboard`
- `history` -> use `fleet history`
- `inspect` -> use `debug inspect`
- `involvement` -> use `edit involvement`
- `list` -> use `fleet list`
- `log` -> use `show log`
- `memory` -> use `show memory`
- `patch-criteria` -> use `edit criteria`
- `patch-harness` -> use `edit harness`
- `patch-objective` -> use `edit objective`
- `recover` -> use `debug recover`
- `report` -> use `show report`
- `resume` -> use `debug resume`
- `session` -> use `show session`
- `set-execution-profile` -> use `edit execution-profile`
- `sessions` -> use `debug sessions`
- `stop-turn` -> use `interrupt`
- `tasks` -> use `show tasks`
- `tick` -> use `debug tick`
- `trace` -> use `debug trace`
- `wakeups` -> use `debug wakeups`

## Debug-only commands

### Debug / repair

- `debug`
- `debug command`
- `debug context`
- `debug daemon`
- `debug event`
- `debug event append`
- `debug inspect`
- `debug recover`
- `debug resume`
- `debug sessions`
- `debug tick`
- `debug trace`
- `debug wakeups`

### Verification / live smoke

- `smoke`
- `smoke alignment-post-research-plan`
- `smoke alignment-post-research-plan-claude-acp`
- `smoke codex-continuation`
- `smoke mixed-agent-selection`
- `smoke mixed-agent-selection-claude-acp`
- `smoke mixed-code-agent-selection`
- `smoke mixed-code-agent-selection-claude-acp`
