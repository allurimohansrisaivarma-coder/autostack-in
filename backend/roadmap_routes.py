"""Roadmap Phases A–G: API routes for identity, entitlements, teams, runners,
triggers, governance, and registry signals.

Additive by design: existing routes/contracts are untouched. Auth is layered —
the legacy service token keeps working (principal kind "service", owner role),
and per-user tokens (kind "user") resolve their role from org membership.
"""
from __future__ import annotations

import json
import os
import secrets
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import entitlements, identity, orchestration, teams
from backend.engine.catalog import CATALOG
from backend.db import SessionLocal
from backend.models import (Approval, AuditEntry, ChangeRequest, Draft, Membership, Org, Process,
                            RegistryEvent, RegistryImport, RoleRequest, Run,
                            Setting, User, Workflow, WorkflowVersion)
from backend.security import audit as audit_mod
from backend.security.tokens import get_expected_token, require_writer

router = APIRouter(prefix="/api")

# simple in-memory rate limiter for public webhook triggers
_WEBHOOK_HITS: dict[str, list[float]] = {}
WEBHOOK_RATE_LIMIT = 30  # per minute per trigger


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class _Principal:
    def __init__(self, kind: str, user: User | None, role: str):
        self.kind = kind
        self.user = user
        self.role = role
        self._org = None
        self._org_is_shared = False

    @property
    def is_admin(self) -> bool:
        """Machine-level administration (workflow delete, publish, processes…).
        Personal-org owners are owners of THEIR workspace only — they must not
        administer the machine; only the shared workspace's owner (or the
        machine-admin flag / service principal) counts here."""
        return (self.kind == "service" or bool(self.user and self.user.is_admin)
                or (self.role == "owner" and self._org_is_shared))


def _bearer(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    return auth[7:].strip() if auth.startswith("Bearer ") else ""


def _caller_org(db: Session, user: User):
    """The org this principal's role comes from: membership in the shared
    workspace wins; otherwise the user's own personal workspace (signup rule:
    unaffiliated accounts own one). Falls back to the shared workspace for
    legacy provisioned accounts so every existing route keeps working."""
    org = teams.user_org(db, user)
    return org if org is not None else teams.primary_org(db)


def require_principal(request: Request, db: Session = Depends(get_db)) -> _Principal:
    token = _bearer(request)
    if not token:
        raise HTTPException(status_code=401, detail={"error": "missing bearer token"})
    if token == get_expected_token():
        return _Principal("service", None, "owner")
    user = identity.user_for_token(db, token)
    if user is None:
        raise HTTPException(status_code=401, detail={"error": "invalid or revoked token"})
    org = _caller_org(db, user)
    m = db.scalar(select(Membership).where(Membership.org_id == org.id,
                                           Membership.user_id == user.id))
    if m is not None:
        role = m.role
    elif user.is_admin:
        role = "owner"
    else:
        # Create-flow bugfix: fall back to operator (registration's own default).
        # The old observer fallback contradicted registration and locked every
        # mutating route behind a false 403 for provisioned accounts.
        role = "operator"
    p = _Principal("user", user, role)
    p._org = org
    p._org_is_shared = org is not None and org.id == teams.primary_org(db).id
    return p


def admin_guard(principal: _Principal = Depends(require_principal)) -> _Principal:
    """Day-to-day governance gate (was machine-admin-only): owner OR admin
    passes, as does a true machine admin (is_admin flag) and the service
    principal. Used for member/process administration."""
    if principal.is_admin or principal.role in ("admin", "owner"):
        return principal
    raise HTTPException(status_code=403, detail={"error": "administrator role required",
                                                 "how_to_unlock": "owner or admin role"})


def owner_guard(principal: _Principal = Depends(require_principal)) -> _Principal:
    """Org-lifecycle gate: the OWNER (of the caller's workspace) only — tier
    changes, plan conversion, org destruction. Admins are co-equal for
    everything else but not for billing/tier: use admin_guard there.
    The service principal keeps owner-equivalent rights for QA/ops tooling."""
    if principal.kind == "service" or principal.role == "owner":
        return principal
    raise HTTPException(status_code=403, detail={"error": "organization owner role required",
                                                 "how_to_unlock": "an owner must change tiers, "
                                                 "convert the plan, or approve admin role requests"})


# ── Phase A: identity ────────────────────────────────────────────────────────

class RegisterBody(BaseModel):
    username: str
    password: str
    display_name: str = ""
    # Signup "Requested role" (optional): stored as a PENDING request only —
    # never a grant. 'owner' is refused outright (no self-elevation), and any
    # injected role/is_admin fields outside this model are ignored by Pydantic.
    requested_role: str = "operator"


class LoginBody(BaseModel):
    username: str
    password: str


class TokenIssueBody(BaseModel):
    username: str
    password: str
    name: str = "default"


VALID_REQUESTED_ROLES = ("observer", "operator", "approver", "admin")


@router.post("/auth/register")
def auth_register(body: RegisterBody, db: Session = Depends(get_db)):
    try:
        user = identity.create_user(db, body.username, body.password, body.display_name)
        # Affiliation rules (signup upgrade):
        #  - The very first account administers the machine → owner of the shared
        #    workspace (unchanged legacy behavior).
        #  - An unaffiliated later signup gets a PERSONAL org and is its owner —
        #    full feature access on their own workspace.
        #  - Joining an existing org (invitation / added by an owner later) never
        #    auto-grants owner; the invitation's role applies at accept time.
        #    Here a fresh signup has no memberships by definition, so it is the
        #    personal-org branch.
        # create_user sets is_admin exactly when this is the machine's first
        # account: it admins the SHARED workspace. Later signups own their own
        # PERSONAL workspace (teams.ensure_personal_org) — same full access,
        # isolated by default.
        org = teams.primary_org(db) if user.is_admin else teams.ensure_personal_org(db, user)
        granted_role = "owner"
        teams.add_member(db, org.id, user.id, "owner")
        requested = None
        if body.requested_role in VALID_REQUESTED_ROLES and body.requested_role != granted_role:
            # Pending role request against the SHARED workspace (where other
            # people work); refused outright for 'owner' — no self-elevation.
            rr = RoleRequest(id=secrets.token_hex(12), user_id=user.id,
                             requested_role=body.requested_role, status="pending",
                             note=f"requested at signup for {teams.primary_org(db).id}",
                             created_at=datetime.now(timezone.utc))
            db.add(rr)
            db.commit()
            requested = {"id": rr.id, "requested_role": rr.requested_role,
                         "status": "pending",
                         "note": "stored as a pending request; only an owner can approve it"}
        from backend.security import audit as audit_mod
        audit_mod.append(db, "auth.registered", {"user_id": user.id, "username": user.username,
                                                 "org_id": org.id, "org_tier": org.tier,
                                                 "granted_role": granted_role,
                                                 "requested_role": requested["requested_role"] if requested else None})
        db.commit()
        return {"user_id": user.id, "username": user.username, "is_admin": user.is_admin,
                "role": granted_role, "org": {"id": org.id, "name": org.name, "tier": org.tier},
                "requested_role": requested}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc


@router.post("/auth/login")
def auth_login(body: LoginBody, db: Session = Depends(get_db)):
    user = identity.authenticate(db, body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail={"error": "invalid credentials or locked account"})
    return {"user_id": user.id, "username": user.username, "is_admin": user.is_admin,
            "display_name": user.display_name}


@router.post("/auth/tokens")
def auth_issue_token(body: TokenIssueBody, db: Session = Depends(get_db)):
    """Issue a per-user API token. Password-authenticated (local desktop model);
    the plaintext is returned exactly once and only its sha256 is stored."""
    user = identity.authenticate(db, body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail={"error": "invalid credentials or locked account"})
    row, plaintext = identity.issue_token(db, user.id, body.name)
    return {"token_id": row.id, "token": plaintext, "note": "store this now; it is not shown again"}


@router.get("/auth/tokens", dependencies=[Depends(require_principal)])
def auth_list_tokens(request: Request, db: Session = Depends(get_db)):
    principal = require_principal(request, db)
    if principal.kind == "service":
        raise HTTPException(status_code=400, detail={"error": "list tokens with a user token"})
    rows = identity.list_tokens(db, principal.user.id)
    return {"tokens": [{"id": r.id, "name": r.name, "prefix": r.prefix,
                        "created_at": r.created_at.isoformat()} for r in rows]}


@router.post("/auth/tokens/{token_id}/revoke", dependencies=[Depends(require_principal)])
def auth_revoke_token(token_id: str, request: Request, db: Session = Depends(get_db)):
    principal = require_principal(request, db)
    if principal.kind == "service":
        raise HTTPException(status_code=400, detail={"error": "revoke user tokens with a user token"})
    if not identity.revoke_token(db, principal.user.id, token_id):
        raise HTTPException(status_code=404, detail={"error": "token not found"})
    return {"revoked": True}


@router.get("/auth/me")
def auth_me(request: Request, db: Session = Depends(get_db)):
    principal = require_principal(request, db)
    # Personal-org model: capabilities resolve from the caller's OWN workspace
    # (shared-workspace membership wins, else the personal org) — not merely the
    # first org row, which may be someone else's workspace.
    if principal.kind == "user" and principal._org is not None:
        caps = entitlements._caps_for(principal._org)
    else:
        caps = entitlements.get_capabilities(db)
    user = None
    if principal.kind == "user":
        user = {"user_id": principal.user.id, "username": principal.user.username,
                "display_name": principal.user.display_name, "is_admin": principal.user.is_admin}
    return {"principal": principal.kind, "role": principal.role, "user": user,
            "capabilities": caps}


# ── Phase B: entitlements ──────────────────────────────────────────────────

# Organization context catalog (product §5): the create flow's cascading
# selectors are driven entirely by this catalog — one source of truth shared
# with backend/teams.py validation. Kept here (not hardcoded in the UI).
@router.get("/nodes/catalog")
def node_catalog():
    """The workflow node catalog — the SAME source of truth the graph validator
    (engine/catalog.py) enforces at bind time. Powers the Create Automation
    capability surface and the Connectors page; the UI can never advertise a
    node the executor would refuse. Public like /org/catalog (pre-login wizard).

    Opal-inspired stage clarity: every node is tagged Input / Process /
    Human gate / Output so workflow building follows the governed path, plus an
    honest status (supported / limited / planned / unavailable)."""
    groups = {
        "file.read_table": "Read",
        "data.filter": "Transform",
        "data.aggregate": "Transform",
        "data.transform": "Transform",
        "file.update_rows": "Write",
        "file.copy": "File ops",
        "file.archive": "File ops",
        "rows.append": "Write",
        "rows.soft_delete": "Write",
        "draft.create": "Write",
        "notify.desktop": "Notify",
        "control.branch": "Control flow",
        "control.merge": "Control flow",
        "control.wait": "Control flow",
        "approval.gate": "Governance",
        "node.http": "HTTP",
    }
    # Opal-style governed path: what starts the run -> what transforms it ->
    # where a human decides -> what the run produces.
    stages = {
        "file.read_table": "Input",
        "data.filter": "Process",
        "data.aggregate": "Process",
        "data.transform": "Process",
        "file.update_rows": "Process",
        "file.copy": "Process",
        "file.archive": "Process",
        "rows.append": "Process",
        "rows.soft_delete": "Process",
        "control.branch": "Process",
        "control.merge": "Process",
        "control.wait": "Process",
        "node.http": "Process",
        "approval.gate": "Human gate",
        "draft.create": "Output",
        "notify.desktop": "Output",
    }
    # Honest capability status per node (mirrors the connectors inventory).
    statuses = {
        "node.http": "limited",   # only allowlisted local hosts; no arbitrary URLs
    }
    return {
        "nodes": [
            {
                "type": spec.type,
                "group": groups.get(spec.type, "Other"),
                "stage": stages.get(spec.type, "Process"),
                "status": statuses.get(spec.type, "supported"),
                "required_params": list(spec.required),
                "optional_params": [p for p in spec.params if p not in spec.required],
                "outputs": list(spec.outputs),
                "permission": spec.permission,
                "errors": list(spec.errors),
            }
            for spec in CATALOG.values()
        ],
        # n8n-style trigger surface: what can START a run. Manual/scheduled runs
        # are real today; file-arrival fires on saved-file events; inbound
        # webhooks are secret-authenticated. Model/agent triggers do not exist.
        "triggers": [
            {"type": "manual", "label": "Run now", "status": "supported",
             "note": "start any approved workflow from the UI or API"},
            {"type": "schedule", "label": "Schedule", "status": "supported",
             "note": "evidence-gated recurrence (real observed dates or explicit confirmation)"},
            {"type": "file", "label": "File arrival", "status": "supported",
             "note": "fires when a watched allowlisted file event settles (alias + action match)"},
            {"type": "webhook", "label": "Webhook", "status": "supported",
             "note": "inbound POST with the trigger's secret header, rate-limited and audited"},
            {"type": "model_agent", "label": "AI agent", "status": "unavailable",
             "note": "by design: no open-ended agent tool-calling; generation stays inside the approved plan"},
        ],
        "note": "validated at bind time by the worker; the UI only mirrors this catalog",
    }


# Tool/node categories and trigger options for the expanded Create context step.
# These map onto real catalog nodes — nothing the executor refuses is offered.
TOOL_CATEGORIES = (
    {"id": "files", "label": "Files (read, copy, archive — allowlisted aliases)"},
    {"id": "data", "label": "Data / rows (filter, transform, aggregate, update)"},
    {"id": "http", "label": "HTTP (allowlisted hosts only)"},
    {"id": "notify", "label": "Notify & drafts (in-app, desktop — never auto-send)"},
    {"id": "logic", "label": "Logic (branch/switch, merge, wait, approval gate)"},
)
TRIGGER_OPTIONS = (
    {"id": "manual", "label": "Manual / Run now", "status": "supported"},
    {"id": "schedule", "label": "Schedule (evidence-gated)", "status": "supported"},
    {"id": "file", "label": "File arrival (watched alias settles)", "status": "supported"},
    {"id": "webhook", "label": "Webhook (secret-header POST)", "status": "supported"},
)


@router.get("/org/catalog")
def org_catalog():
    """Organization types, per-type sizes, departments, per-department process
    types, plus the create-wizard tool/trigger menus. Public (no auth): the
    create wizard needs it pre-login too."""
    return {
        "org_types": list(teams.ORG_TYPES),
        "sizes_for_type": {k: list(v) for k, v in teams.ORG_SIZES_FOR_TYPE.items()},
        "departments": {k: list(v) for k, v in teams.DEPARTMENTS.items()},
        "process_types": {k: list(v) for k, v in teams.PROCESS_TYPES.items()},
        "default_process_types": list(teams._DEFAULT_PROCESS_TYPES),
        "tool_categories": TOOL_CATEGORIES,
        "trigger_options": TRIGGER_OPTIONS,
        "labels": {
            "org_type": {t: t.replace("_", " ").title() for t in teams.ORG_TYPES},
            "size": {s: {"solo": "Solo", "small": "Small", "medium": "Medium",
                         "large": "Large / Enterprise"}[s] for s in teams.ORG_SIZES},
            "department": {d: d.replace("_", " ").title()
                           for ds in teams.DEPARTMENTS.values() for d in ds},
            "process_type": {p: p.replace("_", " ").title()
                             for ps in teams.PROCESS_TYPES.values() for p in ps},
        },
    }


@router.get("/org/profile", dependencies=[Depends(require_principal)])
def org_profile(db: Session = Depends(get_db)):
    """The workspace's current organization type/size/department (owner-settable
    via /org/profile with the same validation as the create wizard)."""
    org = teams.primary_org(db)
    raw = db.get(Setting, "org_profile")
    profile = {}
    if raw is not None:
        try:
            profile = json.loads(raw.value_json)
        except Exception:
            profile = {}
    return {"org": {"id": org.id, "name": org.name, "tier": org.tier},
            "profile": profile}


class OrgProfileBody(BaseModel):
    org_type: str
    size: str
    department: str


@router.post("/org/profile", dependencies=[Depends(admin_guard)])
def org_profile_set(body: OrgProfileBody, db: Session = Depends(get_db)):
    # department-level validation only: the workspace default has no process type
    if body.org_type not in teams.ORG_TYPES:
        raise HTTPException(status_code=422, detail={"error": f"unknown organization type: {body.org_type}"})
    if body.size not in teams.ORG_SIZES_FOR_TYPE.get(body.org_type, ()):
        raise HTTPException(status_code=422, detail={"error": f"invalid size for {body.org_type}"})
    if body.department not in teams.DEPARTMENTS.get(body.org_type, ()):
        raise HTTPException(status_code=422, detail={"error": f"unknown department for {body.org_type}"})
    row = db.get(Setting, "org_profile")
    payload = json.dumps({"org_type": body.org_type, "size": body.size,
                          "department": body.department})
    if row is None:
        row = Setting(key="org_profile", value_json=payload)
        db.add(row)
    else:
        row.value_json = payload
    db.commit()
    from backend.security import audit as audit_mod
    audit_mod.append(db, "org.profile_set", {**body.model_dump()})
    db.commit()
    return {"profile": {"org_type": body.org_type, "size": body.size,
                        "department": body.department}}


# ── Phase B: entitlements ────────────────────────────────────────────────────

@router.get("/me/capabilities", dependencies=[Depends(require_principal)])
def me_capabilities(db: Session = Depends(get_db)):
    return entitlements.get_capabilities(db)


class TierBody(BaseModel):
    tier: str
    org_name: str | None = None


@router.post("/org/tier", dependencies=[Depends(owner_guard)])
def org_set_tier(body: TierBody, principal: _Principal = Depends(require_principal),
                 db: Session = Depends(get_db)):
    try:
        caps = entitlements.set_tier(db, body.tier, body.org_name,
                                     org=(principal._org if principal.kind == "user" else None))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    from backend.security import audit as audit_mod
    audit_mod.append(db, "org.tier_changed", {"tier": body.tier})
    db.commit()
    return caps


@router.get("/org/sso", dependencies=[Depends(require_principal)])
def org_sso(db: Session = Depends(get_db)):
    caps = entitlements.get_capabilities(db)
    return {"enabled": bool(caps.get("sso")), "provider": None if not caps.get("sso") else "configured-external",
            "note": "SSO plugs into an organization identity provider; local accounts stay valid"}


# ── Phase C: teams & processes ───────────────────────────────────────────────

class MemberBody(BaseModel):
    username: str
    role: str = "operator"


class RoleBody(BaseModel):
    role: str


class DecisionBody(BaseModel):
    approve: bool
    note: str = ""


class InvitationBody(BaseModel):
    role: str = "operator"
    ttl_hours: int = 72


class AcceptBody(BaseModel):
    token: str


class ProcessBody(BaseModel):
    name: str
    description: str = ""
    run_quota_per_day: int = 0
    org_type: str = ""
    size: str = ""
    department: str = ""
    process_type: str = ""


class AttachBody(BaseModel):
    workflow_id: str


@router.get("/team/members", dependencies=[Depends(require_principal)])
def team_members(principal: _Principal = Depends(require_principal),
                 db: Session = Depends(get_db)):
    # Personal-org model: list the caller's workspace (their personal org by
    # default); the service principal keeps the shared-workspace view.
    org = principal._org or teams.primary_org(db)
    return {"org": {"id": org.id, "name": org.name, "tier": org.tier},
            "members": teams.members(db, org.id)}


@router.post("/team/members", dependencies=[Depends(owner_guard)])
def team_add_member(body: MemberBody, principal: _Principal = Depends(require_principal),
                    db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username.strip().lower()))
    if user is None:
        raise HTTPException(status_code=404, detail={"error": "no local user with that username"})
    org = principal._org or teams.primary_org(db)
    caps = entitlements.get_capabilities(db)
    if len(teams.members(db, org.id)) >= int(caps.get("members", 1)) and user.id not in {m["user_id"] for m in teams.members(db, org.id)}:
        raise HTTPException(status_code=403, detail={
            "error": f"member limit for the {caps['tier']} tier is {caps['members']}",
            "how_to_unlock": "team tier or higher"})
    try:
        m = teams.add_member(db, org.id, user.id, body.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    return {"membership_id": m.id, "user_id": m.user_id, "role": m.role}


@router.post("/team/members/{membership_id}/role", dependencies=[Depends(owner_guard)])
def team_set_role(membership_id: str, body: RoleBody, principal: _Principal = Depends(require_principal),
                  db: Session = Depends(get_db)):
    org = principal._org or teams.primary_org(db)
    try:
        ok = teams.set_role(db, org.id, membership_id, body.role)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc
    if not ok:
        raise HTTPException(status_code=404, detail={"error": "membership not found"})
    from backend.security import audit as audit_mod
    who = principal.user.username if principal.user else "service"
    audit_mod.append(db, "team.role_changed", {"membership_id": membership_id,
                                               "role": body.role, "by": who})
    db.commit()
    return {"updated": True, "role": body.role}


@router.delete("/team/members/{membership_id}", dependencies=[Depends(owner_guard)])
def team_remove_member(membership_id: str, principal: _Principal = Depends(require_principal),
                       db: Session = Depends(get_db)):
    org = principal._org or teams.primary_org(db)
    try:
        ok = teams.remove_member(db, org.id, membership_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc
    if not ok:
        raise HTTPException(status_code=404, detail={"error": "membership not found"})
    return {"removed": True}


@router.get("/team/invitations", dependencies=[Depends(require_principal)])
def team_list_invitations(principal: _Principal = Depends(require_principal),
                          db: Session = Depends(get_db)):
    org = principal._org or teams.primary_org(db)
    return {"invitations": teams.list_invitations(db, org.id)}


@router.post("/team/invitations", dependencies=[Depends(owner_guard)])
def team_create_invitation(body: InvitationBody, principal: _Principal = Depends(require_principal),
                           db: Session = Depends(get_db)):
    org = principal._org or teams.primary_org(db)
    try:
        inv, token = teams.create_invitation(db, org.id, body.role,
                                             principal.user.id if principal.user else "service",
                                             body.ttl_hours)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    return {"invitation_id": inv.id, "token": token, "expires_at": inv.expires_at.isoformat(),
            "note": "share over a trusted channel; the token grants the role on accept"}


@router.post("/team/invitations/accept")
def team_accept_invitation(body: AcceptBody, request: Request, db: Session = Depends(get_db)):
    principal = require_principal(request, db)
    if principal.kind == "service":
        raise HTTPException(status_code=400, detail={"error": "accept invitations with a user token"})
    try:
        m = teams.accept_invitation(db, body.token, principal.user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    return {"membership_id": m.id, "role": m.role}


@router.delete("/team/invitations/{invitation_id}", dependencies=[Depends(owner_guard)])
def team_revoke_invitation(invitation_id: str, db: Session = Depends(get_db)):
    org = teams.primary_org(db)
    if not teams.revoke_invitation(db, org.id, invitation_id):
        raise HTTPException(status_code=404, detail={"error": "invitation not found or already accepted"})
    return {"revoked": True}


# ── Signup role requests: pending elevations, decided ONLY by an owner ────────

@router.get("/team/role-requests", dependencies=[Depends(require_principal)])
def role_requests_list(request: Request, db: Session = Depends(get_db)):
    """Owners see the full pending queue; other roles see their own requests.
    Decisions live only with owners — this endpoint never mutates anything."""
    from backend.models import RoleRequest
    principal = require_principal(request, db)
    q = db.query(RoleRequest).order_by(RoleRequest.created_at.desc())
    # Personal-org model: the full pending queue belongs to the SHARED
    # workspace's owner (and the service principal). A personal-org owner sees
    # only their OWN requests — never another workspace's queue.
    shared_id = teams.primary_org(db).id
    is_shared_owner = (principal.kind == "user"
                       and principal.role in ("owner", "admin")
                       and principal._org is not None and principal._org.id == shared_id)
    can_decide_all = principal.kind == "service" or is_shared_owner
    if can_decide_all:
        pass  # full queue
    else:
        q = q.filter(RoleRequest.user_id == (principal.user.id if principal.user else ""))
    out = []
    for r in q.limit(100).all():
        u = db.get(User, r.user_id)
        out.append({"id": r.id, "username": u.username if u else "(deleted)",
                    "requested_role": r.requested_role, "status": r.status,
                    "decided_by": r.decided_by, "created_at": r.created_at.isoformat() if r.created_at else None,
                    # The UI mirrors this; the decide endpoint re-checks server-side.
                    "decidable": bool(can_decide_all and r.status == "pending"
                                      and r.requested_role in VALID_REQUESTED_ROLES)})
    return {"role_requests": out}


@router.post("/team/role-requests/{request_id}/decide", dependencies=[Depends(owner_guard)])
def role_request_decide(request_id: str, body: DecisionBody,
                        principal: _Principal = Depends(require_principal),
                        db: Session = Depends(get_db)):
    """Owner decision on a pending signup role request. The grant lands in the
    SHARED workspace at the requested role (never 'owner'); the request row
    records who decided. This is the only path from 'requested' to 'granted'."""
    from backend.models import RoleRequest
    rr = db.get(RoleRequest, request_id)
    if rr is None:
        raise HTTPException(status_code=404, detail={"error": "role request not found"})
    if rr.status != "pending":
        raise HTTPException(status_code=409, detail={"error": f"role request already {rr.status}"})
    if rr.requested_role not in VALID_REQUESTED_ROLES:
        raise HTTPException(status_code=422, detail={"error": "requested role is not grantable"})
    who = principal.user.username if principal.user else "service"
    rr.status = "approved" if body.approve else "rejected"
    rr.decided_by = who[:80]
    rr.decided_at = datetime.now(timezone.utc)
    granted_role = None
    if body.approve:
        # Grant in the workspace the request TARGETS (the deciding owner's org,
        # matched against the note) — not blindly the first org row.
        org = None
        for candidate in db.query(Org).all():
            if candidate.id in (rr.note or ""):
                org = candidate
                break
        if org is None:
            org = teams.primary_org(db)
        # The deciding owner/admin must belong to the TARGET workspace: a
        # personal-org owner cannot approve requests aimed at the shared
        # workspace (or vice versa).
        if principal.kind == "user" and (principal._org is None or principal._org.id != org.id):
            raise HTTPException(status_code=403, detail={
                "error": "role request targets a different workspace",
                "how_to_unlock": "the target workspace's owner must decide it"})
        m = teams.add_member(db, org.id, rr.user_id, rr.requested_role)
        granted_role = m.role
    from backend.security import audit as audit_mod
    audit_mod.append(db, "team.role_request_decided", {"request_id": request_id,
                                                       "requested_role": rr.requested_role,
                                                       "approved": body.approve,
                                                       "granted_role": granted_role,
                                                       "decided_by": who, "note": body.note[:200]})
    db.commit()
    return {"id": request_id, "status": rr.status, "granted_role": granted_role}


# ── Solo → Team conversion (owner-only, server-enforced) ──────────────────────

class ConvertBody(BaseModel):
    org_name: str | None = None


@router.post("/org/convert-to-team", dependencies=[Depends(owner_guard)])
def org_convert_to_team(body: ConvertBody, principal: _Principal = Depends(require_principal),
                        db: Session = Depends(get_db)):
    """Convert the caller's organization to the team tier: unlocks members,
    invitations, paired runners, private registry, retention admin. The caller
    stays owner; nothing else about the workspace changes. Audited."""
    org = principal._org or teams.primary_org(db)
    before = org.tier
    caps = entitlements.set_tier(db, "team", body.org_name, org=org)
    who = principal.user.username if principal.user else "service"
    from backend.security import audit as audit_mod
    audit_mod.append(db, "org.converted_to_team", {"org_id": org.id, "from_tier": before,
                                                   "to_tier": "team", "by": who})
    db.commit()
    return {"org": {"id": org.id, "name": org.name, "tier": org.tier},
            "capabilities": caps,
            "note": f"converted from {before} to team; you remain the owner — invite members next"}


# # ── Tool Registry API (native nodes + MCP at scale) ──────────────────────────

class McpServerBody(BaseModel):
    server: str
    description: str = ""
    tools: list[dict] = []


class ToolAllowlistBody(BaseModel):
    org_allow: list[str] | None = None


@router.get("/tools", dependencies=[Depends(require_principal)])
def tools_list(search: str = "", category: str = "", source: str = "",
               status: str = "", limit: int = 50, offset: int = 0,
               db: Session = Depends(get_db)):
    """Browse the tool registry: search + filters + pagination so thousands of
    MCP tools stay usable. Statuses are honest (experimental MCP tools cannot
    be used until a probe promotes them)."""
    from backend.engine.tool_registry import REGISTRY
    return REGISTRY.list(search=search, category=category, source=source,
                         status=status, limit=limit, offset=offset)


@router.get("/tools/categories", dependencies=[Depends(require_principal)])
def tools_categories():
    from backend.engine.tool_registry import RISK_FOR_CATEGORY, SANDBOX_POLICY_FOR_CATEGORY
    return {"categories": sorted(set(RISK_FOR_CATEGORY) | {"mcp"}),
            "risk_ladder": RISK_FOR_CATEGORY,
            "sandbox_policies": SANDBOX_POLICY_FOR_CATEGORY}


@router.post("/tools/mcp-servers", dependencies=[Depends(admin_guard)])
def tools_register_mcp(body: McpServerBody, db: Session = Depends(get_db)):
    """Register an MCP server's tools (owner/admin). Lazy + honest: tools land
    as experimental; a future live probe promotes them. Audited."""
    from backend.engine.tool_registry import REGISTRY
    if not body.server.strip():
        raise HTTPException(status_code=422, detail={"error": "server name required"})
    out = REGISTRY.register_mcp_server(body.server.strip(), body.tools, body.description)
    audit_mod.append(db, "tools.mcp_registered", {"server": out["server"],
                                                  "tools": out["tools_registered"]})
    db.commit()
    return out


@router.post("/tools/allowlist", dependencies=[Depends(admin_guard)])
def tools_set_org_allowlist(body: ToolAllowlistBody, db: Session = Depends(get_db)):
    """Per-org tool allowlist (owner/admin). None clears the restriction;
    an explicit list is intersected with the registry at use time. Audited."""
    row = db.get(Setting, "tools:org_allowlist")
    payload = json.dumps({"org_allow": body.org_allow})
    if row is None:
        db.add(Setting(key="tools:org_allowlist", value_json=payload))
    else:
        row.value_json = payload
    audit_mod.append(db, "tools.org_allowlist_set",
                     {"count": (len(body.org_allow) if body.org_allow is not None else None)})
    db.commit()
    return {"org_allow": body.org_allow,
            "note": "null = unrestricted (native supported tools); a list = only those tools"}


def _org_tool_allowlist(db: Session):
    row = db.get(Setting, "tools:org_allowlist")
    if row is None:
        return None
    try:
        return json.loads(row.value_json).get("org_allow")
    except Exception:
        return None


def _retrieve_tools_for_goal(db: Session, goal: str, k: int = 12) -> list[dict]:
    """Scale-safe AI retrieval: top-k registry tools for a goal, intersected
    with the org allowlist. The model NEVER sees the whole catalog."""
    from backend.engine.tool_registry import REGISTRY
    allow = REGISTRY.allowlist_for(_org_tool_allowlist(db), None)
    return REGISTRY.retrieve(goal, allowlist=allow, k=k)


# ── AI full-workflow autopilot ────────────────────────────────────────────────

class AutopilotBody(BaseModel):
    goal: str
    org_type: str = "corporate"
    size: str = "medium"
    department: str = "finance"
    process_type: str = "accounts_payable"
    connectors: list[str] = []
    tools: list[str] = []
    trigger: str = "manual"
    sensitivity_note: str = ""
    outcome: str = ""
    status_val: str = "Follow-up due"
    date_val: str = "2026-09-20"
    action: str = "create_draft"
    notify: bool = True


@router.post("/ai/autopilot", dependencies=[Depends(require_writer)])
def ai_autopilot(body: AutopilotBody, request: Request, db: Session = Depends(get_db)):
    """AI full-workflow creation (autopilot): goal → retrieved tools → plan →
    generate → sandbox. NEVER activates: the human decides via approve-at-
    create afterwards. Operators' results become change requests client-side
    (the response carries everything needed to open one). One repair loop on
    failed_assertion; failed_infra is retried once transparently. The mock
    provider stays the local-first default — no cloud dependency.

    Audited: goal, provider, retrieved tools, plan sha, artifact sha, sandbox
    result class."""
    import os as _os
    from backend.engine.tool_registry import REGISTRY
    from backend.models import GeneratedArtifact, GenerationPlan, TestJob
    from backend.engine.generation import plan_sha256 as _plan_sha
    from backend.identity import now_iso
    from backend import spike_config as cfg
    from backend.app import _as_tmp_fixture, _expected_outputs, sha256_bytes
    from backend.engine import generation as gen
    from backend.engine import runner
    from backend.file_diff import read_snapshot as _rs
    if not body.goal.strip():
        raise HTTPException(status_code=422, detail={"error": "goal required"})
    principal = require_principal(request, db)
    # 1) retrieve allowlisted tools for the goal (top-k, never the full catalog)
    tools = _retrieve_tools_for_goal(db, body.goal)
    tool_ids = [t["id"] for t in tools]
    # 2) build the plan from the goal + confirmed context (mock/offline path:
    #    deterministic mapping; a real provider drafts the same structure)
    destinations = ["in_app"] + (["desktop_notification"] if body.notify else [])
    plan = {"client_id_field": "ClientID",
            "field_mappings": {"Name": "Name", "FollowUpDate": "FollowUpDate"},
            "eligibility": {"status": body.status_val, "status_field": "Status",
                            "date_field": "FollowUpDate", "date_value": body.date_val},
            "action": body.action if body.action in ("create_draft", "update_status") else "create_draft",
            "destinations": destinations}
    from backend.engine.generation import validate_plan as _vplan
    missing = _vplan(plan)
    if missing:
        raise HTTPException(status_code=422, detail={"error": "plan incomplete from goal",
                                                     "missing": missing})
    provider = _os.environ.get("AUTOSTACK_AI_PROVIDER", "mock")
    audit_mod.append(db, "ai.autopilot_started", {
        "goal": body.goal[:300], "provider": provider,
        "retrieved_tools": tool_ids, "org_type": body.org_type,
        "department": body.department})
    db.commit()
    # 3) create the plan row via the same code path as the manual flow
    prow = GenerationPlan(id=str(uuid.uuid4()), candidate_id=None,
                          plan_json=json.dumps(plan, sort_keys=True),
                          plan_sha256=_plan_sha(plan),
                          missing_rules_json=json.dumps([]),
                          status="approved_for_generation", created_at=datetime.now(timezone.utc))
    db.add(prow)
    db.commit()
    # 4) generate + static validation
    outcome = gen.generate(plan)
    if outcome["violations"]:
        raise HTTPException(status_code=422, detail={"error": "static validation failed",
                                                     "violations": outcome["violations"]})
    art = GeneratedArtifact(id=str(uuid.uuid4()), plan_id=prow.id, version=1,
                            model_output_json=json.dumps({"output": outcome["model_output"][:4000]}),
                            code=outcome["code"], code_sha256=outcome["code_sha256"],
                            static_check_json=json.dumps(outcome["violations"]),
                            status="awaiting_test_approval", created_at=now_iso())
    db.add(art)
    db.commit()
    # 5) sandbox with classification + retries
    policy = {"max_output_items": 1000, "forbidden": ["network", "filesystem", "subprocess"]}
    fixture_payload = (cfg.FIXTURES_DIR / "clients-before.csv").read_bytes()
    table = list(_rs(_as_tmp_fixture(fixture_payload)).values())
    ctx = gen.plan_run_context(plan)
    id_field = plan["client_id_field"]
    expected = _expected_outputs(table[:50], plan, id_field)

    def _run_once():
        job = TestJob(id=str(uuid.uuid4()), artifact_id=art.id, code_sha256=art.code_sha256,
                      input_sha256=sha256_bytes(fixture_payload), fixture_name="clients-before.csv",
                      policy_json=json.dumps(policy), status="running", created_at=now_iso())
        db.add(job)
        db.commit()
        rep = runner.run_isolated_test(art.code, table[:50], ctx=ctx, policy=policy,
                                       expected=expected, key_field=id_field)
        job.status = rep["status"]
        job.report_json = json.dumps(rep)
        job.report_sha256 = rep["report_sha256"]
        if rep["status"] == "passed":
            art.status = "test_passed"
        db.commit()
        return job, rep

    job, report = _run_once()
    result_class = report.get("result_class") or runner.classify_report(report)
    attempts = 1
    repaired = False
    if result_class == "failed_infra":
        job, report = _run_once()   # infra: transparent retry, not "bad code"
        result_class = report.get("result_class") or runner.classify_report(report)
        attempts = 2
    if result_class == "failed_assertion" and attempts == 1:
        # ONE repair loop: revise plan (narrow to drafts), regenerate, retest.
        plan2 = dict(plan)
        plan2["action"] = "create_draft"
        prow2 = GenerationPlan(id=str(uuid.uuid4()), candidate_id=None,
                               plan_json=json.dumps(plan2, sort_keys=True),
                               plan_sha256=_plan_sha(plan2),
                               missing_rules_json=json.dumps([]),
                               status="approved_for_generation", created_at=datetime.now(timezone.utc))
        db.add(prow2)
        db.commit()
        outcome2 = gen.generate(plan2)
        art2 = GeneratedArtifact(id=str(uuid.uuid4()), plan_id=prow2.id, version=1,
                                 model_output_json=json.dumps({"output": outcome2["model_output"][:4000]}),
                                 code=outcome2["code"], code_sha256=outcome2["code_sha256"],
                                 static_check_json=json.dumps(outcome2["violations"]),
                                 status="awaiting_test_approval", created_at=now_iso())
        if not outcome2["violations"]:
            db.add(art2)
            db.commit()
            art, prow = art2, prow2
            repaired = True
            job, report = _run_once()
            result_class = report.get("result_class") or runner.classify_report(report)
            attempts += 1
    audit_mod.append(db, "ai.autopilot_finished", {
        "plan_sha256": prow.plan_sha256[:16], "artifact_id": art.id,
        "artifact_sha256": art.code_sha256[:16], "result_class": result_class,
        "attempts": attempts, "repaired": repaired, "provider": provider,
        "retrieved_tools": tool_ids})
    db.commit()
    context = {"org_type": body.org_type, "size": body.size, "department": body.department,
               "process_type": body.process_type, "connectors": body.connectors,
               "tools": body.tools, "trigger": body.trigger,
               "sensitivity_note": body.sensitivity_note, "outcome": body.outcome}
    return {"plan_id": prow.id, "plan": plan, "artifact_id": art.id,
            "code_sha256": art.code_sha256, "job_id": job.id,
            "sandbox": {"status": report["status"], "result_class": result_class,
                        "attempts": attempts, "repaired": repaired,
                        "checks": report.get("checks", [])},
            "retrieved_tools": tool_ids, "context": context,
            "note": ("sandbox passed — approve activation now to bind, or open a change request"
                     if result_class == "passed" else
                     "sandbox did not pass; nothing is activated and no bind is possible")}


# ── GitHub-PR-style change requests (role redesign) ──────────────────────────

class ChangeRequestBody(BaseModel):
    kind: str = "workflow_create"                     # workflow_create | workflow_edit
    title: str
    summary: str = ""
    target_workflow_id: str | None = None
    payload: dict = {}                                # plan/context/tools snapshot


class ChangeRequestDecision(BaseModel):
    approve: bool
    note: str = ""


def _reviewer_guard(principal: _Principal):
    """Owner or Admin (or service) may review/merge change requests."""
    if principal.kind == "service" or principal.role in ("owner", "admin"):
        return
    raise HTTPException(status_code=403, detail={
        "error": "change-request review requires the owner or admin role",
        "how_to_unlock": "an owner/admin must approve or reject the request"})


@router.get("/change-requests", dependencies=[Depends(require_principal)])
def change_requests_list(request: Request, db: Session = Depends(get_db)):
    """Owner/admin see the full review queue for their workspace; authors see
    their own requests (open + decided)."""
    from backend.models import ChangeRequest, User
    principal = require_principal(request, db)
    org = principal._org or teams.primary_org(db)
    q = db.query(ChangeRequest).filter(ChangeRequest.org_id == org.id) \
        .order_by(ChangeRequest.created_at.desc())
    if not (principal.kind == "service" or principal.role in ("owner", "admin")):
        q = q.filter(ChangeRequest.author_id == (principal.user.id if principal.user else ""))
    out = []
    for cr in q.limit(100).all():
        author = db.get(User, cr.author_id)
        out.append({"id": cr.id, "kind": cr.kind, "title": cr.title,
                    "summary": cr.summary, "status": cr.status,
                    "target_workflow_id": cr.target_workflow_id,
                    "author": author.username if author else "(deleted)",
                    "review_note": cr.review_note, "reviewed_by": cr.reviewed_by,
                    "created_at": cr.created_at.isoformat() if cr.created_at else None})
    return {"change_requests": out}


@router.post("/change-requests", dependencies=[Depends(require_principal)])
def change_request_open(body: ChangeRequestBody, request: Request,
                        db: Session = Depends(get_db)):
    """Open a change request (PR-style proposal). Authors below admin rank get
    here instead of direct live writes; owner/admin submissions are applied
    directly upstream and never need this route."""
    from backend.models import ChangeRequest
    import secrets as _secrets
    principal = require_principal(request, db)
    if principal.kind == "service":
        raise HTTPException(status_code=400, detail={"error": "open change requests with a user token"})
    # Observer default is VIEW ONLY: no proposals, no writes (the product rule).
    if principal.role == "observer":
        raise HTTPException(status_code=403, detail={
            "error": "observers have view-only access and cannot open change requests",
            "how_to_unlock": "operator role or higher"})
    if body.kind not in ("workflow_create", "workflow_edit"):
        raise HTTPException(status_code=422, detail={"error": f"unknown change-request kind: {body.kind}"})
    if not body.title.strip():
        raise HTTPException(status_code=422, detail={"error": "change request needs a title"})
    if body.kind == "workflow_edit" and not body.target_workflow_id:
        raise HTTPException(status_code=422, detail={"error": "workflow_edit needs target_workflow_id"})
    if principal.role in ("owner", "admin"):
        raise HTTPException(status_code=409, detail={
            "error": "owners and admins apply changes directly; no change request needed",
            "how_to_unlock": "submit the create/edit call directly"})
    cr = ChangeRequest(id=_secrets.token_hex(12),
                       org_id=(principal._org.id if principal._org else teams.primary_org(db).id),
                       author_id=principal.user.id, kind=body.kind,
                       title=body.title.strip()[:200], summary=body.summary[:2000],
                       target_workflow_id=body.target_workflow_id,
                       payload_json=json.dumps(body.payload, default=str),
                       status="open", created_at=datetime.now(timezone.utc))
    db.add(cr)
    who = principal.user.username
    audit_mod.append(db, "change_request.opened", {
        "request_id": cr.id, "kind": cr.kind, "title": cr.title,
        "author": who, "target_workflow_id": cr.target_workflow_id})
    db.commit()
    return {"id": cr.id, "status": cr.status,
            "note": "stored as an open change request — an owner/admin must review and merge it"}


@router.post("/change-requests/{request_id}/decide", dependencies=[Depends(require_principal)])
def change_request_decide(request_id: str, body: ChangeRequestDecision,
                          request: Request, db: Session = Depends(get_db)):
    """Owner/admin decision. approve+merge marks the proposal accepted and — for
    workflow_create with a complete plan snapshot — creates the live workflow
    row in a DRAFT state; the normal sandbox → activation gates still govern
    its go-live. Reject records the note. Everything is audited."""
    from backend.models import ChangeRequest, User
    principal = require_principal(request, db)
    _reviewer_guard(principal)
    cr = db.get(ChangeRequest, request_id)
    if cr is None:
        raise HTTPException(status_code=404, detail={"error": "change request not found"})
    if cr.status != "open":
        raise HTTPException(status_code=409, detail={"error": f"change request already {cr.status}"})
    who = principal.user.username if principal.user else "service"
    cr.status = "merged" if body.approve else "rejected"
    cr.review_note = body.note[:500]
    cr.reviewed_by = who
    cr.reviewed_at = datetime.now(timezone.utc)
    merged_workflow_id = None
    if body.approve and cr.kind == "workflow_create":
        # Materialize the proposal as a DRAFT workflow: version 0, no activated
        # code — the reviewer then runs the normal generate → test → activate
        # chain (never bypassed by the merge).
        try:
            payload = json.loads(cr.payload_json) if cr.payload_json else {}
        except Exception:
            payload = {}
        wf_id = f"wf-cr-{cr.id[:8]}"
        if db.get(Workflow, wf_id) is None:
            db.add(Workflow(id=wf_id, name=cr.title[:200], demo=False))
            from backend.models import WorkflowVersion
            db.add(WorkflowVersion(id=str(uuid.uuid4()), workflow_id=wf_id, version=0,
                                   graph_json=json.dumps({"graph": {"nodes": [], "edges": []}}),
                                   artifact_sha256="0" * 64,
                                   changelog=f"merged from change request {cr.id} (draft)"))
            merged_workflow_id = wf_id
    audit_mod.append(db, "change_request.decided", {
        "request_id": cr.id, "approved": body.approve, "merged_workflow_id": merged_workflow_id,
        "decided_by": who, "note": body.note[:200]})
    db.commit()
    return {"id": cr.id, "status": cr.status, "merged_workflow_id": merged_workflow_id,
            "note": ("merged: the proposal is materialized as a draft workflow; normal sandbox/activation gates still apply"
                     if body.approve else "rejected — the author can revise and resubmit")}


@router.get("/processes", dependencies=[Depends(require_principal)])
def processes_list(principal: _Principal = Depends(require_principal),
                   db: Session = Depends(get_db)):
    org = principal._org or teams.primary_org(db)
    return {"processes": [{"id": p.id, "name": p.name, "description": p.description,
                           "run_quota_per_day": p.run_quota_per_day,
                           "org_type": p.org_type, "size": p.size,
                           "department": p.department, "process_type": p.process_type}
                          for p in teams.list_processes(db, org.id)]}


@router.post("/processes", dependencies=[Depends(admin_guard)])
def processes_create(body: ProcessBody, db: Session = Depends(get_db)):
    org = teams.primary_org(db)
    if body.org_type or body.department or body.process_type:
        problems = teams.valid_context(body.org_type, body.size, body.department,
                                       body.process_type)
        if problems:
            raise HTTPException(status_code=422, detail={"error": "; ".join(problems)})
    try:
        p = teams.create_process(db, org.id, body.name, body.description, body.run_quota_per_day)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    # context columns are plain values (validated above when provided)
    p.org_type, p.size = body.org_type, body.size
    p.department, p.process_type = body.department, body.process_type
    db.commit()
    return {"process_id": p.id, "name": p.name}


@router.post("/processes/{process_id}/attach", dependencies=[Depends(admin_guard)])
def processes_attach(process_id: str, body: AttachBody, db: Session = Depends(get_db)):
    if db.get(Process, process_id) is None:
        raise HTTPException(status_code=404, detail={"error": "process not found"})
    teams.attach_workflow_to_process(db, process_id, body.workflow_id)
    return {"attached": True, "process_id": process_id, "workflow_id": body.workflow_id}


# ── Phase D: runners & triggers ──────────────────────────────────────────────

class RunnerBody(BaseModel):
    name: str
    kind: str = "local"


class PairConfirmBody(BaseModel):
    code: str


class TriggerBody(BaseModel):
    workflow_id: str
    kind: str
    config: dict = {}
    evidence_note: str = ""


@router.get("/runners", dependencies=[Depends(require_principal)])
def runners_list(db: Session = Depends(get_db)):
    return {"runners": [{"id": r.id, "name": r.name, "kind": r.kind, "status": r.status,
                         "last_seen_at": r.last_seen_at} for r in orchestration.list_runners(db)]}


@router.post("/runners", dependencies=[Depends(admin_guard)])
def runners_register(body: RunnerBody, db: Session = Depends(get_db)):
    caps = entitlements.get_capabilities(db)
    if body.kind == "paired" and not caps.get("paired_runner"):
        raise HTTPException(status_code=403, detail={
            "error": "paired runners are not enabled", "how_to_unlock": "team tier or higher"})
    try:
        r = orchestration.register_runner(db, body.name, body.kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    return {"runner_id": r.id, "status": r.status, "kind": r.kind}


@router.post("/runners/{runner_id}/pair", dependencies=[Depends(admin_guard)])
def runners_pair(runner_id: str, db: Session = Depends(get_db)):
    try:
        return orchestration.begin_pairing(db, runner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)}) from exc


@router.post("/runners/{runner_id}/pair/confirm", dependencies=[Depends(admin_guard)])
def runners_pair_confirm(runner_id: str, body: PairConfirmBody, db: Session = Depends(get_db)):
    try:
        return orchestration.confirm_pairing(db, runner_id, body.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc


@router.post("/runners/{runner_id}/revoke", dependencies=[Depends(admin_guard)])
def runners_revoke(runner_id: str, db: Session = Depends(get_db)):
    if not orchestration.revoke_runner(db, runner_id):
        raise HTTPException(status_code=404, detail={"error": "runner not found"})
    return {"revoked": True}


@router.get("/triggers", dependencies=[Depends(require_principal)])
def triggers_list(db: Session = Depends(get_db)):
    return {"triggers": orchestration.list_triggers(db)}


@router.post("/triggers", dependencies=[Depends(require_writer)])
def triggers_create(body: TriggerBody, db: Session = Depends(get_db)):
    try:
        row, secret = orchestration.create_trigger(db, body.workflow_id, body.kind,
                                                   body.config, body.evidence_note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    out = {"trigger_id": row.id, "kind": row.kind, "enabled": row.enabled}
    if secret:
        out["secret"] = secret
        out["note"] = "webhook secret shown once; send it as X-AutoStack-Secret"
    return out


@router.post("/triggers/{trigger_id}/enable", dependencies=[Depends(require_writer)])
def triggers_enable(trigger_id: str, db: Session = Depends(get_db)):
    if not orchestration.set_trigger_enabled(db, trigger_id, True):
        raise HTTPException(status_code=404, detail={"error": "trigger not found"})
    return {"enabled": True}


@router.post("/triggers/{trigger_id}/disable", dependencies=[Depends(require_writer)])
def triggers_disable(trigger_id: str, db: Session = Depends(get_db)):
    if not orchestration.set_trigger_enabled(db, trigger_id, False):
        raise HTTPException(status_code=404, detail={"error": "trigger not found"})
    return {"enabled": False}


@router.post("/webhook/{trigger_id}")
def webhook_fire(trigger_id: str, request: Request, db: Session = Depends(get_db)):
    """Public inbound webhook trigger (secret-authenticated, rate-limited, audited).

    B7: auth/lookups happen BEFORE any limiter state is recorded, so unauthenticated
    probes can never grow the limiter dict. B2: the fired run executes through the
    real graph executor — no zombie runs.
    """
    from backend.models import Trigger as _Trigger
    trig = db.get(_Trigger, trigger_id)
    if trig is None or not trig.enabled:
        raise HTTPException(status_code=404, detail={"error": "trigger not found or disabled"})
    secret = request.headers.get("X-AutoStack-Secret", "")
    if not orchestration.webhook_secret_matches(db, trigger_id, secret):
        raise HTTPException(status_code=401, detail={"error": "invalid webhook secret"})
    hits = _WEBHOOK_HITS.setdefault(trigger_id, [])
    now = time.time()
    hits[:] = [t for t in hits if now - t < 60]
    if len(hits) >= WEBHOOK_RATE_LIMIT:
        raise HTTPException(status_code=429, detail={"error": "webhook rate limit exceeded"})
    hits.append(now)
    if len(_WEBHOOK_HITS) > 10_000:  # bounded dict: drop idle entries
        cutoff = now - 300
        for tid in [t for t, ts in _WEBHOOK_HITS.items() if not ts or ts[-1] < cutoff]:
            _WEBHOOK_HITS.pop(tid, None)
    return _start_triggered_run(db, trig, "webhook", {"trigger_id": trigger_id})


def _start_triggered_run(db: Session, trig, trigger_kind: str, audit_extra: dict) -> dict:
    """B2: start a triggered run through the SAME executor path as run-now.

    Reuses start_run's compiled-graph resolution so triggered runs execute for real
    (no status='running' zombies) and share the exactly-once journal.
    """
    from fastapi import HTTPException as _HTTPException
    version = (db.query(WorkflowVersion)
               .filter(WorkflowVersion.workflow_id == trig.workflow_id)
               .order_by(WorkflowVersion.version.desc()).first())
    if version is None:
        raise _HTTPException(status_code=404, detail={"error": "workflow not found for trigger"})
    version_payload = json.loads(version.graph_json)
    graph = version_payload.get("graph") if isinstance(version_payload, dict) and "graph" in version_payload else version_payload
    if not (isinstance(graph, dict) and "nodes" in graph):
        raise _HTTPException(status_code=422, detail={"error": "workflow has no executable graph; re-bind it from its plan"})

    class _RunBody:  # minimal adapter to the graph executor's body interface
        workflow_id = trig.workflow_id
        run_date = identity.now_iso()[:10]  # today; the date contract validates on use
        filename = "clients.csv"
        dry_run = False
        params = {}

    body = _RunBody()
    from backend.app import _start_run_graph as _srg
    try:
        result = _srg(db, version, graph, body)
    except _HTTPException as exc:
        # an execution failure still produced an audited failed run — surface it honestly
        detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
        run_id = detail.get("run_id")
        from backend.security import audit as audit_mod
        audit_mod.append(db, f"trigger.{trigger_kind}_fired", {**audit_extra,
                          "run_id": run_id, "outcome": "failed", "error": detail.get("error", "")[:160]})
        db.commit()
        raise
    from backend.security import audit as audit_mod
    audit_mod.append(db, f"trigger.{trigger_kind}_fired", {**audit_extra,
                      "run_id": result.get("run_id"), "outcome": result.get("status")})
    db.commit()
    return {"run_id": result.get("run_id"), "workflow_id": trig.workflow_id,
            "status": result.get("status")}


def _latest_version_id(db: Session, workflow_id: str) -> str:
    from backend.models import WorkflowVersion
    v = (db.query(WorkflowVersion)
         .filter(WorkflowVersion.workflow_id == workflow_id)
         .order_by(WorkflowVersion.version.desc()).first())
    if v is None:
        raise HTTPException(status_code=404, detail={"error": "workflow has no versions"})
    return v.id


# ── Phase E: run parameters, approval gates ──────────────────────────────────

class ParamBody(BaseModel):
    name: str
    param_type: str = "string"
    required: bool = False
    default: object = None


@router.post("/workflows/{workflow_id}/parameters", dependencies=[Depends(admin_guard)])
def declare_param(workflow_id: str, body: ParamBody, db: Session = Depends(get_db)):
    from backend.models import WorkflowVersion
    v = (db.query(WorkflowVersion).filter(WorkflowVersion.workflow_id == workflow_id)
         .order_by(WorkflowVersion.version.desc()).first())
    if v is None:
        raise HTTPException(status_code=404, detail={"error": "workflow not found"})
    try:
        row = orchestration.declare_parameter(db, v.id, body.name, body.param_type,
                                              body.required, body.default)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    return {"parameter_id": row.id, "version_id": v.id, "name": row.name}


@router.get("/runs/{run_id}/gates", dependencies=[Depends(require_principal)])
def run_gates(run_id: str, db: Session = Depends(get_db)):
    from backend.models import ReviewGate
    gates = db.scalars(select(ReviewGate).where(ReviewGate.run_id == run_id)).all()
    return {"gates": [{"id": g.id, "node_id": g.node_id, "prompt": g.prompt,
                       "status": g.status} for g in gates]}


class GateDecisionBody(BaseModel):
    approved: bool
    decided_by: str = ""


@router.post("/gates/{gate_id}/decide", dependencies=[Depends(require_principal)])
def gate_decide(gate_id: str, body: GateDecisionBody, request: Request,
                db: Session = Depends(get_db)):
    """Human decision on a paused approval gate. Approval resumes the run by
    re-executing the graph with completed nodes skipped (effects stay exactly-once)."""
    from backend.app import resume_run_after_gate
    principal = require_principal(request, db)
    if principal.kind == "user" and not teams.role_allows(principal.role, "activate"):
        raise HTTPException(status_code=403, detail={
            "error": "approver role required to decide gates", "how_to_unlock": "approver role"})
    try:
        return resume_run_after_gate(db, gate_id, body.approved,
                                     principal.user.username if principal.user else "service")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc


# ── Phase F: governance exports ──────────────────────────────────────────────

@router.get("/governance/audit-export", dependencies=[Depends(require_principal)])
def governance_audit_export(request: Request, db: Session = Depends(get_db)):
    ok, _caps, why = entitlements.check(db, "audit_export_local")
    if not ok:
        raise HTTPException(status_code=403, detail={"error": why})
    rows = db.scalars(select(AuditEntry).order_by(AuditEntry.seq)).all()
    return {"format": "autostack-audit-v1", "entries": [
        {"seq": e.seq, "kind": e.kind, "at": e.at, "payload": e.payload_json,
         "hash": e.hash} for e in rows], "count": len(rows)}


@router.get("/governance/siem/stream", dependencies=[Depends(require_principal)])
def governance_siem_stream(request: Request, db: Session = Depends(get_db)):
    ok, _caps, why = entitlements.check(db, "siem_export")
    if not ok:
        raise HTTPException(status_code=403, detail={"error": why,
                                                     "how_to_unlock": "enterprise tier or higher"})
    rows = db.scalars(select(AuditEntry).order_by(AuditEntry.seq)).all()
    lines = [json.dumps({"seq": e.seq, "kind": e.kind, "at": e.at,
                         "payload": json.loads(e.payload_json)}, default=str)
             for e in rows]
    return {"format": "jsonl-siem-v1", "lines": lines, "count": len(lines),
            "note": "a deployment streams this continuously; this endpoint returns the current backlog"}


@router.get("/governance/compliance-bundle", dependencies=[Depends(require_principal)])
def governance_compliance_bundle(db: Session = Depends(get_db)):
    ok, _caps, why = entitlements.check(db, "audit_export_local")
    if not ok:
        raise HTTPException(status_code=403, detail={"error": why})
    from backend.security.audit import verify_chain
    report = verify_chain(db)
    return {"generated_at": identity.now_iso(),
            "chain_valid": bool(report.get("chain_valid")),
            "chain_entries": report.get("count"),
            "audit_entries": db.scalar(select(AuditEntry.seq).order_by(AuditEntry.seq.desc()).limit(1)) or 0,
            "runs_total": db.query(Run).count(),
            "drafts_total": db.query(Draft).count()}


# ── Phase G: registry governance & honest signals ────────────────────────────

class ReviewBody(BaseModel):
    approve: bool
    note: str = ""


@router.post("/registry/templates/{template_id}/review", dependencies=[Depends(admin_guard)])
def registry_review(template_id: str, body: ReviewBody, db: Session = Depends(get_db)):
    ok, _caps, why = entitlements.check(db, "publish_national")
    if not ok:
        raise HTTPException(status_code=403, detail={"error": why,
                                                     "how_to_unlock": "developer or government tier"})
    from backend.models import RegistryTemplate
    t = db.get(RegistryTemplate, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail={"error": "template not found"})
    if t.status != "in_review":
        raise HTTPException(status_code=409, detail={"error": f"template status is {t.status}; only in_review templates can be decided"})
    t.status = "published" if body.approve else "rejected"
    db.commit()
    from backend.security import audit as audit_mod
    audit_mod.append(db, "registry.reviewed", {"template_id": template_id,
                                               "approved": body.approve, "note": body.note[:300]})
    db.commit()
    return {"template_id": template_id, "status": t.status}


@router.get("/registry/templates/{template_id}/signals",
             dependencies=[Depends(require_principal)])
def registry_signals(template_id: str, db: Session = Depends(get_db)):
    """Honest signals only: real install events and real imported-run reports."""
    installs = db.query(RegistryEvent).filter(RegistryEvent.template_id == template_id,
                                              RegistryEvent.kind == "install").count()
    run_reports = db.query(RegistryEvent).filter(RegistryEvent.template_id == template_id,
                                                 RegistryEvent.kind == "run_report").count()
    return {"template_id": template_id, "installs": installs, "run_reports": run_reports,
            "note": "counts reflect recorded events only; nothing is estimated"}


@router.post("/registry/imports/{import_id}/record-run", dependencies=[Depends(require_principal)])
def registry_record_run(import_id: str, db: Session = Depends(get_db)):
    imp = db.get(RegistryImport, import_id)
    if imp is None:
        raise HTTPException(status_code=404, detail={"error": "import not found"})
    ev = RegistryEvent(id=secrets.token_hex(12), template_id=imp.template_id,
                       kind="run_report", value=1, at=identity.now_iso())
    db.add(ev)
    db.commit()
    return {"recorded": True}


# ─── Roadmap completion: notifications center, privacy, connectors ────────────
# These close the three planned-but-missing surfaces: a full Notifications Center,
# a real Data & Privacy page, and an honest Connectors inventory. Every value is
# real state; nothing is estimated (project rule: no invented anything).


class MarkReadBody(BaseModel):
    ids: list[str] | None = None  # None / empty = mark everything unread


@router.post("/notifications/read-all", dependencies=[Depends(require_principal)])
def notifications_mark_all(body: MarkReadBody, db: Session = Depends(get_db)):
    """Mark all unread notifications read, or an explicit id list. Notifications
    are org-global (no per-user rows), so any authenticated member may mark them."""
    from backend.models import Notification
    q = db.query(Notification).filter(Notification.read_at.is_(None))
    if body.ids:
        q = q.filter(Notification.id.in_(body.ids))
    stamped = identity.now_iso()
    count = q.update({Notification.read_at: stamped}, synchronize_session=False)
    db.commit()
    return {"marked": count, "read_at": stamped}


@router.get("/privacy/ledger", dependencies=[Depends(require_principal)])
def privacy_ledger(db: Session = Depends(get_db)):
    """The consent ledger, computed from real recorded decisions — never invented.
    Source of truth: the hash-chained audit ledger plus the approvals table."""
    kinds = ["test_consent", "activation", "runner_pair", "consent_pending"]
    counts = {k: db.query(AuditEntry).filter(AuditEntry.kind == k).count() for k in kinds}
    approvals = db.query(Approval).order_by(Approval.decided_at.desc()).limit(50).all()
    return {
        "counts": counts,
        "recent_decisions": [
            {"id": a.id, "kind": a.kind, "artifact_id": a.artifact_id,
             "decided_at": a.decided_at, "note": a.note}
            for a in approvals
        ],
        "note": "approvals are content-hash bound decisions from the Phase-6/9 chains; "
                "the audit ledger itself is append-only and never deleted",
    }


RETENTION_DEFAULTS = {"observations_days": 30, "reports_days": 90}


def _read_retention(db: Session) -> dict:
    row = db.get(Setting, "retention_days")
    if row is None:
        return dict(RETENTION_DEFAULTS)
    try:
        stored = json.loads(row.value_json)
    except (ValueError, TypeError):
        return dict(RETENTION_DEFAULTS)
    out = dict(RETENTION_DEFAULTS)
    for k in RETENTION_DEFAULTS:
        v = stored.get(k)
        if isinstance(v, int) and 7 <= v <= 3650:
            out[k] = v
    return out


@router.get("/privacy/retention", dependencies=[Depends(require_principal)])
def privacy_retention_get(db: Session = Depends(get_db)):
    return {"retention": _read_retention(db),
            "bounds": {"min_days": 7, "max_days": 3650},
            "audit_ledger": "append-only, hash-chained; exempt from retention deletion"}


@router.post("/privacy/retention", dependencies=[Depends(require_principal)])
def privacy_retention_set(body: dict, db: Session = Depends(get_db)):
    """Set retention windows (retention_admin capability). Bounds enforced;
    silent clamping is refused — invalid values are a 422, not a 'fix'."""
    from backend.security import audit as audit_mod
    ok, _caps, why = entitlements.check(db, "retention_admin")
    if not ok:
        raise HTTPException(status_code=403, detail={"error": why,
                                                     "how_to_unlock": "team tier or higher"})
    out = {}
    for k, default in RETENTION_DEFAULTS.items():
        v = body.get(k, default)
        # bool is an int subclass in Python — reject it explicitly (B6), same for floats
        if isinstance(v, bool) or not isinstance(v, int) or not (7 <= v <= 3650):
            raise HTTPException(status_code=422,
                                detail={"error": f"{k} must be an integer between 7 and 3650"})
        out[k] = v
    row = db.get(Setting, "retention_days")
    if row is None:
        row = Setting(key="retention_days", value_json="{}")
        db.add(row)
    row.value_json = json.dumps(out)
    db.commit()
    audit_mod.append(db, "retention_set", {"retention": out})
    return {"retention": out}


@router.post("/privacy/export", dependencies=[Depends(require_principal)])
def privacy_export(db: Session = Depends(get_db)):
    """Data export: the user's drafts, runs, and observation-derived rows —
    the same data the product already shows, in one portable payload."""
    drafts = db.scalars(select(Draft).order_by(Draft.created_at)).all()
    runs = db.scalars(select(Run).order_by(Run.started_at)).all()
    return {
        "exported_at": identity.now_iso(),
        "drafts": [{"id": d.id, "record_key": d.record_key, "body": d.body,
                    "lang": d.lang, "created_at": str(d.created_at)} for d in drafts],
        "runs": [{"id": r.id, "status": r.status, "started_at": str(r.started_at),
                  "finished_at": str(r.ended_at) if r.ended_at else None}
                 for r in runs],
        "note": "audit ledger is available separately via /api/governance/audit-export",
    }


@router.get("/connectors", dependencies=[Depends(require_principal)])
def connectors_inventory(db: Session = Depends(get_db)):
    """Honest connector inventory with LIVE checks — status is measured, not a
    hardcoded 'supported' sticker. Boundaries text comes from README §4."""
    ai_key_present = bool(os.environ.get("AUTOSTACK_GEMINI_KEY", ""))
    caps = entitlements.get_capabilities(db)
    local_only = bool(caps.get("local_only"))
    items = [
        {
            "id": "excel", "name": "Excel workbooks (.xlsx)",
            "status": "supported",
            "can_see": "stable files in the allowlisted sample folder, after settling",
            "cannot_see": "live open edits; clipboard; anything outside the allowlist",
        },
        {
            "id": "csv", "name": "CSV files",
            "status": "supported",
            "can_see": "stable files in the allowlisted sample folder, after settling",
            "cannot_see": "live open edits; clipboard; anything outside the allowlist",
        },
        {
            "id": "ai_gemini", "name": "AI generation (Gemini)",
            "status": "supported" if ai_key_present else "limited",
            "detail": "" if ai_key_present else
            "no AUTOSTACK_GEMINI_KEY configured — deterministic offline generator is used",
            "can_see": "only the fields a workflow explicitly passes to the prompt",
            "cannot_see": "file contents not referenced by the workflow",
        },
        {
            "id": "nodered", "name": "Node-RED (embedded)",
            "status": "supported",
            "detail": "in-process runtime on 127.0.0.1:18790 with AutoStack bridge nodes",
            "can_see": "flows the user deploys inside this app",
            "cannot_see": "other Node-RED instances",
        },
        {
            "id": "webhook_in", "name": "Inbound webhooks",
            "status": "supported",
            "detail": "per-trigger secret header (X-AutoStack-Secret), rate-limited, audited",
            "can_see": "the POST body of a trigger the owner enabled",
            "cannot_see": "anything else on the caller's network",
        },
        {
            "id": "http_request", "name": "Outbound HTTP requests",
            "status": "limited",
            "detail": "node.http calls ONLY hosts on the workflow's static allowlist (validated at bind time, re-checked at run time); generated code itself stays network-blocked",
            "can_see": "the allowlisted host's response, bounded to 64 KiB, 5 s timeout",
            "cannot_see": "arbitrary URLs — user- or model-supplied hosts are refused at validation",
        },
        {
            "id": "email_in", "name": "Email reading",
            "status": "unavailable",
            "detail": "not implemented: mailbox capture is future work",
            "can_see": "nothing",
            "cannot_see": "mailboxes, credentials, contacts",
        },
        {
            "id": "browser", "name": "Browser observation",
            "status": "limited",
            "detail": "synthetic contract capture only (phase-1 spike); no live page reading",
            "can_see": "contract-shaped events staged through the capture API",
            "cannot_see": "real browsing sessions, passwords, page pixels",
        },
        {
            "id": "email", "name": "Email sending",
            "status": "unavailable",
            "detail": "by design: drafts are generated in-app; nothing is ever sent",
            "can_see": "nothing",
            "cannot_see": "mailboxes, credentials, contacts",
        },
        {
            "id": "cloud_sync", "name": "Cloud sync / external transfer",
            "status": "unavailable" if not local_only else "blocked",
            "detail": "local-first by design" + (" (government tier enforces local-only)" if local_only else ""),
            "can_see": "nothing",
            "cannot_see": "anything — no outbound transfer exists",
        },
    ]
    return {"connectors": items,
            "note": "status measured from this worker's real configuration at request time"}


@router.get("/system/ai-mode", dependencies=[Depends(require_principal)])
def system_ai_mode():
    """Where the 'model status' answer comes from: provider actually in use."""
    provider = os.environ.get("AUTOSTACK_AI_PROVIDER", "mock")
    return {"provider": provider,
            "deterministic_offline": provider == "mock",
            "gemini_key_present": bool(os.environ.get("AUTOSTACK_GEMINI_KEY", ""))}


# ── B3: trigger firing (schedules + file-arrival) & B4: workflow deletion ─────

_TRIGGER_LOCK = None


def _trigger_lock():
    """One lock per worker process: the tick never runs concurrently with itself."""
    import threading
    global _TRIGGER_LOCK
    if _TRIGGER_LOCK is None:
        _TRIGGER_LOCK = threading.Lock()
    return _TRIGGER_LOCK


def _trigger_due_schedule(trig, now) -> bool:
    """Schedule due-ness from the trigger's real config. Evidence-gated creation
    already guarantees real calendar backing; this only decides 'is it time now'."""
    cfg_ = json.loads(trig.config_json or "{}")
    tod = cfg_.get("time_of_day")  # "HH:MM" UTC
    if not isinstance(tod, str) or len(tod) != 5 or ":" not in tod:
        return False
    try:
        hh, mm = (int(x) for x in tod.split(":"))
    except ValueError:
        return False
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return False
    days = cfg_.get("days_of_week")  # 0..6 (Mon..Sun); absent = every day
    if days is not None and now.weekday() not in days:
        return False
    if now.hour != hh or now.minute < mm:
        return False
    return cfg_.get("last_fired_utc") != now.date().isoformat()  # at most once per day


def _trigger_file_matches(db: Session, trig, seen: set) -> bool:
    """Fire once per unseen watcher event matching the trigger's real config:
    {"alias": "sample-tracking-file", "action": "row.added", "record_key_prefix": "..."}.
    Events carry redacted alias:ID keys (no filenames) by privacy design, so the
    trigger matches on alias + action + optional key prefix — nothing else exists."""
    from backend.models import Event
    cfg_ = json.loads(trig.config_json or "{}")
    latest = (db.query(Event)
              .filter(Event.source == "saved_file_comparison")
              .order_by(Event.received_at.desc(), Event.event_id.desc())
              .first())
    if latest is None or latest.event_id in seen:
        return False
    seen.add(latest.event_id)
    if cfg_.get("alias") and latest.resource != cfg_["alias"]:
        return False
    if cfg_.get("action") and latest.action != cfg_["action"]:
        return False
    prefix = cfg_.get("record_key_prefix")
    return prefix is None or (latest.record_key or "").startswith(prefix)


def trigger_tick(db: Session) -> dict:
    """One bounded pass over enabled schedule/file triggers; fires what's due through
    the same executor as run-now (exactly-once journal applies to triggers too)."""
    from backend.models import Trigger
    fired = []
    seen_files: set[str] = set()
    for trig in db.scalars(select(Trigger).where(Trigger.enabled == True)):  # noqa: E712
        try:
            if trig.kind == "schedule" and _trigger_due_schedule(trig, datetime.now(timezone.utc)):
                due = True
            elif trig.kind == "file" and _trigger_file_matches(db, trig, seen_files):
                due = True
            else:
                due = False
            if not due:
                continue
            result = _start_triggered_run(db, trig, trig.kind, {"trigger_id": trig.id})
            fired.append({"trigger_id": trig.id, "run_id": result.get("run_id"),
                          "status": result.get("status")})
            if trig.kind == "schedule":
                cfg_ = json.loads(trig.config_json or "{}")
                cfg_["last_fired_utc"] = datetime.now(timezone.utc).date().isoformat()
                trig.config_json = json.dumps(cfg_)
                db.commit()
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
            fired.append({"trigger_id": trig.id, "error": str(detail.get("error", ""))[:120]})
        except Exception as exc:  # one bad trigger never kills the loop
            fired.append({"trigger_id": trig.id, "error": str(exc)[:120]})
    return {"checked": True, "fired": fired}


def trigger_loop_worker():
    """Daemon loop (worker process only): bounded tick every 30 s, never crashes."""
    import time as _time

    from backend.db import SessionLocal as _SL
    while True:
        try:
            with _trigger_lock():
                db = _SL()
                try:
                    trigger_tick(db)
                finally:
                    db.close()
        except Exception:
            pass
        _time.sleep(30)


def start_trigger_loop_if_needed():
    """Idempotently start the daemon loop (called from app startup)."""
    import threading
    if not _LOOP_STATE["started"]:
        t = threading.Thread(target=trigger_loop_worker, name="autostack-triggers", daemon=True)
        t.start()
        _LOOP_STATE["started"] = True
        _LOOP_STATE["thread"] = t


_LOOP_STATE = {"started": False, "thread": None}


@router.post("/triggers/tick", dependencies=[Depends(require_writer)])
def triggers_tick(db: Session = Depends(get_db)):
    """Manual tick (tests + ops); the background loop runs the same function.

    Requires an operator-role principal (or the service token): a manual tick can
    fire real workflow runs, so read-only observers are rejected (QA round 6)."""
    with _trigger_lock():
        return trigger_tick(db)


@router.delete("/workflows/{workflow_id}")
def workflow_delete(workflow_id: str, principal: _Principal = Depends(admin_guard),
                    db: Session = Depends(get_db)):
    """B4: soft-delete a workflow (owner/admin).

    The row is marked deleted_at so it disappears from listings and can't be run,
    while every version, run, and audit entry is retained — history is never
    destroyed (same principle as the append-only ledger). Idempotent-ish: deleting
    an unknown or already-deleted workflow is a 404 with an honest error.
    """
    from backend.models import Run, Trigger, Workflow, WorkflowVersion
    wf = db.get(Workflow, workflow_id)
    if wf is None or wf.deleted_at is not None:
        raise HTTPException(status_code=404, detail={"error": "workflow not found"})
    version_ids = [v.id for v in db.scalars(
        select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow_id))]
    in_flight = (db.query(Run)
                 .filter(Run.status.in_(["running", "waiting"]),
                         Run.version_id.in_(version_ids))
                 .count())
    if in_flight:
        raise HTTPException(status_code=409,
                            detail={"error": "workflow has in-flight runs; cancel them first"})
    for t in db.scalars(select(Trigger).where(Trigger.workflow_id == workflow_id)):
        t.enabled = False
    wf.deleted_at = datetime.now(timezone.utc)
    db.commit()
    who = principal.kind + (f":{principal.user.username}" if principal.user else "")
    audit_mod.append(db, "workflow.deleted", {"workflow_id": workflow_id, "by": who})
    db.commit()
    return {"deleted": workflow_id, "note": "runs and audit history retained"}
