# vibechord

`vibechord` is a minimalist successor to `operator`: a Python library and CLI
for supervising agent work through an inspectable operation loop.

Current status: `verified local release gate`. The repository has a working
stdlib-based operation-loop core, file-backed event store, CLI, REST surface,
line-oriented terminal TUI runtime, pure TUI view/reducer layer, full-screen
curses TUI runtime, public local Python SDK, MCP stdio/HTTP surface, fake
adapters, process-agent adapter, process-brain adapter, OpenAI Responses brain
adapter, and local verification gates.

## Product Direction

`vibechord` targets the same broad functional space as `operator`:

- goal-directed operation runs,
- deterministic stop policies and guardrails,
- LLM-assisted planning and evaluation,
- external agent adapters,
- durable event traces,
- resumable supervision,
- fleet-level operation views,
- live operator chat through shared commands and delivery surfaces.

The project intentionally starts from a smaller conceptual core. Feature parity
is a product target, not a claim about current implementation.

## Design Bias

- One central operation loop.
- One canonical event authority.
- Shared command/query contracts for CLI, TUI, REST, SDK, and future MCP
  surfaces.
- Protocol-oriented integration.
- Minimal layers with explicit authority boundaries.
- Transparent status, trace, and live-feed surfaces.
- No hidden fallback paths unless a real migration requires them.

## Start Here

- [Design vision](design/VISION.md)
- [SDLC](design/SDLC.md)
- [Testing rails](design/TESTING-RAILS.md)
- [Verification scenarios](design/VERIFICATION-SCENARIOS.md)
- [Moving parts](design/MOVING-PARTS.md)
- [Architecture](design/ARCHITECTURE.md)
- [CLI vision](design/CLI-VISION.md)
- [TUI vision](design/TUI-VISION.md)
- [REST API vision](design/REST-API-VISION.md)
- [Quickstart](docs/quickstart.md)
- [CLI](docs/cli.md)
- [REST](docs/rest.md)
- [TUI](docs/tui.md)
- [Python SDK](docs/sdk.md)
- [MCP](docs/mcp.md)
- [Adapters](docs/adapters.md)
- [Verification matrix](docs/verification-matrix.md)
- [Policies](policies/README.md)
- [Backlog](design/BACKLOG.md)

## Implementation Status

- `implemented`: six-part core, JSONL event store, replay/projections,
  command application, operation driver, fake brain/agent adapters, CLI first
  slice, REST first slice with scoped bearer-token auth and local binding guard,
  pure TUI view/reducer slice, line-oriented terminal TUI runtime, full-screen
  curses TUI runtime, public local Python SDK, MCP stdio and HTTP POST
  tools/resources/prompts/progress surface, local process-agent adapter, local
  process-brain adapter, OpenAI Responses brain adapter, fake harness, release
  docs, and local verification gates.
- `verified`: `uv run vibechord verify full` passes locally.
- `planned`: none currently documented for the verified local release gate.
- `blocked`: none currently.
