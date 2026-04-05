# RFC 0003: Introduce a shared ACP session runner beneath vendor adapters

## Status

Proposed

## Historical note

This RFC still discusses vendor adapters as the active public runtime shell. Current repository
truth keeps the ACP session runner as an implementation detail, while public runtime ownership is
described by ADR 0081, ADR 0082, ADR 0083, ADR 0089, and ADR 0091.

## Context

RFC 0001 establishes that `operator` should adopt the ACP Python SDK as the default implementation
substrate for ACP-backed agents while preserving an operator-owned ACP boundary. That substrate seam
now exists.

That change removed most duplicated low-level ACP transport work, but it did not remove a second
layer of duplication in the adapters themselves.

Today `claude_acp` and `codex_acp` still carry parallel logic for:

- connection initialization,
- session creation and session loading,
- prompt/send lifecycle,
- notification and request draining,
- in-memory session bookkeeping,
- transcript and progress accumulation,
- terminal result collection,
- and cancel / close skeleton behavior.

This duplication is visible in the current adapter pair:

- [`src/agent_operator/adapters/claude_acp.py`](/Users/thunderbird/Projects/operator/src/agent_operator/adapters/claude_acp.py)
- [`src/agent_operator/adapters/codex_acp.py`](/Users/thunderbird/Projects/operator/src/agent_operator/adapters/codex_acp.py)

At the same time, the two adapters still differ in meaningful ways that should not be collapsed into
one generic vendor-neutral policy layer. Examples include:

- Claude-specific model and permission-mode application,
- Claude-specific rate-limit and cooldown classification,
- Codex-specific approval and sandbox policy,
- Codex-specific session configuration via ACP config-setting requests,
- and vendor-specific request semantics and result interpretation.

The architectural question is therefore no longer whether ACP code should be deduplicated at all.
It is where the next shared layer should sit.

## Decision

Introduce a shared operator-owned ACP session runner beneath the vendor adapters and above the ACP
substrate.

The intended shape is:

- ACP substrate:
  - transport, stdio wiring, ACP request/response primitives, canonical payloads
- ACP session runner:
  - shared session execution mechanics for ACP-backed adapters
- vendor adapters:
  - thin vendor-specific policy and normalization shells implementing `AgentAdapter`

This RFC explicitly does **not** choose a single monolithic ACP adapter and does **not** choose an
inheritance-heavy `BaseAcpAdapter` as the primary design.

The session runner should own shared ACP-backed session mechanics such as:

- opening and loading ACP connections and sessions,
- creating new sessions,
- applying a prompt/send cycle,
- draining notifications and requests,
- maintaining shared in-memory session state,
- accumulating transcript/progress state in a vendor-agnostic form,
- detecting terminal completion,
- and driving generic cancel / close behavior.

Vendor adapters should remain responsible for:

- applying vendor-specific session configuration,
- classifying vendor-specific failures,
- mapping vendor-specific permission and approval requests into operator policy,
- projecting runner state into `AgentProgress`,
- projecting runner state into `AgentResult`,
- and preserving any vendor-specific semantics around continuation and cleanup.

## Why this boundary is correct

The current duplication sits in the session-execution skeleton, not primarily in transport and not
primarily in operator-level policy.

The ACP substrate is now already the shared transport layer. The next duplication seam is the
session runner.

That seam is the right place to share code because:

- it matches the actual duplicated logic visible in the repository,
- it preserves the repository bias toward composition over inheritance,
- it keeps vendor-specific behavior explicit rather than hiding it in a hook maze,
- it keeps `AgentAdapter` stable as the operator-facing contract,
- and it allows the shared runtime core to be tested directly without pretending Claude and Codex
  are behaviorally identical.

## What should be shared

The shared ACP session runner should cover:

- runner-level session state model,
- connection/session open/load/new lifecycle,
- generic prompt dispatch,
- generic notification draining loop,
- generic request dispatch loop,
- transcript chunk accumulation,
- shared terminal-state detection,
- shared stderr/diagnostic capture,
- and generic cancel/close choreography.

The shared runner may also define narrow hook points such as:

- `configure_session(...)`
- `handle_request(...)`
- `classify_error(...)`
- `project_progress(...)`
- `build_result(...)`

Those hooks should stay narrow and explicit.

## What should remain vendor-specific

The following should remain in `claude_acp` or `codex_acp`, not in the shared runner:

- vendor-specific model / effort / permission configuration,
- vendor-specific approval or sandbox policy,
- vendor-specific request interpretation when ACP payloads mean different things operationally,
- rate-limit and cooldown classification,
- any vendor-specific assumptions around reuse, continuation, or cleanup,
- and any operator policy that is not truly protocol-generic.

In particular, this RFC does **not** authorize moving operator policy into a generic ACP layer.

## Alternatives Considered

- Keep the current design and accept duplicated adapter session logic.
- Introduce a single generic ACP adapter with vendor flags.
- Introduce an inheritance-heavy `BaseAcpAdapter` with many protected hooks.

Keeping the current design would preserve needless duplication and make future lifecycle changes
harder to apply consistently.

A single generic ACP adapter would over-compress real Claude/Codex differences and obscure
vendor-specific runtime semantics.

An inheritance-heavy base adapter would likely turn into a hook-heavy hierarchy that hides the
important design boundary. That conflicts with the repository preference for small explicit
abstractions and protocol-oriented design.

## Consequences

- Positive:
  - less duplicated adapter lifecycle code,
  - clearer separation between shared ACP session mechanics and vendor policy,
  - easier parity testing across ACP-backed adapters,
  - and lower risk of lifecycle drift between Claude and Codex paths.
- Negative:
  - one more internal abstraction layer,
  - some short-term migration churn inside both adapters,
  - and a new shared contract that must be kept narrow to avoid abstraction bloat.
- Follow-up implication:
  - implementation should proceed as a staged refactor with contract-style tests for the runner and
    parity tests for both adapters.

## Proposed Implementation Direction

### Stage 1: Extract a shared runner state model

Create a shared runner-owned session state model for the common ACP lifecycle fields that both
adapters currently duplicate.

Do not force all vendor-specific fields into one large union model. Keep vendor-specific side state
adapter-owned unless it is clearly generic.

### Stage 2: Extract a shared session runner

Move the common ACP lifecycle skeleton into a shared runner object or service beneath the adapters.

The preferred design is composition-first rather than inheritance-first.

### Stage 3: Thin the vendor adapters

Reduce `claude_acp` and `codex_acp` to thin policy shells that:

- provide vendor-specific hooks,
- call the shared runner,
- and translate shared runner state into `AgentProgress` and `AgentResult`.

### Stage 4: Add parity and regression coverage

Add tests that prove:

- the shared runner preserves lifecycle semantics for both vendors,
- vendor-specific permission and error logic still behaves as before,
- and no operator-visible contract drift occurred in `start`, `send`, `poll`, `collect`, `cancel`,
  or `close`.

## Open Questions

- Should the shared runner expose one normalized request/event model, or should it preserve some
  vendor-specific raw payload alongside normalized fields?
- How much shared session state should become a formal model versus remaining private runner
  implementation detail?
- Should vendor-specific request handling be callback-based or protocol-based?

## Relationship to RFC 0001 and RFC 0002

RFC 0001 defines the ACP SDK migration boundary.

RFC 0002 explains why `operator` should keep control-plane ownership while reusing ACP protocol
infrastructure.

This RFC defines the next layer above that ACP substrate: a shared session runner for ACP-backed
adapters that reduces duplication without collapsing vendor-specific policy into one generic
adapter.

RFC 0004 inventories the broader ACP SDK capability surface that still remains unused and sets the
recommended integration order for permission brokerage, session accumulation, usage, richer session
control, and extension hooks above this runner layer.
