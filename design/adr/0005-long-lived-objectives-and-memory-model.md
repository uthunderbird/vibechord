# ADR 0005: Long-Lived Objectives, Memory Stratification, And Interruptible Waits

## Status

Accepted

## Context

`operator` is intended to drive work that may span:

- many operator iterations,
- many external agent runs,
- many sessions,
- and potentially many different agent types.

The early implementation centered runtime state around:

- one `OperationState`,
- one `active_session`,
- and iteration-local results.

That model is sufficient for short runs and simple continuation, but it is not a strong enough foundation for long-lived objectives.

The long-lived design needs to answer at least four questions:

1. What is the durable source of truth: the objective or the session transcript?
2. How is continuity preserved across one-shot, reusable, and mixed-vendor sessions?
3. What is the operational work unit for orchestration: task, session, or transcript?
4. What does `wait_for_agent` mean once many agents or sessions may be active at once?

## Decision

The accepted direction is:

- objective-centric runtime state,
- stratified memory rather than transcript-as-memory,
- task-first orchestration,
- explicit session policy,
- and `wait_for_agent` treated as an exceptional, interruptible focus choice.

This ADR accepts the direction and the primary abstractions.
It does not claim that these abstractions alone already guarantee safe or correct long-lived orchestration.

### 1. Objective-centric state

The durable source of truth is the long-lived objective state, not any single agent session or transcript thread.

Agent sessions are execution resources.
They may be:

- one-shot,
- reusable,
- or long-lived,

but they do not define canonical work state by themselves.

### 2. Minimal accepted long-lived model

The minimal accepted shape for long-lived work is:

- `Objective`
- `Task`
- `SessionRecord`
- `Artifact`
- `MemoryEntry`

This is the smallest model the project should treat as architecturally committed at this stage.

Richer concepts such as `TaskAssignment`, `FocusState`, or more elaborate scheduling entities may still be introduced later, but they are not yet part of the minimal accepted guarantee surface of this ADR.

### 3. Stratified memory

The architecture will distinguish memory layers such as:

- `turn context`
- `session snapshot`
- `task memory`
- `objective memory`
- `artifact store`

Transcripts are raw evidence, not canonical memory.

The system should preserve durable continuity by carrying distilled state through memory entries and artifacts rather than by depending on replay of full transcripts.

### 4. Task-first orchestration

The operator should think primarily in tasks, not in threads.

Tasks are operational control units.
They should stay narrow and structured.

Long narrative summaries, discussion logs, and broad prose belong in memory entries or artifacts, not in task records.

### 5. Session policy

Task execution should support explicit session policy distinctions such as:

- `one_shot`
- `prefer_reuse`
- `require_reuse`

This replaces the assumption that continuation can be inferred only from the presence of one active session.

### 6. Interruptible waits

`wait_for_agent` is not a normal blocking mode for the operator loop.

It is an exceptional focus choice for cases where the operator intentionally wants to park on a specific dependency, session, or result.

Even then, waits are intended to be interruptible by other material events.

## Non-Guarantees

This ADR does not, by itself, guarantee:

- that distilled memory is correct or fresh,
- that event-driven wakeups are durable or deterministic,
- that the brain and scheduler will not conflict,
- or that interruptible waits are safe without a concrete event model.

The ADR accepts the direction, not the full mechanism set.

## Required Follow-Up Mechanisms

The following mechanisms are required before the stronger interpretation of this architecture should be treated as true:

### Memory provenance and freshness

`MemoryEntry` needs more than summary text.

At minimum, the design still needs:

- source references,
- freshness state such as `current`, `stale`, or `superseded`,
- invalidation or refresh semantics,
- and a way to tell whether a later artifact or finding overrides an older memory entry.

### Event and wakeup semantics

Interruptible waits only become meaningful once the operator has a defined event model.

That future model must state assumptions around:

- event ordering,
- event loss,
- duplicate delivery,
- replay,
- and wakeup triggers.

### Authority split

Long-lived task state requires a boundary between:

- what the brain may propose,
- and what the deterministic runtime enforces.

That boundary is still a required follow-up design item, especially for:

- task priority,
- dependency blocking,
- retries,
- concurrency limits,
- and runnable state.

### Blocking semantics

`wait_for_agent` cannot remain a vague synonym for "block."

The system still needs an explicit model for:

- legitimate dependency barriers,
- interrupt policy,
- and resume policy after preemption.

## Alternatives Considered

### Option A: Keep the session as the main runtime anchor

This keeps the model simpler for short runs and maps directly to headless CLI or ACP continuation.

Rejected because:

- it makes long-lived work overly vendor-thread-dependent,
- encourages transcript-as-memory behavior,
- and does not scale cleanly to multiple live sessions.

### Option B: Keep a single `active_session`, but attach richer metadata

This is the most incremental evolution of the current implementation.

Rejected because:

- it still assumes one foreground session,
- under-models multiple live agents,
- and leaves `wait_for_agent` semantics underspecified.

### Option C: Accept objective/task/session separation plus stratified memory as the direction, and defer missing mechanisms explicitly

Accepted because:

- it gives the architecture the right center of gravity,
- avoids overclaiming what is already solved,
- and leaves room to add the missing enforcement layers cleanly.

## Consequences

### Positive

- The architecture now has a clear long-lived direction without pretending it is already fully mechanized.
- One-shot and reusable sessions fit into one model.
- Task-first orchestration is explicitly preferred over session-first orchestration.
- The project avoids treating transcripts as its primary durable memory layer.

### Negative

- The design remains incomplete until the follow-up mechanisms are specified.
- Some terms that previously sounded settled are now explicitly provisional.
- Implementation cannot safely infer stronger guarantees from this ADR alone.

### Follow-Up Implications

- `design/ARCHITECTURE.md` should mirror these weaker but more precise guarantees.
- Future documentation should specify:
  - memory freshness and invalidation,
  - event and wakeup semantics,
  - authority split between brain and deterministic runtime,
  - and explicit blocking semantics.
