from __future__ import annotations

import json
from typing import Any

import typer

from agent_operator.adapters.runtime_bindings import build_agent_runtime_bindings

from ..app import agent_app
from ..helpers.services import load_settings


def _build_bindings() -> dict[str, Any]:
    settings = load_settings()
    return build_agent_runtime_bindings(settings)


def _agent_inventory_payload() -> list[dict[str, object]]:
    bindings = _build_bindings()
    payload: list[dict[str, object]] = []
    for agent_key, binding in sorted(bindings.items()):
        descriptor = binding.descriptor
        payload.append(
            {
                "key": agent_key,
                "display_name": descriptor.display_name,
                "supports_follow_up": descriptor.supports_follow_up,
                "supports_cancellation": descriptor.supports_cancellation,
                "capability_names": [capability.name for capability in descriptor.capabilities],
            }
        )
    return payload


def _agent_detail_payload(agent_key: str) -> dict[str, object]:
    settings = load_settings()
    bindings = _build_bindings()
    binding = bindings.get(agent_key)
    if binding is None:
        raise typer.BadParameter(f"Unknown agent: {agent_key}")
    descriptor = binding.descriptor
    configured_settings = getattr(settings, agent_key, None)
    if configured_settings is None:
        raise typer.BadParameter(f"Settings for agent {agent_key!r} were not found.")
    return {
        "key": agent_key,
        "display_name": descriptor.display_name,
        "supports_follow_up": descriptor.supports_follow_up,
        "supports_cancellation": descriptor.supports_cancellation,
        "capabilities": [
            capability.model_dump(mode="json") for capability in descriptor.capabilities
        ],
        "configured_settings": configured_settings.model_dump(mode="json"),
    }


def _emit_agent_inventory(payload: list[dict[str, object]]) -> None:
    typer.echo("Agents")
    if not payload:
        typer.echo("- none")
        return
    for item in payload:
        typer.echo(f"- {item['key']}: {item['display_name']}")


def _emit_agent_detail(payload: dict[str, object]) -> None:
    typer.echo(f"Agent: {payload['key']}")
    typer.echo(f"Display name: {payload['display_name']}")
    typer.echo(
        "Supports follow-up: "
        + ("yes" if bool(payload["supports_follow_up"]) else "no")
    )
    typer.echo(
        "Supports cancellation: "
        + ("yes" if bool(payload["supports_cancellation"]) else "no")
    )
    typer.echo("Capabilities:")
    capabilities = payload["capabilities"]
    assert isinstance(capabilities, list)
    if not capabilities:
        typer.echo("- none")
    else:
        for capability in capabilities:
            assert isinstance(capability, dict)
            typer.echo(
                f"- {capability.get('name')}: {capability.get('description') or '-'}"
            )
    typer.echo("Configured settings:")
    typer.echo(
        json.dumps(
            payload["configured_settings"],
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@agent_app.command("list")
def agent_list(json_mode: bool = typer.Option(False, "--json")) -> None:
    payload = _agent_inventory_payload()
    if json_mode:
        typer.echo(json.dumps({"agents": payload}, indent=2, ensure_ascii=False))
        return
    _emit_agent_inventory(payload)


@agent_app.command("show")
def agent_show(
    key: str = typer.Argument(..., help="Stable agent key such as codex_acp."),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    payload = _agent_detail_payload(key)
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    _emit_agent_detail(payload)
