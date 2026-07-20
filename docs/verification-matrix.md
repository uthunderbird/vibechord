# Verification Matrix

Status: `verified`

Current local gate:

```sh
uv run vibechord verify full
```

Current evidence:

- `ruff check .`: passes;
- `mypy .`: passes under strict configuration;
- `pytest`: passes;
- full release checks run fake harness workflows and this docs claim audit.

## Claim Mapping

| Claim | Evidence |
| --- | --- |
| Six-part core exists | `tests/test_harness_and_architecture.py` |
| JSONL event store supports replay/idempotency/corrupt-event failure | `tests/test_core.py` |
| Operation loop handles completion, attention, limits, adapter failure | `tests/test_core.py` |
| Operation loop records native multi-worker invocations, starts them before terminal events, invokes them concurrently, and projects outputs | `tests/test_core.py` |
| Process-backed agent and brain adapters fail explicitly | `tests/test_core.py` |
| Direct Codex exec validates bounded JSONL and final-message evidence and runs exactly once under the deterministic brain | `tests/test_core.py` |
| OpenAI Responses brain adapter maps structured decisions and failures | `tests/test_openai_adapter.py` |
| CLI JSON status/fleet/report are shared DTO surfaces | `tests/test_delivery.py` |
| REST uses shared command/query paths and idempotency keys | `tests/test_delivery.py` |
| REST scoped hashed-token auth, production guard, and security headers exist | `tests/test_delivery.py` |
| TUI render/reducer/full-screen runtime are testable without owning canonical state | `tests/test_delivery.py` |
| Public Python SDK uses shared command/query contracts | `tests/test_sdk_and_release.py` |
| MCP tools/resources/prompts/progress surface uses shared SDK contracts | `tests/test_mcp.py` |
| MCP HTTP POST/SSE transport persists and resumes events | `tests/test_mcp_http.py` |
| Fake harness writes machine-readable summaries | `tests/test_harness_and_architecture.py` |
| Full gate runs fake harness workflows and docs audit | `tests/test_sdk_and_release.py` |

## Known Limitations

- None currently documented for the verified local release gate.
