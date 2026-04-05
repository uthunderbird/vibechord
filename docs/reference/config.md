# Configuration Reference

## Operator data directory

By default, runtime state lives under `.operator/`.

Resolution order:

1. absolute configured `data_dir`
2. explicitly configured relative `data_dir`
3. nearest ancestor existing `.operator/`
4. nearest git root plus `.operator/`
5. current directory plus `.operator/`

## Project profile files

Committed project profiles:

- `operator-profile.yaml`
- `operator-profiles/*.yaml`

Local runtime-only profiles:

- `.operator/profiles/*.yaml`

## Current profile fields

Supported profile fields include:

- `name`
- `cwd`
- `paths`
- `history_ledger`
- `default_objective`
- `default_agents`
- `default_harness_instructions`
- `default_success_criteria`
- `default_max_iterations`
- `default_run_mode`
- `default_involvement_level`
- `adapter_settings`
- `dashboard_prefs`
- `session_reuse_policy`
- `default_message_window`

## Runtime defaults

If no profile overrides are provided:

- default run mode: `attached`
- default involvement level: `auto`
- default message window: `3`
- default max iterations: `100`

For the design rationale and full profile direction, see `design/WORKFLOW-UX-VISION.md` and
`design/adr/0094-run-init-project-create-workflow-and-project-profile-lifecycle.md` in the
repository.
