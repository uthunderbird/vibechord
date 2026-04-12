from __future__ import annotations

import sys

import anyio
import typer
from typer.main import get_command as typer_get_command

app = typer.Typer(
    no_args_is_help=False,
    context_settings={"help_option_names": []},
    help=(
        "Workspace lifecycle shell for operator. Use `init` to prepare a workspace, "
        "`run` to start work, `operator` or `fleet` to supervise it, and `clear` to "
        "reset local runtime state."
    ),
)
smoke_app = typer.Typer(no_args_is_help=True)
debug_app = typer.Typer(no_args_is_help=False)
project_app = typer.Typer(no_args_is_help=True)
policy_app = typer.Typer(no_args_is_help=True)
agent_app = typer.Typer(no_args_is_help=True)

app.add_typer(smoke_app, name="smoke")
app.add_typer(debug_app, name="debug")
app.add_typer(project_app, name="project")
app.add_typer(policy_app, name="policy")
app.add_typer(agent_app, name="agent")


@debug_app.callback(invoke_without_command=True)
def debug_main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    typer.echo(ctx.get_help())
    raise typer.Exit()


def _iter_click_commands(command) -> list[object]:
    commands = [command]
    nested = getattr(command, "commands", None)
    if isinstance(nested, dict):
        for child in nested.values():
            commands.extend(_iter_click_commands(child))
    return commands


def _emit_help(*, show_all: bool) -> None:
    click_command = typer_get_command(app)
    commands = _iter_click_commands(click_command)
    previous_hidden: list[tuple[object, bool]] = []
    for command in commands:
        hidden = getattr(command, "hidden", None)
        if not isinstance(hidden, bool):
            continue
        name = getattr(command, "name", None)
        next_hidden = hidden
        if show_all:
            next_hidden = False
        elif name in {"debug", "smoke"}:
            next_hidden = True
        if next_hidden != hidden:
            previous_hidden.append((command, hidden))
            command.hidden = next_hidden
    try:
        typer.echo(click_command.get_help(typer.Context(click_command)))
        if show_all:
            typer.echo(
                "\nHidden Commands:\n"
                "- debug\n- smoke\n- resume\n- tick\n- daemon\n- recover\n- wakeups\n"
                "- sessions\n- command\n- context\n- trace\n- inspect"
            )
    finally:
        for command, hidden in previous_hidden:
            command.hidden = hidden


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    help_: bool = typer.Option(
        False, "--help", "-h", help="Show this message and exit.", is_eager=True
    ),
    all_commands: bool = typer.Option(
        False, "--all", help="Show hidden commands when combined with --help.", is_eager=True
    ),
) -> None:
    if help_:
        _emit_help(show_all=all_commands)
        raise typer.Exit()
    if ctx.resilient_parsing or ctx.invoked_subcommand is not None:
        return
    from .workflows import fleet_async, has_any_operations_async

    if sys.stdout.isatty() and sys.stdin.isatty():
        anyio.run(fleet_async, None, False, False, False, 0.5)
        raise typer.Exit()
    has_operations = anyio.run(has_any_operations_async)
    if has_operations:
        anyio.run(fleet_async, None, False, True, False, 0.5)
        raise typer.Exit()
    typer.echo(ctx.get_help())
    raise typer.Exit()


from .commands import agent as _commands_agent  # noqa: E402,F401
from .commands import debug as _commands_debug  # noqa: E402,F401
from .commands import fleet as _commands_fleet  # noqa: E402,F401
from .commands import operation_control as _commands_operation_control  # noqa: E402,F401
from .commands import operation_detail as _commands_operation_detail  # noqa: E402,F401
from .commands import policy as _commands_policy  # noqa: E402,F401
from .commands import project as _commands_project  # noqa: E402,F401
from .commands import run as _commands_run  # noqa: E402,F401
from .commands import smoke as _commands_smoke  # noqa: E402,F401
