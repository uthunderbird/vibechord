# Agent Turn Summary Implementation Plan

## Goal

Make brain history decision-relevant by replacing most raw recent-agent prose with structured
turn summaries, while preserving the full latest completed agent result.

## Target Behavior

For recent history in brain prompts:

- older completed turns should be represented primarily as:
  - prior operator instruction,
  - structured turn summary,
  - result status,
  - optional fallback raw excerpt,
- the most recent completed turn should include the full raw agent result,
- the currently running turn should still appear as in-flight / awaiting result.

## Proposed Summary Contract

Each completed turn should attempt to populate:

- `declared_goal`
- `actual_work_done`
- `route_or_target_chosen`
- `repo_changes`
- `state_delta`
- `verification_status`
- `remaining_blockers`
- `recommended_next_step`

The summary should be concise and factual. It is not a second essay.

## Rollout Phases

### Phase 1: Data Shape

- add a structured turn-summary field to persisted traceability or iteration state,
- keep it optional at first,
- preserve backward compatibility for old runs with no summary.

### Phase 2: Summary Production

- after a completed agent turn, generate the summary from the full result,
- prefer provider-backed structured extraction rather than ad hoc regex parsing,
- store both the full result and the structured summary.

### Phase 3: Prompt Integration

- update decision prompt history:
  - older turns -> instruction + summary + status
  - most recent completed turn -> full result + summary
- update evaluation prompt similarly, but keep enough direct evidence for terminal judgments.

### Phase 4: Fallback Policy

- if structured extraction fails, fall back to the existing balanced raw excerpt,
- mark fallback explicitly so the brain can treat it as lower-confidence evidence.

### Phase 5: Tests

- long-result regression:
  - latest full result appears untruncated,
  - older turns use summaries instead of full prose,
- fallback regression:
  - missing summary still preserves useful raw evidence,
- prompt-size regression:
  - decision prompts shrink materially on long multi-iteration runs.

## Open Questions

- whether the latest completed turn should be fully raw in both decision and evaluation prompts,
  or only in decision prompts,
- whether the summary extractor should use the same provider as the brain or a cheaper structured
  model,
- whether summaries belong in `IterationState`, traceability artifacts, or both.

## Immediate Compatibility Note

The current balanced `head + tail` excerpt should remain in place until structured summaries are
fully integrated. It is the current safety net for tail-heavy conclusions.
