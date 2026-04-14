# ADR 0161: Python SDK surface (OperatorClient)

- Date: 2026-04-13

## Decision Status

Accepted

## Implementation Status

Verified

## Context

`src/agent_operator/__init__.py` currently exports:

```python
from agent_operator.application.service import OperatorService
from agent_operator.bootstrap import build_service

__all__ = ["OperatorService", "build_service"]
```

This is an internal service surface, not a stable public client API. It requires the caller
to understand bootstrap configuration, `OperatorService` internals, and the full domain model.
There is no `agent_operator.client` module.

AGENT-INTEGRATION-VISION.md Surface 4 defines a thin async `OperatorClient` wrapper:

> Thin async wrapper over the existing service layer. Direct Python method calls — no subprocess
> spawning, no serialization overhead. The `OperatorClient` manages settings loading and resource
> lifecycle.
>
> ```python
> from agent_operator.client import OperatorClient
> ```

The vision notes: "Implementation cost: Low. The `OperatorService` and `FileOperationStore`
already implement all of this. The SDK is a thin async context manager that handles settings
loading (same logic as CLI `_load_settings()`), wraps the service calls, and exposes
`stream_events` via the existing JSONL event file."

### Why this matters

Python agent frameworks (LangGraph, Pydantic AI, custom async orchestrators) need to embed
operator without subprocess overhead. The current `OperatorService` + `build_service` approach
works but has no stability contract, requires internal knowledge, and is not documented as a
supported surface. `OperatorClient` formalizes a stable public surface.

## Decision

Create `src/agent_operator/client.py` with `OperatorClient` as a public stable API.

### API surface

```python
class OperatorClient:
    """Thin async context manager wrapping OperatorService for programmatic embedding."""

    async def list_operations(
        self,
        project: str | None = None,
    ) -> list[OperationSummary]: ...

    async def run(
        self,
        goal: str,
        *,
        project: str | None = None,
        agents: list[str] | None = None,
        mode: str = "background",
    ) -> str: ...                                # returns operation_id

    async def get_status(self, operation_id: str) -> OperationBrief: ...

    async def get_attention(self, operation_id: str) -> list[AttentionRequest]: ...

    async def answer_attention(
        self,
        operation_id: str,
        attention_id: str,
        text: str,
    ) -> None: ...

    async def cancel(self, operation_id: str) -> None: ...

    async def interrupt(
        self,
        operation_id: str,
        task_id: str | None = None,
    ) -> None: ...

    async def stream_events(
        self,
        operation_id: str,
    ) -> AsyncIterator[RunEvent]: ...
```

`operation_id="last"` is accepted by all methods that take an operation ID (consistent with CLI
resolution semantics).

### Context manager protocol

```python
async with OperatorClient(data_dir=Path(".operator")) as client:
    op_id = await client.run("fix auth module", agents=["claude_acp"])
    ...
```

`__aenter__` performs settings loading (equivalent to CLI `_load_settings()`). `__aexit__`
releases any open resources (file handles, background tasks from `stream_events`).

### `stream_events` contract

- Yields `RunEvent` objects as lines are appended to the event JSONL file.
- Auto-terminates after receiving an `operation.cycle_finished` event and a drain window of
  1 second with no further writes.
- If the operation is already terminal when called, drains the existing file and returns.
- Does not raise `FileNotFoundError` if the event file does not yet exist — waits up to a
  configurable timeout for the file to appear (default: 30 seconds).
- Callers may `break` at any time without resource leaks.

### Stability contract

`agent_operator.client.OperatorClient` and all parameter/return types exposed in its public
API are covered by the stability contract from ADR 0145:
- Adding optional parameters and return fields: non-breaking.
- Removing parameters, renaming methods, changing return types: breaking — requires
  deprecation cycle.

The stability contract is documented at `docs/reference/python-sdk.md` (to be created).

### Implementation approach

The client wraps the existing service layer:

```python
class OperatorClient:
    def __init__(self, *, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or _discover_data_dir()
        self._service: OperatorService | None = None

    async def __aenter__(self) -> OperatorClient:
        settings = _load_settings()
        self._service = build_service(settings, data_dir=self._data_dir)
        return self

    async def __aexit__(self, *_: object) -> None:
        # release resources
        pass

    async def run(self, goal: str, ...) -> str:
        assert self._service is not None
        return await self._service.run_operation(goal, ...)
```

No new business logic. All methods delegate to `OperatorService`.

### Export

Add `OperatorClient` to `src/agent_operator/__init__.py`:

```python
from agent_operator.client import OperatorClient

__all__ = ["OperatorService", "build_service", "OperatorClient"]
```

## Prerequisites for resolution

1. Create `src/agent_operator/client.py` with `OperatorClient`.
2. Implement `stream_events` using the event JSONL file (tail-like async reader).
3. Expose `OperatorClient` in `__init__.py`.
4. Create `docs/reference/python-sdk.md` with the stability contract and usage example.
5. Tests: context manager lifecycle; `run` returns an operation ID; `stream_events` terminates
   on terminal event; `"last"` resolves correctly.

## Consequences

- Python agent frameworks can embed operator without subprocess overhead or internal knowledge.
- `OperatorService` + `build_service` remain available for advanced use but are not part of
  the stable surface.
- The stability contract formalizes a public commitment that did not exist before.

## Related

- `src/agent_operator/__init__.py`
- `src/agent_operator/application/service.py` — `OperatorService`
- `src/agent_operator/bootstrap.py` — `build_service`
- [AGENT-INTEGRATION-VISION.md §Surface 4: Python SDK](../AGENT-INTEGRATION-VISION.md)
- [ADR 0145](./0145-cli-output-format-and-agent-integration-stability-contract.md)
- [ADR 0146](./0146-mcp-server-surface-and-tool-contract.md)
