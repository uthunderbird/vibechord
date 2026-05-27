# Minimum Moving Parts Swarm

Status: `complete`

## Phase 1: Problem Definition

Core problem: define the minimum set of independently moving architectural
parts that covers all planned functional requirements while preserving
extension paths.

Scope: design corpus only. Runtime code and framework choices are out of
scope.

Success criteria:

- one minimal core set is selected;
- extension rules are explicit;
- forbidden authority splits are explicit;
- functional requirements map to the selected parts;
- architecture and ADRs are updated.

## Phase 2: Expert Assembly

- Barbara Liskov: critic, protocol boundaries and substitutability.
- David Parnas: critic, information hiding and module boundaries.
- Leslie Lamport: critic, replay/order/failure semantics.
- Martin Fowler: balanced, service boundaries and delivery architecture.
- Kent Beck: evangelist, smallest useful implementation slice.

Evidence boundary: local design corpus.

## Phase 3: Round-Robin

Liskov: protocols are useful only where implementations can substitute without
changing callers. Too many protocols before implementations exist becomes
ceremony. Keep protocol boundaries around external variation: event storage,
adapters, delivery, and time.

Parnas: the right module boundaries hide decisions likely to change. Persistence
backend, provider/runtime integration, and delivery transport qualify. Fleet
versus operation queries do not need separate authorities yet; they are both
projection decisions over the same event truth.

Lamport: command application, event append/replay, and operation driving cannot
collapse into delivery surfaces. Idempotency, sequence conflicts, and replay
need one authority path.

Fowler: application services should describe authority, not nouns. The current
`OperationQueries`, `FleetQueries`, and `LiveFeedService` split is premature as
independent services. A single `ProjectionService` is enough until proven
otherwise.

Beck: the first implementation should be easy to fake end to end. Six moving
parts are enough for a walking skeleton: domain, command application, driver,
store, projections, gateway.

## Adjudication

Competing routes:

- Route A: keep the existing service list and rely on service-minimalism gates.
- Route B: collapse read-side services and adapter invocation into a smaller
  explicit moving-parts contract.

Decision: Route B.

Reason: Route A preserves too many names that look like separate authorities.
Route B still covers all planned behavior while making extension rules explicit.

## Result

The selected minimum core set is:

1. Domain Model;
2. CommandApplication;
3. OperationDriver;
4. EventStore;
5. ProjectionService;
6. AdapterGateway.

`MOVING-PARTS.md` and ADR 0007 record the decision.
