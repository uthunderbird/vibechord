# ADR 0191: Execution Profile Transparency And Status UX

- Date: 2026-04-15

## Decision Status

Accepted

## Implementation Status

Verified

Skim-safe status on 2026-04-22:

- `implemented`: ADR 0190 adds bounded dynamic execution-profile overrides through
  `set_execution_profile`, operation-local overlays, and session execution-profile stamps
- `implemented`: operation projections already expose per-adapter execution-profile views and
  session stamp payloads
- `verified`: operator-facing command/timeline rendering shows explicit request-time and
  application-time execution-profile transitions
- `verified`: status surfaces expose `active_session_execution_profile` only when an active
  session stamp exists, avoiding a duplicate derived "current model" authority
- `verified`: per-adapter `execution_profiles` and active-session execution-profile payloads are
  covered by projection, status-query, and CLI tests

## Context

ADR 0190 establishes the runtime-control and persistence contract for dynamic model and effort
overrides:

- launch defaults remain the baseline execution profile for each adapter
- accepted runtime changes are stored as operation-local execution-profile overlays
- the effective execution profile for an adapter is derived from launch defaults plus the latest
  accepted overlay
- the actual execution profile used by a concrete session is recorded in that session's
  execution-profile stamp

This is the correct state split for runtime behavior, but it leaves one UX gap and one design risk.

The UX gap:

- operators need to see when model switches were requested
- operators need to see when a session is actually running on a different model or effort level
- brief status output should make the active session's current model visible without forcing the
  reader to inspect nested JSON structures

The design risk:

- adding visibility for "current model" can easily recreate the repository's older duplicated-state
  failure mode
- a naive implementation would persist extra top-level state such as `current_model`,
  `active_model`, or `last_applied_model`, then allow that redundant state to drift from the
  operation overlay or session stamp

The design problem is therefore:

- improve model-switch transparency in logs and status surfaces
- while preserving the canonical state hygiene established by ADR 0190

## Decision

Add explicit execution-profile transparency surfaces for logs and status, but keep canonical truth
limited to the existing ADR 0190 layers.

### 1. Canonical truth remains unchanged

This ADR does not add a new authoritative execution-profile state object.

The only canonical execution-profile authorities remain:

- the launch default execution profile for each adapter
- the operation-local execution-profile overlay for each adapter
- the effective execution profile derived from those two layers
- the session execution-profile stamp for a concrete session

This ADR must not introduce any new persisted canonical fields such as:

- `current_model`
- `active_model`
- `last_applied_model`
- `current_effort`
- `active_execution_profile`

If a delivery surface needs to display the active agent's "current model", it must derive that
value from the active session stamp.

If there is no active session, delivery surfaces may instead display the adapter's effective
execution profile for future turns, but they must not label that as the active agent's current
model.

### 2. The system must distinguish three different execution-profile truths

User-facing surfaces must not collapse all execution-profile facts into one ambiguous label.

The repository must preserve these distinctions:

#### A. Requested profile change

This is the accepted command-level change to operation-local runtime intent.

Its authority comes from:

- the accepted `set_execution_profile` command
- the resulting `operation.execution_profile.updated` event

This answers:

- what change the operator requested

It does not answer:

- which session is currently using that profile

#### B. Effective profile for an adapter

This is the current operation-level execution profile in force for future turns of that adapter.

Its authority is derived from:

- the launch default execution profile
- plus the latest accepted overlay for that adapter, if any

This answers:

- what profile the operator will try to use the next time that adapter is started or reused

It does not answer:

- whether the currently active session has already picked that profile up

#### C. Actual profile of a concrete session

This is the profile the active or idle session was actually started or rebound with.

Its authority comes from:

- the session execution-profile stamp

This answers:

- what model and effort the current agent session is actually using

This session-local fact is the canonical source for active-session transparency.

### 3. Logs must show both request-time and application-time transitions

Operator-visible logs and command/event narratives must explicitly show model-switch transitions.

This ADR requires two kinds of visibility:

#### A. Request-time transparency

When `set_execution_profile` is accepted, the operation timeline and related command/event surfaces
must show a clear before/after execution-profile transition for the targeted adapter.

The rendered narrative should make it obvious:

- which adapter changed
- which profile was previously effective
- which profile is now effective

For example, the effective-profile narrative may read like:

- `execution profile updated for codex_acp: gpt-5.4 / low -> gpt-5.4-mini / medium`

The exact text may vary, but the semantic content must remain explicit.

#### B. Application-time transparency

When a session is started, rebound, or reused for a turn, the operation timeline must also show the
profile that concrete session is actually running with.

This requires an explicit derived lifecycle event or equivalent explicit timeline record that says,
in substance:

- session `<id>` started with adapter `<adapter>` on model `<model>` with effort `<level>`
- or session `<id>` reused with the same execution profile

This application-time record is required for auditability and operator comprehension.

However, this application-time record is not a second source of truth.

Its authority is derived from the session start/reuse lifecycle plus the session execution-profile
stamp. It exists for observability and narration only.

If the implementation introduces a named event for this purpose, that event must remain:

- derived from existing lifecycle facts and session stamp data
- non-authoritative for replay or state reconstruction
- replaceable by recomputation from canonical sources without changing operation truth

### 4. Status surfaces must show the current model explicitly

Status surfaces must expose the active session's current execution profile as a first-class field,
not only as deeply nested projection data.

#### A. Brief status

When an operation has an active session, brief status must explicitly show:

- the active adapter key
- the active model
- the active effort value when the adapter has one

This is the shortest truthful answer to "what model is the agent using right now?"

If there is no active session, brief status may omit a "current model" line rather than presenting
an operation-level effective profile as if it were already active-session fact.

#### B. Full status and inspect surfaces

Detailed status surfaces should keep the richer per-adapter execution-profile view introduced by
ADR 0190 and add an explicit active-session execution-profile section derived from the session
stamp.

The intended split is:

- `execution_profiles`:
  per-adapter `default`, `overlay`, `effective`, and `allowed_models`
- `active_session_execution_profile`:
  the active session's actual model/effort, if an active session exists

This keeps operation-level and session-level facts visible without collapsing them together.

### 5. The transparency layer must stay derived

All new transparency outputs required by this ADR must be derived from existing canonical layers.

Allowed derivation sources:

- accepted command payloads and command results
- `operation.execution_profile.updated`
- launch default execution-profile metadata
- operation execution-profile overlays
- derived effective execution profiles
- session execution-profile stamps
- session lifecycle facts such as start, attach, reuse, wait, or recovery

Forbidden implementation patterns:

- persisting a separate authoritative `current model` field on `OperationState`
- treating log-only transparency events as if they were canonical execution state
- persisting a duplicate active-session execution profile outside the session stamp
- allowing brief status formatting to mint its own local truth that can diverge from projections

### 6. The brief status contract must prefer active-session fact over operation-level intent

When both operation-level intent and active-session fact exist, status surfaces must not present the
effective profile as if it were the same thing as the active session profile.

Priority order for "current model" wording:

1. active session execution-profile stamp, when an active session exists
2. no active-session current-model statement, when only operation-level effective profile is known

Detailed surfaces may additionally show the effective profile for future turns, but brief status
must not blur that distinction.

## Consequences

### Positive

- operators can see model switches explicitly in the operation narrative
- brief status answers the practical question "what model is the agent using now?"
- the design keeps the canonical authority boundaries from ADR 0190
- session reuse and delayed application remain explainable because logs show both the requested
  change and the session-local applied profile

### Negative

- status and timeline rendering become more opinionated and therefore more complex
- there will be two user-visible transparency moments for one switch:
  request-time and application-time
- some readers may initially expect the accepted overlay to imply immediate active-session change,
  so surfaces must stay careful about wording

### Neutral

- this ADR does not change which execution-profile transitions are allowed
- this ADR does not permit adapter switching
- this ADR does not alter the session-reuse compatibility rules from ADR 0190

## Rejected Alternatives

### Persist a new authoritative `current model` field on the operation

Rejected because it recreates duplicated-state risk.

This would create a second operation-level execution-profile authority that could drift from:

- the latest accepted overlay
- the derived effective execution profile
- the active session stamp

### Show only per-adapter effective profile and omit active-session current-model UX

Rejected because it under-serves the operator.

The user requirement is about what the agent is using now, not only what future turns intend to
use.

### Use only session stamps and avoid an explicit request-time log narrative

Rejected because it makes model switches harder to audit.

Operators need to see both:

- that the requested profile change was accepted
- and when it became active in a concrete session

## Verification

Implementation for this ADR should not be considered complete until all of the following are
verified:

- `set_execution_profile` acceptance appears in command/timeline surfaces with explicit before/after
  execution-profile wording
- session start or reuse surfaces show the concrete applied execution profile from the session stamp
- brief status shows active adapter plus active model and effort when an active session exists
- brief status does not misrepresent an operation-level effective profile as active-session fact
- full status / inspect surfaces expose both per-adapter execution-profile views and the active
  session execution profile without duplicating canonical state
- no new authoritative execution-profile fields are added outside launch defaults, overlays,
  effective derivation, and session stamps

## Implementation Notes

The intended implementation direction is:

1. keep `OperationState` canonical execution-profile truth unchanged from ADR 0190
2. add explicit timeline rendering for accepted `set_execution_profile` transitions
3. add explicit application-time timeline rendering derived from session lifecycle plus session
   execution-profile stamp
4. add an `active_session_execution_profile` projection for status and inspect surfaces
5. update brief status renderers to show active adapter/model/effort from that active-session
   projection

Rollout order matters.

The repository should not ship the new brief-status wording or application-time timeline wording
before the underlying projections and derived lifecycle facts are in place.

The required order is:

1. canonical sources remain unchanged
2. projections expose active-session execution-profile truth from the session stamp
3. timeline/query machinery can derive request-time and application-time transparency records
4. text and JSON status renderers consume those derived surfaces

This prevents delivery-layer UX from inventing execution-profile truth ahead of the actual query
contract.

The implementation should remain projection-first.

CLI rendering helpers may format these values for text output, but they should consume derived query
payloads rather than recomputing execution-profile truth ad hoc in the delivery layer.
