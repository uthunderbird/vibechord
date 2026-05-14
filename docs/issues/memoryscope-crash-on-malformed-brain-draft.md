# Operation crashes after successful agent turn: `MemoryScope('task:<uuid>')` raises ValueError

## Summary

After an agent run completes successfully and produces artifacts, operator
crashes in `application/agent_results.py:543` while persisting task memory:

```
ValueError: 'task:2ec9c1f6-0f83-4dee-898a-b146ae11e02e' is not a valid MemoryScope
```

The operation flips from successful agent turn to **FAILED** status with the
artifacts on disk but no follow-up iteration. The brain returns a malformed
`scope` field in its memory draft (concatenates `scope:` and `scope_id`),
and the call site does not validate / normalize before constructing the enum.

## Reproduction

1. `operator-profile.yaml` with `claude_acp` as agent, `codex_brain` model
   `gpt-5.3-codex-spark`, `effort: low`.
2. Issue a substantial objective. Agent completes one full turn and writes
   artifacts to disk.
3. operator attempts to distill task memory from artifact, brain returns a
   draft with `scope="task:<task_id>"` instead of `scope="task"`.
4. `MemoryScope(draft.scope)` raises, operation transitions to FAILED.

Two observed crash payloads from real runs:

**Crash 1** — operation `0e3896e0-ef42-44bd-9457-284b833d8189`, brain returned
`scope_id` concatenated onto `scope`:

```
ValueError: 'task:2ec9c1f6-0f83-4dee-898a-b146ae11e02e' is not a valid MemoryScope
```

**Crash 2** — operation `603eac13-860c-491d-b16e-20515c336161` (same brain
model `gpt-5.3-codex-spark`, ~30 min later, fresh session), brain returned
a **full English sentence** as `scope`:

```
ValueError: 'R2B Step-3.1 kThresholdGapSource discharge status for Erdős #625' is not a valid MemoryScope
```

Same call site each time:

```
File ".../application/agent_results.py", line 172, in handle_agent_result
    await self.refresh_task_memory(state, task, artifact)
File ".../application/agent_results.py", line 543, in refresh_task_memory
    scope=MemoryScope(draft.scope),
File ".../enum.py", line 1193, in __new__
    raise ve_exc
```

The two payloads confirm the brain treats `scope` as a freeform description
field, not as the enum it actually is. The schema is not constraining the model.

Operation status afterward:

```
FAILED · iter 0/100
Progress: Doing: background turn started
Attention: none
```

(No `attention` request raised, so the user has no signal to act on — the
operation just sits dead.)

## Reproducibility

The same `gpt-5.3-codex-spark` model hit the bug **twice in one session** on
unrelated tasks. The malformed payload differs each time (uuid-concat in one,
free sentence in the other), so any code-side fix must accept that `draft.scope`
can be **any string** at the call site. D1 (defensive skip) or D2 (split on `:`)
will not catch the free-sentence case — only **D3 (schema enforcement)** or
**D1 + free-form fallback to a default scope** are sufficient.

## Root cause

`agent_results.py:520-549` (`refresh_task_memory`):

```python
draft = await self._operator_policy.distill_memory(
    state,
    scope=MemoryScope.TASK.value,    # passed in as "task"
    scope_id=task.task_id,           # passed in as <uuid>
    ...
)
...
entry = MemoryEntry(
    scope=MemoryScope(draft.scope),  # ← crashes if draft.scope is malformed
    scope_id=draft.scope_id,
    ...
)
```

Two problems:

1. **Brain returns malformed `scope`.** `gpt-5.3-codex-spark` (and likely other
   brain models) sometimes returns `scope="task:<scope_id>"` — the prompt or
   schema apparently encourages it to encode `scope` and `scope_id` jointly.
   This is **brain-side**: either the structured-output JSON schema for
   `distill_memory` allows freeform strings, or the prompt example shows the
   concatenated form.

2. **Operator has no validation / normalization.** A malformed brain response
   should not crash the operation. The call site should either:
   - validate the draft against the enum *before* mutating state, and treat a
     failure as a soft error (log + skip the memory write + keep the
     successful agent turn), or
   - normalize `task:<id>` → scope=`"task"`, scope_id=`<id>` when both
     components are present, or
   - reject the draft and ask the brain to resubmit (within iteration budget).

Currently neither happens, so a single bad brain response loses the entire
iteration's progress.

## Impact

- Loss of iteration progress: in the reproducer, the agent successfully
  produced two substantial artifacts (10.8K and 7.2K markdown files
  representing real research output); operator threw all of it away from a
  routing standpoint and stopped iterating.
- Silent failure: no `attention` request, no human-visible signal except
  `operator status` showing FAILED. A long-running operation can sit dead
  for hours unnoticed.
- Wasted brain + agent tokens: the failing iteration consumed full quota of
  both, then refused to make progress on the next iteration.

## Proposed fix — defensive (D1, minimal)

Wrap the enum coercion and continue without crashing:

```python
try:
    coerced_scope = MemoryScope(draft.scope)
except ValueError:
    logger.warning(
        "brain returned malformed memory scope %r; skipping memory write for task %s",
        draft.scope,
        task.task_id,
    )
    return  # successful agent turn is preserved
entry = MemoryEntry(
    scope=coerced_scope,
    ...
)
```

~5 lines. Preserves the agent turn, logs the malformed response, lets
operator continue to the next iteration.

## Proposed fix — normalizing (D2, complementary)

If `draft.scope` matches `<enum_value>:<id>` and `draft.scope_id` is empty or
matches the suffix, split and accept:

```python
def _normalize_memory_scope(raw_scope: str, raw_scope_id: str | None) -> tuple[MemoryScope, str | None]:
    raw_scope = (raw_scope or "").strip()
    if ":" in raw_scope:
        prefix, _, suffix = raw_scope.partition(":")
        try:
            enum_value = MemoryScope(prefix)
        except ValueError:
            raise
        scope_id = raw_scope_id or suffix or None
        return enum_value, scope_id
    return MemoryScope(raw_scope), raw_scope_id
```

Recovers the brain's malformed-but-recoverable case as a success path.

## Proposed fix — schema (D3, root-cause)

Tighten the structured-output JSON schema for `distill_memory` so that
`scope` accepts only the four enum values. pydantic-settings / structured
output frameworks will reject the malformed payload at the brain boundary,
forcing a retry from a clean state instead of letting the bad value
propagate.

In `providers/codex.py` (or wherever `distill_memory` builds its schema),
the `scope` field should be `Literal["objective", "task", "session", "project"]`
or `enum: [...]` in the JSON schema. Verify that the strict schema mode
(`build_strict_json_schema`) is being used here.

## Proposed fix — surface as attention (D4, UX)

When operator decides not to crash but the draft is unusable, raise an
`attention` request so the user sees "brain produced malformed memory
draft; operator continued without it" instead of silent FAILED state.

## Acceptance criteria

- [ ] A brain response with `scope="task:<uuid>"` does not crash the
      operation; the agent turn's artifacts and progress are preserved.
- [ ] Either D1 (skip) or D2 (normalize) is implemented as the immediate
      patch; D3 is implemented to remove the bug class at the brain boundary.
- [ ] Regression test: simulate `distill_memory` returning malformed scope;
      verify operation continues and iteration counter advances.
- [ ] If skipping, a log warning is emitted with the offending value and
      task_id for diagnostics.

## Related context

- Discovered in the `erdos-625` research project on 2026-05-11 while running
  operator with `claude_acp` agent (model=default = Opus 4.7[1m]) and
  `codex_brain` model `gpt-5.3-codex-spark`. Operations
  `0e3896e0-ef42-44bd-9457-284b833d8189` and
  `603eac13-860c-491d-b16e-20515c336161` (~30 min apart, same brain model,
  different malformed payloads).
- Companion issue: "Project profile silently overrides env vars for adapter
  settings" — both were discovered in the same session debugging why a
  promising research operation failed after one good iteration.
