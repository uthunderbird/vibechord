"""Command line delivery surface."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, NoReturn, cast

from vibechord.command import CommandApplication
from vibechord.domain import CommandName, ExecutionBudget, OperationCommand
from vibechord.jsonutil import to_jsonable
from vibechord.mcp import run_stdio
from vibechord.mcp_http import serve_http as serve_mcp_http
from vibechord.projection import ProjectionError
from vibechord.rest import serve
from vibechord.tui import run_terminal
from vibechord.verify import run_verification
from vibechord.workspace import build_context, init_workspace


def main(argv: list[str] | None = None) -> int:
    """Run the vibechord CLI."""

    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except ProjectionError as exc:
        _print_error(
            "operation_not_found", str(exc), json_output=getattr(args, "json", False)
        )
        return 3
    except OSError as exc:
        _print_error("store_error", str(exc), json_output=getattr(args, "json", False))
        return 4


def _dispatch(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if args.command == "init":
        state_dir = init_workspace(root)
        _print({"state_dir": str(state_dir)}, args.json)
        return 0

    context = build_context(root)
    command_application = context.command_application
    if args.command == "run":
        command = OperationCommand(
            name=CommandName.START,
            command_id=_command_id(args),
            payload={"goal": args.goal},
        )
        result = command_application.apply(command)
        if result.accepted and result.operation_id is not None:
            context.operation_driver.run_until_blocked_or_terminal(
                result.operation_id, ExecutionBudget()
            )
        _print_result(result, args.json)
        return 0 if result.accepted else 1
    if args.command == "status":
        _print(context.projection_service.status(args.operation_id), args.json)
        return 0
    if args.command == "fleet":
        _print(context.projection_service.fleet(), args.json)
        return 0
    if args.command == "agent":
        _print({"agents": [{"name": "fake-agent", "kind": "fake"}]}, args.json)
        return 0
    if args.command == "project":
        _print(
            {"root": str(root), "state_dir": str(root / ".vibechord")},
            args.json,
        )
        return 0
    if args.command == "watch":
        _print(context.projection_service.live_feed(args.operation_id), args.json)
        return 0
    if args.command == "serve":
        serve(
            root,
            host=args.host,
            port=args.port,
            unsafe=args.unsafe,
            token=args.token,
            read_token=args.read_token,
            control_token=args.control_token,
            production=args.production,
            tls_cert=Path(args.tls_cert) if args.tls_cert else None,
            tls_key=Path(args.tls_key) if args.tls_key else None,
        )
        return 0
    if args.command == "tui":
        run_terminal(context, once=args.once)
        return 0
    if args.command == "mcp":
        return run_stdio(root)
    if args.command == "mcp-http":
        serve_mcp_http(
            root,
            host=args.host,
            port=args.port,
            unsafe=args.unsafe,
            token=args.token,
        )
        return 0
    if args.command == "verify":
        return run_verification(args.tier, root).return_code
    if args.command == "message":
        return _apply_command(
            command_application,
            OperationCommand(
                name=CommandName.POST_MESSAGE,
                command_id=_command_id(args),
                operation_id=args.operation_id,
                payload={"text": args.text},
            ),
            args.json,
        )
    if args.command == "answer":
        return _apply_command(
            command_application,
            OperationCommand(
                name=CommandName.ANSWER_ATTENTION,
                command_id=_command_id(args),
                operation_id=args.operation_id,
                payload={"attention_id": args.attention_id, "text": args.text},
            ),
            args.json,
        )
    if args.command in {"cancel", "pause", "resume", "interrupt"}:
        name = {
            "cancel": CommandName.CANCEL,
            "pause": CommandName.PAUSE,
            "resume": CommandName.RESUME,
            "interrupt": CommandName.INTERRUPT,
        }[args.command]
        return _apply_command(
            command_application,
            OperationCommand(
                name=name,
                command_id=_command_id(args),
                operation_id=args.operation_id,
            ),
            args.json,
        )
    if args.command == "show":
        if args.show_target == "events":
            _print(context.event_store.replay(args.operation_id), args.json)
        elif args.show_target == "status":
            _print(context.projection_service.status(args.operation_id), args.json)
        elif args.show_target == "report":
            _print(
                {
                    "status": to_jsonable(
                        context.projection_service.status(args.operation_id)
                    ),
                    "events": to_jsonable(
                        context.projection_service.live_feed(args.operation_id)
                    ),
                },
                args.json,
            )
        elif args.show_target == "sessions":
            events = context.event_store.replay(args.operation_id)
            sessions = tuple(
                event for event in events if event.kind.startswith("agent.")
            )
            _print(sessions, args.json)
        return 0
    _die(f"unsupported command: {args.command}")


def _apply_command(
    command_application: CommandApplication,
    command: OperationCommand,
    json_output: bool,
) -> int:
    result = command_application.apply(command)
    _print_result(result, json_output)
    return 0 if result.accepted else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vibechord")
    parser.add_argument("--root", default=".", help="Workspace root.")
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    run = sub.add_parser("run")
    run.add_argument("goal")
    status = sub.add_parser("status")
    status.add_argument("operation_id")
    fleet = sub.add_parser("fleet")
    fleet.add_argument("--once", action="store_true")
    sub.add_parser("agent")
    sub.add_parser("project")
    watch = sub.add_parser("watch")
    watch.add_argument("operation_id")
    watch.add_argument("--once", action="store_true")
    message = sub.add_parser("message")
    message.add_argument("operation_id")
    message.add_argument("text")
    answer = sub.add_parser("answer")
    answer.add_argument("operation_id")
    answer.add_argument("attention_id")
    answer.add_argument("text")
    for name in ("cancel", "pause", "resume", "interrupt"):
        command = sub.add_parser(name)
        command.add_argument("operation_id")
    show = sub.add_parser("show")
    show.add_argument("show_target", choices=["events", "status", "report", "sessions"])
    show.add_argument("operation_id")
    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--unsafe", action="store_true")
    serve_parser.add_argument("--token")
    serve_parser.add_argument("--read-token")
    serve_parser.add_argument("--control-token")
    serve_parser.add_argument("--production", action="store_true")
    serve_parser.add_argument("--tls-cert")
    serve_parser.add_argument("--tls-key")
    tui = sub.add_parser("tui")
    tui.add_argument("--once", action="store_true")
    sub.add_parser("mcp")
    mcp_http = sub.add_parser("mcp-http")
    mcp_http.add_argument("--host", default="127.0.0.1")
    mcp_http.add_argument("--port", type=int, default=8766)
    mcp_http.add_argument("--unsafe", action="store_true")
    mcp_http.add_argument("--token")
    verify = sub.add_parser("verify")
    verify.add_argument("tier", choices=["fast", "focused", "full"])
    return parser


def _print_result(result: object, json_output: bool) -> None:
    _print(result, json_output)


def _print(value: object, json_output: bool) -> None:
    if json_output:
        print(json.dumps(to_jsonable(value), indent=2, sort_keys=True))
        return
    if isinstance(value, tuple):
        for item in value:
            print(_human_line(item))
        return
    print(_human_line(value))


def _human_line(value: object) -> str:
    if hasattr(value, "__dataclass_fields__"):
        data = asdict(cast(Any, value))
        if "operation_id" in data and "status" in data:
            return f"{data['operation_id']} {data['status']}"
        if "accepted" in data:
            return f"{data['code']}: {data['message']}"
    return str(value)


def _print_error(code: str, message: str, json_output: bool) -> None:
    payload = {"code": code, "message": message, "retryable": False}
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stderr)
    else:
        print(f"{code}: {message}", file=sys.stderr)


def _command_id(args: argparse.Namespace) -> str:
    provided = getattr(args, "command_id", None)
    return str(provided or uuid.uuid4())


def _die(message: str) -> NoReturn:
    raise SystemExit(message)
