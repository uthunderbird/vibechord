# Python SDK

Status: `verified`

The local Python SDK uses the same command application, operation driver, and
projection service as the CLI, TUI, and REST surfaces. It does not create a
separate runtime authority.

## Example

```python
from vibechord import VibechordClient

client = VibechordClient(".")
result = client.run("summarize the workspace")

if result.operation_id is not None:
    status = client.status(result.operation_id)
    fleet = client.fleet()
    live = client.live(result.operation_id)
```

## Available Methods

- `run(goal)`: starts an operation and drives it until it is blocked or
  terminal.
- `status(operation_id)`: returns the shared status DTO.
- `fleet()`: returns shared fleet rows.
- `live(operation_id)`: returns live-feed envelopes.
- `message(operation_id, text)`: posts a live operator message through the
  shared command path.

## Verification

SDK behavior is covered by `tests/test_sdk_and_release.py` and the full local
gate:

```sh
uv run vibechord verify full
```
