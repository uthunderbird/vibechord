# ADR 0017: Involvement Levels And Autonomy Policy

## Status

Accepted

## Context

[ADR 0013](/Users/thunderbird/Projects/operator/design/adr/0013-operation-command-inbox-and-command-envelope.md)
introduces a live command inbox for human intervention.

[ADR 0014](/Users/thunderbird/Projects/operator/design/adr/0014-deterministic-command-reducer-vs-brain-mediated-replanning.md)
separates deterministic command control from brain-mediated replanning.

[ADR 0015](/Users/thunderbird/Projects/operator/design/adr/0015-scheduler-state-and-pause-semantics-for-attached-runs.md)
defines the first scheduler-state and pause model for attached runs.

[ADR 0016](/Users/thunderbird/Projects/operator/design/adr/0016-attention-request-taxonomy-and-answer-routing.md)
introduces typed `AttentionRequest` objects and answer routing.

Those decisions create the next policy question:

- how often should the operator ask the user for direction
- when should it continue autonomously
- when should it defer one path and keep working on others
- and when should it hard-stop because human judgment is required

Today the system does not have a first-class autonomy policy model.

Without one, "human in the loop" behavior will remain too implicit and unstable:

- one run may ask too often
- another may invent policy in places where it should stop
- unattended usage will be awkward
- and future TUI attention surfaces will lack a principled threshold for what deserves human
  interruption now

The project needs an explicit involvement model that is:

- inspectable
- adjustable at runtime
- tied to typed attention requests
- and compatible with long-lived autonomous work

## Decision

`operator` will introduce explicit involvement levels as part of its control-plane autonomy
policy.

The purpose of involvement levels is not only to tune how chatty the operator is.
Their purpose is to determine:

- which situations must create attention requests
- which attention types are blocking
- when the operator may defer one branch and continue others
- and when the operator must ask before consequential or conceptually novel decisions

The initial involvement levels are:

- `unattended`
- `auto`
- `collaborative`
- `approval_heavy`

## Semantic Meaning Of Each Level

### `unattended`

The user is effectively unavailable.

The operator should:

- continue autonomously where existing policy permits
- create attention requests when needed
- prefer deferring blocked branches rather than stopping the whole operation where possible
- avoid waking or blocking on the user except for configured hard-stop conditions

This mode is intended for times when the user is away from the machine.

### `auto`

This should be the default.

The operator should ask the user when it encounters a conceptually novel situation that it
cannot resolve confidently from:

- existing project policy
- prior accepted decisions
- the current objective and harness
- or deterministic runtime rules

Ordinary tactical work should continue without asking.

### `collaborative`

The operator should ask more readily before:

- major route changes
- strategic reprioritization
- destructive actions
- or project-shaping decisions

This mode favors closer human steering without requiring approval for everything.

### `approval_heavy`

The operator should ask before many classes of consequential decisions.

This mode is appropriate for:

- unfamiliar projects
- high-risk environments
- or work where the user wants strong approval control

## Relation To Attention Requests

Involvement levels are defined in terms of attention behavior, not just prose policy.

They should influence at least:

- which situations become attention requests
- which attention requests are blocking
- whether unresolved attention may be deferred
- and whether the scheduler may continue other work while some attention items remain open

This means involvement policy sits above the attention model, not beside it as an unrelated
feature.

## Strong Rule

The operator should prefer:

- defer-and-continue

over:

- total-stop

when all of the following are true:

- the current issue is represented as non-blocking attention
- policy at the current involvement level permits deferral
- other meaningful work remains available

The operator should hard-block only when:

- the attention item is blocking
- and no policy allows autonomous continuation around it

This is especially important for `unattended` and `auto` modes.

## Novelty And Policy Gap Detection

This ADR does not attempt to formalize a full novelty-detection algorithm.

But it does define the policy expectation:

- in `auto`, conceptually novel situations and unresolved policy gaps should become attention
  requests rather than silent operator improvisation

Examples include:

- a new class of repo bootstrap decision
- a previously unseen destructive cleanup
- a strategic fork not covered by prior accepted precedent
- repeated agent disagreement on whether the objective is actually complete

This keeps the operator from quietly inventing policy where it should instead surface a new
decision boundary.

## Runtime Adjustability

The involvement level should be:

- visible in operation state
- adjustable by command during a live run
- reflected in inspection and future TUI surfaces

Changing involvement level is a deterministic control-plane action.

Its downstream effect on planning and attention behavior may require replanning, but the level
change itself should not depend on the operator brain's approval.

## Relation To Policy Learning

Involvement levels and policy learning are related but not identical.

The involvement level answers:

- how willing the operator is to proceed without asking

Project-local policy answers:

- what previously approved decisions the operator may rely on

The intended relationship is:

- stronger project policy reduces unnecessary interruptions at a given involvement level
- but involvement level still controls whether conceptually novel or sensitive situations must be
  surfaced

This ADR does not define policy promotion workflow.
It only defines the autonomy policy that such workflow will feed.

## Non-Goals

This ADR does not define:

- the final project-local policy storage model
- the full novelty-detection algorithm
- the exact scoring or threshold system for uncertainty
- per-branch or per-task overrides beyond the initial global operation-level model
- or the full TUI rendering of involvement state

Those are follow-up decisions.

## Minimum Requirements

The stronger guarantee of this ADR depends on several minimum rules:

- involvement level must be explicit and inspectable
- the current involvement level must influence attention behavior
- `unattended` must prefer defer-and-continue over unnecessary global blocking
- `auto` must surface conceptually novel situations and policy gaps rather than silently invent
  policy
- changing involvement level at runtime must be deterministic and auditable
- inspection and trace surfaces should expose the active involvement level

## Alternatives Considered

### Option A: Keep one implicit human-in-the-loop behavior

Rejected because:

- it makes long-lived usage brittle,
- gives users poor control over autonomy,
- and leaves too much behavior hidden in prompts or implementation accidents.

### Option B: Treat involvement as just a UI preference or verbosity knob

Rejected because:

- the real issue is not message frequency
- it is runtime control over when the operator may proceed, defer, or block

### Option C: Introduce explicit involvement levels as autonomy policy

Accepted because:

- it matches real usage patterns
- it integrates naturally with attention requests
- it supports unattended operation without forcing unsafe improvisation
- and it gives later policy-learning work a clear behavioral frame

## Consequences

### Positive

- Long-lived runs gain explicit autonomy policy rather than hidden prompt behavior.
- Unattended execution becomes more principled.
- `auto` mode has a clearer product meaning.
- Attention requests gain a policy context for blocking vs deferral.
- Future TUI surfaces can show why the operator did or did not ask the user.

### Negative

- The project will need to define novelty and policy-gap detection more concretely later.
- Users may still disagree with the default `auto` threshold until the model matures.
- A purely global involvement level may feel too coarse for some mixed-sensitivity operations.

### Follow-Up Implications

- A follow-up ADR should define policy memory and promotion workflow.
- A follow-up ADR should define deferred-branch behavior in more detail.
- The runtime will likely need an `InvolvementLevel` domain model.
- `inspect`, `list`, and future live monitoring should surface the active involvement level and
  relevant autonomy reasoning.
