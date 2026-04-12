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

`answer_question` is not treated as an operator-loop policy decision. The CLI query path resolves
an operation reference, then calls `OperatorService.answer_question(...)`, which loads persisted
`OperationState` and reaches the brain through the configured policy's `brain` property.
`LlmFirstOperatorPolicy` remains unchanged as the loop-decision adapter.

## Closure Evidence Matrix

| ADR line / closure claim | Repository evidence | Schema evidence | Verification |
| --- | --- | --- | --- |
| Add a read-only brain question method | `src/agent_operator/protocols/brain.py:OperatorBrain.answer_question`; `src/agent_operator/protocols/providers.py:StructuredOutputProvider.answer_question`; `src/agent_operator/application/service.py:OperatorService.answer_question` | `src/agent_operator/dtos/brain.py:QuestionAnswerDTO` | `tests/test_service.py::test_operator_service_answers_question_from_loaded_operation_state` |
| Provider-backed brain implements the method | `src/agent_operator/providers/brain.py:ProviderBackedBrain.answer_question` | `src/agent_operator/dtos/brain.py:QuestionAnswerDTO` | `tests/test_service.py::test_operator_service_answers_question_from_loaded_operation_state` |
| Concrete providers support NL single-shot answering | `src/agent_operator/providers/openai_responses.py:OpenAIResponsesStructuredOutputProvider.answer_question`; `src/agent_operator/providers/codex.py:CodexStructuredOutputProvider.answer_question`; `src/agent_operator/bootstrap.py:build_brain` | `QuestionAnswerDTO.model_json_schema()` is passed through `build_strict_json_schema(...)` in both providers | `uv run mypy src/agent_operator/providers/openai_responses.py src/agent_operator/providers/codex.py src/agent_operator/providers/brain.py` |
| The prompt is explicitly read-only and grounded in operation context | `src/agent_operator/providers/prompting.py:build_question_answer_prompt` | Prompt references serialized `OperationState` context; no write-side schema is accepted or emitted | `tests/test_prompting.py::test_build_question_answer_prompt_enforces_read_only_boundary` |
| `operator ask OP QUESTION` exists as a committed CLI surface | `src/agent_operator/cli/commands/operation_control.py:ask`; `src/agent_operator/cli/workflows/control.py:ask_async`; `src/agent_operator/cli/workflows/__init__.py:ask_async` | `docs/reference/cli-json-schemas.md` documents `question` and `answer` fields | `tests/test_cli.py::test_ask_cli_renders_text_output`; `tests/test_cli.py::test_ask_cli_json_output_contract`; `tests/test_cli.py::test_ask_command_answers_question`; `tests/test_cli.py::test_ask_command_json_emits_machine_readable_payload` |
| Operation references include full id, short prefix, `last`, and profile name | `src/agent_operator/cli/workflows/control.py:_resolve_ask_operation_id` | Resolver reads `goal.metadata["project_profile_name"]` from persisted `OperationState` | `tests/test_cli.py::test_ask_cli_resolves_profile_name_to_latest_operation` |
| Missing operations fail explicitly with exit code `4` | `src/agent_operator/cli/workflows/control.py:ask_async` catches resolver/service `RuntimeError` and raises `typer.Exit(code=EXIT_INTERNAL_ERROR)`; `src/agent_operator/cli/helpers/exit_codes.py:EXIT_INTERNAL_ERROR` | CLI JSON schema intentionally omits any fallback/null payload for not-found cases | `tests/test_cli.py::test_ask_cli_missing_operation_exits_code_4`; `tests/test_cli.py::test_ask_command_missing_operation_exits_with_internal_error_code` |
| The query path is read-only and does not enqueue commands | `src/agent_operator/application/service.py:OperatorService.answer_question` only loads state and calls `brain.answer_question(...)`; no command inbox or event mutation path is touched | `QuestionAnswerDTO` contains only `answer: str`; CLI JSON contract exposes only `question` and `answer` | `uv run pytest tests/test_prompting.py tests/test_service.py tests/test_cli.py -q` |
| Docs and shipped JSON contract are closed | `docs/reference/cli.md`; `docs/reference/cli-json-schemas.md` | Human output shape plus JSON field contract are documented there | `tests/test_cli.py::test_ask_cli_json_output_contract` |
| Final repository closure is verified against current codebase | Changed implementation lives in `src/agent_operator/...`; no follow-on tranche artifact is needed for this minimal surface | `QuestionAnswerDTO` and CLI JSON schema docs are committed with code | `uv run ruff check src/agent_operator/dtos/brain.py src/agent_operator/dtos/__init__.py src/agent_operator/providers/prompting.py src/agent_operator/providers/openai_responses.py src/agent_operator/providers/codex.py src/agent_operator/providers/brain.py src/agent_operator/application/service.py src/agent_operator/cli/workflows/views.py src/agent_operator/cli/workflows/control.py src/agent_operator/cli/workflows/__init__.py src/agent_operator/cli/commands/operation_control.py tests/test_prompting.py tests/test_service.py tests/test_cli.py`; `uv run mypy src/agent_operator/dtos/brain.py src/agent_operator/dtos/__init__.py src/agent_operator/providers/prompting.py src/agent_operator/providers/openai_responses.py src/agent_operator/providers/codex.py src/agent_operator/providers/brain.py src/agent_operator/application/service.py src/agent_operator/cli/workflows/views.py src/agent_operator/cli/workflows/control.py src/agent_operator/cli/workflows/__init__.py src/agent_operator/cli/commands/operation_control.py`; `uv run pytest tests/test_prompting.py tests/test_service.py tests/test_cli.py -q`; `uv run pytest -q` |

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
