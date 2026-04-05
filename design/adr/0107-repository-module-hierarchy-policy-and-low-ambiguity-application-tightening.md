# ADR 0107: Repository module hierarchy policy and low-ambiguity application tightening

## Status

Implemented

## Context

The repository currently contains multiple top-level Python packages under
`src/agent_operator/`, but they do not all have the same structural needs.

The most urgent problem is `src/agent_operator/application`, which has accumulated many files at one
flat namespace level. The package already contains multiple implicit families encoded in filenames
rather than in the filesystem hierarchy:

- `event_sourced_*`
- `operation_drive*`
- a larger residual `operation_*` family
- `attached_*`
- `process_*`

This is not just a naming inconvenience. It creates real ambiguity about:

1. which files form durable module families
2. which files are special top-level anchors
3. which files do not belong in `application` at all
4. whether `__init__` barrels are being used as public API curation or as camouflage for poor file
   placement

At the same time, a repository-wide hierarchy policy must avoid the opposite failure mode:
mechanically normalizing every package into deeper subpackages just to make the tree look symmetric.

The codebase already suggests different categories of packages:

- packages that are actively over-flattened
- packages that may become hierarchy candidates later
- packages that are coherent enough to remain flat for now
- intentionally thin support packages
- single-surface packages that should remain simple unless growth forces a split

The most obvious file-level misplacement currently identified is
`application/requests.py`. `AgentRunRequest` is used by adapters, ACP/runtime code, protocols, and
tests. That usage pattern is broader than application-orchestration ownership and makes the file
look more like a shared contract / DTO artifact than an application-local service module.

## Decision

This ADR defines a repository-wide module hierarchy policy and one concrete first restructuring
target.

### 1. Repository-wide package classification

The current top-level packages should be treated as follows.

#### Active hierarchy-tightening target

- `agent_operator.application`

This is the package where hierarchy debt is currently strongest and where the next structural
cleanup should actively land.

#### Future hierarchy candidate

- `agent_operator.runtime`

`runtime/` has enough density and latent family structure to merit future hierarchy review, but this
ADR does **not** prescribe its eventual subpackage map.

Current high-confidence latent families inside `runtime/` are:

- control-delivery infrastructure:
  - `runtime/commands.py`
  - `runtime/control_bus.py`
  - `runtime/wakeups.py`
- vendor-log surfaces:
  - `runtime/claude_logs.py`
  - `runtime/codex_logs.py`

These are strong future clustering candidates because they already read as semantic families rather
than as accidental filename similarity.

At the same time, this ADR intentionally leaves several `runtime/` questions open:

- whether `background_inspection.py` and `supervisor.py` should eventually form a
  `runtime/background` or `runtime/supervisor` family
- whether file-backed stores should group by persistence mechanism or remain separated by bounded
  context:
  - `store.py`
  - `trace.py`
  - `history.py`
  - `policies.py`
  - `project_memory.py`
  - `facts.py`
- whether thin/special modules should remain standalone:
  - `files.py`
  - `clock.py`
  - `console.py`
  - `agenda.py`
  - `profiles.py`

Any future `runtime/` decomposition should preserve the curated import ergonomics currently exposed
by `runtime.__init__` rather than replacing them with a raw internal tree.

#### Stable flat for now

- `agent_operator.domain`
- `agent_operator.protocols`
- `agent_operator.providers`
- `agent_operator.adapters`
- `agent_operator.acp`

These packages are broad, but their current flatness is not yet the dominant architectural problem.
They should be treated as flat **for now**, not as permanently frozen.

#### Intentionally thin support packages

- `agent_operator.dtos`
- `agent_operator.mappers`
- `agent_operator.projectors`
- `agent_operator.testing`

These should remain intentionally small and flat unless real growth creates a clear, semantic reason
to split them further.

#### Single-surface package

- `agent_operator.cli`

`cli/` should remain a single-surface package unless command-surface growth produces a real,
coherent family structure that justifies deeper hierarchy.

### 2. Root package rule

The root package should remain very small.

- `agent_operator.__init__` should stay a thin façade
- `bootstrap.py` remains the composition-root / assembly boundary

Neither should become a dumping ground for family modules that merely lack a better location.

### 3. Subpackage justification rule

A subpackage is justified when a family is:

- semantic rather than purely prefix-based
- dense enough to benefit from a dedicated namespace
- visible as a real family in naming, dependency shape, and usage
- unlikely to become a leftovers bucket

A subpackage is **not** justified merely because:

- another package was recently split
- the current tree looks asymmetrical
- a group of files shares a filename prefix

### 4. Anti-symmetry rule

The repository should not be normalized by symmetry.

The fact that one package is over-flattened does **not** imply that all other top-level packages
must be reshaped to look similar. Structure should follow semantic pressure, not aesthetic
uniformity.

### 5. Export-surface rule

`__init__.py` and `__all__` are for curated import surfaces, not for masking poor placement.

Barrel exports may remain useful where they improve ergonomics, but they should expose stable,
intentional names rather than mirror every internal module.

### 6. First-pass application hierarchy decision

The first restructuring pass inside `application/` should introduce these subpackages:

- `agent_operator.application.drive`
- `agent_operator.application.event_sourcing`

These families already exist clearly in both naming and responsibility shape, and moving them into
real subpackages is expected to improve the hierarchy without introducing speculative
reclassification.

### 7. Selective relocation decision

`application/requests.py` should be moved out of `application` in the same broad wave or an
adjacent focused wave.

It should be treated as a shared contract / DTO artifact rather than an application-local service
module. The preferred landing place is an existing contract-oriented package such as `dtos/`, or
another small contract namespace if that proves clearer during implementation.

This ADR does **not** decide that `AgentRunRequest` belongs to `domain`.

### 8. Explicit defer decision

The larger `operation_*` family should **not** be bulk-moved into `application/operation/` yet.

That move is deferred until the repository defines a stricter membership rule than "filename starts
with `operation_`".

Examples of files that are explicitly left top-level in `application` for now:

- `application/service.py`
- `application/operator_policy.py`
- `application/loaded_operation.py`
- `application/attached_session_registry.py`
- `application/attached_turns.py`
- `application/process_managers.py`
- `application/process_signals.py`

These files are either:

- special top-level anchors
- still semantically ambiguous
- or likely to require a later boundary decision rather than immediate relocation

## Alternatives Considered

### Option A: Keep `application/` flat and only refine naming

Rejected.

The package is already carrying structure in filename prefixes. Leaving the filesystem flat would
preserve the mismatch between semantic families and package hierarchy.

### Option B: Create `application/drive/`, `application/event_sourcing/`, and `application/operation/` immediately

Rejected for the first pass.

`drive` and `event_sourcing` are already low-ambiguity families. The residual `operation_*` set is
not yet disciplined enough to justify one bulk move. Doing that now would likely recreate a broad
catch-all package under a new folder name.

### Option C: Move many `application` files into `domain`

Rejected.

The current evidence supports selective relocation of a few contract-like artifacts, not a broad
claim that much of `application` is actually domain logic.

### Option D: Use `application.__init__` and `__all__` to hide the flat structure

Rejected.

Barrel exports can curate import ergonomics, but they do not fix an incoherent filesystem shape.

### Option E: Normalize all top-level packages into similar multi-level trees

Rejected.

This would optimize for symmetry rather than for actual semantic pressure and would likely create
more hierarchy than the current repository needs.

## Consequences

- `implemented`: `application/` is the active hierarchy-tightening target
- `implemented`: the first `application` pass should create `drive/` and `event_sourcing/`
  subpackages
- `implemented`: `application/requests.py` should move into a contract-oriented package
- `implemented`: export surfaces should be curated after hierarchy improvements rather than used as a
  substitute for them
- `planned`: `runtime/` remains the next likely package to review after `application/`
- `planned`: the strongest currently visible `runtime/` family candidates are control-delivery
  infrastructure and vendor-log surfaces
- `deferred`: the final home of the `operation_*` family remains a separate architectural question
- `deferred`: the eventual `runtime/` subpackage map is intentionally left undecided
- `stable for now`: `domain/`, `protocols/`, `providers/`, `adapters/`, and `acp/` do not require
  immediate hierarchy intervention
- `intentionally thin`: `dtos/`, `mappers/`, `projectors/`, and `testing/` should not be
  restructured without real growth pressure

This ADR intentionally favors low-ambiguity structure over maximal early cleanup. The goal is to
make the module tree more honest without replacing one flat junk drawer with another or normalizing
the whole repository by aesthetic symmetry.
