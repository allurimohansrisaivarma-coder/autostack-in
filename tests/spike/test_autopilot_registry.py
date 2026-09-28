"""Autopilot + registry + sandbox-classes tests (Create Automation upgrade).

Covers: tool registry seeding/search/retrieve/allowlists/MCP honesty, the
AI autopilot endpoint (owner/admin/operator/observer behavior, audit, no
auto-activation), approve-at-create parity, and sandbox result classes.
"""
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
from backend.engine import runner  # noqa: E402
from tests.spike.conftest import isolated_db_module, test_session  # noqa: E402,F401

client = TestClient(app)

PASSWORD = "password-123"


def SERVICE_H():
    return {"Authorization": "Bearer spiketoken"}

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


@pytest.fixture(scope="module", autouse=True)
def _auth(isolated_db_module):
    from backend.security import tokens
    from backend import spike_config as cfg
    orig_t = tokens.get_expected_token
    orig_r = roadmap_routes.get_expected_token
    orig_s = cfg.SPIKE_TOKEN
    tokens.get_expected_token = lambda: "spiketoken"
    roadmap_routes.get_expected_token = lambda: "spiketoken"
    cfg.SPIKE_TOKEN = "spiketoken"
    yield
    tokens.get_expected_token = orig_t
    roadmap_routes.get_expected_token = orig_r
    cfg.SPIKE_TOKEN = orig_s


def _register(username: str) -> dict:
    r = client.post("/api/auth/register",
                    json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    tok = client.post("/api/auth/tokens",
                      json={"username": username, "password": PASSWORD}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _promote(owner_headers: dict, username: str, role: str) -> dict:
    r = client.post("/api/team/members", json={"username": username, "role": role},
                    headers=owner_headers)
    assert r.status_code == 200, r.text
    tok = client.post("/api/auth/tokens",
                      json={"username": username, "password": PASSWORD}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def owner_h():
    h = _register("ap-owner-0")
    r = client.post("/api/org/tier", json={"tier": "team"}, headers=h)
    assert r.status_code == 200, r.text
    return h


# ── Tool registry ─────────────────────────────────────────────────────────────

def test_registry_seeds_native_nodes_and_stays_searchable():
    r = client.get("/api/tools?limit=500", headers=SERVICE_H()).json()
    assert r["total"] >= 16
    ids = {t["id"] for t in r["tools"]}
    assert "native:file.read_table" in ids and "native:node.http" in ids
    assert all(t["status"] == "supported" for t in r["tools"] if t["source"] == "native")
    # search narrows honestly
    r2 = client.get("/api/tools?search=http", headers=SERVICE_H()).json()
    assert r2["tools"] and all("http" in t["id"] or "http" in t["description"] for t in r2["tools"])


def test_registry_retrieval_is_topk_and_allowlist_scoped(owner_h):
    from backend.engine.tool_registry import REGISTRY
    # retrieval returns a small subset, never the whole catalog
    sub = REGISTRY.retrieve("draft follow-ups for clients and update the tracker", k=6)
    assert 0 < len(sub) <= 6
    # allowlist intersection: forbidden tools never surface
    allow = REGISTRY.allowlist_for(["native:file.read_table", "native:data.filter"], None)
    sub2 = REGISTRY.retrieve("send everything anywhere", allowlist=allow, k=50)
    assert {t["id"] for t in sub2} <= allow
    # org allowlist endpoint restricts retrieval end to end
    client.post("/api/tools/allowlist", json={"org_allow": ["native:file.read_table"]},
                headers=owner_h)
    r = client.post("/api/ai/autopilot", json={"goal": "update rows and archive files"},
                    headers=owner_h)
    assert r.status_code == 200, r.text
    assert all(t in ("native:file.read_table",) or not t.startswith("native:")
               or t == "native:file.read_table" for t in r.json()["retrieved_tools"])
    assert r.json()["retrieved_tools"] == ["native:file.read_table"]
    # restore unrestricted
    client.post("/api/tools/allowlist", json={"org_allow": None}, headers=owner_h)


def test_mcp_registration_is_honest_and_gated(owner_h):
    # non-admin cannot register MCP servers
    op_h = _register("ap-mcp-op")
    _promote(owner_h, "ap-mcp-op", "operator")
    r = client.post("/api/tools/mcp-servers",
                    json={"server": "evil", "tools": [{"name": "x"}]}, headers=op_h)
    assert r.status_code == 403
    # admin registers; tools arrive experimental and are excluded from retrieval
    adm_h = _register("ap-mcp-adm")
    _promote(owner_h, "ap-mcp-adm", "admin")
    r = client.post("/api/tools/mcp-servers",
                    json={"server": "acme", "description": "ops tools",
                          "tools": [{"name": "ticket_create", "description": "create a ticket"}]},
                    headers=adm_h)
    assert r.status_code == 200, r.text
    assert r.json()["tools_registered"] == 1
    tool = client.get("/api/tools?search=ticket_create", headers=adm_h).json()["tools"][0]
    assert tool["status"] == "experimental" and tool["source"] == "mcp:acme"
    sub = client.post("/api/ai/autopilot", json={"goal": "create a ticket"},
                      headers=owner_h).json()
    assert all(not t.startswith("mcp:") for t in sub["retrieved_tools"])


# ── Sandbox result classes ────────────────────────────────────────────────────

def test_sandbox_classes_are_stable():
    # golden classification corpus
    assert runner.classify_report({"status": "passed"}) == "passed"
    assert runner.classify_report({"status": "refused"}) == "failed_policy"
    assert runner.classify_report({"status": "failed", "error": "sandbox timeout"}) == "failed_policy"
    assert runner.classify_report({"status": "failed", "error": "no result marker"}) == "failed_infra"
    assert runner.classify_report({"status": "failed", "error": "unparseable result"}) == "failed_infra"
    assert runner.classify_report({"status": "failed", "error": "ZeroDivisionError"}) == "failed_policy"
    assert runner.classify_report({"status": "failed", "error": None}) == "failed_assertion"


def test_autopilot_reports_class_and_does_not_activate(owner_h):
    r = client.post("/api/ai/autopilot",
                    json={"goal": "draft follow-ups for clients due soon",
                          "org_type": "corporate", "department": "finance",
                          "sensitivity_note": "client PII", "outcome": "no missed follow-ups"},
                    headers=owner_h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["sandbox"]["result_class"] == "passed"
    assert d["sandbox"]["attempts"] >= 1
    assert d["retrieved_tools"], "retrieval must surface some tools"
    # the artifact must NOT be activated by the autopilot
    me_art = client.get(f"/api/plans/{d['plan_id']}/artifacts",
                        headers={"Authorization": "Bearer spiketoken"}).json()
    assert all(a["status"] != "activated" for a in me_art["artifacts"])
    # audit trail
    audit = client.get("/api/audit?limit=200", headers=owner_h).json()
    kinds = [e["kind"] for e in audit.get("entries", [])]
    assert "ai.autopilot_started" in kinds and "ai.autopilot_finished" in kinds


def test_approve_at_create_binds_and_is_audited(owner_h):
    # autopilot up to sandbox-passed
    d = client.post("/api/ai/autopilot",
                    json={"goal": "draft client follow-ups", "department": "finance"},
                    headers=owner_h).json()
    assert d["sandbox"]["result_class"] == "passed"
    # approve activation NOW (same human action as the Verify step, in-session)
    act = client.post("/api/approvals/activation",
                      json={"artifact_id": d["artifact_id"], "job_id": d["job_id"],
                            "note": "approve-at-create"}, headers=owner_h)
    assert act.status_code == 200, act.text
    # bind with the full context in the same flow
    bind = client.post(f"/api/plan/{d['plan_id']}/create-workflow",
                       json=dict(CTX, connectors=["csv"], tools=["data", "notify"],
                                 trigger="schedule", sensitivity_note="PII",
                                 outcome="done same-day"), headers=owner_h)
    assert bind.status_code == 200, bind.text
    # evidence quality: approval recorded with plan sha + artifact sha + actor
    audit = client.get("/api/audit?limit=50", headers=owner_h).json()
    entry = next(e for e in audit["entries"] if e["kind"] == "artifact.activated"
                 and e["payload"].get("artifact_id") == d["artifact_id"])
    assert entry["payload"]["via"] == "approve_at_create"
    assert entry["payload"].get("plan_sha256") and entry["payload"].get("actor")


def test_operator_autopilot_cannot_bind_and_goes_through_cr(owner_h):
    op_h = _register("ap-operator-1")
    _promote(owner_h, "ap-operator-1", "operator")
    d = client.post("/api/ai/autopilot",
                    json={"goal": "draft client follow-ups"}, headers=op_h)
    assert d.status_code == 200, d.text
    d = d.json()
    # direct bind refused
    r = client.post(f"/api/plan/{d['plan_id']}/create-workflow", json=CTX, headers=op_h)
    assert r.status_code == 403
    # even with a passing sandbox, activation is an approver/admin act — the
    # operator opens a change request with the whole autopilot result instead
    cr = client.post("/api/change-requests", json={
        "kind": "workflow_create", "title": "Autopilot: client follow-ups",
        "summary": d["note"], "target_workflow_id": None,
        "payload": {"plan_id": d["plan_id"], "artifact_id": d["artifact_id"],
                    "job_id": d["job_id"], **d["context"]}}, headers=op_h)
    assert cr.status_code == 200, cr.text
    # operator cannot merge their own request
    assert client.post(f"/api/change-requests/{cr.json()['id']}/decide",
                       json={"approve": True}, headers=op_h).status_code == 403


def test_observer_cannot_run_autopilot(owner_h):
    obs_h = _register("ap-observer-1")
    _promote(owner_h, "ap-observer-1", "observer")
    r = client.post("/api/ai/autopilot", json={"goal": "anything"}, headers=obs_h)
    assert r.status_code == 403


def test_old_csv_followup_path_still_binds(owner_h):
    """Regression: the classic step-by-step CSV follow-up path is unchanged."""
    plan = client.post("/api/plans", json={"plan": PLAN}, headers=owner_h).json()
    art = client.post("/api/artifacts/generate",
                      json={"plan_id": plan["plan_id"], "approve_generation": True},
                      headers=owner_h).json()
    job = client.post("/api/test-jobs",
                      json={"artifact_id": art["artifact_id"], "fixture": "reset",
                            "consent": True}, headers=owner_h)
    assert job.status_code == 200 and job.json()["result_class"] == "passed"
    act = client.post("/api/approvals/activation",
                      json={"artifact_id": art["artifact_id"], "job_id": job.json()["job_id"]},
                      headers=owner_h)
    assert act.status_code == 200
    r = client.post(f"/api/plan/{plan['plan_id']}/create-workflow",
                    json={"org_type": "corporate", "size": "medium",
                          "department": "finance", "process_type": "client_followup"},
                    headers=owner_h)
    assert r.status_code == 200, r.text
    assert r.json()["workflow_id"].startswith("wf-")
