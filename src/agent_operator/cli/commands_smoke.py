from __future__ import annotations

import anyio
import typer

from agent_operator.smoke import (
    extract_final_plan,
    run_alignment_post_research_plan_smoke,
    run_codex_continuation_smoke,
    run_mixed_agent_selection_smoke,
    run_mixed_code_agent_selection_smoke,
)

from .app import smoke_app


@smoke_app.command("alignment-post-research-plan")
def smoke_alignment_post_research_plan() -> None:
    outcome = anyio.run(run_alignment_post_research_plan_smoke)
    typer.echo(extract_final_plan(outcome))
    typer.echo(f"operation_id={outcome.operation_id}", err=True)


@smoke_app.command("alignment-post-research-plan-claude-acp")
def smoke_alignment_post_research_plan_claude_acp() -> None:
    outcome = anyio.run(run_alignment_post_research_plan_smoke, "claude_acp")
    typer.echo(extract_final_plan(outcome))
    typer.echo(f"operation_id={outcome.operation_id}", err=True)


@smoke_app.command("mixed-agent-selection")
def smoke_mixed_agent_selection() -> None:
    outcome = anyio.run(run_mixed_agent_selection_smoke)
    typer.echo(extract_final_plan(outcome))
    typer.echo(f"operation_id={outcome.operation_id}", err=True)


@smoke_app.command("mixed-agent-selection-claude-acp")
def smoke_mixed_agent_selection_claude_acp() -> None:
    outcome = anyio.run(run_mixed_agent_selection_smoke, "claude_acp")
    typer.echo(extract_final_plan(outcome))
    typer.echo(f"operation_id={outcome.operation_id}", err=True)


@smoke_app.command("mixed-code-agent-selection")
def smoke_mixed_code_agent_selection() -> None:
    outcome = anyio.run(run_mixed_code_agent_selection_smoke)
    typer.echo(extract_final_plan(outcome))
    typer.echo(f"operation_id={outcome.operation_id}", err=True)


@smoke_app.command("mixed-code-agent-selection-claude-acp")
def smoke_mixed_code_agent_selection_claude_acp() -> None:
    outcome = anyio.run(run_mixed_code_agent_selection_smoke, "claude_acp")
    typer.echo(extract_final_plan(outcome))
    typer.echo(f"operation_id={outcome.operation_id}", err=True)


@smoke_app.command("codex-continuation")
def smoke_codex_continuation() -> None:
    outcome = anyio.run(run_codex_continuation_smoke)
    typer.echo(extract_final_plan(outcome))
    typer.echo(f"operation_id={outcome.operation_id}", err=True)
