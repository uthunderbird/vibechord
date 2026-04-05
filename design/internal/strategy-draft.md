# operator — Strategic Package (Draft)

Internal document. Not for public distribution in this form.

---

## 1. Mission Statement

**One-liner** (README hero, HN posts, talks):

> *Operator drives your goals across multiple AI agents — so you define the objective, not the steps.*

**Full mission** (README intro and project description):

> *Operator is a minimal Python control plane for multi-agent supervision. You set the goal; operator drives heterogeneous agents toward it through an iterative loop — with deterministic guardrails, full traceability, and human control over every blocking decision.*

**Discrimination function** — what the mission rules out:

- Not an agent execution environment (code execution lives in the agents)
- Not a workflow engine (steps are not specified in advance)
- Not a black-box autonomous system (every decision is traceable and guardrailed)
- Not a single-agent tool (the problem is coordination across heterogeneous agents)

---

## 2. Values

Operational values — intended to guide PR review, roadmap decisions, and scope questions after open-sourcing. Not aspirational statements.

**V1 — Small abstractions, earned.**
Every new abstraction must be justified by a concrete capability it enables or a coupling it removes. "It seems cleaner" is not sufficient justification.

**V2 — Deterministic guardrails are not negotiable.**
Stop conditions, iteration limits, budget caps, and concurrency rules are enforced by the runtime. The brain decides how; the runtime decides whether to continue. The brain cannot override the guardrails.

**V3 — The operator is responsible, not the agent.**
When an agent fails or produces ambiguous output, the operator decides the next move. The control plane is where accountability lives — not distributed across agents.

**V4 — Visibility without micromanagement.**
The human stays in the loop. Blocking decisions surface to the operator; non-blocking events are recorded but don't interrupt. The design assumes the human is busy, not absent.

**V5 — Claim discipline throughout.**
Implemented, verified, partial, planned — these are not interchangeable. The codebase, the docs, and the contributors all hold this distinction. "Done" requires evidence.

**V6 — Vendor isolation at the boundary.**
All agent-specific behavior lives in adapters. The core loop has no knowledge of specific agents. This is how the system stays minimal as the agent landscape changes.

---

## 3. License

**Apache 2.0**

Rationale: The project targets platform engineers and developers at companies. Apache 2.0 provides the patent grant that enterprise legal teams require. MIT is Apache without the patent clause — no reason to choose MIT over Apache for this profile. AGPL is only the right choice when protecting a hosted SaaS product that competes with the tool; that's not the case here. Apache 2.0 maximizes adoption without giving away meaningful protection.

---

## 4. Category — Where to Be Best

**Category: Multi-agent supervision**

Operator should be best at: *giving a human operator reliable, traceable control over long-running multi-agent work — with enough visibility to know what's happening and enough guardrails to stop it.*

Distinct from:

| Category | Examples | Distinction |
|----------|----------|-------------|
| Orchestration / flow graphs | LangGraph, Prefect, Temporal | Those require specifying the steps. Operator takes a goal and decides the steps via the operator loop. |
| Agent execution | Claude Code, Codex | Those are the agents (the hands). Operator supervises them (the decision-maker). |
| Multi-agent frameworks | CrewAI, AutoGen | Those wire agents together statically. Operator drives heterogeneous agents dynamically through iterative evaluation. |
| Observability platforms | LangSmith, Braintrust, Weave | Those record what happened. Operator decides what happens next — and records it. |
| Hosted agent platforms | Devin, SWE-agent-as-SaaS | Full-stack products. Operator is a library and CLI — you run it, you own it. |

The word "supervision" should appear consistently in the README, talks, HN posts, and comparison tables — repeated until it becomes the category anchor.

---

## 5. Competitors and Positioning

**Positioning claim:**
*Operator is the only open-source tool that combines iterative LLM-driven goal decomposition with deterministic stop enforcement and a human attention system — in a minimal Python library.*

> Note: specific competitor feature set claims require external verification before publishing. The table above is category-level positioning; individual product capabilities may have changed.

---

## 6. Name

**Brand / repo name: `operator`**
**PyPI package name: `agent-operator`** (already established in pyproject.toml)

Rationale: Category tools win with plain nouns. The project's internal vocabulary (`operator`, `agent`, `operation`, `operator loop`) is already consistent. The Kubernetes "Operator" overlap is manageable — the term is migrating toward AI-context semantics (the Claude API uses "operator" as an identity role). The AI meaning will dominate within 12-18 months.

**Rejected alternatives:**

- `vibecoder` / `vibecored` / `vibechord` — all taken on PyPI; more critically, "vibe" framing contradicts the project's ethos of determinism and precision. This project is the opposite of generate-and-pray.
- `op`-prefixed names — virtually all taken on PyPI
- "Control plane"-derived names — technically correct but not standalone

**Name consistency rule:** The repo is `operator`. The concept is the operator loop. The CLI command is `operator`. The pip install is `pip install agent-operator`. This split between brand and package name is standard practice (e.g., `python-dotenv` → `from dotenv import`).

---

## 7. Launch Strategy

**Primary channel: Hacker News (Show HN)**

Platform engineers read HN. The Show HN format is the highest-value launch surface for a CLI dev tool. Agent frameworks are already HN-native content.

**Pre-launch deliverable: The "why I built this" essay**

Write this before anything else. Not the README — a 1000-1500 word account of the specific problem that existing tools fail to solve, told through a concrete example (e.g., "I tried to supervise a multi-step refactor across Claude and Codex, and here's what broke with existing tools"). This essay becomes the HN link, the reference post for all future discussions, and the content that gets shared.

The target distribution is HN and a personal or project blog. Platform engineers don't read LinkedIn. Reddit (r/LocalLLaMA, r/devops) and AI engineering Slack communities are secondary amplification surfaces.

**Launch sequence:**

1. Essay published (personal blog or dev.to)
2. `agent-operator` published on PyPI with working quickstart
3. Show HN post linking to essay + GitHub
4. Follow-up: r/LocalLLaMA, r/devops, AI engineering Slack communities

**Growth flywheel:** Operator's differentiation (traceability, human-in-the-loop, heterogeneous agent support) is demonstrable, not just described. The launch should include a short terminal recording showing: fleet view → blocking attention surfaced → user answers it → operation completes. Visual TUI demos spread on HN and Twitter/X.

**Quickstart requirement:** The README quickstart must show the differentiating behavior — not `operator run --goal "write a function"` (that's boring), but a scenario with two agents involved, one blocking attention surfaced, and the user answering it. The differentiation must be visible within the first 5 minutes of use.

---

## 8. What's Still Missing

Items not yet produced; required before public launch:

**a) GOVERNANCE.md**
One page stating: who decides what gets merged during the bootstrap phase (BDFL model is fine for early stage), what the scope of the project is, and how scope is defended against drift. Without this, OSS drift begins on day one.

**b) Anti-portfolio / committed non-goals**
A public list of things operator will never do. Examples:
- We will never implement tool use inside operator (that lives in the agents)
- We will never add a visual drag-and-drop workflow builder
- We will never host your agents
- We will never become a general workflow engine

Belongs in the README or a SCOPE.md. Creates trust with the right contributors; repels scope creep.

**c) CONTRIBUTING.md**
How to submit a new agent adapter. The adapter pattern (vendor isolation at the boundary) is the primary extension surface. Clear adapter guidelines prevent the project from becoming a dumping ground for every agent integration.

**d) ROADMAP.md**
Distinguishes `implemented`, `planned`, and `will-not-do`. Aligns with the project's claim discipline value. Builds credibility with the platform engineering audience who have been burned by inflated claims.

**e) Quickstart that demonstrates differentiation**
See §7. The README quickstart is a launch artifact, not a documentation afterthought.

---

## Open Questions

- Specific competitor feature set claims require external verification before publishing positioning materials
- Timing: how many other projects are currently building toward "multi-agent supervision" as a category framing?
- PyPI package name `agent-operator` ownership status should be verified before public launch announcement
