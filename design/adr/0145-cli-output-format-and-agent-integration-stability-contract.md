# ADR 0145: CLI output format and agent-integration stability contract

- Date: 2026-04-12

## Decision Status

Accepted

## Implementation Status

Verified

Implementation grounding on 2026-04-26:

- `implemented`: semantic exit codes remain centralized in
  `src/agent_operator/cli/helpers/exit_codes.py`, with `completed=0`, `failed=1`,
  `needs_human=2`, `cancelled=3`, and internal/wait failure paths mapped to `4`.
- `implemented`: `operator run` still exposes the ADR-required `--wait`, resumable-only
  `--timeout`, `--brief`, and `--json` flags through `src/agent_operator/cli/commands/run.py`,
  with runtime enforcement in `src/agent_operator/cli/workflows/control.py`.
- `implemented`: operation-control commands still expose the required machine-readable surfaces for
  `status`, `attention`, `answer`, and `cancel` in
  `src/agent_operator/cli/commands/operation_control.py`, and `cancel_async()` still emits the
  stable JSON payload plus semantic exit codes from
  `src/agent_operator/cli/workflows/control_runtime.py`.
- `implemented`: detail/fleet surfaces still expose the ADR-required one-shot machine-readable
  coverage for `fleet --once`, `list --json`, `tasks --json`, and `watch --once --json` in
  `src/agent_operator/cli/commands/fleet.py` and
  `src/agent_operator/cli/commands/operation_detail.py`.
- `implemented`: the committed schema reference still names the covered command set and their
  stable JSON payload shapes in `docs/reference/cli-json-schemas.md`.
- `verified`: CLI regressions currently cover the status/cancel/watch JSON surfaces, scoped cancel
  exit-code behavior, resumable `run --wait --brief`, resumable `run --wait --json`, and the
  attached-mode timeout guard in `tests/test_cli.py`.
- `verified`: full repository verification passed in this wave with
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest` (`1038 passed, 11 skipped`).

## Context

`AGENT-INTEGRATION-VISION.md` identifies the CLI as the baseline integration surface for agents
that invoke `operator` as a subprocess. That requires stable machine-readable output, stable
single-line polling output where needed, and semantic exit codes for command paths that intentionally
wait for an operation outcome.

Repository truth before this closure wave was inconsistent:

- `operator status` already exposed `--json` and `--brief`.
- `operator run` exposed JSON event streaming but did not expose `--wait`, `--timeout`, or
  `--brief`.
- `operator cancel` and `operator answer` did not expose `--json`.
- `operator watch` did not expose `--once`.
- No committed schema reference documented the stable `--json` contract for the required
  agent-facing command set.

This ADR also needed to be grounded in the actual runtime architecture. The repository's canonical
product story is still the attached long-lived run. `operator run` is not redefined here into a
background-only launcher. Instead, this ADR stabilizes the agent-facing CLI contract around the
existing runtime model.

## Decision

The CLI publishes a stable agent-integration contract for output formats and semantic exit codes.

### Semantic exit codes

Commands that intentionally wait until an operation reaches a terminal or attention-gated outcome
exit with:

| Code | Meaning |
|------|---------|
| `0` | Operation completed successfully |
| `1` | Operation failed |
| `2` | Operation requires human input (`needs_human`) |
| `3` | Operation was cancelled |
| `4` | Internal operator-side failure, including wait timeout |

Implemented command paths covered by this contract:

- `operator run --wait`
- `operator cancel`

### `operator run --wait`

`operator run` now supports:

- `--wait`: block until the operation reaches `completed`, `failed`, `needs_human`, or `cancelled`
- `--timeout SECONDS`: maximum wait time for resumable-mode waiting; exits with code `4` on timeout
- `--brief`: emit a single-line completion summary when `--wait` is used

Grounded runtime behavior:

- Attached mode remains the canonical long-lived foreground mode.
- `--wait` is therefore mainly useful for resumable launches and for scripts that want semantic
  exit-code routing on an attached run.
- `--timeout` is currently grounded only for `--mode resumable`; attached-mode timeout control is
  not part of this ADR's implemented contract.

`operator run --wait --brief` emits:

```text
STATUS=completed OPERATION=op-abc123 ITERATIONS=4
```

### Output coverage

The following commands are the required agent-facing machine-readable surfaces:

| Command | `--json` | `--brief` |
|---------|---------|---------|
| `operator run` | required | required with `--wait` |
| `operator status` | required | required |
| `operator fleet --once` | required | — |
| `operator list` | required | — |
| `operator tasks` | required | — |
| `operator attention` | required | — |
| `operator answer` | required | — |
| `operator cancel` | required | — |
| `operator watch --once` | required | — |

### `--json` schema stability contract

For the required coverage set:

- field names are stable once published
- adding new optional fields is non-breaking
- removing a field, renaming a field, or changing a field type is breaking
- breaking schema changes require a deprecation cycle

The schema reference lives in `docs/reference/cli-json-schemas.md`.

## Consequences

- Agents can route on stable exit codes instead of scraping prose output.
- `operator run --wait` supports synchronous agent workflows without changing the attached-run
  architecture.
- `operator cancel`, `operator answer`, and the required watch/fleet one-shot surfaces are now
  explicitly machine-readable.
- The committed schema reference, not ad hoc examples, is the stability anchor for the covered
  command set.

## Grounding Evidence

This ADR is grounded in the following implementation and verification surfaces:

- `src/agent_operator/cli/commands/run.py`
- `src/agent_operator/cli/commands/operation_control.py`
- `src/agent_operator/cli/commands/operation_detail.py`
- `src/agent_operator/cli/workflows/control.py`
- `src/agent_operator/cli/helpers/exit_codes.py`
- `src/agent_operator/application/queries/operation_status_queries.py`
- `docs/reference/cli-json-schemas.md`
- `tests/test_cli.py`

## Related

- [AGENT-INTEGRATION-VISION.md](../interfaces/agent-integration.md)
- [CLI-UX-VISION.md](../interfaces/cli.md)
- [ADR 0093](./0093-cli-command-taxonomy-visibility-tiers-and-default-operator-entry-behavior.md)
- [ADR 0131](./0131-cross-operation-supervisory-snapshot-surface.md)
