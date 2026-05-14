# Project profile silently overrides env vars for adapter settings, inverting 12-factor convention

## Summary

`adapter_settings` in `operator-profile.yaml` are applied via an unconditional
`setattr` **after** `OperatorSettings()` has already loaded env vars, so a
committed project profile silently wins over `OPERATOR_*` env vars. This is
the opposite of the precedence convention used by pydantic-settings, terraform,
kubectl, docker, gcloud, ansible, and 12-factor apps generally.

The asymmetric defaults code path (`apply_global_user_defaults`) already gets
this right via a `model_fields_set` guard. Only `apply_project_profile_to_settings`
forces the override.

## Reproduction

Project `operator-profile.yaml`:

```yaml
adapter_settings:
  claude_acp:
    model: sonnet
    effort: medium
```

Invocation:

```sh
OPERATOR_CLAUDE_ACP__MODEL=default \
OPERATOR_CLAUDE_ACP__EFFORT=none \
uv run operator run --agent claude_acp "..."
```

**Expected** (12-factor / pydantic-settings convention): adapter uses
`default` / `none` because env > file.

**Actual**: adapter uses `sonnet` / `medium`. The ACP log shows
`session/set_model` being sent with `modelId: claude-sonnet-4-6` despite the
env vars. Silent override — no warning, no trace.

Confirmed by reading `runtime/profiles.py:215-238`:

```python
def apply_project_profile_to_settings(...):
    ...
    for adapter_key, overrides in profile.adapter_settings.items():
        target = getattr(settings, adapter_key, None)
        if target is None:
            continue
        payload = (
            overrides.model_dump(mode="json", exclude_none=True)
            if hasattr(overrides, "model_dump")
            else overrides
        )
        if not isinstance(payload, dict):
            continue
        for field_name, value in payload.items():
            if hasattr(target, field_name):
                setattr(target, field_name, value)   # ← forced, no guard
```

Compare with `apply_global_user_defaults` (config.py:209), which correctly
guards with `"codex_brain" not in settings.model_fields_set` — same pattern
should apply here.

## Impact

- Per-shell / per-CI env overrides for adapter model and effort are inert.
- Users who follow the documented `OPERATOR_*` env convention silently get a
  different model than they asked for. In this project's case, expensive Opus
  invocations silently fell back to Sonnet and consumed an unrelated rate-limit
  bucket, requiring code reading to diagnose.
- Breaks the symmetry with `codex_brain` settings (which respect env vars
  because they live on `OperatorSettings` directly, not under `adapter_settings`).

## Proposed canonical precedence

```
Lowest  → Code defaults
        → Global user config        (~/.operator/config.yaml)
        → Project committed config  (./operator-profile.yaml)
        → Project local config      (./operator-profile.local.yaml, optional, gitignored)
        → Environment variables     (OPERATOR_*)
        → CLI flags                 (--model, --effort, --adapter-set k=v)
Highest → In-conversation overrides (set-execution-profile, patch-objective)
```

Same rule as terraform, kubectl, docker, gcloud, ansible. Principle:
**more local + more per-invocation = higher precedence.**

## Proposed fix — minimal (B1)

Add a `model_fields_set` guard in `apply_project_profile_to_settings`:

```python
for field_name, value in payload.items():
    if hasattr(target, field_name) and field_name not in target.model_fields_set:
        setattr(target, field_name, value)
```

This makes env > profile while preserving profile > defaults. ~3 lines of code.

**Validation needed**: confirm that pydantic-settings marks env-sourced nested
fields as `model_fields_set` on the inner `BaseModel` (ClaudeAcpAdapterSettings,
etc.), not just on the outer `BaseSettings`. If not, the guard needs to inspect
the outer settings instance's `model_fields_set` for the adapter key.

A quick test:

```python
import os
os.environ["OPERATOR_CLAUDE_ACP__MODEL"] = "default"
from agent_operator.config import OperatorSettings
s = OperatorSettings()
print("outer:", s.model_fields_set)         # expected: {'claude_acp'}
print("inner:", s.claude_acp.model_fields_set)  # expected: {'model'} or similar
```

If the inner set is empty, fall back to a `field_sources` dict tracked
explicitly during load.

## Proposed fix — full (B2)

Track value source per field through load (struct `{field, value, source}`)
and apply layers in the canonical order. Expose via:

```sh
operator config show --trace
```

Sample output:

```
claude_acp.model = default
  ← env OPERATOR_CLAUDE_ACP__MODEL
  (was sonnet from project profile, was claude-sonnet-4-6 from code default)
claude_acp.effort = none
  ← env OPERATOR_CLAUDE_ACP__EFFORT
  (was medium from project profile)
codex_brain.model = gpt-5.3-codex-spark
  ← env OPERATOR_CODEX_BRAIN__MODEL
```

This solves both the override bug and the diagnostic gap (right now, diagnosing
"why is operator running with the wrong model" requires reading source code).

## Proposed fix — CLI flag (B3, complementary)

Add `--model` / `--effort` to `operator run` (and `--adapter-set k=v` for the
general case), highest precedence below in-conversation overrides:

```sh
operator run --agent claude_acp --model default --effort none "..."
```

Closes the "per-invocation override without editing files" case.

## Acceptance criteria

- [ ] `OPERATOR_CLAUDE_ACP__MODEL=default operator run ...` actually runs with
      `default` even when `operator-profile.yaml` sets `model: sonnet`.
- [ ] Regression test: env var > committed profile > global config > default.
- [ ] Same precedence holds for all four adapters (claude, claude_acp,
      codex_acp, opencode_acp) and for fields beyond `model` (`effort`,
      `permission_mode`, `command`, `timeout_seconds`).
- [ ] Docs updated (`docs/quickstart.md`, `docs/how-to/run-first-operation.md`,
      `docs/reference/`) to state the canonical order.

## Related context

- Discovered in the `erdos-625` research project on 2026-05-11 while trying to
  swap a long-running operator from Sonnet (rate-limited) to Opus 4.7[1m]
  (fresh quota). The env-var override silently failed; the operator burned
  ~iterations on the rate-limited account before the symptom surfaced.
- This issue also covers a documentation gap: nowhere in `docs/` is the
  precedence order stated, so the inversion was not catchable from docs alone.
