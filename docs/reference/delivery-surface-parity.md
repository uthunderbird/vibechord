# Delivery Surface Parity

CLI, TUI, MCP, and Python SDK surfaces are delivery adapters over shared application authority for
the covered operation capabilities. Surface-specific rendering and SDK return types remain local to
each adapter.

## Shared Authorities

| Capability | Shared authority | Covered surfaces | Surface output |
| --- | --- | --- | --- |
| operation reference resolution | `DeliverySurfaceService.resolve_operation_id()` over `OperationResolutionService` | CLI, TUI, MCP, SDK | surface-local errors and identifiers |
| list | `DeliverySurfaceService.list_operation_states()` over `OperationResolutionService` | MCP, SDK, CLI query helpers | CLI JSON lines, MCP dicts, SDK `OperationSummary` |
| status/read payload | `DeliverySurfaceService.build_read_payload()` over `OperationStatusQueryService` | MCP, SDK, CLI status/query helpers, TUI operation payloads | surface-local projections |
| answer | `DeliverySurfaceService.answer_attention()` over `OperationDeliveryCommandService` | TUI production callbacks, MCP, SDK, CLI command facade | command acknowledgements or `None` |
| cancel | `DeliverySurfaceService.cancel_operation()` over `OperationDeliveryCommandService` | TUI production callbacks, MCP, SDK, CLI command facade | outcome projection or `None` |
| interrupt | `DeliverySurfaceService.interrupt_operation()` over `OperationDeliveryCommandService` | TUI production callbacks, MCP, SDK, CLI command facade | acknowledgement or `None` |

## Intentional Gaps

- `operator watch` and `OperatorClient.stream_events()` still read `.operator/events/<operation_id>.jsonl`.
  They resolve operation references through the shared resolver, but the event source is the legacy
  run event file rather than canonical v2 operation events.
- TUI keeps callback injection at the controller boundary for UI tests. Production callback
  construction is backed by `DeliverySurfaceService`; controller tests may still pass fakes.

## Machine-Facing Errors

- Resolver `not_found` and ambiguous-prefix failures remain distinguishable at the resolver layer.
- MCP maps those failures to `McpToolError` with `error.data.code` set to `not_found` or
  `invalid_state`.
- CLI human commands map delivery failures to `typer.BadParameter`; published JSON command payloads
  keep their existing schemas.
- SDK methods keep their documented return types and raise Python exceptions for failures.
