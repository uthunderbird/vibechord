# CLI Command Contracts

This page is the command-by-command contract matrix for ADR 0210.

- `Stability` comes from [CLI Command Inventory](cli-command-inventory.md).
- `JSON contract` points to [CLI JSON Schemas](cli-json-schemas.md) when the command exposes
  `--json`.
- `Semantic exit codes` lists only codes the repository intentionally publishes as part of the
  command contract today. If a row says `success only`, the command exits `0` on success and does
  not currently publish additional semantic codes beyond normal Typer/runtime failures.
- `Error notes` call out shared behavior that ADR 0210 treats as part of the final-form shell
  contract.

## Stable Lifecycle

| Path | Stability | JSON contract | Semantic exit codes | Error notes |
| --- | --- | --- | --- | --- |
| `run` | `stable` | `operator run --json` | `0/1/2/3/4` when `--wait`; otherwise success only | `--timeout` is resumable-only; operation-ref confusion is blocked by ADR 0204 entrypoint guards. |
| `init` | `stable` | none | success only | Existing profile overwrite is explicit and test-covered. |
| `clear` | `stable` | none | success only | Destructive apply path requires confirmation or `--yes/--force`. |
| `fleet` | `stable` | `operator fleet --once --json` | success only | Default help keeps fleet as the no-arg entry surface under ADR 0093. |

## Stable Control

| Path | Stability | JSON contract | Semantic exit codes | Error notes |
| --- | --- | --- | --- | --- |
| `answer` | `stable` | `operator answer --json` | success only | Uses shared resolution; attention resolution is deterministic and event-sourced. |
| `cancel` | `stable` | `operator cancel --json` | `0/3/4` | Operation-level cancel publishes semantic status; scoped run/session cancel can remain `0` while queued. |
| `converse` | `stable` | none | success only | Read-only turns answer directly; write proposals require explicit confirmation. |
| `edit` | `stable` | none | success only | Namespace for grouped operation mutation surfaces. |
| `edit criteria` | `stable` | none | success only | Uses the event-sourced command/control path. |
| `edit execution-profile` | `stable` | none | success only | Uses the event-sourced command/control path. |
| `edit harness` | `stable` | none | success only | Uses the event-sourced command/control path. |
| `edit involvement` | `stable` | none | success only | Uses the event-sourced command/control path. |
| `edit objective` | `stable` | none | success only | Uses the event-sourced command/control path. |
| `interrupt` | `stable` | none | success only | Session-targeted interruption remains the explicit non-ADR-0205 command-path exception. |
| `involvement` | `stable` | none | success only | Shared command-application path handles accepted/rejected outcomes. |
| `message` | `stable` | none | success only | Uses the event-sourced command/control path. |
| `pause` | `stable` | none | success only | Uses the event-sourced command/control path. |
| `unpause` | `stable` | none | success only | Uses the event-sourced command/control path. |

## Stable Read And Supervision

| Path | Stability | JSON contract | Semantic exit codes | Error notes |
| --- | --- | --- | --- | --- |
| `agenda` | `stable` | `operator agenda --json` | success only | Uses the shared read/query path rather than delivery-local state assembly. |
| `artifacts` | `stable` | `operator artifacts --json` | success only | Uses shared operation resolution. |
| `ask` | `stable` | `operator ask --json` | `0/4` | Missing-operation and runtime query failures use the stable internal-error code. |
| `attention` | `stable` | `operator attention --json` | success only | Uses shared operation resolution. |
| `dashboard` | `stable` | `operator dashboard --json` | success only | Dashboard text and JSON render the same read/query payload family. |
| `fleet agenda` | `stable` | `operator fleet agenda --json` | success only | Grouped alias for cross-operation agenda. |
| `fleet history` | `stable` | `operator fleet history --json` | success only | Grouped alias for committed history ledger. |
| `fleet list` | `stable` | `operator fleet list --json` | success only | Grouped alias for persisted operation inventory. |
| `history` | `stable` | `operator history --json` | success only | Reads committed ledger truth rather than live runtime summaries. |
| `list` | `stable` | `operator list --json` | success only | Inventory-shaped output remains distinct from fleet/agenda supervision payloads. |
| `log` | `stable` | `operator log --json` | success only | Transcript/log payload stays agent-flavor aware. |
| `memory` | `stable` | `operator memory --json` | success only | Uses shared operation resolution. |
| `report` | `stable` | `operator report --json` | success only | Report JSON keeps synthesized report plus durable-truth context explicit. |
| `session` | `stable` | `operator session --json` | success only | Task-addressed session lookup is explicit; missing linkage is a deterministic non-zero failure. |
| `show` | `stable` | none | success only | Namespace for grouped operation-detail surfaces. |
| `show artifacts` | `stable` | `operator show artifacts --json` | success only | Grouped alias for artifact inspection. |
| `show attention` | `stable` | `operator show attention --json` | success only | Grouped alias for attention inspection. |
| `show dashboard` | `stable` | `operator show dashboard --json` | success only | Grouped alias for one-operation dashboard. |
| `show log` | `stable` | `operator show log --json` | success only | Grouped alias for transcript/log inspection. |
| `show memory` | `stable` | `operator show memory --json` | success only | Grouped alias for memory inspection. |
| `show report` | `stable` | `operator show report --json` | success only | Grouped alias for operation report. |
| `show session` | `stable` | `operator show session --json` | success only | Grouped alias for task-addressed session lookup. |
| `show tasks` | `stable` | `operator show tasks --json` | success only | Grouped alias for task-board inspection. |
| `status` | `stable` | `operator status --json` | success only | Ambiguous prefixes use the shared resolver error contract. |
| `tasks` | `stable` | `operator tasks --json` | success only | Uses shared operation resolution. |
| `watch` | `stable` | `operator watch --once --json` | `0/4` | Canonical v2 event streams are preferred; watch timeout/runtime failure uses the internal-error code. |

## Stable Project, Policy, Admin, And Integration

| Path | Stability | JSON contract | Semantic exit codes | Error notes |
| --- | --- | --- | --- | --- |
| `agent` | `stable` | none | success only | Namespace only. |
| `agent list` | `stable` | `operator agent list --json` | success only | Lists configured agent descriptors from runtime bindings. |
| `agent show` | `stable` | `operator agent show --json` | success only | Unknown agent keys fail deterministically. |
| `config` | `stable` | none | success only | Namespace only. |
| `config edit` | `stable` | none | success only | Editor-open failure is surfaced explicitly. |
| `config set-root` | `stable` | `operator config set-root --json` | success only | Path validation is handled by Typer plus config-layer guards. |
| `config show` | `stable` | `operator config show --json` | success only | Redacted payload is the machine-readable authority. |
| `mcp` | `stable` | none | success only | Stdio MCP entrypoint; machine-facing contract is MCP, not CLI JSON. |
| `policy` | `stable` | none | success only | Namespace only. |
| `policy explain` | `stable` | `operator policy explain --json` | success only | Uses shared operation resolution and deterministic policy evaluation. |
| `policy inspect` | `stable` | `operator policy inspect --json` | success only | Missing policy ids fail deterministically. |
| `policy list` | `stable` | `operator policy list --json` | success only | Inventory payload remains distinct from inspect/explain payloads. |
| `policy projects` | `stable` | `operator policy projects --json` | success only | Project inventory payload remains distinct from list/inspect. |
| `policy record` | `stable` | none | success only | Explicit durable mutation surface. |
| `policy revoke` | `stable` | none | success only | Destructive apply path requires confirmation or `--yes`. |
| `project` | `stable` | none | success only | Namespace only. |
| `project create` | `stable` | `operator project create --json` | success only | Explicit profile mutation path. |
| `project dashboard` | `stable` | `operator project dashboard --json` | success only | Shares the project-scoped supervision payload family. |
| `project inspect` | `stable` | `operator project inspect --json` | success only | Missing local profile selection fails deterministically. |
| `project list` | `stable` | `operator project list --json` | success only | Inventory payload remains distinct from inspect/resolve. |
| `project resolve` | `stable` | `operator project resolve --json` | success only | Effective defaults remain distinct from declared profile content. |

## Transitional Aliases

| Path | Stability | JSON contract | Semantic exit codes | Error notes |
| --- | --- | --- | --- | --- |
| `daemon` | `transitional` | `operator debug daemon --json` | success only | Hidden alias for `debug daemon`. |
| `command` | `transitional` | none | success only | Hidden alias for `debug command`. |
| `context` | `transitional` | `operator debug context --json` | success only | Hidden alias for `debug context`. |
| `inspect` | `transitional` | `operator debug inspect --json` | success only | Hidden alias for `debug inspect`. |
| `patch-criteria` | `transitional` | none | success only | Compatibility alias for `edit criteria`. |
| `patch-harness` | `transitional` | none | success only | Compatibility alias for `edit harness`. |
| `patch-objective` | `transitional` | none | success only | Compatibility alias for `edit objective`. |
| `recover` | `transitional` | `operator debug recover --json` | success only | Hidden alias for `debug recover`. |
| `resume` | `transitional` | `operator debug resume --json` | success only | Hidden alias for `debug resume`. |
| `set-execution-profile` | `transitional` | none | success only | Compatibility alias for `edit execution-profile`. |
| `sessions` | `transitional` | `operator debug sessions --json` | success only | Hidden alias for `debug sessions`. |
| `stop-turn` | `transitional` | none | success only | Hidden alias retained during `interrupt` cutover. |
| `tick` | `transitional` | none | success only | Hidden alias for `debug tick`. |
| `trace` | `transitional` | `operator debug trace --json` | success only | Hidden alias for `debug trace`. |
| `wakeups` | `transitional` | `operator debug wakeups --json` | success only | Hidden alias for `debug wakeups`. |

## Debug And Verification Surfaces

| Path | Stability | JSON contract | Semantic exit codes | Error notes |
| --- | --- | --- | --- | --- |
| `debug` | `debug-only` | none | success only | Namespace only. |
| `debug command` | `debug-only` | none | success only | Low-level command enqueue surface. |
| `debug context` | `debug-only` | `operator debug context --json` | success only | Effective control-plane context payload. |
| `debug daemon` | `debug-only` | `operator debug daemon --json` | success only | Wakeup sweep / background resume payload. |
| `debug event` | `debug-only` | none | success only | Namespace only. |
| `debug event append` | `debug-only` | `operator debug event append --json` | success only | Dry-run/apply repair payload is machine-readable. |
| `debug inspect` | `debug-only` | `operator debug inspect --json` | success only | Forensic payload may be brief or `--full`. |
| `debug recover` | `debug-only` | `operator debug recover --json` | success only | Repair/recovery payload. |
| `debug resume` | `debug-only` | `operator debug resume --json` | success only | Manual lifecycle continuation payload. |
| `debug sessions` | `debug-only` | `operator debug sessions --json` | success only | Session/background inspection payload. |
| `debug tick` | `debug-only` | none | success only | Single scheduler-cycle helper. |
| `debug trace` | `debug-only` | `operator debug trace --json` | success only | Forensic trace payload. |
| `debug wakeups` | `debug-only` | `operator debug wakeups --json` | success only | Wakeup queue inspection payload. |
| `smoke` | `debug-only` | none | success only | Namespace only. |
| `smoke alignment-post-research-plan` | `debug-only` | none | success only | Live verification helper. |
| `smoke alignment-post-research-plan-claude-acp` | `debug-only` | none | success only | Live verification helper. |
| `smoke codex-continuation` | `debug-only` | none | success only | Live verification helper. |
| `smoke mixed-agent-selection` | `debug-only` | none | success only | Live verification helper. |
| `smoke mixed-agent-selection-claude-acp` | `debug-only` | none | success only | Live verification helper. |
| `smoke mixed-code-agent-selection` | `debug-only` | none | success only | Live verification helper. |
| `smoke mixed-code-agent-selection-claude-acp` | `debug-only` | none | success only | Live verification helper. |
