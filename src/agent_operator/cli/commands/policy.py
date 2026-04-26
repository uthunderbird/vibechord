from __future__ import annotations

import json

import anyio
import typer

from agent_operator.bootstrap import build_policy_store
from agent_operator.domain import (
    CommandTargetScope,
    InvolvementLevel,
    OperationCommandType,
    PolicyStatus,
    RunMode,
)

from ..app import policy_app
from ..helpers.policy import (
    policy_applicability_payload,
    policy_evaluation_payload,
    policy_payload,
    resolve_operation_policy_scope,
)
from ..helpers.resolution import (
    load_required_canonical_operation_state_async,
    resolve_operation_id_async,
)
from ..helpers.services import load_settings
from ..options import (
    POLICY_ATTENTION_OPTION,
    POLICY_CATEGORY_OPTION,
    POLICY_ID_OPTION,
    POLICY_INVOLVEMENT_MATCH_OPTION,
    POLICY_JSON_OPTION,
    POLICY_OBJECTIVE_KEYWORD_OPTION,
    POLICY_REASON_OPTION,
    POLICY_RULE_OPTION,
    POLICY_RUN_MODE_OPTION,
    POLICY_TASK_KEYWORD_OPTION,
    POLICY_TEXT_OPTION,
    POLICY_TITLE_OPTION,
)
from ..workflows import enqueue_custom_command_async

POLICY_AGENT_OPTION = typer.Option(
    None,
    "--agent",
    help="Limit the policy to operations that allow or use this adapter key.",
)


def _emit_policy_entry(payload: dict[str, object]) -> None:
    typer.echo(f"Policy: {payload['policy_id']}")
    typer.echo(f"Project scope: {payload['project_scope']}")
    typer.echo(f"Status: {payload['status']}")
    typer.echo(f"Title: {payload['title']}")
    typer.echo(f"Category: {payload['category']}")
    typer.echo("Rule:")
    typer.echo(str(payload["rule_text"]))
    typer.echo(f"Applicability: {payload['applicability_summary']}")

    applicability = payload.get("applicability")
    if isinstance(applicability, dict):
        typer.echo("Applicability details:")
        for label, key in (
            ("Objective keywords", "objective_keywords"),
            ("Task keywords", "task_keywords"),
            ("Agents", "agent_keys"),
            ("Run modes", "run_modes"),
            ("Involvement levels", "involvement_levels"),
        ):
            values = applicability.get(key, [])
            if isinstance(values, list) and values:
                typer.echo(f"- {label}: {', '.join(str(item) for item in values)}")
            else:
                typer.echo(f"- {label}: none")
    rationale = payload.get("rationale")
    typer.echo(f"Rationale: {rationale or '-'}")
    typer.echo(f"Created at: {payload.get('created_at') or '-'}")
    typer.echo(f"Revoked at: {payload.get('revoked_at') or '-'}")
    typer.echo(f"Revoked reason: {payload.get('revoked_reason') or '-'}")
    typer.echo(f"Superseded by: {payload.get('superseded_by') or '-'}")


def _policy_project_payload(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for item in entries:
        scope = str(item["project_scope"])
        bucket = grouped.setdefault(
            scope,
            {
                "project_scope": scope,
                "policy_count": 0,
                "active_policy_count": 0,
                "categories": set(),
            },
        )
        bucket["policy_count"] = int(bucket["policy_count"]) + 1
        if item["status"] == PolicyStatus.ACTIVE.value:
            bucket["active_policy_count"] = int(bucket["active_policy_count"]) + 1
        categories = bucket["categories"]
        assert isinstance(categories, set)
        categories.add(str(item["category"]))
    payload: list[dict[str, object]] = []
    for scope in sorted(grouped):
        bucket = grouped[scope]
        categories = bucket["categories"]
        assert isinstance(categories, set)
        project_name = scope.partition(":")[2] if ":" in scope else scope
        payload.append(
            {
                "project": project_name,
                "project_scope": scope,
                "policy_count": bucket["policy_count"],
                "active_policy_count": bucket["active_policy_count"],
                "categories": sorted(categories),
            }
        )
    return payload


@policy_app.command("projects")
def policy_projects(json_mode: bool = typer.Option(False, "--json")) -> None:
    settings = load_settings()
    store = build_policy_store(settings)

    async def _projects() -> None:
        entries = [policy_payload(entry) for entry in await store.list()]
        payload = _policy_project_payload(entries)
        if json_mode:
            typer.echo(json.dumps({"policy_projects": payload}, indent=2, ensure_ascii=False))
            return
        typer.echo("Projects With Policies")
        if not payload:
            typer.echo("- none")
            return
        for item in payload:
            typer.echo(f"- {item['project']}")

    anyio.run(_projects)


@policy_app.command("list")
def policy_list(
    project: str | None = typer.Argument(None, help="Project profile name."),
    project_option: str | None = typer.Option(None, "--project", help="Project profile name."),
    scope: str | None = typer.Option(None, "--scope", help="Explicit project scope."),
    include_inactive: bool = typer.Option(
        False, "--all", help="Include revoked and superseded entries."
    ),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    settings = load_settings()
    store = build_policy_store(settings)
    resolved_scope = scope or project_option or project

    async def _list_policies() -> None:
        entries = await store.list(project_scope=resolved_scope)
        if not entries and resolved_scope is not None:
            entries = await store.list(project_scope=f"profile:{resolved_scope}")
        if not include_inactive:
            entries = [entry for entry in entries if entry.status is PolicyStatus.ACTIVE]
        payload = [policy_payload(entry) for entry in entries]
        if json_mode:
            typer.echo(
                json.dumps(
                    {"project_scope": resolved_scope, "policy_entries": payload},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"Project scope: {resolved_scope or '(all)'}")
        typer.echo("Policy entries:")
        if not payload:
            typer.echo("- none")
            return
        for item in payload:
            typer.echo(f"- {item['policy_id']} [{item['status']}] {item['title']}")
            typer.echo(f"  category: {item['category']}")
            typer.echo(f"  rule: {item['rule_text']}")
            typer.echo(f"  applies: {item['applicability_summary']}")

    anyio.run(_list_policies)


@policy_app.command("inspect")
def policy_inspect(policy_id: str, json_mode: bool = POLICY_JSON_OPTION) -> None:
    settings = load_settings()
    store = build_policy_store(settings)

    async def _inspect_policy() -> None:
        entry = await store.load(policy_id)
        if entry is None:
            raise typer.BadParameter(f"Policy entry {policy_id!r} was not found.")
        payload = policy_payload(entry)
        if json_mode:
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        _emit_policy_entry(payload)

    anyio.run(_inspect_policy)


@policy_app.command("explain")
def policy_explain(
    operation_id: str,
    include_inactive: bool = typer.Option(
        False, "--all", help="Include revoked and superseded entries from the same project scope."
    ),
    json_mode: bool = POLICY_JSON_OPTION,
) -> None:
    settings = load_settings()
    policy_store = build_policy_store(settings)

    async def _explain_policy() -> None:
        try:
            resolved_operation_id = await resolve_operation_id_async(operation_id)
            operation = await load_required_canonical_operation_state_async(
                settings, resolved_operation_id
            )
        except RuntimeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        project_scope = resolve_operation_policy_scope(operation)
        entries = (
            await policy_store.list(project_scope=project_scope)
            if project_scope is not None
            else []
        )
        if not include_inactive:
            entries = [entry for entry in entries if entry.status is PolicyStatus.ACTIVE]
        evaluations = [policy_evaluation_payload(entry, operation) for entry in entries]
        matched = [item for item in evaluations if bool(item.get("applies_now"))]
        skipped = [item for item in evaluations if not bool(item.get("applies_now"))]
        payload = {
            "operation_id": operation.operation_id,
            "project_scope": project_scope,
            "matched_policy_entries": matched,
            "skipped_policy_entries": skipped,
            "has_policy_scope": project_scope is not None,
        }
        if json_mode:
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        typer.echo(f"Operation {operation.operation_id}")
        typer.echo(f"Project scope: {project_scope or '-'}")
        if project_scope is None:
            typer.echo(
                "Policy evaluation: operation has no persisted policy scope, so scoped "
                "project policy cannot be evaluated."
            )
            return
        typer.echo("Matched policy:")
        if not matched:
            typer.echo("- none")
        for item in matched:
            typer.echo(f"- {item['policy_id']} [{item['status']}] {item['title']}")
            typer.echo(f"  category: {item['category']}")
            typer.echo(f"  rule: {item['rule_text']}")
            typer.echo(f"  applies: {item['applicability_summary']}")
            match_reasons = item.get("match_reasons")
            if isinstance(match_reasons, list) and match_reasons:
                typer.echo("  matched_by: " + " | ".join(str(reason) for reason in match_reasons))
        typer.echo("Skipped policy:")
        if not skipped:
            typer.echo("- none")
        for item in skipped:
            typer.echo(f"- {item['policy_id']} [{item['status']}] {item['title']}")
            typer.echo(f"  category: {item['category']}")
            typer.echo(f"  rule: {item['rule_text']}")
            typer.echo(f"  applies: {item['applicability_summary']}")
            skip_reasons = item.get("skip_reasons")
            if isinstance(skip_reasons, list) and skip_reasons:
                typer.echo("  skipped_by: " + " | ".join(str(reason) for reason in skip_reasons))

    anyio.run(_explain_policy)


@policy_app.command("record")
def policy_record(
    operation_id: str,
    title: str | None = POLICY_TITLE_OPTION,
    text: str | None = POLICY_TEXT_OPTION,
    rule: str | None = POLICY_RULE_OPTION,
    category: str = POLICY_CATEGORY_OPTION,
    objective_keyword: list[str] | None = POLICY_OBJECTIVE_KEYWORD_OPTION,
    task_keyword: list[str] | None = POLICY_TASK_KEYWORD_OPTION,
    agent: list[str] | None = POLICY_AGENT_OPTION,
    run_mode: list[RunMode] | None = POLICY_RUN_MODE_OPTION,
    involvement: list[InvolvementLevel] | None = POLICY_INVOLVEMENT_MATCH_OPTION,
    rationale: str | None = typer.Option(None, "--rationale", help="Optional rationale."),
    attention_id: str | None = POLICY_ATTENTION_OPTION,
) -> None:
    effective_text = (text or rule or "").strip()
    effective_title = (title or "").strip() or None
    if attention_id is None and effective_title is None:
        raise typer.BadParameter("--title is required unless --attention is provided.")
    if attention_id is None and not effective_text:
        raise typer.BadParameter("--text or --rule is required unless --attention is provided.")
    anyio.run(
        enqueue_custom_command_async,
        operation_id,
        OperationCommandType.RECORD_POLICY_DECISION,
        {
            "title": effective_title,
            "text": effective_text,
            "category": category,
            **policy_applicability_payload(
                objective_keyword, task_keyword, agent, run_mode, involvement
            ),
            "rationale": rationale,
        },
        CommandTargetScope.ATTENTION_REQUEST
        if attention_id is not None
        else CommandTargetScope.OPERATION,
        attention_id or operation_id,
    )


@policy_app.command("revoke")
def policy_revoke(
    operation_id: str,
    policy_id: str = POLICY_ID_OPTION,
    reason: str | None = POLICY_REASON_OPTION,
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation prompt."),
) -> None:
    if not yes:
        confirmed = typer.confirm(f"Revoke policy {policy_id} for operation {operation_id}?")
        if not confirmed:
            typer.echo("cancelled")
            raise typer.Exit()
    anyio.run(
        enqueue_custom_command_async,
        operation_id,
        OperationCommandType.REVOKE_POLICY_DECISION,
        {"policy_id": policy_id, "reason": reason},
        CommandTargetScope.OPERATION,
        operation_id,
    )
