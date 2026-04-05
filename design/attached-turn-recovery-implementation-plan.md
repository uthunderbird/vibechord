# Attached Turn Recovery Implementation Plan

## Goal

Prevent attached runs from waiting forever on half-completed agent turns.

The first implementation target is:

- detect attached turns that exceed a timeout,
- recover from persisted truth,
- and replan from the recovered state instead of hanging indefinitely.

## First Slice

### 1. Add attached-turn timeout configuration

Add a narrow runtime setting for attached turns, for example:

- `attached_turn_timeout_minutes`

This should default to a conservative value such as `60`.

The timeout applies to one attached agent turn, not to the entire operation.

### 2. Persist enough timing state to detect suspect turns

Track attached-turn timing on the active session or iteration, such as:

- turn started at
- last progress timestamp already known to the operation
- recovery attempted at

Do not create a hidden in-memory-only timeout mechanism.

The timeout decision should be reconstructable from persisted operation truth.

### 3. Add deterministic attached-turn timeout detection

During scheduler progress checks, if:

- an attached turn is still active,
- no completed result has been recorded,
- and elapsed wall-clock time exceeds the configured timeout,

then mark the turn as timed out and move into recovery handling.

This should surface a runtime alert instead of silently remaining in normal waiting.

### 4. Add recovery inspection

Recovery should gather evidence from:

- current `OperationState`
- current session metadata
- latest completed tool results visible in adapter logs
- latest completed full agent message if present
- current repository truth such as dirty files or recent commits

Recovery should produce a compact internal summary:

- whether the agent appears alive
- latest meaningful completed output
- latest completed tool action
- whether repo changes were landed
- whether verification already ran
- whether the turn appears safe to replan from

### 5. Replan from recovered state

If recovery finds enough canonical evidence, do not keep waiting.

Instead:

- persist the recovery summary,
- close the stuck waiting state,
- and run the brain again using recovered state as the new planning seam.

If recovery does not find enough evidence, mark the task blocked with an explicit runtime reason
rather than silently looping.

## Prompt / Brain Implications

Recovery should not inject arbitrary streamed text into prompts.

Prefer:

1. latest completed full agent message
2. otherwise completed tool-backed recovery summary
3. otherwise the last persisted completed result already in the operation

The brain should see recovery as a visible event, not as invisible mutation of history.

## Suggested State / Event Additions

Potential additions:

- runtime alert code such as `attached_turn_timeout`
- recovery event such as `attached_turn.recovery_started`
- recovery event such as `attached_turn.recovered`
- recovery event such as `attached_turn.recovery_failed`

Potential persisted fields:

- `recovery_summary`
- `recovered_from_session_id`
- `recovered_from_iteration_index`

## Tests

Add tests for:

- attached turn exceeding timeout and triggering recovery
- recovery that finds a latest completed agent message and replans successfully
- recovery that finds only completed tool output plus repo diff and replans successfully
- recovery that finds nothing trustworthy and marks the task blocked
- report/runtime-alert surfaces showing timeout recovery honestly

## Follow-Up Slices

After the first slice:

1. expose timeout and recovery status in `watch`, `report`, and `sessions`
2. add adapter-specific helpers for extracting latest completed tool state cleanly
3. tune timeout heuristics by agent class or task type if needed
4. consider a manual `recover-agent-turn` command only if the automatic path proves insufficient
