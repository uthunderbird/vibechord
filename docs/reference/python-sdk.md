# Python SDK reference

`agent_operator.OperatorClient` is the stable Python SDK surface for embedding `operator` without
subprocess orchestration.

## Stability contract

This SDK surface follows the public stability contract from ADR 0145.

- Adding optional parameters: non-breaking.
- Adding optional return fields: non-breaking.
- Removing parameters: breaking.
- Renaming methods: breaking.
- Changing return types: breaking.

## Usage

```python
from pathlib import Path

from agent_operator import OperatorClient


async def main() -> None:
    async with OperatorClient(data_dir=Path(".operator")) as client:
        operation_id = await client.run(
            "fix auth module",
            agents=["claude_acp"],
            mode="background",
        )
        brief = await client.get_status(operation_id)
        print(brief.status.value)

        async for event in client.stream_events(operation_id):
            print(event.event_type)
```

## Public methods

- `list_operations(project: str | None = None) -> list[OperationSummary]`
- `run(goal: str, *, project: str | None = None, agents: list[str] | None = None, mode: str = "background") -> str`
- `get_status(operation_id: str) -> OperationBrief`
- `get_attention(operation_id: str) -> list[AttentionRequest]`
- `answer_attention(operation_id: str, attention_id: str, text: str) -> None`
- `cancel(operation_id: str, *, reason: str | None = None) -> None`
- `message(operation_id: str, text: str) -> None`
- `interrupt(operation_id: str, task_id: str | None = None) -> None`
- `pause(operation_id: str) -> None`
- `unpause(operation_id: str) -> None`
- `stream_events(operation_id: str) -> AsyncIterator[RunEvent]`

## Control semantics

- `answer_attention()`, `cancel()`, `message()`, `interrupt()`, `pause()`, and `unpause()`
  resolve operation references through the same shared delivery command path used by other
  delivery surfaces.
- `cancel()` executes immediately. Unlike the CLI `operator cancel` command, the Python SDK does
  not prompt for confirmation; SDK callers are responsible for any confirmation step they require.
- `cancel(reason=...)` forwards an optional operator-supplied cancellation reason into the shared
  application cancellation path.
- `message()` enqueues `inject_operator_message` with the same trimmed text semantics as other
  delivery surfaces.
- `pause()` queues `pause_operator`; if an attached turn is running, the pause becomes effective
  after that turn yields.
- `unpause()` queues `resume_operator` and resumes attached execution when the operation is already
  paused.

## Event streaming contract

- Reads canonical v2 events from `.operator/operation_events/<operation_id>.jsonl` when present,
  otherwise falls back to legacy `.operator/events/<operation_id>.jsonl`.
- Waits for the event file to appear instead of raising `FileNotFoundError`.
- Exits after a terminal event plus a 1 second quiet drain window.
- If the operation is already terminal when called, drains the existing file and returns.
- Callers may break iteration at any time.
