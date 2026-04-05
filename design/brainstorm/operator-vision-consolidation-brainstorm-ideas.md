# Operator Vision Consolidation Brainstorm Ideas

## Status

Brainstorm only. Not a source-of-truth architecture document.

## Starting Point From The Current Vision

`operator` already has the right center of gravity:

- a control-plane mindset
- an operator loop
- LLM-first deliberation
- deterministic guardrails
- transparency and CLI-first inspectability

The new pressure is not to abandon that vision.
It is to extend it from "operator loop that can call agents" into "true harness for long-lived, transparent, steerable agent work."

## Consolidated Direction

The most coherent next-stage vision looks like this:

1. `operator` becomes a true long-lived harness
2. the default user experience is a live attached control shell
3. the persisted control plane remains authoritative for recovery
4. user interventions become first-class runtime events
5. human attention becomes an explicit runtime concept
6. project profiles shrink repetitive launch ceremony
7. approved human decisions can become project-local policy

## Thematic Breakdown

### Theme 1: True harness runtime

Need:

- richer control primitives
- per-agent and per-operation stop/pause semantics
- user-message injection
- explicit attention state

Likely first milestone:

- one-operation attached harness with pause/resume/stop/message

### Theme 2: Realtime dashboard/TUI

Need:

- live monitoring
- human-attention queue
- fast drill-down into agent activity
- intervention actions without leaving the main surface

Likely first milestone:

- one ergonomic TUI that can monitor many operations and control one selected operation well

### Theme 3: Involvement levels and policy

Need:

- explicit user-involvement model
- deferral instead of total blocking
- project-local learned precedent

Likely first milestone:

- `0`, `auto`, `guided`, `strict` semantics with visible behavior

### Theme 4: Project profiles

Need:

- reuse of stable run defaults
- transparent resolved configuration
- reduced launch friction

Likely first milestone:

- repo-local YAML profile plus explicit CLI overrides

## Most Important Internal Tension

The project now has two simultaneous pressures:

- become more interactive and shell-like
- remain recoverable, inspectable, and deterministic where it matters

The correct answer is not to choose one and drop the other.
It is to keep the persisted control plane authoritative while building a much better attached live runtime on top of it.

## Suggested Sequencing

### Near-term

1. define user intervention event model
2. define pause/stop semantics
3. define attention-state model
4. define first project-profile schema

### Mid-term

5. build a thin TUI over those state models
6. add involvement-level semantics tied to real scheduler behavior
7. add project-local policy learning and inspection/editing

### Later

8. richer multi-agent branch deferral and unattended execution
9. more adaptive autonomy around learned precedent
10. broader project/workspace management

## Candidate ADR Set

Strong candidates for the next ADR tranche:

1. True harness control-state model
2. User intervention event schema
3. Pause/stop/cancel semantics across operation and agent scopes
4. Human-attention queue and involvement-level runtime semantics
5. Project profile schema and override model
6. TUI delivery boundary over the application layer
7. Project policy / precedent memory model

## Recommended Near-Term Deliverable Shape

Do not jump straight to a huge TUI.
First make the runtime model explicit enough that a TUI can be honest.

Good first package:

- typed interventions
- explicit pause/resume
- attention-state surfacing in CLI
- repo-local project profile
- one initial attached live monitor/control surface

## Open Questions To Carry Forward

- Can the current task model support real branch deferral, or does it need another structural step first?
- Should the first dashboard be multi-operation-first or one-operation-first?
- How should project policy be reviewed, edited, and revoked?
- Which user commands should be operational events versus direct administrative actions?
