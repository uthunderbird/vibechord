# Codex brain returns invalid JSON for AgentTurnSummaryDTO structured-output → operation crashes

## Summary

`gpt-5.3-codex-spark` occasionally returns a JSON payload that fails strict
JSON parsing for the `AgentTurnSummaryDTO` schema in
`providers/codex.py:206`. The error propagates uncaught and crashes the
operation. Same brain model has hit two other malformed-structured-output
bugs in the same session (see related issues), so this is the third confirmed
case of brain payloads not respecting the JSON schema.

## Reproduction

Crash traceback tail from operation `4567a6aa-7341-47ee-8fef-f0d38cf0f1df`
(metadata-enrichment run, ~iter 29):

```
File ".../providers/codex.py", line 206, in _request_structured_output
    return cast(dict[str, Any], httpx.Response(200, content=text.e...
File ".../httpx/_models.py", line 832, in json
    return jsonlib.loads(self.content, **kwargs)
File ".../json/decoder.py", line 361, in raw_decode
    obj, end = self.scan_once(s, idx)
JSONDecodeError: Expecting ',' delimiter: line 1 column 811 (char 810)
```

The call stack:

```
codex.decide_next_action / map_decision_dto
  → codex._request_structured_output
    → httpx.Response(...).json()
      → jsonlib.loads(...)   ← raises JSONDecodeError
```

The schema being requested at the moment of crash is
`build_strict_json_schema(AgentTurnSummaryDTO.model_...)` (codex.py:98).
The brain returned a payload that passes initial transport but is not valid
JSON at byte 810.

## Root cause hypothesis

`_request_structured_output` uses `await _consume_sse_text(response)` to
accumulate SSE chunks, then constructs `httpx.Response(200, content=text...)`
and calls `.json()`. Two ways this can go wrong:

1. The model emits content that, when joined, contains an unescaped
   delimiter, runaway string, or partial JSON (e.g. truncated at a token
   boundary). Codex's strict-JSON-schema mode is meant to prevent this, but
   `gpt-5.3-codex-spark` evidently does not honour the schema deterministically.
2. SSE chunk assembly in `_consume_sse_text` might miss a continuation chunk
   under back-pressure, producing truncated text.

The user-visible effect is the same regardless of which: a single bad payload
silently kills a multi-hour operation.

## Impact

- Operation `4567a6aa-7341-47ee-8fef-f0d38cf0f1df` ran 28 iterations
  successfully (22 of 642 problems enriched with full metadata), then crashed
  on iter 29 with no recovery.
- Each crash loses the in-flight iteration context. The work itself survives
  in committed metadata.yaml files (the run is idempotent against the queue),
  but the operation must be restarted manually.
- The other two structured-output bugs in this session
  (`task:<uuid>` → `MemoryScope` ValueError, `task <uuid>` → same) showed that
  the same brain returns malformed payloads under multiple distinct schemas.
  This is a brain-side robustness issue plus an operator-side missing
  defensive boundary.

## Proposed fixes

### J1 (minimal, defensive) — wrap the parse, retry once

In `providers/codex.py:_request_structured_output`, wrap the `.json()` call
in try/except and retry the request once on `JSONDecodeError`. After a
second failure, raise a typed `BrainResponseError` that the caller
(`OperatorPolicy`) can catch and translate to a soft retry / skip rather than
an uncaught operation crash.

```python
try:
    return cast(dict[str, Any], httpx.Response(200, content=text.encode()).json())
except json.JSONDecodeError as exc:
    _log.warning("brain returned invalid JSON (%s); preview=%r", exc, text[:200])
    raise BrainResponseError("brain returned invalid JSON; retry recommended") from exc
```

~10 lines. Preserves the operation; surfaces the failure as a transient
error instead of a process crash.

### J2 (caller side) — retry-with-budget

`OperatorPolicy` (or whatever calls `decide_next_action` /
`build_turn_summary`) should catch `BrainResponseError` and retry up to N
times before marking the iteration `FAILED` (with the same crash-recovery
path that already exists for agent failures). This keeps a single bad payload
from killing the run.

### J3 (root cause) — verify strict-schema mode is actually being used

`codex.py:98` builds `build_strict_json_schema(AgentTurnSummaryDTO.model_...)`.
Verify that this schema is being passed in the request body in the form
Codex actually enforces (the format may have evolved). If the schema is
present but Codex returns non-conforming JSON, that's a Codex bug to surface
upstream. Either way, log the full payload preview when the parse fails so
the failing example can be filed with Codex / OpenAI.

### J4 (logging) — checksum + size of failing payloads

When a payload fails to parse, log `len(text)`, the surrounding ±50 chars of
the parser-reported offset, and a SHA-256 hash. This makes it possible to
correlate repeated failures with specific brain behaviour patterns.

## Acceptance criteria

- [ ] A single `JSONDecodeError` from Codex does NOT crash an operation —
      it triggers a logged warning + retry + soft FAILED if persistent.
- [ ] Regression test: simulate `_consume_sse_text` returning malformed
      JSON; verify operation continues.
- [ ] Failure preview is logged to stderr / operator log so the failing
      example can be reproduced.

## Related context

- Discovered in the `erdos-625` research project on 2026-05-11 while running
  operator with `claude_acp` agent (model=default = Opus 4.7[1m]) and
  `codex_brain` model `gpt-5.3-codex-spark`. Operation
  `4567a6aa-7341-47ee-8fef-f0d38cf0f1df`.
- Companion issues, both same brain model, same session:
  - `docs/issues/memoryscope-crash-on-malformed-brain-draft.md`
    (brain returns malformed `scope` strings — `task:<uuid>`, `task <uuid>`,
    full English sentences). Hot-fix applied in
    `application/agent_results.py:543`.
  - `docs/issues/project-profile-overrides-env-vars.md`
    (project profile silently overrides env vars for adapter settings;
    12-factor violation).
- All three issues observed in a single 4-hour session. Recommend filing
  them upstream together; `gpt-5.3-codex-spark` may benefit from being
  pinned to a different brain model until structured-output reliability is
  verified.
