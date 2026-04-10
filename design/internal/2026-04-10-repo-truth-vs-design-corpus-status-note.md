# Repo Truth Vs Design Corpus Status Note — 2026-04-10

Internal note. Not public product documentation.

## Purpose

This note compares current committed repository truth against the committed design authority:

- [VISION.md](/Users/thunderbird/Projects/operator/design/VISION.md)
- [ARCHITECTURE.md](/Users/thunderbird/Projects/operator/design/ARCHITECTURE.md)
- [CLI-UX-VISION.md](/Users/thunderbird/Projects/operator/design/CLI-UX-VISION.md)
- [RFC 0014](/Users/thunderbird/Projects/operator/design/rfc/0014-cli-output-contract-and-example-corpus.md)
- committed [ADR corpus](/Users/thunderbird/Projects/operator/design/adr)

It is a synchronization memo for contributors, not a replacement for the ADRs or RFCs.

## Skim-Safe Summary

- `implemented`: the repository now has a real public/operator-facing CLI surface with fleet entry,
  operation summary and control, session inspection, transcript escalation, project/profile read
  surfaces, and policy read/mutation surfaces
- `verified`: current tests enforce the application package split, the CLI package split, the
  event-sourced run path, and key project/policy CLI workflows
- `partial`: the repository still only partially closes the broader CLI output-contract ambitions
  in [RFC 0014](/Users/thunderbird/Projects/operator/design/rfc/0014-cli-output-contract-and-example-corpus.md)
- `partial`: the application shell is thinner than before, but
  [service.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/service.py)
  still carries a large coordination surface relative to the ideal architecture in
  [ARCHITECTURE.md](/Users/thunderbird/Projects/operator/design/ARCHITECTURE.md)
- `partial`: attached live continuity and some next-wave CLI/TUI family closure are still ahead of
  committed implementation, which is consistent with committed
  [ADR 0143](/Users/thunderbird/Projects/operator/design/adr/0143-attached-live-wakeup-reconciliation-contract.md)
  and the current `Draft` / `Partial` status of
  [RFC 0014](/Users/thunderbird/Projects/operator/design/rfc/0014-cli-output-contract-and-example-corpus.md)

## Evidence Anchors

Primary committed implementation evidence used for this note:

- [app.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/app.py)
- [service.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/service.py)
- [project.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/commands/project.py)
- [policy.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/commands/policy.py)
- [test_application_structure.py](/Users/thunderbird/Projects/operator/tests/test_application_structure.py)
- [test_cli.py](/Users/thunderbird/Projects/operator/tests/test_cli.py)
- [test_cli_rendering_imports.py](/Users/thunderbird/Projects/operator/tests/test_cli_rendering_imports.py)
- [test_operator_service_shell.py](/Users/thunderbird/Projects/operator/tests/test_operator_service_shell.py)
- [docs/reference/cli.md](/Users/thunderbird/Projects/operator/docs/reference/cli.md)

## Comparison Against VISION.md

### Control-plane and operator-loop thesis

- `implemented`: the repository still centers execution around an operator-owned application loop
  rather than a bag of direct adapter calls
- `implemented`: deterministic control-plane concerns remain first-class in the domain/application
  stack: budgets, runtime hints, event sinks, command inboxes, wakeups, runtime reconciliation, and
  cancellation all exist as explicit concepts
- `verified`: event-sourced canonical persistence is exercised in
  [test_operator_service_shell.py](/Users/thunderbird/Projects/operator/tests/test_operator_service_shell.py)

### Transparency by default

- `implemented`: committed CLI surfaces expose operation summary, session inspection, transcript
  escalation, project profile inventory/inspection, and policy inventory/explainability
- `verified`: focused CLI coverage exists in
  [test_cli.py](/Users/thunderbird/Projects/operator/tests/test_cli.py)
- `partial`: transparency is real, but not yet uniformly closed to the textual family examples in
  RFC 0014

## Comparison Against ARCHITECTURE.md

### Application layering and shell thinning

- `implemented`: `application/commands`, `application/queries`, `application/runtime`,
  `application/drive`, and `application/event_sourcing` are all real package families
- `verified`: the package split and some boundary constraints are enforced in
  [test_application_structure.py](/Users/thunderbird/Projects/operator/tests/test_application_structure.py)
- `partial`: [service.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/service.py)
  remains a large composition shell with many collaborators, which matches ARCHITECTURE's own
  statement that shell thinning is incomplete

### Delivery package shape

- `implemented`: the CLI surface is now package-shaped under `commands`, `helpers`, `rendering`,
  `tui`, and `workflows`
- `verified`: import/export integrity is checked in
  [test_cli_rendering_imports.py](/Users/thunderbird/Projects/operator/tests/test_cli_rendering_imports.py)

## Comparison Against CLI-UX-VISION.md

### What is already real

- `implemented`: no-arg `operator` remains fleet-first and TTY-aware in
  [app.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/app.py)
- `implemented`: `project` and `policy` are real domain subgroups rather than hidden internal
  namespaces
- `implemented`: current committed CLI supports human-readable default output and `--json` on the
  main public read surfaces, including the recently landed `project list` and `policy projects`
  inventory paths

### What is still only partial

- `partial`: CLI UX Vision is still ahead of committed implementation in some family-level output
  polish and help/discoverability refinement
- `partial`: the design vision is more complete than the current public docs/help examples for some
  secondary command families

## Comparison Against RFC 0014

- `implemented`: the committed repository agrees with RFC 0014's own skim-safe status that the CLI
  package shape, fleet snapshot, one-operation summary, and session surface are real
- `implemented`: human-readable-by-default is now true for the project/policy inventory/inspection
  surfaces that were lagging earlier
- `partial`: RFC 0014 remains `Draft` with `Implementation Status: Partial`, and that is still the
  honest repository truth
- `partial`: the remaining gap is not command existence so much as full command-family output
  closure and example alignment across the broader CLI surface

## Comparison Against The Committed ADR Corpus

### Clearly landed fronts

- `implemented`: CLI package/subpackage shape from
  [ADR 0123](/Users/thunderbird/Projects/operator/design/adr/0123-cli-package-submodules-and-subpackage-shape.md)
- `implemented`: application package/subpackage shape from
  [ADR 0121](/Users/thunderbird/Projects/operator/design/adr/0121-application-submodule-organization-and-boundary-rules.md)
- `implemented`: public session surface from
  [ADR 0117](/Users/thunderbird/Projects/operator/design/adr/0117-public-session-scope-cli-surface.md)
- `implemented`: retained operation detail/inventory family from
  [ADR 0137](/Users/thunderbird/Projects/operator/design/adr/0137-operation-detail-and-inventory-surfaces.md)

### Still honestly partial

- `partial`: one-operation live follow remains a refinement front consistent with
  [ADR 0134](/Users/thunderbird/Projects/operator/design/adr/0134-one-operation-live-follow-surface.md)
- `partial`: attached live wakeup continuity remains an explicit partial front consistent with
  [ADR 0143](/Users/thunderbird/Projects/operator/design/adr/0143-attached-live-wakeup-reconciliation-contract.md)
- `partial`: top application control-layer closure remains incomplete in the sense already recorded
  by the architecture text and the earlier shell-thinning ADR sequence

## Current Read On `project list` And `policy projects`

Against committed authority, these are no longer the next missing slice.

- `implemented`: `project list` now behaves as a real inventory surface rather than a bare name
  dump
- `implemented`: `policy projects` now behaves as a project-aggregation read surface rather than a
  bare scope dump
- `verified`: both command paths are covered in
  [test_cli.py](/Users/thunderbird/Projects/operator/tests/test_cli.py)

## Best Current Gap

The next gap is no longer project/policy inventory.

The best next committed-corpus gap appears to be one of these partial fronts:

1. broader CLI output-contract closure against RFC 0014 for command families that still have
   thinner-than-specified output/help treatment
2. further application-shell boundary completion above
   [service.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/service.py)
3. attached live continuity closure under
   [ADR 0143](/Users/thunderbird/Projects/operator/design/adr/0143-attached-live-wakeup-reconciliation-contract.md)

Of those, the strongest design-authority-aligned next step is still a narrow, evidence-backed
closure wave for CLI output-contract families or attached live continuity, not another generic
cleanup pass.
