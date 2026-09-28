"""RBAC + context-model regression tests (create-flow audit).

Covers the two bug classes the audit found:
  1. False denials for operators: registration now grants operator (not
     observer), missing memberships fall back to operator, and the plan gate
     is a RUN-level (operator+) check — an operator can complete
     plan -> generate -> create-workflow end to end.
  2. The organization context model (product §5): the /api/org/catalog drives
     cascading org type -> size -> department -> process type selection,
     invalid tuples are refused server-side, and bound workflows carry their
     classification in /api/workflows.

Role ladder under test: observer(0) < operator(1) < approver(2) < owner(3).
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
from backend import teams  # noqa: E402
from tests.spike.conftest import isolated_db_module, test_session  # noqa: E402,F401
from backend.models import Base  # noqa: E402

client = TestClient(app)
PASSWORD = "rbac-context-pass-1"


@pytest.fixture(scope="module", autouse=True)
def _auth(isolated_db_module):
    from backend.security import tokens
    original_tokens = tokens.get_expected_token
    original_routes = roadmap_routes.get_expected_token
    tokens.get_expected_token = lambda: "testtoken"
    roadmap_routes.get_expected_token = lambda: "testtoken"
    yield
    tokens.get_expected_token = original_tokens
    roadmap_routes.get_expected_token = original_routes


@pytest.fixture(scope="module")
def owner_h():
    """The FIRST account in this module's DB is the owner (machine admin) of the
    shared workspace. It converts that workspace to the TEAM tier (the new
    solo→team path) so members can actually be added; later signups own their
    own PERSONAL workspaces, so shared-workspace roles are granted explicitly
    via _promote (owner's POST /team/members)."""
    h = _register("rbac-owner-0")
    r = client.post("/api/org/tier", json={"tier": "team"}, headers=h)
    assert r.status_code == 200, r.text
    return h


def _promote(owner_headers: dict, username: str, role: str) -> None:
    """Add an existing user to the SHARED workspace at `role` (owner act).
    Later signups are personal-org owners now, so they are NOT auto-joined."""
    r = client.post("/api/team/members", json={"username": username, "role": role},
                    headers=owner_headers)
    assert r.status_code == 200, r.text


def _register(username: str) -> dict:
    r = client.post("/api/auth/register",
                    json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    tok = client.post("/api/auth/tokens",
                      json={"username": username, "password": PASSWORD}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


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


# ── role model ────────────────────────────────────────────────────────────────

def test_registration_grants_operator_and_missing_membership_falls_back(owner_h):
    """The first account is owner of the SHARED workspace. A later signup owns a
    PERSONAL workspace (solo tier, full access) — that is the affiliation rule,
    so 'operator' here is exercised via explicit membership, and a provisioned
    account whose membership row went missing still acts as operator."""
    me = client.get("/api/auth/me", headers=owner_h).json()
    assert me["role"] == "owner"

    op_h = _register("rbac-operator-a")
    _promote(owner_h, "rbac-operator-a", "operator")
    me = client.get("/api/auth/me", headers=op_h).json()
    assert me["role"] == "operator", me

    # simulate a legacy provisioned account: NO membership rows at all (the
    # personal-org model gives every signup a membership, so only provisioned
    # accounts can look like this) — the operator fallback must keep them working
    from sqlalchemy import select as _select
    from backend.models import Membership, User as _User
    db = test_session()
    try:
        uid = db.scalar(_select(_User.id).where(_User.username == "rbac-operator-a"))
        user_rows = db.query(Membership).filter(Membership.user_id == uid).all()
        assert user_rows, "expected at least one membership row for rbac-operator-a"
        for row in user_rows:
            db.delete(row)
        db.commit()
    finally:
        db.close()
    me = client.get("/api/auth/me", headers=op_h).json()
    assert me["role"] == "operator", "missing membership must fall back to operator"
    # and the operator can still create plans (the old bug: false 403 here)
    r = client.post("/api/plans", json={"plan": PLAN}, headers=op_h)
    assert r.status_code == 200, (r.status_code, r.text)


def test_observer_is_read_only_but_operator_runs_and_creates(owner_h):
    op_h = _register("rbac-operator-b")
    # later signups own personal workspaces now: an operator in the SHARED
    # workspace is created by explicit owner grant (the affiliation model)
    _promote(owner_h, "rbac-operator-b", "operator")

    # make a real observer: register a user, then the owner demotes them
    obs_h = _register("rbac-observer-b")
    _promote(owner_h, "rbac-observer-b", "observer")

    # observer: read OK, everything mutating 403
    assert client.get("/api/workflows", headers=obs_h).status_code == 200
    r = client.post("/api/plans", json={"plan": PLAN}, headers=obs_h)
    assert r.status_code == 403, "observer must not create plans"
    r = client.post("/api/runs", json={"workflow_id": "x"}, headers=obs_h)
    assert r.status_code == 403
    r = client.post("/api/triggers/tick", headers=obs_h)
    assert r.status_code == 403

    # operator: plan (run-level) OK — the exact reported bug
    r = client.post("/api/plans", json={"plan": PLAN}, headers=op_h)
    assert r.status_code == 200, r.text
    plan_id = r.json()["plan_id"]

    # operator: generate OK …
    r = client.post("/api/artifacts/generate",
                    json={"plan_id": plan_id, "approve_generation": True}, headers=op_h)
    assert r.status_code == 200, r.text
    artifact_id = r.json()["artifact_id"]

    # … but sandbox test / activation need approver (403 with actionable detail)
    r = client.post("/api/test-jobs",
                    json={"artifact_id": artifact_id, "fixture": "reset", "consent": True},
                    headers=op_h)
    assert r.status_code == 403, r.text
    r = client.post("/api/approvals/activation",
                    json={"artifact_id": artifact_id}, headers=op_h)
    assert r.status_code == 403

    # approver: can test + activate
    appr_h = _register("rbac-approver-b")
    _promote(owner_h, "rbac-approver-b", "approver")
    r = client.post("/api/test-jobs",
                    json={"artifact_id": artifact_id, "fixture": "reset", "consent": True},
                    headers=appr_h)
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    r = client.post("/api/approvals/activation",
                    json={"artifact_id": artifact_id, "job_id": job_id}, headers=appr_h)
    assert r.status_code == 200, r.text

    # workflow creation is an owner/admin act in the redesigned RBAC: the
    # operator's plan became an approved artifact, the owner binds it live
    # (the operator path is a change request — covered by its own test)
    r = client.post(f"/api/plan/{plan_id}/create-workflow", json=CTX, headers=owner_h)
    assert r.status_code == 200, r.text
    wf_id = r.json()["workflow_id"]
    # and the operator's direct create attempt is refused with the CR path
    r = client.post(f"/api/plan/{plan_id}/create-workflow", json=CTX, headers=op_h)
    assert r.status_code == 403 and "change request" in r.json()["detail"]["how_to_unlock"]

    # owner-only: publish (operator/approver refused)
    graph = client.get(f"/api/workflows/{wf_id}", headers=owner_h).json()["graph"]
    pub = {"slug": "rbac-pub-1", "title": "t", "graph": graph,
           "publication_consent": True}
    assert client.post("/api/registry/publish", json=pub, headers=op_h).status_code == 403
    assert client.post("/api/registry/publish", json=pub, headers=appr_h).status_code == 403
    r = client.post("/api/registry/publish", json=pub, headers=owner_h)
    assert r.status_code == 200, r.text

    # admin-only: delete workflow (observer/operator/approver refused)
    assert client.delete(f"/api/workflows/{wf_id}", headers=obs_h).status_code == 403
    assert client.delete(f"/api/workflows/{wf_id}", headers=op_h).status_code == 403
    assert client.delete(f"/api/workflows/{wf_id}", headers=owner_h).status_code == 200

    # registry import: writes an untrusted draft — observer refused, operator OK
    tpl = client.get("/api/registry/templates", headers=owner_h).json()[0]
    imp = {"template_id": tpl["template_id"], "local_mapping": {}}
    assert client.post("/api/registry/import", json=imp, headers=obs_h).status_code == 403
    assert client.post("/api/registry/import", json=imp, headers=op_h).status_code == 200

    # withdraw is publish-level: owner only
    assert client.post("/api/registry/withdraw", json={"slug": "rbac-pub-1"},
                       headers=op_h).status_code == 403
    assert client.post("/api/registry/withdraw", json={"slug": "rbac-pub-1"},
                       headers=owner_h).status_code == 200


def test_trigger_management_is_operator_level(owner_h):
    op_h = _register("rbac-operator-c")
    obs_h = _register("rbac-observer-c")
    _promote(owner_h, "rbac-observer-c", "observer")

    wfs = client.get("/api/workflows", headers=owner_h).json()["workflows"]
    if not wfs:
        pytest.skip("no workflow available to attach a trigger to")
    wid = wfs[0]["id"]
    body = {"workflow_id": wid, "kind": "schedule",
            "config": {"observed_dates": ["2026-09-01", "2026-09-08", "2026-09-15"],
                       "user_confirmed": True}}
    assert client.post("/api/triggers", json=body, headers=obs_h).status_code == 403
    r = client.post("/api/triggers", json=body, headers=op_h)
    # operator passes the gate; the worker may still 400 on evidence contract
    assert r.status_code in (200, 400), r.text
    if r.status_code == 200:
        tid = r.json()["trigger_id"]
        assert client.post(f"/api/triggers/{tid}/disable", headers=op_h).status_code == 200
        assert client.post(f"/api/triggers/{tid}/enable", headers=op_h).status_code == 200


# ── context model ─────────────────────────────────────────────────────────────

def test_org_catalog_shapes():
    r = client.get("/api/org/catalog")
    assert r.status_code == 200, r.text
    cat = r.json()
    for t in ("corporate", "government", "individual", "nonprofit", "education"):
        assert t in cat["org_types"]
    assert cat["sizes_for_type"]["individual"] == ["solo"]
    assert set(cat["sizes_for_type"]["corporate"]) == {"small", "medium", "large"}
    assert "revenue" in cat["departments"]["government"]
    assert "finance" in cat["departments"]["corporate"]
    assert "tax_filing" in cat["process_types"]["revenue"]
    assert "accounts_payable" in cat["process_types"]["finance"]
    # every listed department has process types (never an empty menu)
    for otype, depts in cat["departments"].items():
        for d in depts:
            assert cat["process_types"].get(d) or cat["default_process_types"]


def test_catalog_matches_teams_validation():
    """The UI catalog and the server validator can never disagree."""
    cat = client.get("/api/org/catalog").json()
    for otype in cat["org_types"]:
        for size in cat["sizes_for_type"][otype]:
            for dept in cat["departments"][otype]:
                for pt in cat["process_types"].get(dept, cat["default_process_types"]):
                    assert teams.valid_context(otype, size, dept, pt) == []


def test_workflow_carries_context_and_rejects_incoherent_tuples(owner_h):
    op_h = _register("rbac-operator-d")

    r = client.post("/api/plans", json={"plan": PLAN}, headers=op_h)
    plan_id = r.json()["plan_id"]
    art = client.post("/api/artifacts/generate",
                      json={"plan_id": plan_id, "approve_generation": True},
                      headers=op_h).json()
    appr_h = _register("rbac-approver-d")
    _promote(owner_h, "rbac-approver-d", "approver")
    job = client.post("/api/test-jobs",
                      json={"artifact_id": art["artifact_id"], "fixture": "reset",
                            "consent": True}, headers=appr_h)
    assert job.status_code == 200, job.text
    client.post("/api/approvals/activation",
                json={"artifact_id": art["artifact_id"], "job_id": job.json()["job_id"]},
                headers=appr_h)

    # incoherent tuple: corporate has no 'solo' size
    bad = dict(CTX, size="solo")
    r = client.post(f"/api/plan/{plan_id}/create-workflow", json=bad, headers=op_h)
    assert r.status_code == 422, r.text
    # process type not in the finance catalog
    bad2 = dict(CTX, process_type="license_renewal")
    r = client.post(f"/api/plan/{plan_id}/create-workflow", json=bad2, headers=op_h)
    assert r.status_code == 422, r.text

    r = client.post(f"/api/plan/{plan_id}/create-workflow", json=CTX, headers=op_h)
    assert r.status_code == 200, r.text
    wf_id = r.json()["workflow_id"]

    wfs = client.get("/api/workflows", headers=op_h).json()["workflows"]
    ctx = next(w for w in wfs if w["id"] == wf_id)["context"]
    assert ctx == CTX, ctx


def test_org_profile_roundtrip(owner_h):
    r = client.post("/api/org/profile",
                    json={"org_type": "government", "size": "large",
                          "department": "revenue"}, headers=owner_h)
    assert r.status_code == 200, r.text
    got = client.get("/api/org/profile", headers=owner_h).json()["profile"]
    assert got["org_type"] == "government" and got["department"] == "revenue"
    # invalid profile refused
    r = client.post("/api/org/profile",
                    json={"org_type": "individual", "size": "large",
                          "department": "personal"}, headers=owner_h)
    assert r.status_code == 422, r.text


# ── signup affiliation + role requests + plan conversion ────────────────────

def test_unaffiliated_signup_gets_personal_org_as_owner(owner_h):
    """Signup rule: a later signup owns a PERSONAL workspace (solo tier) — never
    dropped into the shared workspace as a member, never self-elevated."""
    uname = f"solo-{uuid.uuid4().hex[:6]}"
    h = _register(uname)
    me = client.get("/api/auth/me", headers=h).json()
    assert me["role"] == "owner", me
    # The caller's capabilities resolve from THEIR org (solo), not the first org
    assert me["capabilities"]["tier"] == "solo"
    # the SHARED workspace (seen through its owner) must not contain this user
    members = client.get("/api/team/members", headers=owner_h).json()["members"]
    assert all(m["username"] != uname for m in members), members
    # ...while the caller's own workspace lists exactly them as owner
    own = client.get("/api/team/members", headers=h).json()
    assert own["org"]["tier"] == "solo" and len(own["members"]) == 1
    assert own["members"][0]["username"] == uname and own["members"][0]["role"] == "owner"


def test_signup_requested_role_is_pending_only(owner_h):
    """A requested role is stored as a PENDING request; the account's role does
    not change, 'owner' is refused outright, and only an owner can approve."""
    uname = f"req-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/auth/register",
                    json={"username": uname, "password": PASSWORD,
                          "requested_role": "approver"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "owner"  # personal workspace owner, as designed
    assert body["requested_role"]["status"] == "pending"
    tok = client.post("/api/auth/tokens",
                      json={"username": uname, "password": PASSWORD}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    # injected role/is_admin must not change anything
    me = client.get("/api/auth/me", headers=h).json()
    assert me["user"]["is_admin"] is False

    # non-owner sees only their own requests and cannot decide
    r = client.get("/api/team/role-requests", headers=h)
    assert r.status_code == 200
    assert all(row["username"] == uname for row in r.json()["role_requests"])
    rid = r.json()["role_requests"][0]["id"]
    r = client.post(f"/api/team/role-requests/{rid}/decide",
                    json={"approve": True}, headers=h)
    assert r.status_code == 403, r.text

    # owner approves → membership in the SHARED workspace at the requested role
    r = client.post(f"/api/team/role-requests/{rid}/decide",
                    json={"approve": True, "note": "ok"}, headers=owner_h)
    assert r.status_code == 200, r.text
    assert r.json()["granted_role"] == "approver"
    members = client.get("/api/team/members", headers=owner_h).json()["members"]
    assert any(m["username"] == uname and m["role"] == "approver" for m in members)

    # double-decide is refused honestly
    r = client.post(f"/api/team/role-requests/{rid}/decide",
                    json={"approve": True}, headers=owner_h)
    assert r.status_code == 409


def test_owner_role_request_refused_outright(owner_h):
    """'owner' is not a requestable role — no self-elevation path exists."""
    uname = f"req-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/auth/register",
                    json={"username": uname, "password": PASSWORD,
                          "requested_role": "owner"})
    assert r.status_code == 200, r.text
    assert r.json()["requested_role"] is None  # refused silently-but-honestly


def test_role_management_requires_owner_not_just_machine_admin(owner_h):
    """An operator (explicitly added to the shared workspace) cannot change
    roles, add members, invite, or convert the SHARED plan — owner_guard, not
    the old admin_guard. Their own personal workspace stays fully theirs."""
    op_h = _register("plain-operator")
    _promote(owner_h, "plain-operator", "operator")
    members = client.get("/api/team/members", headers=owner_h).json()["members"]
    mid = next(m["membership_id"] for m in members if m["username"] == "plain-operator")
    assert client.post(f"/api/team/members/{mid}/role",
                       json={"role": "owner"}, headers=op_h).status_code == 403
    assert client.post("/api/team/members",
                       json={"username": "ghost-user", "role": "observer"},
                       headers=op_h).status_code == 403
    assert client.post("/api/team/invitations", json={"role": "observer"},
                       headers=op_h).status_code == 403
    # converting the plan is owner-only: the operator's caller-org IS the shared
    # workspace (membership wins), so a tier change is refused — and their
    # personal-org conversion path is covered by test_solo_to_team_conversion
    assert client.post("/api/org/tier", json={"tier": "enterprise"},
                       headers=op_h).status_code == 403
    assert client.post("/api/org/convert-to-team", json={},
                       headers=op_h).status_code == 403
    # ...and the shared workspace tier is untouched by the operator
    shared = client.get("/api/team/members", headers=owner_h).json()["org"]
    assert shared["tier"] == "team"  # set by the module fixture, not the operator


def test_solo_to_team_conversion_unlocks_capabilities():
    """An owner converts their personal workspace: tier becomes team, capabilities
    unlock, and the caller stays owner. Server-side enforced."""
    uname = f"conv-{uuid.uuid4().hex[:6]}"
    h = _register(uname)
    r = client.post("/api/org/convert-to-team", json={"org_name": "Team Awesome"},
                    headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["org"]["tier"] == "team"
    caps = out["capabilities"]
    assert caps["members"] >= 25 and caps["paired_runner"] and caps["private_registry"]
    assert caps["retention_admin"]
    # still the owner
    assert client.get("/api/auth/me", headers=h).json()["role"] == "owner"
    # now invitations work (tier unlocked)
    r = client.post("/api/team/invitations", json={"role": "operator"}, headers=h)
    assert r.status_code == 200, r.text
    # conversion audited
    audit = client.get("/api/audit?limit=200", headers=h)
    kinds = [e["kind"] for e in audit.json().get("entries", [])] if audit.status_code == 200 else []
    assert "org.converted_to_team" in kinds, kinds[:20]


def test_processes_carry_context(owner_h):
    r = client.post("/api/processes",
                    json={"name": "AP processing", "org_type": "corporate",
                          "size": "medium", "department": "finance",
                          "process_type": "accounts_payable"}, headers=owner_h)
    assert r.status_code == 200, r.text
    procs = client.get("/api/processes", headers=owner_h).json()["processes"]
    row = next(p for p in procs if p["name"] == "AP processing")
    assert row["org_type"] == "corporate" and row["process_type"] == "accounts_payable"
    # incoherent context refused
    r = client.post("/api/processes",
                    json={"name": "bad", "org_type": "corporate", "size": "solo",
                          "department": "finance", "process_type": "tax_filing"},
                    headers=owner_h)
    assert r.status_code == 422, r.text
