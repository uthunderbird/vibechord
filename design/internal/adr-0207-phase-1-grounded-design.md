# ADR 0207 Phase 1 Grounded Design

- Date: 2026-04-25
- ADR: `design/adr/0207-delivery-surface-parity-contract.md`
- Decision Status: `Proposed`
- Implementation Status: `Planned`
- Scope: design grounding and implementation plan only; no production code changes are claimed.

## Swarm Iteration Brief

### Phase 1 - Problem Definition

Core problem: ADR 0207 needs to be grounded in current code before implementation. The repository
already has some shared resolver/read/command pieces, but delivery parity is not yet a named,
enforced contract across CLI, TUI, MCP, and Python SDK.

Scope:

- In scope: ADR 0207 text refinement, current-code grounding, and a full implementation/test/
  verification plan for the next phase.
- Out of scope: changing production code, moving ADR 0207 to `Accepted`, claiming
  `Implemented`, or editing ADRs outside 0203..0212.

Success criteria:

- ADR 0207 remains `Decision Status: Proposed` and `Implementation Status: Planned`.
- Grounded claims cite concrete grep/read evidence.
- The plan identifies required code changes, tests, verification commands, and risks.
- The plan preserves existing ADR 0204/0205/0206 decisions rather than inventing a competing
  authority.

Uncertainties:

- Whether SDK should expose richer parity payloads or keep its current domain-object return style.
- Whether TUI callback injection should be formalized as a public protocol or hidden behind a
  package-local adapter.
- Whether stream/watch parity should target legacy run event files first or the canonical v2 event
  stream first.

Swarm configuration snapshot:

- preset: Diagnosis / Engineering
- rigor / grounding: high
- branching budget: narrow
- closure strictness: high
- evidence boundary: local files and command output only

### Phase 2 - Expert Assembly

- Barbara Liskov (Critic, abstraction boundaries): checks that the proposed contract preserves one
  authority per fact and does not leak surface-specific behavior into the domain.
- Martin Fowler (Balanced, application architecture): checks that shared services are small
  application-facing contracts rather than a framework layer.
- Leslie Lamport (Critic, consistency): checks that parity tests prove observable consistency, not
  just similar code shape.
- Ward Cunningham (Evangelist): keeps the artifact practical and incremental enough to be executed
  in one working wave.
- Completer-Finisher (Critic): checks missing tests, docs, risks, and status wording.

### Iteration 1 - Option E: Ground Current Code

Moderator reasoning: the unresolved gap was factual. ADR 0207 could overclaim if the current
surface state was inferred from ADR 0204/0205/0206 rather than checked in code, so the executor
grounded resolver, command, read, TUI, MCP, SDK, and tests before synthesis.

Executor scope and commands:

- Read repository rules: `sed -n '1,240p' AGENTS.md`,
  `sed -n '1,260p' policies/architecture.md`,
  `sed -n '1,280p' policies/engineering.md`,
  `sed -n '1,260p' policies/verification.md`,
  `sed -n '1,260p' design/ARCHITECTURE.md`.
- Read ADR target and adjacent v2 ADRs:
  `nl -ba design/adr/0207-delivery-surface-parity-contract.md`,
  `nl -ba design/adr/0204-v2-operation-identity-resolution-and-lifecycle-entrypoints.md`,
  `nl -ba design/adr/0205-event-sourced-command-and-control-plane.md`,
  `nl -ba design/adr/0206-v2-query-and-read-model-canonicalization.md`.
- Grep delivery/application surfaces:
  `rg -n "MCP|Python SDK|sdk|status|answer|cancel|interrupt|operation resolver|OperationResolver|resolve.*operation|query|command" src tests docs design`.
- Read code regions cited below with `nl -ba`.

Tool-backed findings:

- Shared operation resolution is implemented in
  `OperationResolutionService.resolve_operation_id()` and canonical listing/loading helpers.
  Citation: `src/agent_operator/application/queries/operation_resolution.py:61-103`,
  `src/agent_operator/application/queries/operation_resolution.py:114-151`.
- CLI resolution delegates through `resolve_operation_id_async()` / `resolve_operation_id()`.
  Citation: `src/agent_operator/cli/helpers/resolution.py:32-41`.
- CLI control commands use the shared resolver for covered operation references.
  Citation: `src/agent_operator/cli/commands/operation_control.py:43-90`,
  `src/agent_operator/cli/commands/operation_control.py:155-211`,
  `src/agent_operator/cli/commands/operation_control.py:224-344`.
- CLI attention/tasks/memory/artifacts/report/dashboard/watch read paths use canonical operation
  loading or shared query services. Citation:
  `src/agent_operator/cli/commands/operation_detail.py:239-340`,
  `src/agent_operator/cli/commands/operation_detail.py:430-548`.
- MCP list/status/control paths construct shared resolver/query/delivery services. Citation:
  `src/agent_operator/mcp/service.py:96-114`,
  `src/agent_operator/mcp/service.py:198-287`,
  `src/agent_operator/mcp/service.py:309-341`,
  `src/agent_operator/mcp/service.py:394-411`.
- Python SDK constructs `OperationResolutionService`, uses it for listing and loading, and resolves
  operation refs before status/control/event streaming. Citation:
  `src/agent_operator/client.py:108-136`, `src/agent_operator/client.py:155-205`,
  `src/agent_operator/client.py:258-309`, `src/agent_operator/client.py:330-430`,
  `src/agent_operator/client.py:432-501`, `src/agent_operator/client.py:535-545`.
- Status-like read payload is typed and carries runtime overlay authority/staleness metadata.
  Citation: `src/agent_operator/application/queries/operation_status_queries.py:61-85`,
  `src/agent_operator/application/queries/operation_status_queries.py:154-230`.
- CLI status rendering consumes the read payload, and MCP status builds its response from the same
  payload. Citation:
  `src/agent_operator/application/queries/operation_status_queries.py:248-294`,
  `src/agent_operator/mcp/service.py:198-238`.
- `OperationDeliveryCommandService` is the current command facade for delivery actions, covering
  cancel/resume/tick/recover and command enqueue/auto-resume behavior. Citation:
  `src/agent_operator/application/commands/operation_delivery_commands.py:61-213`.
- TUI is callback-driven, not directly service-bound. It receives load/control callbacks at
  construction and invokes those for pause, unpause, interrupt, cancel, answer, and payload refresh.
  Citation: `src/agent_operator/cli/tui/controller.py:39-62`,
  `src/agent_operator/cli/tui/controller.py:538-617`,
  `src/agent_operator/cli/tui/controller.py:775-821`,
  `src/agent_operator/cli/tui/controller.py:823-843`.
- Existing tests already cover MCP v2-only resolution/listing. Citation:
  `tests/test_mcp_server.py:443-478`, `tests/test_mcp_server.py:481-523`,
  `tests/test_mcp_server.py:526-571`.
- Existing docs describe MCP and SDK surfaces separately, which is useful evidence of public
  surface shape but not yet a parity guarantee. Citation: `design/reference/mcp-tool-schemas.md:31-34`,
  `docs/reference/python-sdk.md:42-47`, `docs/reference/cli-json-schemas.md:32-84`.

Route update:

- Route: "implement parity by inventing new surface-specific adapters."
- Prior state: plausible but ungrounded.
- New state: closed.
- Justification: current architecture already has shared resolver, query, and delivery command
  services; adding another authority would violate the ADR's own intent.

- Route: "formalize and enforce existing shared application services as the parity contract."
- Prior state: candidate.
- New state: selected.
- Justification: citations above show the existing shared pieces are real but partial; this route
  closes gaps by naming and testing the contract rather than replacing working boundaries.

### Iteration 2 - Option D: Adjudicate SDK/TUI Shape

Moderator reasoning: the unresolved gap was whether parity requires identical return payloads or
identical authority paths. The ADR text says rendering may differ while authority must not, so the
decision needs to preserve ergonomic surface differences while proving common resolver/command/read
authority.

Adjudication:

- CLI and MCP should keep machine-facing JSON shapes documented in
  `docs/reference/cli-json-schemas.md` and `design/reference/mcp-tool-schemas.md`.
- SDK may keep domain-object return values where they are already public, but covered methods must
  delegate to the same resolver, command facade, and read service used by CLI/MCP.
- TUI should keep callback injection for UI testability, but the production callback provider should
  be backed by the same delivery parity facade.
- The parity contract is therefore "same application authority, surface-local rendering/return
  mapping," not "all surfaces emit the same JSON object."

Route update:

- Route: "identical payloads across all surfaces."
- Prior state: open.
- New state: closed.
- Justification: ADR 0207 permits surface-specific rendering; SDK domain-object ergonomics and TUI
  callbacks can remain if authority is shared.

- Route: "same authority with explicit surface mappers."
- Prior state: selected.
- New state: refined.
- Justification: matches ADR 0207 required properties and the current code shape.

### Iteration 3 - Option H: Finalization

Convergence judgment: enough evidence exists to refine ADR 0207 without claiming implementation.
The next phase is an implementation wave, not more design debate.

## Required Code Changes

1. Introduce a named parity facade/protocol in the application layer, tentatively
   `DeliveryParityService` or `DeliverySurfaceService`, that composes:
   - `OperationResolutionService` for operation reference resolution and canonical listing.
   - `OperationStatusQueryService` for status/read payloads.
   - `OperationDashboardQueryService` or a smaller operation-detail query contract for TUI/session/
     log/attention/task inspection payloads.
   - `OperationDeliveryCommandService` for answer, cancel, interrupt, pause, unpause, message, and
     patch-like commands.
2. Keep the facade thin. It should not own business semantics already owned by ADR 0204/0205/0206
   services; it should coordinate delivery-facing calls and normalize surface errors.
3. Add a stable operation-resolution error mapping contract for machine-facing surfaces:
   - resolver `not_found` stays distinguishable from ambiguous-prefix failures.
   - CLI maps to `typer.BadParameter` for human commands and documented JSON error shape where a
     command already emits JSON.
   - MCP maps to `McpToolError` with `error.data.code`.
   - SDK raises a typed exception or a documented `RuntimeError` subclass.
4. Move SDK `answer_attention()`, `cancel()`, and `interrupt()` onto the shared delivery command
   facade instead of direct command-inbox/service calls. Preserve SDK return style unless a separate
   accepted ADR changes the SDK API.
5. Move SDK `get_status()` toward `OperationStatusQueryService.build_read_payload()` or an explicit
   SDK mapper over that payload, so status facts come from the same read authority as CLI/MCP.
6. Make production TUI callback construction come from the parity facade. Keep
   `FleetWorkbenchController` callback injection as a UI boundary, but ensure the real callbacks are
   not parallel command/query implementations.
7. Extend stream/watch parity:
   - CLI `watch` and SDK `stream_events()` must agree on the event source for v2 operations.
   - If the first phase keeps legacy run event files for stream/watch, document that as an intentional
     parity gap with a follow-up to move both to canonical v2 events.
8. Add a small parity matrix document under `docs/reference/` that lists covered surfaces, shared
   authority service, output shape, and intentional gaps. This is public/integrator documentation,
   not design authority.
9. Keep ADR 0207 status at `Proposed` until the code and tests are reviewed. Move to `Accepted`
   only in a committed work wave per architecture policy.

## Required Tests

1. Add `tests/test_delivery_surface_parity.py` for cross-surface fixture setup and assertions.
2. Resolver parity tests:
   - exact id resolves in CLI helper, MCP service, SDK client, and TUI production callback provider.
   - unique prefix resolves identically.
   - `last` resolves from v2 event/checkpoint metadata.
   - ambiguous prefix returns the correct surface-specific error mapping while preserving the same
     underlying resolver code.
3. Command parity tests:
   - answer/cancel/interrupt through CLI workflow, MCP service, SDK client, and TUI production
     callback all call or consume the same command facade.
   - v2-only operation fixture with no `.operator/runs` works for answer/cancel/interrupt where the
     command is valid.
   - terminal-operation cancel rejection is consistent across CLI/MCP/SDK.
4. Status/read parity tests:
   - CLI `status --json`, MCP `get_status`, SDK `get_status`, and TUI operation payload agree on
     operation id, status, attention count/facts, session facts, and runtime overlay authority.
   - text rendering may differ; assertions should target shared payload facts.
5. Stream/watch parity tests:
   - SDK `stream_events()` and CLI `watch --json --once` agree on the source used for a v2 operation,
     or the documented intentional gap is asserted explicitly.
6. Structure/import tests:
   - public delivery modules for covered commands must import/use the parity facade or approved
     lower-level shared service; direct `build_store()` / command inbox usage in new covered paths
     should fail the test unless explicitly allowed.
7. Documentation tests or snapshot checks:
   - `docs/reference/delivery-surface-parity.md` lists each covered row and all intentional gaps.

Mutation intent for tests:

- Resolver tests should catch replacing shared resolver use with legacy store-only listing.
- Command tests should catch SDK/TUI bypassing `OperationDeliveryCommandService`.
- Status tests should catch MCP/CLI/SDK assembling status from divergent payloads.
- Stream/watch tests should catch one surface tailing a different source silently.
- Structure tests should catch new surface-local authority paths.

## Verification Steps

Targeted:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_operation_resolution.py tests/test_client.py tests/test_mcp_server.py tests/test_cli.py -k "resolve or status or answer or cancel or interrupt"
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_delivery_surface_parity.py
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_tui.py -k "answer or cancel or interrupt or payload or parity"
```

Changed-file quality gates:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src/agent_operator/application src/agent_operator/cli src/agent_operator/mcp src/agent_operator/client.py tests/test_delivery_surface_parity.py
UV_CACHE_DIR=/tmp/uv-cache uv run mypy src/agent_operator/application src/agent_operator/cli src/agent_operator/mcp src/agent_operator/client.py
```

Full gate before ADR acceptance:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run pytest
```

Manual/public-doc verification:

```sh
rg -n "Delivery Surface Parity|intentional gaps|CLI|TUI|MCP|SDK" docs/reference
rg -n "OperationDeliveryCommandService|OperationStatusQueryService|OperationResolutionService" src/agent_operator/cli src/agent_operator/mcp src/agent_operator/client.py
```

## Risks

- A facade can become a second business authority if it duplicates resolver, command, or read-model
  semantics instead of composing existing services.
- SDK API compatibility is a design risk: moving to shared payloads must not silently change public
  return types without a separate SDK decision.
- TUI callback testability could regress if the parity facade is pushed into the controller instead
  of only into production callback construction.
- Stream/watch parity may expose an existing event-source split between user-facing run events and
  canonical v2 operation events.
- Error normalization can hide useful surface-specific detail if all errors are flattened too early.
- Tests that assert only import shape can become brittle; behavioral parity tests must be primary.
- Full `mypy` may still fail on unrelated repository-wide typing debt; changed-file mypy and a
  named residual risk are required if that remains true.

## Next Working Point

Nearest working point: add the thin parity facade and route SDK status/answer/cancel/interrupt plus
MCP service construction through it, with CLI/TUI still using existing shared services. This is
reachable without breaking public interfaces because return mapping can remain surface-local while
authority moves behind the facade.

External sign-off is still required before implementation under R15 because the full parity wave
touches multiple delivery surfaces.
