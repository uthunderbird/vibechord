# RFC 0001 Critique Round 1

## Focus

Completeness and correctness of dependencies, prerequisites, interface impacts, and architectural
boundary claims.

## Scope and evidence boundary

- Target only: `design/rfc/0001-acp-python-sdk-integration.md`
- Repo evidence used for claim checking:
  - `src/agent_operator/protocols/agents.py`
  - `src/agent_operator/config.py`
  - `src/agent_operator/bootstrap.py`
  - `src/agent_operator/background_worker.py`
  - `src/agent_operator/runtime/profiles.py`
  - `tests/test_codex_acp_adapter.py`
  - `tests/test_claude_acp_adapter.py`
- Constraint: the ACP Python SDK source is not vendored in this repo, so SDK-surface concerns below are
  bounded to what the RFC claims and what the local code requires.

## Critical findings

1. `verified issue`: the prerequisites section omits a material runtime prerequisite: SDK adoption does
   not by itself remove the need for ACP-speaking subprocesses or equivalent launch targets.
   The current adapters still depend on adapter-specific commands and subprocess startup settings for
   `claude_acp` and `codex_acp`, so the RFC should explicitly preserve that prerequisite unless it is
   separately being changed.
   Evidence:
   - RFC dependency section speaks only about adding the SDK as a Python dependency at
     `design/rfc/0001-acp-python-sdk-integration.md:63`.
   - Current runtime still depends on adapter command settings at
     `src/agent_operator/config.py:33`, `src/agent_operator/config.py:41`.
   - Those commands are wired into the live service and background worker at
     `src/agent_operator/bootstrap.py:52`, `src/agent_operator/bootstrap.py:59`,
     `src/agent_operator/background_worker.py:106`, `src/agent_operator/background_worker.py:113`.

2. `verified issue`: the “internal adapter refactor, not a contract change” claim is too strong unless
   it explicitly includes the full session lifecycle and visible behavior already attached to the
   `AgentAdapter` boundary.
   The stable boundary is not just method names. It includes follow-up semantics, `WAITING_INPUT`
   projection, `close`, background-worker handoff, and adapter-visible approval behavior.
   Evidence:
   - The formal protocol includes `start`, `send`, `poll`, `collect`, `cancel`, and `close` at
     `src/agent_operator/protocols/agents.py:22`.
   - The RFC currently states the claim broadly at
     `design/rfc/0001-acp-python-sdk-integration.md:46`.
   - Tests show operator-visible semantics that must survive the refactor:
     reload/follow-up behavior at `tests/test_codex_acp_adapter.py:159`,
     waiting-for-approval behavior at `tests/test_codex_acp_adapter.py:224`,
     approval auto-handling at `tests/test_codex_acp_adapter.py:248`,
     live-connection reuse for Claude at `tests/test_claude_acp_adapter.py:186`,
     and Claude permission handling at `tests/test_claude_acp_adapter.py:248`.

3. `verified issue`: the dependency/prerequisite inventory is still incomplete because it understates
   how much non-adapter wiring currently encodes ACP-specific behavior.
   The RFC names bootstrap and background-worker composition, but it should also name config/profile
   surfaces and operator inspection surfaces that depend on session metadata and log paths.
   Evidence:
   - Adapter settings are part of the public runtime configuration surface at
     `src/agent_operator/config.py:33`, `src/agent_operator/config.py:41`.
   - Project profiles can override those adapter settings at
     `src/agent_operator/runtime/profiles.py:188`.
   - CLI/dashboard paths read adapter-specific session metadata and Codex log artifacts at
     `src/agent_operator/cli/main.py:1783`, `src/agent_operator/cli/main.py:1841`,
     `src/agent_operator/cli/main.py:1996`.

## Lower-priority findings

1. `bounded concern`: the scope section says session create/load/resume/fork lifecycle glue should move
   into the SDK-backed layer, but the repo evidence only demonstrates `new` and `load` in the current
   adapters. Without local evidence for `resume` or `fork`, this wording risks over-inventorying the
   migration target.
   Evidence:
   - Scope claim at `design/rfc/0001-acp-python-sdk-integration.md:83`.
   - Current tested lifecycle evidence is `session/new` and `session/load` at
     `tests/test_codex_acp_adapter.py:180`,
     `tests/test_claude_acp_adapter.py:140`,
     `tests/test_claude_acp_adapter.py:149`.

2. `bounded concern`: the Phase 1 inventory list omits `bootstrap.py`, `config.py`, and
   `runtime/profiles.py` even though the RFC earlier acknowledges those surfaces.
   That makes the migration plan less complete than the dependency section above it.
   Evidence:
   - Phase 1 inventory list at `design/rfc/0001-acp-python-sdk-integration.md:145`.
   - Wiring/config/profile impact at `src/agent_operator/bootstrap.py:42`,
     `src/agent_operator/config.py:50`,
     `src/agent_operator/runtime/profiles.py:188`.

## Recommendations

1. Add an explicit prerequisite note that SDK adoption does not eliminate the need for ACP-capable
   worker executables or equivalent subprocess launch targets; the SDK is a client-side substrate, not
   the worker implementation.
2. Narrow the “not a contract change” claim so it preserves the full `AgentAdapter` lifecycle and the
   externally visible semantics already attached to that lifecycle: follow-up behavior,
   `WAITING_INPUT`, approval routing outcomes, close/cleanup behavior, and background-worker handoff.
3. Expand the dependency inventory to include configuration, project-profile overrides, and
   inspection/log surfaces that currently encode ACP-specific behavior.
4. Downgrade or justify the `resume/fork` lifecycle wording unless the repo can point to a concrete
   current or planned operator dependency on those session paths.
5. Make the migration-plan inventory list match the broader dependency section by explicitly naming
   `bootstrap.py`, `config.py`, and `runtime/profiles.py`.

## Exact ordered fix list for repair round

1. Amend the dependencies/prerequisites section to say that, even after SDK adoption, `operator`
   still requires ACP-speaking worker commands or an equivalent adapter-specific launch target unless a
   separate RFC changes that runtime assumption.
2. Rewrite the “internal adapter refactor, not a contract change” sentence so it preserves the whole
   `AgentAdapter` lifecycle boundary and its visible semantics, not just a vague “API unchanged”
   reading.
3. Add config/profile/inspection surfaces to the dependency inventory: `config.py`,
   `runtime/profiles.py`, and CLI/log consumers that depend on session metadata or upstream logs.
4. Either remove `resume/fork` from the scope list or justify them with an explicit operator
   dependency claim.
5. Expand Phase 1 inventory and classification work to include `bootstrap.py`, `config.py`, and
   `runtime/profiles.py` in addition to the currently listed ACP files.

## Ledger

- target document: `design/rfc/0001-acp-python-sdk-integration.md`
- focus used: completeness and correctness of dependencies, prerequisites, interface impacts, and
  architectural boundary claims
- main findings:
  - prerequisites currently understate that ACP worker executables or equivalent launch targets remain
    a runtime dependency
  - the “internal refactor” claim needs to preserve full `AgentAdapter` lifecycle semantics, not just
    method names
  - dependency and migration inventories still omit config/profile/inspection surfaces that encode ACP
    behavior today
- exact ordered fix list for the repair round:
  1. Amend the prerequisites section to preserve the ACP-worker runtime dependency assumption.
  2. Narrow the “not a contract change” claim to the full `AgentAdapter` lifecycle and visible
     semantics.
  3. Add config/profile/inspection surfaces to the dependency inventory.
  4. Remove or justify the `resume/fork` lifecycle wording.
  5. Expand the Phase 1 inventory list to include bootstrap/config/profile files.
