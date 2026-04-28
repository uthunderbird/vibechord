# User-Facing Docs Red Team — 2026-04-27

Target:
- `README.md`
- `docs/`

Canon used:
- `design/VISION.md`
- `design/ARCHITECTURE.md`
- `design/adr/0210-cli-command-canonicalization-and-ux-final-form.md`
- `design/adr/0214-canonical-live-session-and-event-streaming-contract.md`
- `design/adr/0215-public-python-api-v2-canonicalization-and-v1-shell-retirement.md`
- `design/adr/0216-public-release-contract-and-distribution-acceptance-gate.md`

## Findings

1. Verified issue: `docs/reference/delivery-surface-parity.md` still describes `watch` and
   `OperatorClient.stream_events()` as legacy-event-file readers, which contradicts the accepted
   live-streaming contract.
   - Evidence:
     - `docs/reference/delivery-surface-parity.md:20-22`
     - `design/adr/0214-canonical-live-session-and-event-streaming-contract.md:21-27`
   - Why it matters:
     - This doc tells users and integrators the opposite of the current v2 live-streaming truth.
     - It understates canonical event-stream adoption exactly where parity is being claimed.

2. Verified issue: public Python-surface docs still overstate stable public SDK scope beyond
   `agent_operator.OperatorClient`.
   - Evidence:
     - `docs/integrations.md:7-18`
     - `docs/reference/python/overview.md:5-15`
     - `docs/reference/public-release.md:73-87`
     - `design/adr/0215-public-python-api-v2-canonicalization-and-v1-shell-retirement.md:55-73`
   - Why it matters:
     - `docs/integrations.md` advertises “Python package imports for selected stable modules” and
       “ACP-related client/runtime utilities” as current public entrypoints.
     - `docs/reference/python/overview.md` publishes `Runtime utilities`, `ACP surfaces`, and
       `Adapter bindings` under the public Python API reference.
     - The accepted v2 public Python contract is narrower: stable package-root entrypoint
       `agent_operator.OperatorClient`.

3. Verified issue: `docs/how-to/resume-and-inspect.md` teaches a debug-only resume path as normal
   user workflow.
   - Evidence:
     - `docs/how-to/resume-and-inspect.md:10-16`
     - `docs/reference/cli-command-contracts.md:103-117`
     - `docs/reference/public-release.md:63-71`
   - Why it matters:
     - The doc is user-facing how-to content, but it recommends `operator debug resume last`.
     - The CLI contract marks `debug resume` as `debug-only`, not part of the default stable public
       contract.
     - This weakens the stable-vs-debug boundary that `ADR 0216` now requires public docs to keep
       explicit.

## Bounded Concerns

1. `README.md` is still mixing quickstart/public entrypoint duties with a long release-note-style
   TUI capability dump.
   - This is not a canon mismatch by itself, but it increases the risk of future drift because the
     public landing page carries too much low-level surface detail.

## Verdict

The user-facing docs are close enough that the remaining drift looks repairable, not structural.
But they are not yet cleanly aligned with v2 canon for merge-quality public truth. The highest
value repair wave is:

1. rewrite `docs/reference/delivery-surface-parity.md` to match `ADR 0214`
2. narrow Python public-entrypoint claims in `docs/integrations.md` and `docs/reference/python/`
3. stop presenting `operator debug resume` as a normal how-to path unless that debug-only status is
   explicit
