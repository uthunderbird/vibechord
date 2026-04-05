# RFC 0001 Critique Round 2

## Focus

Migration order, failure modes, rollback or compatibility risks, verification adequacy, and
implementation realism.

## Scope and evidence boundary

- Target only: `design/rfc/0001-acp-python-sdk-integration.md`
- Repo evidence used for claim checking:
  - `src/agent_operator/bootstrap.py`
  - `src/agent_operator/background_worker.py`
  - `src/agent_operator/runtime/supervisor.py`
  - `src/agent_operator/adapters/codex_acp.py`
  - `src/agent_operator/adapters/claude_acp.py`
  - `tests/test_codex_acp_adapter.py`
  - `tests/test_claude_acp_adapter.py`
  - `tests/test_live_background_runtime.py`
  - `tests/test_service.py`
- Constraint: critique is limited to what the RFC claims and what the local code and tests show
  about migration mechanics.

## Mechanism audit

### 1. What the RFC explicitly promises

- `codex_acp` should be migrated first as the lower-risk substrate swap at
  `design/rfc/0001-acp-python-sdk-integration.md:198-204`.
- The interim mixed state, with one ACP adapter SDK-backed and the other still bespoke, is an
  acceptable compatibility stage at
  `design/rfc/0001-acp-python-sdk-integration.md:221-225`.
- Rollback should mean leaving the bespoke adapter path in place for the regressing adapter at
  `design/rfc/0001-acp-python-sdk-integration.md:252-253`.
- ACP transport code should be deleted only after both adapters satisfy the regression gates at
  `design/rfc/0001-acp-python-sdk-integration.md:247-251`.

### 2. What the mechanism actually guarantees

- The RFC defines intent and gate language, but it does not yet specify a concrete selection
  mechanism for running bespoke and SDK-backed ACP implementations side by side during migration.
- The current runtime wiring still instantiates concrete ACP adapters directly in
  `src/agent_operator/bootstrap.py:35-64` and `src/agent_operator/background_worker.py:96-121`.
- The background worker also carries Claude-specific failure classification directly in
  `src/agent_operator/background_worker.py:181-182`, which means mixed-mode migration touches more
  than just adapter internals.

### 3. Where the stronger reading fails

- The RFC reads as if phased migration and rollback are operationally available, but it does not yet
  describe the operator-level mechanism that would make dual-path selection, fallback, or
  per-adapter rollback possible.
- The RFC reads as if the Phase 2 and Phase 3 verification gates are sufficient to protect shared
  ACP transport deletion, but the verification matrix still leaves important mixed-mode and
  per-adapter runtime paths under-specified.

### 4. Minimal fix set

- `P0`: add an explicit migration/rollback mechanism for dual-path selection during the mixed stage.
- `P0`: strengthen the verification matrix so deletion is gated on the runtime paths that are
  actually risky in a mixed bespoke/SDK-backed deployment.
- `P1`: tighten the argument that `codex_acp` is the right first target by distinguishing adapter
  risk from shared ACP substrate risk.

## Critical findings

1. `verified issue`: the RFC promises a mixed compatibility stage and adapter-by-adapter rollback,
   but it does not specify the operator-owned mechanism that makes that possible.
   Right now the runtime composes concrete ACP adapters directly in bootstrap and the background
   worker, so “keep the bespoke path in place” is not yet an executable migration plan by itself.
   Evidence:
   - Mixed stage claimed at `design/rfc/0001-acp-python-sdk-integration.md:221-225`.
   - Rollback defined as leaving the bespoke adapter path in place at
     `design/rfc/0001-acp-python-sdk-integration.md:252-253`.
   - Concrete runtime wiring in `src/agent_operator/bootstrap.py:35-64`.
   - Concrete background-worker wiring in `src/agent_operator/background_worker.py:96-121`.
   - Claude-specific background-worker failure classification in
     `src/agent_operator/background_worker.py:181-182`.
   Consequence:
   - Without a named selection mechanism such as per-adapter feature gating, injected substrate
     selection, or side-by-side adapter classes, the rollback and mixed-mode claims are weaker than
     they read.

2. `verified issue`: the verification plan is not yet strong enough to justify the RFC’s deletion
   and parity claims for a shared ACP substrate migration.
   The RFC requires direct runtime evidence for “at least one ACP-backed worker,” but deletion is
   conditioned on both ACP adapters satisfying regression gates and the mixed state remaining safe.
   Current local live evidence is narrower than that stronger reading.
   Evidence:
   - Phase 2 verification list at `design/rfc/0001-acp-python-sdk-integration.md:205-214`.
   - Stage 4 deletion gate at `design/rfc/0001-acp-python-sdk-integration.md:247-251`.
   - Live ACP runtime evidence in repo is Codex background continuation only at
     `tests/test_live_background_runtime.py:77-131`; the Claude live test there is for
     `claude_code`, not `claude_acp`, at `tests/test_live_background_runtime.py:45-75`.
   - Claude cooldown behavior is exercised at the service layer with fake agents rather than through
     the real ACP adapter path in `tests/test_service.py:257-299`.
   Consequence:
   - As written, the RFC could pass its stated runtime-evidence bar while still lacking direct
     end-to-end evidence for the second migrated adapter or for the mixed bespoke/SDK-backed state
     that the migration plan explicitly relies on.

## Lower-priority findings

1. `bounded concern`: the argument that `codex_acp` is the lower-risk first migration target is
   directionally plausible at the adapter level, but it overstates how much shared-substrate risk is
   actually removed by choosing Codex first.
   Both ACP adapters still depend on the shared ACP transport shape, background-worker startup, log
   metadata, and session create/load flows.
   Evidence:
   - Lower-risk claim at `design/rfc/0001-acp-python-sdk-integration.md:198-204`.
   - Shared ACP session/new and session/load patterns in `src/agent_operator/adapters/codex_acp.py:78-149`
     and `src/agent_operator/adapters/claude_acp.py:74-147`.
   - Shared runtime background orchestration in `src/agent_operator/runtime/supervisor.py:61-120`
     and `src/agent_operator/background_worker.py:85-171`.
   Implication:
   - The codex-first choice still makes sense as a first adapter migration, but the RFC should be
     more explicit that it only de-risks part of the shared ACP migration surface.

2. `bounded concern`: rollback is described only as “leave the bespoke adapter path in place,” but
   the RFC does not distinguish rollback of adapter internals from rollback of shared ACP seams such
   as bootstrap wiring, background-worker handling, and observability hooks.
   Evidence:
   - Rollback sentence at `design/rfc/0001-acp-python-sdk-integration.md:252-253`.
   - Shared seam inventory appears earlier in the RFC at
     `design/rfc/0001-acp-python-sdk-integration.md:97-108`, but rollback does not map to those
     surfaces.
   Implication:
   - The current wording risks underestimating how much configuration and runtime wiring might also
     need to remain dual-path until the migration is complete.

## Recommendations

1. Add an explicit migration mechanism for the mixed stage:
   name how `operator` will select bespoke vs SDK-backed ACP implementations per adapter during
   Phases 2 and 3, and how rollback flips that selection back without rewriting the whole runtime.
2. Strengthen the verification gates so Stage 4 deletion requires:
   - direct runtime evidence for each migrated ACP adapter, not just one ACP-backed worker overall,
   - verification of the mixed deployment stage where one ACP adapter is SDK-backed and the other is
     still bespoke,
   - and explicit coverage of background-worker, wakeup reconciliation, and log/metadata parity in
     that mixed stage.
3. Narrow the codex-first rationale:
   say clearly that `codex_acp` is the lower-risk first adapter migration, while shared ACP
   substrate and runtime wiring remain cross-adapter risk surfaces that still need separate
   verification.
4. Expand rollback wording to cover shared seams:
   specify whether bootstrap wiring, background-worker behavior, and observability hooks also remain
   dual-path until both adapters clear the regression gates.

## Ledger

- target document: `design/rfc/0001-acp-python-sdk-integration.md`
- focus used: migration order, failure modes, rollback or compatibility risks, verification
  adequacy, and implementation realism
- main findings:
  - the RFC promises mixed-mode migration and rollback without yet specifying the concrete operator
    mechanism that enables dual-path selection
  - the verification bar is too weak relative to the deletion and parity claims because it can pass
    with runtime evidence for only one ACP-backed adapter
  - the codex-first rationale is directionally sound but currently understates the shared ACP
    substrate and runtime wiring risks that remain
- exact ordered fix list for the repair round:
  1. Add an explicit operator-level mechanism for mixed-mode selection and rollback between bespoke
     and SDK-backed ACP implementations.
  2. Strengthen the verification matrix so deletion requires direct runtime evidence for each
     migrated ACP adapter and for the mixed deployment stage.
  3. Narrow the codex-first rationale so it claims only a lower-risk first adapter migration, not a
     full shared-substrate risk reduction.
  4. Expand rollback wording so it covers shared seams such as bootstrap, background-worker wiring,
     and observability hooks where dual-path compatibility may also be required.
