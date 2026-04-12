# ADR 0149: NL single-shot query surface (`operator ask`)

- Date: 2026-04-12

## Decision Status

Accepted

## Implementation Status

Implemented

## Context

`design/NL-UX-VISION.md` defines two natural-language CLI entry points:

- `operator converse [OP]` for multi-turn dialogue
- `operator ask OP "QUESTION"` for one read-only query

The repository already had the operator brain, persisted `OperationState`, and CLI command wiring,
but it did not yet have a committed single-shot NL query contract closed against repository truth.
The full conversation surface still requires conversation state, write-preview confirmation, and
TUI work that do not exist yet.

This ADR closes only the minimal read-only surface:

- a brain contract for answering a user question from operation context
- provider implementations for that read-only question path
- a CLI command that loads one persisted operation and prints a natural-language answer
- a machine-readable JSON form for scripts

`converse` and the TUI `n` panel remain deferred.

## Decision

`operator` exposes a read-only single-shot NL query surface via `operator ask`.

### Read boundary

`operator ask` is limited to questions about one operation's current or historical state. It does
not enqueue commands, mutate tasks, answer attention, or change runtime state.

The read boundary is enforced by contract:

- `OperatorBrain.answer_question(...)` takes `OperationState` plus the user's question and returns
  only a string answer
- the provider prompt explicitly forbids side effects and command proposals
- the CLI path only loads persisted operation state and renders the returned text

### Brain contract

`OperatorBrain` and `StructuredOutputProvider` both expose:

```python
async def answer_question(self, state: OperationState, question: str) -> str
```

`ProviderBackedBrain` delegates that call to the configured provider, and the concrete providers
implement it with a read-only prompt built from operation context.

### CLI surface

The committed CLI surface is:

```sh
operator ask OP QUESTION
```

with:

- human output:

  ```text
  Question: <question>

  <answer>
  ```

- `--json` output:

  ```json
  {
    "operation_id": "...",
    "question": "...",
    "answer": "..."
  }
  ```

### Operation reference resolution

The implemented `ask` resolver accepts:

- full operation id
- unique short prefix
- `last`
- a profile name that resolves to the most recent operation whose
  `goal.metadata["project_profile_name"]` matches

Missing or ambiguous references exit with code `4`.

### Relationship to `OperatorPolicy`

`answer_question` is not an operator-loop policy decision. The service-level query path now
depends directly on `OperatorBrain` rather than reaching the brain through `OperatorPolicy`.
`LlmFirstOperatorPolicy` remains responsible only for operator-loop decisions.

## Closure Criteria And Evidence

### 1. The brain contract includes a read-only question method

Evidence:

- protocol:
  `src/agent_operator/protocols/brain.py:OperatorBrain.answer_question`
- provider contract:
  `src/agent_operator/protocols/providers.py:StructuredOutputProvider.answer_question`
- direct service dependency:
  `src/agent_operator/application/service.py:OperatorService.answer_question`

Verification:

- `tests/test_provider_brain.py::test_provider_backed_brain_delegates_answer_question`

### 2. Provider-backed brain and concrete providers implement the contract

Evidence:

- brain adapter:
  `src/agent_operator/providers/brain.py:ProviderBackedBrain.answer_question`
- prompt construction:
  `src/agent_operator/providers/prompting.py:build_question_answer_prompt`
- OpenAI provider:
  `src/agent_operator/providers/openai_responses.py:OpenAIResponsesStructuredOutputProvider.answer_question`
- Codex provider:
  `src/agent_operator/providers/codex.py:CodexStructuredOutputProvider.answer_question`
- bootstrap wiring:
  `src/agent_operator/bootstrap.py:build_brain`

Verification:

- `tests/test_prompting.py::test_build_question_answer_prompt_enforces_read_only_grounded_answering`
- `tests/test_provider_brain.py::test_provider_backed_brain_delegates_answer_question`

### 3. `operator ask` exists as a read-only CLI surface with human and JSON output

Evidence:

- command:
  `src/agent_operator/cli/commands/operation_control.py:ask`
- workflow:
  `src/agent_operator/cli/workflows/views.py:ask_async`
- CLI docs:
  `docs/reference/cli.md`
- JSON contract docs:
  `docs/reference/cli-json-schemas.md`

Verification:

- `tests/test_cli.py::test_ask_command_answers_question`
- `tests/test_cli.py::test_ask_command_json_emits_machine_readable_payload`

### 4. Missing-operation handling is explicit and uses exit code 4

Evidence:

- workflow resolver and exit handling:
  `src/agent_operator/cli/workflows/views.py:_resolve_ask_operation_id`
  `src/agent_operator/cli/workflows/views.py:ask_async`

Verification:

- `tests/test_cli.py::test_ask_command_missing_operation_exits_with_internal_error_code`

### 5. The query path does not route through `OperatorPolicy`

Evidence:

- direct service method:
  `src/agent_operator/application/service.py:OperatorService.answer_question`
- unchanged policy seam:
  `src/agent_operator/application/operator_policy.py:LlmFirstOperatorPolicy`

Verification:

- `uv run pytest`

### 6. The implementation is closed against current repository truth

Evidence:

- command and workflow are present in the shipped CLI package:
  `src/agent_operator/cli/commands/operation_control.py`
  `src/agent_operator/cli/workflows/__init__.py`
- test-support wiring updated for the direct brain dependency:
  `src/agent_operator/testing/operator_service_support.py:make_service`

Verification:

- ADR-focused test run:
  `pytest tests/test_prompting.py tests/test_provider_brain.py tests/test_cli.py -q`
- repository suite:
  `uv run pytest`

## Deferred

The following remain out of scope for this ADR:

- `operator converse`
- TUI `n` inline conversation panel
- write-side NL with structured preview/confirmation

Those require additional conversation-state and UI work and should be handled in a follow-up ADR.

## Consequences

- Users can ask a direct natural-language question about a persisted operation from the CLI.
- The repository now has a concrete read-only NL boundary separate from operator-loop policy.
- The future multi-turn NL surfaces can build on the committed `answer_question(...)` seam without
  reopening the single-shot contract.

## Related

- [NL-UX-VISION.md](../NL-UX-VISION.md)
- [CLI-UX-VISION.md](../CLI-UX-VISION.md)
- [ADR 0100](./0100-pluggable-operator-policy-boundary-above-loaded-operation-runtime.md)
- [ADR 0101](./0101-ideal-application-organization-shell-loaded-operation-policy-and-workflow-capabilities.md)
