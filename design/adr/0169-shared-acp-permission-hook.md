# ADR 0169: Shared ACP permission hook for adapter runtime requests

- Date: 2026-04-13

## Decision Status

Proposed

## Implementation Status

Planned

## Context

`operator` now has a shared ACP permission model in:

- `src/agent_operator/acp/permissions.py`
- `src/agent_operator/acp/session_runtime.py`
- `src/agent_operator/adapters/runtime_bindings.py`

That shared layer already owns the canonical concepts for ACP-side approval and waiting-input
handling:

- permission request normalization,
- auto-approve vs escalate vs reject decisions,
- rendered ACP responses,
- waiting-input messages,
- and the runtime path that surfaces ACP server requests into live attached/background execution.

Recent bugs showed that the most important failures were in the shared runtime path, not in
model-specific provider behavior:

- attached runtime originally did not apply the same session configuration path used by adapter
  tests;
- live runtime originally did not forward ACP server requests through adapter hooks;
- normalized live ACP payloads originally dropped request ids, so permission requests were not
  recognized in the shared permission model.

Those fixes reduced the largest truthfulness gaps, but they also made a structural duplication
clearer.

`claude_acp`, `codex_acp`, and `opencode_acp` each still implement a near-identical
`handle_server_request(...)` hook that repeats the same orchestration:

1. normalize the ACP request;
2. compute auto-approve or initial escalation;
3. optionally call the operator permission evaluator;
4. update session pending-input state;
5. install a rejection error when needed;
6. respond to the ACP request;
7. close the session connection for reject/escalate/wait cases.

Only a small part of that flow is genuinely adapter-specific.

This duplication matters because the repository has already had to fix the same permission-session
class of bug across multiple adapters and runtime entry paths. Keeping the orchestration copied in
multiple adapters raises the chance that future fixes land in one hook and drift from the others.

## Decision

Introduce a shared ACP adapter-side permission hook helper for runtime server requests.

The shared helper should own the common orchestration for ACP approval and waiting-input requests.
Individual ACP adapters should provide only narrow vendor-specific seams.

The target split is:

### Shared

One shared helper owns:

- ACP permission request normalization;
- auto-approve / escalate / reject decision flow;
- optional permission-evaluator callout;
- population of `session.pending_input_message` and `session.pending_input_raw`;
- rejection error installation through the active prompt;
- ACP response rendering;
- session-connection closure rules for reject / wait / escalate outcomes.

### Adapter-specific

Each adapter continues to own only:

- session configuration for new/loaded sessions;
- adapter-specific auto-approve heuristics;
- collect-exception classification;
- command bootstrap / CLI argument shaping;
- any truly vendor-specific request forms that do not fit the shared ACP permission contract.

## Scope boundary

This ADR does not unify all ACP adapters into a single inheritance-heavy base class.

The goal is narrower:

- remove the repeated permission-request orchestration,
- keep adapter lifecycle seams explicit,
- and preserve protocol-oriented composition through hooks or helper functions.

This ADR also does not change:

- the operator-level permission policy semantics,
- involvement-level semantics such as `approval_heavy`,
- or the event-sourced attention model that consumes `agent_requested_escalation` and
  `agent_waiting_input`.

## Rationale

This direction keeps the right boundary:

- permission semantics are already shared at the ACP layer;
- runtime truthfulness depends on one canonical flow from ACP request to operator-visible state;
- vendor-specific differences are small and should remain explicit knobs rather than copied control
  flow.

The repository should avoid framework-heavy base classes here. A small shared helper or protocol
backed function is sufficient.

## Implementation notes

The expected implementation shape is:

1. extract the duplicated `handle_server_request(...)` body into a shared ACP helper module;
2. parameterize it with:
   - `adapter_key`,
   - adapter-specific auto-approve callback,
   - optional permission evaluator,
   - connection-close callback,
   - and rejection-error callback if needed;
3. make `claude_acp`, `codex_acp`, and `opencode_acp` delegate to that helper;
4. keep adapter-specific `_should_auto_approve_permission(...)` logic local;
5. retain adapter-specific tests while adding at least one shared regression test for the extracted
   orchestration contract.

## Verification requirements

Before this ADR can move to `Implemented`, the repository should have direct evidence for:

1. identical permission-request outcomes across `claude_acp`, `codex_acp`, and `opencode_acp`
   for the same normalized ACP request shape, except where adapter-specific auto-approve rules
   intentionally differ;
2. live attached/background runtime forwarding through the shared helper path;
3. no regression in operator-visible outcomes:
   - approve,
   - reject,
   - wait for input,
   - escalate to approval attention;
4. targeted tests covering both:
   - shared helper behavior,
   - and adapter-specific auto-approve seams.

## Consequences

- Future permission-path fixes should land once in the shared helper instead of three times.
- Adapter files become smaller and easier to audit.
- The canonical ACP permission behavior becomes easier to reason about end-to-end.
- A bad extraction could over-abstract real vendor differences, so the implementation must keep
  the helper narrow and hook-based.

## Related

- `src/agent_operator/acp/permissions.py`
- `src/agent_operator/acp/session_runtime.py`
- `src/agent_operator/adapters/runtime_bindings.py`
- `src/agent_operator/adapters/claude_acp.py`
- `src/agent_operator/adapters/codex_acp.py`
- `src/agent_operator/adapters/opencode_acp.py`
