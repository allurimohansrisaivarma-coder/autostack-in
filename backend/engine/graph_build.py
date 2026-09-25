"""Plan → graph compiler (Phase 5→9 keystone).

A confirmed plan becomes a runnable workflow graph using ONLY catalog node types, so
`validate_graph` still gates everything before deploy. The compiler is deterministic:
the same plan always yields the same graph (artifact hash binds them).
"""
from __future__ import annotations

from backend.engine.generation import PlanError, validate_plan

DEFAULT_ALIAS = "sample-tracking-file"
DEFAULT_FILENAME = "clients.csv"


def _safe_ident(name: str) -> str:
    """Expression identifiers are restricted to word chars (injection-proof)."""
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in (name or "field"))
    return cleaned or "field"


def _where_clause(plan: dict) -> str:
    elig = plan.get("eligibility") or {}
    status_field = _safe_ident(elig.get("status_field", "Status"))
    status = elig.get("status")
    date_field = elig.get("date_field")
    date_value = elig.get("date_value") or elig.get("run_date")
    clauses: list[str] = []
    if status is not None:
        clauses.append(f"row.{status_field} == '{status}'")
    if date_field and date_value is not None:
        df = _safe_ident(date_field)
        # Jinja2 literal is lowercase `none`; `|string` is a whitelisted filter
        # (the sandbox has no str() builtin — fail-closed by design).
        clauses.append(f"row.{df} is not none and (row.{df} | string) <= '{date_value}'")
    return " and ".join(clauses) if clauses else "True"


def plan_to_graph(plan: dict) -> dict:
    """Build a catalog-valid graph from a plan. Raises PlanError on invalid plans."""
    missing = validate_plan(plan)
    if missing:
        raise PlanError(f"plan is not compilable: {missing}")

    alias = plan.get("resource_alias") or DEFAULT_ALIAS
    filename = plan.get("resource_filename") or DEFAULT_FILENAME
    elig = plan.get("eligibility") or {}
    status_field = elig.get("status_field", "Status")
    id_field = plan.get("client_id_field", "ClientID")
    action = plan["action"]
    destinations = plan["destinations"]

    nodes: list[dict] = [
        {"id": "read", "type": "file.read_table", "params": {"alias": alias}},
        {"id": "filter", "type": "data.filter", "params": {"from": "read", "where": _where_clause(plan)}},
    ]
    edges: list[dict] = [{"from": "read", "to": "filter"}]
    if action == "update_status":
        nodes.append({"id": "act", "type": "file.update_rows",
                      "params": {"alias": alias, "filename": filename,
                                 "set": f"{status_field}='Draft prepared'",
                                 "purpose": "followup", "key_field": id_field},
                      "on_fail": "continue"})
    else:
        nodes.append({"id": "act", "type": "draft.create",
                      "params": {"record_key": f"sample:{{{id_field}}}",
                                 "template_id": "followup_en", "destination": "in_app"},
                      "on_fail": "continue"})
    edges.append({"from": "filter", "to": "act"})
    if "desktop_notification" in destinations:
        nodes.append({"id": "notify", "type": "notify.desktop", "params": {"title_key": "automation.run"}})
        edges.append({"from": "act", "to": "notify"})
    return {"nodes": nodes, "edges": edges}
