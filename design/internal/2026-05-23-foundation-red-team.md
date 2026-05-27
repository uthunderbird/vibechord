# Foundation Red-Team Pass

Date: 2026-05-23

Target artifacts:

- `README.md`
- `AGENTS.md`
- `policies/`
- `design/VISION.md`
- `design/SDLC.md`
- `design/ARCHITECTURE-DRAFT.md`
- `design/BACKLOG.md`

## Result

The initial corpus is directionally sound: it preserves the operation loop,
deterministic guardrails, protocol-oriented integration, event-backed
transparency, shared delivery authority, and documentation status discipline.

The pass found no reason to discard the foundation. It did find several
mechanism gaps that must remain visible before implementation.

## Findings

### P0: Event-backed transparency needs a concrete contract

Result type: verified issue in the draft artifact.

`ARCHITECTURE-DRAFT.md` stated that every observable state transition should
emit an event, but did not name the unresolved event id, sequence, replay,
idempotency, or gap-handling contract.

Fix applied: added an explicit pre-implementation event-contract list and
backlog item.

### P0: ADR lifecycle needs a template

Result type: verified issue in the process corpus.

Policies require ADRs with separate decision and implementation status, but no
template existed.

Fix applied: added `design/adr/0000-template.md`.

### P1: Service families could recreate inherited ceremony

Result type: bounded concern.

The draft names application-service candidates. Without a gate, this could copy
`operator`'s later service proliferation too early.

Fix applied: added a service-minimalism gate.

### P1: Live chat needed clearer separation from commands and attentions

Result type: bounded concern.

The draft named live chat as first-class but did not distinguish free-form
operator messages from typed commands and attention answers.

Fix applied: clarified live-chat semantics and added a backlog item.

## Remaining Open Work

- Exact event schema.
- Fleet read-model schema.
- Live-chat retention and expiry rules.
- Stack choice.
- Whether `promptstrings` or `agent-dashboard` should be dependencies or
  optional integrations.
