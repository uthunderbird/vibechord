# Python SDK reference

`agent_operator.client.OperatorClient` is the stable Python SDK surface for embedding `operator`
without subprocess orchestration.

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

from agent_operator.client import OperatorClient


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
- `cancel(operation_id: str) -> None`
- `interrupt(operation_id: str, task_id: str | None = None) -> None`
- `stream_events(operation_id: str) -> AsyncIterator[RunEvent]`

## Event streaming contract

- Reads persisted events from `.operator/events/<operation_id>.jsonl`.
- Waits for the event file to appear instead of raising `FileNotFoundError`.
- Exits after a terminal event plus a 1 second quiet drain window.
- If the operation is already terminal when called, drains the existing file and returns.
- Callers may break iteration at any time.
