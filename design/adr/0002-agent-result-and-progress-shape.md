# ADR 0002: Agent Progress And Result Have A Minimal Structured Core

## Decision Status

Accepted

## Implementation Status

Implemented

## Evidence

- `src/agent_operator/domain/agent.py` defines `AgentProgress` with the ADR core
  (`session_id`, `state`, `message`, `updated_at`) plus normalized optional fields
  (`progress_text`, `partial_output`, `usage`, `artifacts`, `raw`).
- `src/agent_operator/domain/agent.py` defines `AgentResult` with the ADR core
  (`session_id`, `status`, `output_text`, `artifacts`, `error`, `completed_at`) plus
  optional normalized extensions (`structured_output`, `usage`, `transcript`, `raw`).
- `src/agent_operator/domain/enums.py` provides normalized `AgentProgressState` and
  `AgentResultStatus` enums used across adapters and runtime code.
- `tests/test_acp_session_runner.py`, `tests/test_codex_acp_adapter.py`, and
  `tests/test_claude_acp_adapter.py` assert normalized progress and result behavior across
  ACP-backed adapters, including `running`, `waiting_input`, `success`, `incomplete`, and
  disconnected/failure paths.

## Context

ADR 0001 established that `AgentAdapter` is session-oriented. That decision requires two runtime objects to be meaningful across adapters:

- `AgentProgress`
- `AgentResult`

The operator loop needs these objects to make decisions such as:

- whether an agent is still running,
- whether follow-up input is possible or useful,
- whether a result is complete enough to evaluate,
- whether execution failed, stalled, or was cancelled,
- and what evidence should be shown to the user or passed to the operator brain.

At the same time, adapters will differ widely:

- Claude Code may return a relatively clean headless response.
- Codex via ACP may produce richer session events, tool updates, and structured stop reasons.
- future agents may expose API-native statuses, artifacts, or usage information.

If `AgentProgress` and `AgentResult` are too loose, the operator loop will need adapter-specific branching. If they are too rigid, adapters will be forced into lossy or unnatural mappings.

## Decision

`AgentProgress` and `AgentResult` will have:

- a required minimal structured core used by the operator loop,
- optional normalized fields for common cross-adapter data,
- and a raw vendor payload for adapter-specific detail.

The structured core is the source of truth for orchestration. Raw payload exists for debugging, transparency, and adapter-specific extensions.

## `AgentProgress`

`AgentProgress` should include, at minimum:

- `session_id` or equivalent handle reference
- `state`
- `message`
- `updated_at`

Where `state` is normalized into a small enum such as:

- `pending`
- `running`
- `waiting_input`
- `completed`
- `failed`
- `cancelled`
- `unknown`

Optional fields may include:

- `progress_text`
- `partial_output`
- `usage`
- `artifacts`
- `raw`

The operator loop should depend primarily on normalized `state`, not on adapter-specific status strings.

## `AgentResult`

`AgentResult` should include, at minimum:

- `session_id`
- `status`
- `output_text`
- `artifacts`
- `error`
- `completed_at`

Where `status` is normalized into a small enum such as:

- `success`
- `incomplete`
- `failed`
- `cancelled`

Optional fields may include:

- `structured_output`
- `usage`
- `transcript`
- `raw`

`output_text` is the main human-readable summary or extracted answer. It may be empty if the agent produced only artifacts or failed before producing text.

`artifacts` should be a normalized list of produced files, references, or named outputs where possible.

## Alternatives Considered

### Option A: Raw adapter-defined payloads only

Pros:

- maximum flexibility
- minimal up-front schema work

Cons:

- pushes orchestration complexity into the operator loop
- makes cross-adapter reasoning brittle
- weakens testing and observability
- makes it harder to build a stable CLI and event model

### Option B: Fully rigid universal schema

Pros:

- easy for the operator loop to reason about
- easy to test uniformly

Cons:

- forces unnatural mappings for terminal-oriented adapters
- likely to lose useful vendor-specific details
- increases adapter friction early

### Option C: Minimal structured core plus raw payload

Pros:

- gives the operator loop stable decision inputs
- preserves adapter-specific detail
- fits both clean APIs and messy terminal-backed integrations
- supports transparent debugging and CLI rendering

Cons:

- requires discipline about what belongs in normalized fields
- still needs future ADRs or conventions for some optional subfields

## Consequences

- The application layer can reason over a small set of normalized statuses instead of branching per adapter.
- Adapters remain free to preserve vendor-specific payloads without polluting the core contract.
- The CLI and event system can render consistent run state across Claude Code, Codex, and future agents.
- Contract tests can verify normalized semantics without requiring identical raw payloads.
- Future ADRs may still be needed for:
  - artifact descriptor shape
  - usage accounting shape
  - transcript normalization rules

## Notes

The point of normalization is orchestration, not perfect semantic compression.

If a field is not needed for cross-adapter operator behavior, it should usually remain adapter-specific and live under `raw` or an optional extension field rather than being promoted into the mandatory core.
