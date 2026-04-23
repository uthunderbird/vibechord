# ADR 0202: Brain-owned ACP permission decisions

- Date: 2026-04-23

## Decision Status

Accepted

## Implementation Status

Verified

Skim-safe status:

- `implemented`: ACP permission requests are normalized into `AcpPermissionRequest` objects and can
  be evaluated by `ProviderBackedPermissionEvaluator`
- `implemented`: `v2` permission evaluation can fall back from legacy snapshot state to
  event-sourced replay state before asking the provider for a permission decision
- `implemented`: `v2` incomplete attached turns can be materialized as blocking
  `attention.request.created` events, making permission blockers visible in canonical operation
  state
- `implemented`: `v2` attached incomplete permission escalations now append canonical
  `permission.request.observed`, `permission.request.escalated`, and, for explicit-follow-up
  adapters, `permission.request.followup_required` events
- `implemented`: permission evaluator output now carries decision source metadata so exact active
  autonomy policy decisions can be distinguished from provider-backed brain decisions
- `implemented`: ACP runtime now emits live permission technical facts for observed, decided,
  escalated, and explicit-follow-up-required outcomes before the agent turn terminates
- `implemented`: `v2` drive materializes terminal approval and rejection permission facts as
  canonical `permission.request.*` domain events when they are present in the attached result
- `implemented`: Codex-specific rejection/escalation follow-up is represented as canonical event
  evidence so the operator brain can choose replacement instructions, skip the blocked action, or
  escalate to a human on the next drive decision
- `implemented`: OpenCode post-rejection behavior remains intentionally conservative; until it is
  characterized, `opencode_acp` is treated as requiring explicit follow-up like Codex
- `verified`: unit and integration coverage exercises approval, rejection, escalation, user-input
  wait, deterministic approval, active-policy replay, provider-backed brain decisions, v2 replay
  fallback, Codex explicit follow-up, Claude no-follow-up, OpenCode conservative follow-up,
  permission-event streaming, prompt-turn-scoped permission event accumulation, v2
  materialization, status/inspect replay, incompatible checkpoint replay, and event-sourced
  operation id resolution

## Context

ACP agents can request permission before executing commands, edits, tool calls, or user-input
interactions. Today this path is split across three concerns:

1. adapter-local permission request normalization and response rendering
2. provider-backed permission evaluation using operation state, harness instructions, and active
   autonomy policies
3. runtime behavior after approval, rejection, user-input wait, or escalation

The desired operator behavior is not "always approve" or "always ask the human." The operator must
decide from the same authority surface it uses for normal operation decisions:

- operation objective
- harness instructions
- active autonomy policies
- involvement level
- current operation state
- permission request signature and raw context

The permission decision must be one of:

- approve the request
- reject the request
- escalate to a human as `needs_human`

The runtime must also account for adapter-specific continuation behavior. Current repository truth
shows:

- Claude ACP keeps reusable live connections after collect for non-one-shot handles
- Codex ACP does not keep the connection after collect
- OpenCode ACP does not keep the connection after collect

User-observed behavior for Codex adds an important product constraint: after a rejected action,
Codex does not reliably continue on its own. It needs replacement instructions or a broader
"what to do next" prompt. Claude Code can continue automatically after a declined permission. The
OpenCode behavior is currently unknown and must not be assumed.

## Decision

ACP permission requests are operator decisions. The operator brain is the decision authority for
permission requests that are not covered by deterministic local allow rules or exact active
autonomy policies.

### Decision authority order

Permission requests are resolved in this order:

1. **Deterministic adapter-local allow rules.** Narrow allow rules may approve requests that are
   proven safe without consulting the brain, such as already-existing safe git-add behavior. These
   rules must remain narrow and test-covered.
2. **Exact active autonomy policy replay.** If an active autonomy policy has an exact matching
   permission signature, the operator applies that policy without another LLM call.
3. **Brain-owned permission decision.** If no deterministic rule or exact policy applies, the
   operator asks the same provider-backed brain authority to decide from current operation state,
   harness instructions, active policies, involvement level, and request details.
4. **Human escalation.** If the brain returns `escalate`, or if involvement level requires human
   approval for the request class, the operator creates a blocking attention request and moves the
   operation to `needs_human`.

### Brain decision semantics

The permission decision result is a first-class operator decision with these canonical outcomes:

| Outcome | Runtime effect | Canonical record |
| --- | --- | --- |
| `approve` | respond to ACP with the approval option selected | `permission.request.decided` with `decision=approve` |
| `reject` | respond to ACP with the rejection option selected | `permission.request.decided` with `decision=reject` |
| `escalate` | do not pretend the request was rejected by policy; create blocking attention | `permission.request.escalated` plus `attention.request.created` |

The decision prompt must include:

- operation objective and harness instructions
- active policies and exact policy matches, if any
- involvement level and its implications
- permission request signature
- command/tool/edit/user-input details
- adapter key and adapter continuation mode
- explicit instruction that rejecting Codex requires replacement instructions

### Involvement-level semantics

The involvement level gates escalation, not the brain's access to context:

| Involvement level | Permission behavior |
| --- | --- |
| `unattended` | brain may approve or reject routine requests; escalate only for hard-stop ambiguity or missing policy |
| `auto` | brain may approve or reject; escalation is allowed for policy gaps, external writes, destructive operations, or ambiguous instructions |
| `collaborative` | brain may recommend approve/reject but should escalate materially risky or policy-expanding requests |
| `approval_heavy` | default to human escalation unless an exact active autonomy policy already authorizes the request |

Harness instructions override generic autonomy only by narrowing permission. They do not silently
authorize actions outside their stated scope. For example, "use `../erdosreshala/problems/625` for
e2e" is relevant evidence for approving operator runtime writes in that project, but the brain must
still inspect the requested command and working directory.

### Adapter continuation contract

Adapters expose a permission continuation mode:

| Adapter class | Current behavior | Required operator behavior |
| --- | --- | --- |
| Claude ACP | live connection can be kept and reused | rejection may return a decline response and allow the agent to continue |
| Codex ACP | connection is not kept after collect | rejection must create an operator wakeup requiring replacement instructions before continuing |
| OpenCode ACP | connection is not kept after collect; post-rejection behavior unknown | treat as explicit-follow-up until characterized |

For Codex, a rejected permission request must not be treated as a terminal task result or a quiet
interruption. The operator must wake the brain and require a follow-up decision that gives Codex
specific replacement instructions, such as:

- "do not run that command; inspect status with a read-only command instead"
- "skip the external e2e and record it as blocked"
- "ask the human for permission because the requested write is outside the workspace"

### Event model

The canonical event stream must represent permission decisions explicitly rather than encoding them
only as session failure or waiting-input facts.

Required event families:

- `permission.request.observed`
- `permission.request.decided`
- `permission.request.escalated`
- `permission.request.followup_required`

Current implementation status: `permission.request.observed`,
`permission.request.decided`, `permission.request.escalated`, and
`permission.request.followup_required` are emitted as live permission technical facts by the ACP
runtime. The v2 attached-result path materializes these facts as canonical domain events when they
are available in the terminal attached result. Escalation incomplete results are also converted
directly from `agent_waiting_input` / `agent_requested_escalation` raw metadata.

`permission.request.observed` stores the normalized request payload and signature. It must not
store large raw transcripts beyond bounded diagnostic context.

`permission.request.decided` stores:

- decision: `approve` or `reject`
- decision source: `deterministic_rule`, `active_policy`, or `brain`
- rationale
- policy id, if an exact policy was used
- adapter key
- session id
- request signature

`permission.request.escalated` stores:

- escalation rationale
- suggested options
- involvement level
- linked attention id

`permission.request.followup_required` stores:

- adapter key
- session id
- rejection decision id
- required follow-up reason
- optional recommended instruction draft

### Runtime behavior

Approval:

1. append `permission.request.observed`
2. decide through deterministic rule, exact policy, or brain
3. append `permission.request.decided(decision=approve)`
4. respond to ACP with the adapter's approval option
5. keep/close/reuse connection according to adapter contract

Rejection:

1. append `permission.request.observed`
2. decide through exact policy or brain
3. append `permission.request.decided(decision=reject)`
4. respond to ACP with the adapter's rejection option
5. for Codex and explicit-follow-up adapters, append `permission.request.followup_required`
6. wake the drive loop so the brain can issue concrete replacement instructions

Escalation:

1. append `permission.request.observed`
2. append `permission.request.escalated`
3. create blocking `attention.request.created`
4. move operation to `needs_human`
5. attached mode waits inline if the focus is an answerable attention request

## Alternatives Considered

### Keep permission requests as ACP-level interactive approval

Rejected. This bypasses the operator brain, ignores harness instructions and involvement level as
first-class decision inputs, and produces externally selected `abort` results that are not ordinary
operator decisions.

### Always escalate permission requests to humans

Rejected. This violates the purpose of an operator for unattended or auto runs and prevents
repeatable e2e operation where the harness already gives enough context for safe approval or
rejection.

### Always reject non-auto-approved permission requests

Rejected. This is conservative but not operationally useful. It also fails for Codex because a
rejection requires replacement instructions; silent rejection strands the worker.

### Store only active autonomy policies, not individual permission decision events

Rejected. Policies are reusable rules; permission decisions are historical facts. The event stream
needs both for auditability and replay.

## Consequences

- Positive: permission approvals and refusals become ordinary operator decisions with canonical
  event evidence
- Positive: harness instructions and involvement level influence permission decisions without
  relying on a human approval UI
- Positive: Codex-specific refusal behavior is modeled instead of being hidden as an interrupted
  turn
- Positive: future exact-match autonomy policies remain useful as cached decisions, not as the
  only decision path
- Negative: this adds a new event family and therefore requires projector, query, and TUI updates
- Negative: adapter-specific continuation behavior becomes part of the runtime contract and must
  be tested per adapter
- Open question: OpenCode's post-rejection behavior must be characterized before it can be marked
  equivalent to Claude or Codex

## Implementation Plan

1. Add permission event models and projector support for observed, decided, escalated, and
   followup-required events.
2. Change ACP runtime permission handling so recognized permission requests first append
   `permission.request.observed` before responding to ACP.
3. Replace implicit ACP-layer `abort` fallback with provider-backed brain permission decisions
   when no deterministic or exact-policy decision applies.
4. Preserve existing exact policy replay, but record the policy id and decision source in
   `permission.request.decided`.
5. For rejected Codex requests, append `permission.request.followup_required` and post a wakeup so
   the next brain call gives replacement instructions.
6. For escalation, create blocking attention and set `needs_human` rather than rendering a
   rejection as if it were the operator's final decision.
7. Characterize OpenCode behavior with a live or simulated ACP regression before assigning it a
   non-conservative continuation mode.

## Verification Plan

Targeted tests:

- permission evaluator loads v2 replay state when legacy state is absent
- deterministic adapter-local allow rule records `permission.request.decided(source=deterministic_rule)`
- exact active policy match records `permission.request.decided(source=active_policy)`
- brain-approved request records approval and responds with the adapter approval option
- brain-rejected Codex request records rejection plus `permission.request.followup_required`
- brain-rejected Claude request records rejection without forcing follow-up-required when the
  adapter continues automatically
- brain-escalated request records escalation, creates blocking attention, and moves operation to
  `needs_human`
- approval-heavy involvement escalates unless exact active autonomy policy already authorizes the
  request
- harness instructions are present in the permission decision prompt
- TUI/live event stream receives permission observed/decided/escalated/followup-required events
- permission-event payloads are scoped to one ACP prompt turn and do not leak into later terminal
  results

End-to-end checks:

- run an operator-in-operator `v2` operation where Codex requests permission for
  `../erdosreshala/problems/625`; verify the operator either approves, rejects with replacement
  instructions, or escalates to `needs_human` without external ACP UI selection
- verify rejected Codex permission wakes the operator and produces a follow-up instruction turn
- verify Claude rejection path does not require the Codex follow-up mechanism

Current verification evidence on 2026-04-23:

- `pytest -q tests/test_acp_permissions.py tests/test_agent_session_runtime.py tests/test_drive_service_v2.py tests/test_event_sourced_replay.py tests/test_operation_status_queries.py tests/test_permission_evaluator.py tests/test_cli.py::test_resolution_accepts_event_sourced_operation_id tests/test_operation_command_service.py::test_provider_permission_evaluator_replays_exact_signature_policy_without_llm`
  passed (`65 passed`)
- `uv run pytest` passed (`919 passed, 11 skipped`)

## Closure Criteria

This ADR can move to `Accepted` when:

- the event names and permission decision authority order are agreed
- adapter-specific continuation modes are documented in code-facing contracts
- the OpenCode unknown is either characterized or explicitly tracked as separate follow-up work

It can move to `Verified` when:

- all targeted tests in the verification plan pass
- full `uv run pytest` passes
- at least one live or simulated Codex ACP rejection proves `permission.request.followup_required`
  wakes the operator and produces replacement instructions
- an e2e `operator run --v2` check against `../erdosreshala/problems/625` completes with no
  external ACP permission UI selection
