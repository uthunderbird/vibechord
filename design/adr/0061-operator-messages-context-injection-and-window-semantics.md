# ADR 0061: Operator messages — context injection and window semantics

## Status

Accepted

## Context

The operator already has a typed command model: every user interaction with a running operation
is a typed command routed through the durable operation inbox, applied deterministically, and
acknowledged with a status. This covers control operations (pause, stop, answer) and goal
mutations (patch_objective, patch_harness, patch_success_criteria).

A typed command is the right model for state mutations. It is not the right model for free-form
contextual guidance: "the client moved the deadline to Friday", "ignore the failing CI job, it's
a flaky infra issue", "focus on the auth module first". These are advisory signals, not state
mutations. Routing them as typed commands would require defining a typed schema for every category
of advice, which is neither practical nor valuable.

The question is: what is the right mechanism for injecting free-form context into the operator
brain's planning decisions?

## Decision

### Operator messages — distinct from typed commands

Operator messages are free-form text injected into the operator brain's context at the next
planning decision. They are not typed commands and do not directly mutate persisted state.

The distinction:

| | Operator message | Typed command |
|---|---|---|
| Structure | Free text | Typed, structured payload |
| Routing target | Brain context | Operation state machine |
| Effect | Shapes next brain decision | Mutates persisted state |
| When it takes effect | Next planning cycle | Deterministically on apply |
| Persistence | Expires after N planning cycles | Permanent record |

Operator messages are submitted via `operator message op-id "..."` and enter the operation
through the same command inbox as typed commands (using `INJECT_OPERATOR_MESSAGE` command type).
This ensures durability and ordering.

### Context window — N planning cycles

An operator message persists in the brain's planning context for a configurable number of
planning cycles: the **operator message window**. The default is **3 planning cycles**.

Rationale for a finite window rather than persistent-until-answered:

- Operator messages are advisory context, not questions requiring an answer. A mechanism that
  keeps them until acknowledged would require the user to explicitly clear every message, adding
  friction without adding value.
- Stale context is worse than no context. A message sent 20 iterations ago about a deadline
  that has since passed should not continue influencing planning decisions.
- The window makes the decay explicit and configurable. Projects with fast iteration cadence
  can set a shorter window; projects where messages need to influence many sequential decisions
  can set a longer one.

Valid range: window = 0 through ∞.
- Window = 0: the message is injected into the very next planning cycle only, then aged out
  immediately. Useful for one-shot guidance with no intent of persistence.
- No enforced minimum beyond 0.
- Very large values are permitted but may retain stale context across many iterations.

The window is a per-project or per-run configuration parameter, not a per-message parameter.
All messages in a given operation share the same window setting.

### Explicit drop event — no silent expiry

When a message ages out of the context window, `operator_message.dropped_from_context` is
emitted as a domain event. There is no silent expiry.

Rationale: transparency is a design principle. A user who sent a message and later checks the
dashboard should be able to see whether their message is still active or has expired. Silent
expiry would make the active message list unreliable as an indicator of what the brain currently
knows.

The current implementation uses a buffer cap (50 messages) as the drop trigger rather than a
planning-cycle counter. This is the existing implementation path; the planning-cycle counter
semantics described above are the target model. The buffer cap is a conservative approximation:
in practice, the 50-message limit is not reached under normal use.

### Transparency

Active operator messages — those within the context window and not yet expired — are visible in
`watch` and `dashboard`. This makes the brain's current advisory context inspectable without
reading raw events.

## Consequences

- `OperatorMessage.dropped_from_context: bool` is set when a message is evicted; the
  `operator_message.dropped_from_context` domain event records `message_id`, `text`, and `reason`
  (`window_expired` or `buffer_cap`)
- `OperatorMessage.planning_cycles_active: int` tracks how many planning cycles the message has
  been present; incremented by `_age_operator_messages()` at the start of each planning cycle
- `OperatorService._age_operator_messages()` runs before each brain call: increments counters,
  drops messages where `planning_cycles_active > window`, emits drop events
- Buffer cap (50 messages) remains as a safety valve for the hard-overflow case only
- `OperationConstraints.operator_message_window: int = 3` — per-operation window setting
- `ProjectProfile.default_message_window: int | None` — profile-level override; flows through
  `resolve_project_run_config()` → `ResolvedProjectRunConfig.message_window` → CLI
  `OperationConstraints` construction
- `INJECT_OPERATOR_MESSAGE` remains a command type — operator messages route through the inbox
  for ordering and durability, even though their effect is advisory
