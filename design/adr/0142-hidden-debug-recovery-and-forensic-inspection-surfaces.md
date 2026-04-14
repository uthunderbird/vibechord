# ADR 0142: Hidden debug recovery and forensic inspection surfaces

- Date: 2026-04-10

## Decision Status

Accepted

## Implementation Status

Verified

Implementation grounding on 2026-04-14:

- `implemented`: the hidden `debug` namespace exists as the non-default home for recovery/control,
  runtime introspection, and deeper forensic inspection commands, via `debug_app` in
  `src/agent_operator/cli/app.py` and the registered command family in
  `src/agent_operator/cli/commands/debug.py`
- `implemented`: default top-level help hides the `debug` family, while `operator debug` and
  `operator --help --all` still reveal the hidden namespace and its covered commands, via
  `_emit_help()` in `src/agent_operator/cli/app.py`
- `implemented`: transcript access continues to route through `operator log` rather than moving
  into the `debug` namespace, via `log()` in `src/agent_operator/cli/commands/operation_detail.py`
- `verified`: focused CLI coverage for hidden-help visibility and debug-namespace reachability now
  exists in `tests/test_cli.py`
- `partial`: RFC 0014 remains draft, so broader example-corpus closure beyond this landed slice is
  still incomplete

## Commands Covered

- `operator debug daemon`
- `operator debug tick`
- `operator debug recover`
- `operator debug resume`
- `operator debug wakeups`
- `operator debug sessions`
- `operator debug command`
- `operator debug context`
- `operator debug trace`
- `operator debug inspect`

## Not Covered Here

- public supervisory CLI commands
- transcript-first `log`
- policy mutation/read-side subgroups

## Context

Older ADRs already established the hidden `debug` namespace and moved forensic/internal commands
under it.

RFC 0014 now makes the hidden debug family more explicit and also reveals that this namespace
contains three different subfamilies:

- recovery/control plumbing
- runtime introspection
- deep forensic inspection

The design corpus now needs one current ADR that owns this whole hidden family while keeping those
internal distinctions visible.

## Decision

The CLI should treat the hidden `debug` namespace as one coherent but intentionally non-default
family for recovery and forensic inspection.

### Recovery/control commands

These include:

- `daemon`
- `tick`
- `recover`
- `resume`
- `command`

They exist to manage or recover operator runtime behavior, not to serve as normal public workflow.

### Runtime introspection commands

These include:

- `wakeups`
- `sessions`
- `context`

They expose control-plane or runtime state for advanced inspection.

### Forensic inspection commands

These include:

- `trace`
- `inspect`

They remain the deeper forensic layer beyond public supervisory surfaces and beyond transcript
access through `log`.

## Visibility Rule

These commands remain:

- supported
- reachable
- and completable

but hidden from default help and normal public workflow teaching.

## Consequences

Positive:

- the hidden debug family becomes easier to explain without making it public by default
- RFC 0014 debug examples gain one explicit ADR owner

Tradeoffs:

- the CLI must keep the public-vs-forensic boundary explicit
- the namespace contains multiple subfamilies and therefore needs disciplined discoverability

## Verification

Current evidence for the landed slice:

- `verified`: `pytest -q tests/test_cli.py -k 'test_default_help_hides_debug_commands or
  test_debug_help_lists_hidden_runtime_commands or
  test_help_all_reveals_hidden_debug_commands or
  test_debug_namespace_surfaces_recovery_runtime_and_forensic_commands'` passed on 2026-04-14
- `verified`: hidden debug commands remain outside default public help
- `verified`: transcript access continues to route through `log` rather than through `debug`
- `verified`: recovery/runtime/forensic command families remain distinguishable and reachable
  within the `debug` namespace

The repository should preserve these conditions:

- hidden debug commands remain outside default public help
- transcript access continues to route through `log` rather than through `debug`
- forensic inspection and recovery plumbing remain distinguishable inside the `debug` namespace

## Related

- [ADR 0093](./0093-cli-command-taxonomy-visibility-tiers-and-default-operator-entry-behavior.md)
- [ADR 0097](./0097-forensic-log-unification-and-debug-surface-relocation.md)
- [ADR 0024](./0024-effective-control-context-cli-surface.md)
- [RFC 0014](../rfc/0014-cli-output-contract-and-example-corpus.md)
