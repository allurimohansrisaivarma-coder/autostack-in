"""Redesigned RBAC tests: admin tier, PR-style change requests, expanded
Create-Automation context (org types, departments, tools, triggers, extras)."""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pytest

from fastapi.testclient import TestClient  # noqa: E402
from backend.app import app  # noqa: E402
from backend import roadmap_routes, teams  # noqa: E402
from tests.spike.conftest import isolated_db_module, test_session  # noqa: E402,F401

client = TestClient(app)

SERVICE = {"Authorization": "Bearer spiketoken", "Content-Type": "application/json"}

PLAN = {
    "client_id_field": "ClientID",
    "field_mappings": {"Name": "Name", "FollowUpDate": "FollowUpDate"},
    "eligibility": {"status": "Follow-up due", "status_field": "Status",
                    "date_field": "FollowUpDate", "date_value": "2026-09-20"},
    "action": "create_draft",
    "destinations": ["in_app"],
}

CTX = {"org_type": "corporate", "size": "medium",
       "department": "finance", "process_type": "accounts_payable"}

PASSWORD = "password-123"


# conftest creates an isolated DB per module; the client is bound at import —
# tests only rely on module-scoped fixtures for auth monkeypatching.


@pytest.fixture(scope="module", autouse=True)
def _auth(isolated_db_module):
    from backend.security import tokens
    orig_t = tokens.get_expected_token
    orig_r = roadmap_routes.get_expected_token
    tokens.get_expected_token = lambda: "testtoken"
    roadmap_routes.get_expected_token = lambda: "testtoken"
    yield
    tokens.get_expected_token = orig_t
    roadmap_routes.get_expected_token = orig_r


def _register(username: str) -> dict:
    r = client.post("/api/auth/register",
                    json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    tok = client.post("/api/auth/tokens",
                      json={"username": username, "password": PASSWORD}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _promote(owner_headers: dict, username: str, role: str) -> None:
    r = client.post("/api/team/members", json={"username": username, "role": role},
                    headers=owner_headers)
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module")
def owner_h():
    h = _register("rr-owner-0")
    r = client.post("/api/org/tier", json={"tier": "team"}, headers=h)
    assert r.status_code == 200, r.text
    return h


def _mk_plan(headers) -> str:
    r = client.post("/api/plans", json={"plan": PLAN}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["plan_id"]


def test_admin_is_coequal_with_owner_for_product_actions(owner_h):
    """admin == owner for create/test/activate/publish/review; only org tier
    stays owner-only. The admin role must be assignable by an owner."""
    _register("rr-admin-1")
    _promote(owner_h, "rr-admin-1", "admin")
    # issue a token for the promoted user
    tok = client.post("/api/auth/tokens",
                      json={"username": "rr-admin-1", "password": PASSWORD}).json()["token"]
    adm_h = {"Authorization": f"Bearer {tok}"}
    me = client.get("/api/auth/me", headers=adm_h).json()
    assert me["role"] == "admin", me

    # full product path: plan → generate → test → activate → bind → publish
    plan_id = _mk_plan(adm_h)
    art = client.post("/api/artifacts/generate",
                      json={"plan_id": plan_id, "approve_generation": True},
                      headers=adm_h).json()
    job = client.post("/api/test-jobs",
                      json={"artifact_id": art["artifact_id"], "fixture": "reset",
                            "consent": True}, headers=adm_h)
    assert job.status_code == 200, job.text
    act = client.post("/api/approvals/activation",
                      json={"artifact_id": art["artifact_id"], "job_id": job.json()["job_id"]},
                      headers=adm_h)
    assert act.status_code == 200, act.text
    r = client.post(f"/api/plan/{plan_id}/create-workflow", json=CTX, headers=adm_h)
    assert r.status_code == 200, r.text
    graph = client.get(f"/api/workflows/{r.json()['workflow_id']}", headers=adm_h).json()["graph"]
    pub = {"slug": f"rr-pub-{uuid.uuid4().hex[:6]}", "title": "t", "graph": graph,
           "publication_consent": True}
    assert client.post("/api/registry/publish", json=pub, headers=adm_h).status_code == 200
    # ...but tier changes stay owner-only
    r = client.post("/api/org/tier", json={"tier": "enterprise"}, headers=adm_h)
    assert r.status_code == 403, r.text


def test_owner_has_full_access_to_tools_and_creation(owner_h):
    """The reported bug: an owner (personal-org or shared) must complete the
    whole create path — plan, generate, test, activate, bind with tools — with
    no 'no access' errors anywhere."""
    plan_id = _mk_plan(owner_h)
    art = client.post("/api/artifacts/generate",
                      json={"plan_id": plan_id, "approve_generation": True},
                      headers=owner_h)
    assert art.status_code == 200, art.text
    job = client.post("/api/test-jobs",
                      json={"artifact_id": art.json()["artifact_id"], "fixture": "reset",
                            "consent": True}, headers=owner_h)
    assert job.status_code == 200, job.text
    act = client.post("/api/approvals/activation",
                      json={"artifact_id": art.json()["artifact_id"],
                            "job_id": job.json()["job_id"]}, headers=owner_h)
    assert act.status_code == 200, act.text
    ctx = dict(CTX, connectors=["csv"], tools=["data", "notify"], trigger="manual",
               sensitivity_note="", outcome="drafts prepared without manual work")
    r = client.post(f"/api/plan/{plan_id}/create-workflow", json=ctx, headers=owner_h)
    assert r.status_code == 200, r.text  # the old bug surfaced right here


def test_operator_create_becomes_change_request_not_live_workflow(owner_h):
    """Operator drafting ends in a CHANGE REQUEST: open → owner reviews →
    merged (draft workflow) or rejected. Live create stays refused for them."""
    _register("rr-operator-1")
    _promote(owner_h, "rr-operator-1", "operator")
    tok = client.post("/api/auth/tokens",
                      json={"username": "rr-operator-1", "password": PASSWORD}).json()["token"]
    op_h = {"Authorization": f"Bearer {tok}"}
    plan_id = _mk_plan(op_h)  # operators may still draft plans

    # direct live create: refused with the CR pointer
    r = client.post(f"/api/plan/{plan_id}/create-workflow", json=CTX, headers=op_h)
    assert r.status_code == 403, r.text
    assert "change request" in r.json()["detail"]["how_to_unlock"]

    # open the change request instead
    r = client.post("/api/change-requests", json={
        "kind": "workflow_create", "title": "Follow-up automation for finance",
        "summary": "client follow-up, in-app drafts", "target_workflow_id": None,
        "payload": {"plan_id": plan_id, "org_type": CTX["org_type"],
                    "department": CTX["department"], "connectors": ["csv"],
                    "tools": ["data", "notify"], "trigger": "schedule",
                    "sensitivity_note": "contains client PII",
                    "outcome": "no missed follow-ups"}},
        headers=op_h)
    assert r.status_code == 200, r.text
    cr_id = r.json()["id"]
    assert r.json()["status"] == "open"

    # the author cannot merge their own request
    assert client.post(f"/api/change-requests/{cr_id}/decide",
                       json={"approve": True}, headers=op_h).status_code == 403

    # owner sees it in the queue and merges it
    queue = client.get("/api/change-requests", headers=owner_h).json()["change_requests"]
    assert any(c["id"] == cr_id and c["status"] == "open" for c in queue)
    r = client.post(f"/api/change-requests/{cr_id}/decide",
                    json={"approve": True, "note": "looks good"}, headers=owner_h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "merged"
    assert r.json()["merged_workflow_id"]  # draft workflow materialized

    # double-decide refused; reject path records the note
    assert client.post(f"/api/change-requests/{cr_id}/decide",
                       json={"approve": True}, headers=owner_h).status_code == 409
    r = client.post("/api/change-requests", json={
        "kind": "workflow_create", "title": "Second proposal"}, headers=op_h)
    cr2 = r.json()["id"]
    r = client.post(f"/api/change-requests/{cr2}/decide",
                    json={"approve": False, "note": "scope too broad"}, headers=owner_h)
    assert r.json()["status"] == "rejected"

    # admin can review too; audit trail covers open + decide
    _register("rr-admin-2")
    _promote(owner_h, "rr-admin-2", "admin")
    tok2 = client.post("/api/auth/tokens",
                       json={"username": "rr-admin-2", "password": PASSWORD}).json()["token"]
    r = client.post("/api/change-requests", json={
        "kind": "workflow_create", "title": "Third proposal"}, headers=op_h)
    cr3 = r.json()["id"]
    r = client.post(f"/api/change-requests/{cr3}/decide",
                    json={"approve": True, "note": "admin merge"}, headers={"Authorization": f"Bearer {tok2}"})
    assert r.status_code == 200 and r.json()["status"] == "merged", r.text

    audit = client.get("/api/audit?limit=200", headers=owner_h)
    kinds = [e["kind"] for e in audit.json().get("entries", [])] if audit.status_code == 200 else []
    assert "change_request.opened" in kinds and "change_request.decided" in kinds, kinds[-10:]


def test_observer_cannot_propose_or_write(owner_h):
    """Observer default: view only — no change requests, no plans, no writes."""
    _register("rr-observer-1")
    _promote(owner_h, "rr-observer-1", "observer")
    tok = client.post("/api/auth/tokens",
                      json={"username": "rr-observer-1", "password": PASSWORD}).json()["token"]
    obs_h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/workflows", headers=obs_h).status_code == 200
    assert client.post("/api/plans", json={"plan": PLAN}, headers=obs_h).status_code == 403
    r = client.post("/api/change-requests", json={
        "kind": "workflow_create", "title": "observer proposal"}, headers=obs_h)
    assert r.status_code == 403, r.text  # require_writer blocks observers up front


def test_expanded_context_catalog_cascades():
    """11 org types cascade to departments and process types; tool and trigger
    menus ship from the worker (never invented by the UI)."""
    cat = client.get("/api/org/catalog").json()
    for t in ("healthcare", "legal", "manufacturing", "retail", "logistics", "other"):
        assert t in cat["org_types"], t
    assert len(cat["org_types"]) >= 11
    assert "clinical_operations" in cat["departments"]["healthcare"]
    assert "citizen_services" in cat["departments"]["government"]
    assert "student_services" in cat["departments"]["education"]
    assert "compliance" in cat["departments"]["corporate"]
    assert "personal_productivity" in cat["departments"]["individual"]
    # every department of every org type has a non-empty, valid process menu
    for otype, depts in cat["departments"].items():
        for d in depts:
            allowed = cat["process_types"].get(d) or cat["default_process_types"]
            assert allowed, f"empty process menu for {otype}/{d}"
            assert teams.valid_context(otype, cat["sizes_for_type"][otype][0], d, allowed[0]) == []
    # common verbs available broadly; tools + triggers present
    assert "client_followup" in cat["process_types"]["finance"]
    assert "custom" in cat["process_types"]["operations"]
    assert {"files", "data", "http", "notify", "logic"} == {t["id"] for t in cat["tool_categories"]}
    assert {t["id"] for t in cat["trigger_options"]} == {"manual", "schedule", "file", "webhook"}


def test_extended_context_fields_persist_on_workflow(owner_h):
    """connectors/tools/trigger/sensitivity/outcome ride along on the bind and
    are stored with the workflow context — validated core tuple, verbatim extras."""
    plan_id = _mk_plan(owner_h)
    art = client.post("/api/artifacts/generate",
                      json={"plan_id": plan_id, "approve_generation": True},
                      headers=owner_h).json()
    job = client.post("/api/test-jobs",
                      json={"artifact_id": art["artifact_id"], "fixture": "reset",
                            "consent": True}, headers=owner_h)
    assert job.status_code == 200, job.text
    assert client.post("/api/approvals/activation",
                       json={"artifact_id": art["artifact_id"], "job_id": job.json()["job_id"]},
                       headers=owner_h).status_code == 200
    ctx = dict(CTX, connectors=["csv", "http_request"], tools=["data", "http", "notify"],
               trigger="schedule", sensitivity_note="client PII — internal only",
               outcome="zero missed follow-ups")
    r = client.post(f"/api/plan/{plan_id}/create-workflow", json=ctx, headers=owner_h)
    assert r.status_code == 200, r.text
    wid = r.json()["workflow_id"]
    from backend.models import Setting
    db = test_session()
    try:
        row = db.get(Setting, f"workflow_context:{wid}")
        assert row is not None
        stored = json.loads(row.value_json)
        assert stored["connectors"] == ["csv", "http_request"]
        assert stored["tools"] == ["data", "http", "notify"]
        assert stored["trigger"] == "schedule"
        assert stored["sensitivity_note"] == "client PII — internal only"
        assert stored["outcome"] == "zero missed follow-ups"
    finally:
        db.close()
