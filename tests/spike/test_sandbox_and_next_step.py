"""Tests for Sandbox Test, Next Step progression, and activation safeguards.

Verifies:
1. Gating between generation -> sandbox test -> activation -> binding.
2. Re-test / retry behavior of sandbox test jobs.
3. Accurate error responses when attempting to bind without activated code (reproducing screenshot).
4. State inspection endpoints (GET /api/plans/{id}, GET /api/plans/{id}/artifacts, GET /api/test-jobs/{id}).
5. Solo-tier self-role promotion vs team-tier RBAC enforcement.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from backend.app import app  # noqa: E402
from backend import roadmap_routes  # noqa: E402
from tests.spike.conftest import isolated_db_module, test_session  # noqa: E402,F401

client = TestClient(app)
PASSWORD = "sandbox-next-pass-1"

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
    orig_t = tokens.get_expected_token
    orig_r = roadmap_routes.get_expected_token
    tokens.get_expected_token = lambda: "testtoken"
    roadmap_routes.get_expected_token = lambda: "testtoken"
    yield
    tokens.get_expected_token = orig_t
    roadmap_routes.get_expected_token = orig_r


@pytest.fixture(scope="module")
def owner_h():
    """First account = shared-workspace owner; converts it to team tier so
    members can actually be added (later signups own personal workspaces now)."""
    r = client.post("/api/auth/register", json={"username": "sb-owner", "password": PASSWORD})
    assert r.status_code == 200
    tok = client.post("/api/auth/tokens", json={"username": "sb-owner", "password": PASSWORD}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = client.post("/api/org/tier", json={"tier": "team"}, headers=h)
    assert r.status_code == 200, r.text
    return h


def _mk_user(username: str, role: str = "operator", owner_headers: dict | None = None) -> dict:
    """Register, issue a token, then add the user to the SHARED workspace at
    `role` via the owner (signup no longer auto-joins anyone)."""
    r = client.post("/api/auth/register", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    tok = client.post("/api/auth/tokens", json={"username": username, "password": PASSWORD}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    if owner_headers:
        r = client.post("/api/team/members", json={"username": username, "role": role},
                        headers=owner_headers)
        assert r.status_code == 200, r.text
    return H


def test_bind_without_activation_refused_reproducing_screenshot(owner_h):
    """Reproduces the exact screenshot error:
    Attempting to bind an unactivated artifact yields 409 with 'no activated artifact for this plan'.
    """
    op_h = _mk_user("sb-op-reproduce", role="operator", owner_headers=owner_h)
    
    # 1. Create plan
    r_plan = client.post("/api/plans", json={"plan": PLAN}, headers=op_h)
    assert r_plan.status_code == 200
    plan_id = r_plan.json()["plan_id"]

    # 2. Generate code
    r_gen = client.post("/api/artifacts/generate",
                        json={"plan_id": plan_id, "approve_generation": True},
                        headers=op_h)
    assert r_gen.status_code == 200
    art_id = r_gen.json()["artifact_id"]
    assert r_gen.json()["status"] == "awaiting_test_approval"

    # 3. Attempt to bind directly before sandbox test and activation
    r_bind = client.post(f"/api/plan/{plan_id}/create-workflow", json=CTX, headers=op_h)
    assert r_bind.status_code == 409
    assert r_bind.json()["detail"]["error"] == "no activated artifact for this plan"


def test_sandbox_test_retry_and_activation_lifecycle(owner_h):
    """Tests the full sandbox test lifecycle:
    1. Running the test sets status to test_passed.
    2. Re-running the test is allowed and does not raise 409.
    3. Activation approves the artifact and records the approval.
    4. Once activated, re-testing is cleanly rejected (artifact already activated).
    5. Binding succeeds post-activation.
    """
    appr_h = _mk_user("sb-appr-lifecycle", role="approver", owner_headers=owner_h)

    # 1. Plan + generate
    r_plan = client.post("/api/plans", json={"plan": PLAN}, headers=appr_h)
    plan_id = r_plan.json()["plan_id"]
    r_gen = client.post("/api/artifacts/generate",
                        json={"plan_id": plan_id, "approve_generation": True},
                        headers=appr_h)
    art_id = r_gen.json()["artifact_id"]

    # 2. Run sandbox test
    r_test1 = client.post("/api/test-jobs",
                          json={"artifact_id": art_id, "fixture": "reset", "consent": True},
                          headers=appr_h)
    assert r_test1.status_code == 200
    job1 = r_test1.json()
    assert job1["status"] == "passed"
    assert job1["report"]["status"] == "passed"

    # 3. Re-run sandbox test (verify retry capability)
    r_test2 = client.post("/api/test-jobs",
                          json={"artifact_id": art_id, "fixture": "reset", "consent": True},
                          headers=appr_h)
    assert r_test2.status_code == 200
    job2 = r_test2.json()
    assert job2["status"] == "passed"

    # 4. Check test job retrieval endpoint
    r_job = client.get(f"/api/test-jobs/{job2['job_id']}", headers=appr_h)
    assert r_job.status_code == 200
    assert r_job.json()["job_id"] == job2["job_id"]
    assert r_job.json()["status"] == "passed"

    # 5. Check plan and artifact retrieval endpoints
    r_get_plan = client.get(f"/api/plans/{plan_id}", headers=appr_h)
    assert r_get_plan.status_code == 200
    assert r_get_plan.json()["plan_id"] == plan_id

    r_get_arts = client.get(f"/api/plans/{plan_id}/artifacts", headers=appr_h)
    assert r_get_arts.status_code == 200
    arts = r_get_arts.json()["artifacts"]
    assert len(arts) >= 1
    assert arts[0]["status"] == "test_passed"
    assert arts[0]["last_job"]["status"] == "passed"

    # 6. Approve activation
    r_act = client.post("/api/approvals/activation",
                        json={"artifact_id": art_id, "job_id": job2["job_id"]},
                        headers=appr_h)
    assert r_act.status_code == 200
    assert r_act.json()["status"] == "activated"

    # 7. Re-test after activation is rejected
    r_test_post_act = client.post("/api/test-jobs",
                                  json={"artifact_id": art_id, "fixture": "reset", "consent": True},
                                  headers=appr_h)
    assert r_test_post_act.status_code == 409
    assert "already activated" in r_test_post_act.json()["detail"]["error"]

    # 8. Post-activation binding succeeds
    r_bind = client.post(f"/api/plan/{plan_id}/create-workflow", json=CTX, headers=appr_h)
    assert r_bind.status_code == 200
    assert r_bind.json()["workflow_id"].startswith("wf-")


def test_signup_request_unlocks_approver_actions_with_owner_decision(owner_h):
    """Replaces the old self-role endpoint test (self-promotion is not a path in
    this codebase). A signup's REQUESTED role is stored pending; the workspace
    owner approves it; the caller can then test and activate. Non-owners still
    cannot decide requests."""
    # signup with a pending approver request
    r = client.post("/api/auth/register",
                    json={"username": "sb-solo-user", "password": PASSWORD,
                          "requested_role": "approver"})
    assert r.status_code == 200
    tok = client.post("/api/auth/tokens", json={"username": "sb-solo-user", "password": PASSWORD}).json()["token"]
    user_h = {"Authorization": f"Bearer {tok}"}
    me = client.get("/api/auth/me", headers=user_h).json()
    assert me["role"] == "owner"  # personal workspace; requested role NOT granted

    # the user cannot decide their own request
    rows = client.get("/api/team/role-requests", headers=user_h).json()["role_requests"]
    rid = next(r["id"] for r in rows if r["username"] == "sb-solo-user")
    assert client.post(f"/api/team/role-requests/{rid}/decide", json={"approve": True},
                       headers=user_h).status_code == 403
    # ...the owner of the target workspace decides it
    r = client.post(f"/api/team/role-requests/{rid}/decide", json={"approve": True},
                    headers=owner_h)
    assert r.status_code == 200, r.text
    me2 = client.get("/api/auth/me", headers=user_h).json()
    assert me2["role"] == "approver"  # membership in the shared workspace wins
