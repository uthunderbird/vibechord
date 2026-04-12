# Configuration Reference

This document is the committed reference for operator data-dir resolution and the current
project-profile schema contract.

## Operator Data Directory

By default, runtime state lives under `.operator/`.

Resolution order:

1. absolute configured `data_dir`
2. explicitly configured relative `data_dir`
3. nearest ancestor existing `.operator/`
4. nearest git root plus `.operator/`
5. current directory plus `.operator/`

## Project Profile Files

Committed project profiles:

- `operator-profile.yaml`
- `operator-profiles/*.yaml`

Local runtime-only profiles:

- `.operator/profiles/*.yaml`

## Run Resolution Order

For `operator run`, the binding resolution order is:

1. explicit CLI flag
2. project profile value
3. global default or hardcoded application default

The current resolved run fields are:

- `cwd`
- `history_ledger`
- `objective_text`
- `default_agents`
- `harness_instructions`
- `success_criteria`
- `max_iterations`
- `run_mode`
- `involvement_level`
- `session_reuse_policy`
- `message_window`

`operator project resolve` is the inspection surface for these resolved run defaults.

## Project Profile Schema

### Stable profile fields

- `name`: profile identifier
- `cwd`: working directory associated with the profile
- `history_ledger`: whether completed operations append to `operator-history.jsonl`
- `default_objective`: default objective used when `operator run` is invoked without a goal
- `default_agents`: default agent list
- `default_harness_instructions`: default harness text
- `default_success_criteria`: default success-criteria list
- `default_max_iterations`: default iteration cap
- `default_run_mode`: default run mode
- `default_involvement_level`: default involvement level
- `default_message_window`: default operator-message window

### Stable but non-run-resolved fields

- `paths`: deferred field reserved in the schema; `project inspect` does not surface stored values
- `adapter_settings`: typed per-adapter override map applied only to known adapter settings fields
  with shared documented keys:
  - `timeout_seconds`
  - `mcp_servers`

### Stub or deferred fields

- `dashboard_prefs`: deferred field reserved in the schema; `project inspect` does not surface
  stored values

## Session Reuse Policy

Accepted values:

- `always_new`
- `reuse_if_idle`

`reuse_if_idle` allows the operator to reuse an existing idle non-one-shot session for the same
adapter instead of starting a new session. `always_new` forces a fresh session.

## Runtime Defaults

If no profile overrides are provided:

- default run mode: `attached`
- default involvement level: `auto`
- default message window: `3`
- default max iterations: `100`
