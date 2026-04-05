# ADR 0062: Feature level in task hierarchy

## Status

Accepted

## Context

### Preceding design

ADR 0005 established a three-level runtime entity hierarchy: Objective → Task → Subtask. The
Objective is the durable source of truth for long-lived work; Tasks are atomic work units the
brain proposes and the runtime enforces; Subtasks are managed internally by the assigned agent
and are not visible to the operator loop.

This model is sufficient for work that decomposes cleanly into atomic tasks with a single
acceptance criterion (the Objective's goal is met). It becomes insufficient when:

- A deliverable has its own acceptance criteria separate from the Objective
- A deliverable spans multiple tasks that form a coherent review unit
- The user needs a "ready for review" gate between agent execution and final acceptance

Without a Feature level, the only review mechanism is the Objective itself — all tasks must
complete before the user can evaluate the outcome. This forces an all-or-nothing review cycle
that does not match how iterative delivery actually works.

### Why not just use tasks with labels?

A task is an atomic work unit assigned to one agent session. Grouping tasks with labels or
metadata does not give the group its own lifecycle, acceptance criteria, or review state. The
brain has no way to signal "this coherent unit is ready for review" — it can only signal task
completion or operation termination.

The Feature level is warranted precisely because it needs a lifecycle that tasks do not have.

## Decision

### Four-level runtime entity hierarchy

```
Objective   ← single per operation; jointly owned by user and brain
  └── Feature   ← optional; a bounded deliverable with acceptance criteria and review state
        └── Task   ← atomic work unit; brain proposes, runtime enforces
              └── Subtask   ← managed internally by the assigned agent; not visible to the loop
```

Feature is an **optional** intermediate level. Most operations decompose directly into Tasks.

### When a Feature is warranted

A Feature is warranted when a delivery unit satisfies all three criteria:

1. It has acceptance criteria separate from the Objective — criteria that the user evaluates
   independently of whether the overall Objective is complete.
2. It can be assigned as a whole to one agent or coordinated group — the unit is coherent enough
   to hand off and receive back.
3. It has a meaningful "ready for review" state — there is a distinct point at which the brain
   believes the unit is complete and the user should evaluate it.

When these three criteria are not all met, decompose directly into Tasks. Features should not be
created to group tasks for organisational convenience without a review lifecycle.

### Feature lifecycle states

```
in_progress → ready_for_review → accepted
                              ↘ needs_rework → in_progress (cycle)
```

- `in_progress` — the brain is executing tasks within this Feature.
- `ready_for_review` — the brain has marked all tasks within the Feature complete and is
  signalling to the user that the Feature's acceptance criteria should be evaluated.
- `accepted` — the user has accepted the Feature; its tasks are complete and the deliverable
  is done.
- `needs_rework` — the user has reviewed and found issues; the Feature returns to `in_progress`
  and the brain replans within it.

### Authority model

Both the brain and the user may propose Features:
- The brain may propose Feature decomposition during planning.
- The user may introduce or rename Features through goal patching or direct interaction.

The review lifecycle (`ready_for_review → accepted | needs_rework`) is always user-facing. The
brain may transition a Feature to `ready_for_review` by completing its tasks and signalling
review readiness. The brain cannot unilaterally mark a Feature as `accepted` — only the user can
accept a Feature.

Rationale: the acceptance step is an explicit trust boundary. The brain declaring its own work
accepted would remove the review gate the Feature level exists to provide.

### Rationale for four levels rather than three or five

**Three levels (no Feature):** The brain can decompose an Objective into many Tasks but has no
way to group them into reviewable delivery units. The only review point is operation termination.
This is insufficient for long-lived work with intermediate deliverables.

**Five levels (Feature + Sub-Feature):** Adds nesting complexity without a corresponding
capability gain. The three criteria for a Feature (separate acceptance criteria, coherent
assignment, meaningful review state) do not recurse — a Sub-Feature would have the same criteria
as a Feature, suggesting that the outer group is itself a Feature of the Objective. Four levels
is the minimum that captures the review-gate capability; five adds ceremony.

## Consequences

- `FeatureStatus` enum: `in_progress`, `ready_for_review`, `accepted`, `needs_rework`
- `FeatureState` domain model in `domain/operation.py`: `feature_id`, `title`,
  `acceptance_criteria`, `status`, `notes`, `created_at`, `updated_at`
- `FeatureDraft` / `FeaturePatch` domain types for brain proposal and update
- `OperationState.features: list[FeatureState]`
- `TaskState.feature_id: str | None` — optional FK to parent Feature
- `TaskDraft.feature_id: str | None` — brain can link new tasks to a Feature on creation
- `StructuredDecisionDTO.new_features` / `feature_updates` — brain decision schema extended
- `BrainDecision.new_features` / `feature_updates` — domain decision object extended
- Mapper `_map_feature_draft` / `_map_feature_patch` in `mappers/brain.py`
- `OperatorService._apply_feature_mutations()`: called at each planning cycle before task
  mutations; creates new `FeatureState` entries, applies patches; brain cannot set
  `ACCEPTED` directly — any attempt to set `ACCEPTED` is downgraded to `READY_FOR_REVIEW`
  (authority model enforcement)
- `feature.created` and `feature.status.changed` domain events
- `task.created` event payload includes optional `feature_id` when task belongs to a Feature
- CLI rendering of Features as a grouping layer (`tasks`, `inspect`, `dashboard`) is pending
  — the data model is complete; display is a separate concern
