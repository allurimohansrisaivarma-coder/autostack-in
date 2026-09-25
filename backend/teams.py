"""Roadmap Phase C: teams, roles, invitations, business processes.

Role model maps 1:1 onto README §3's distinct permissions:
  observer  — may see observation/status only
  operator  — runs approved workflows; no test/activate rights
  approver  — may test + activate + run
  owner     — everything incl. publish + administration
Invitations are expiring, token-based; revocation semantics follow README
("Revoking execution access stops dependent operations") — last owner cannot be
demoted, so an org can never lose its administrators.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Invitation, Membership, Org, Process, User

ROLES = ("observer", "operator", "approver", "owner")
ROLE_RANK = {"observer": 0, "operator": 1, "approver": 2, "owner": 3}

# README §3 distinct permissions → minimum role
PERMISSION_MIN_ROLE = {
    "observe": "observer",
    "run": "operator",
    "test": "approver",
    "activate": "approver",
    "publish": "owner",
    "admin": "owner",
}


def role_allows(role: str, permission: str) -> bool:
    need = PERMISSION_MIN_ROLE.get(permission)
    if need is None:
        return False
    return ROLE_RANK.get(role, -1) >= ROLE_RANK[need]


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def primary_org(db: Session) -> Org:
    from backend.entitlements import get_or_create_org
    return get_or_create_org(db)


def user_role(db: Session, user) -> str:
    """A user's effective role in the primary org (admin users are owners)."""
    from backend.models import Membership
    from sqlalchemy import select
    org = primary_org(db)
    m = db.scalar(select(Membership).where(Membership.org_id == org.id,
                                           Membership.user_id == user.id))
    return m.role if m else ("owner" if user.is_admin else "observer")


def members(db: Session, org_id: str) -> list[dict]:
    rows = (db.query(Membership).filter(Membership.org_id == org_id)
            .order_by(Membership.created_at).all())
    out = []
    for m in rows:
        u = db.get(User, m.user_id)
        out.append({"membership_id": m.id, "user_id": m.user_id,
                    "username": u.username if u else "(deleted)",
                    "display_name": u.display_name if u else "",
                    "role": m.role, "since": m.created_at.isoformat() if m.created_at else None})
    return out


def add_member(db: Session, org_id: str, user_id: str, role: str) -> Membership:
    if role not in ROLES:
        raise ValueError(f"unknown role: {role}")
    existing = db.scalar(select(Membership).where(Membership.org_id == org_id,
                                                  Membership.user_id == user_id))
    if existing is not None:
        existing.role = role
        db.commit()
        return existing
    m = Membership(id=secrets.token_hex(12), org_id=org_id, user_id=user_id, role=role)
    db.add(m)
    db.commit()
    return m


def set_role(db: Session, org_id: str, membership_id: str, role: str) -> bool:
    if role not in ROLES:
        raise ValueError(f"unknown role: {role}")
    m = db.get(Membership, membership_id)
    if m is None or m.org_id != org_id:
        return False
    if m.role == "owner" and role != "owner":
        owners = db.scalar(select(Membership.id).where(
            Membership.org_id == org_id, Membership.role == "owner",
            Membership.id != membership_id).limit(1))
        if owners is None:
            raise ValueError("cannot demote the last owner")
    m.role = role
    db.commit()
    return True


def remove_member(db: Session, org_id: str, membership_id: str) -> bool:
    m = db.get(Membership, membership_id)
    if m is None or m.org_id != org_id:
        return False
    if m.role == "owner":
        owners = db.scalar(select(Membership.id).where(
            Membership.org_id == org_id, Membership.role == "owner",
            Membership.id != membership_id).limit(1))
        if owners is None:
            raise ValueError("cannot remove the last owner")
    db.delete(m)
    db.commit()
    return True


def create_invitation(db: Session, org_id: str, role: str, created_by: str,
                      ttl_hours: int = 72) -> tuple[Invitation, str]:
    if role not in ROLES:
        raise ValueError(f"unknown role: {role}")
    token = "inv_" + secrets.token_urlsafe(24)
    inv = Invitation(id=secrets.token_hex(12), org_id=org_id, role=role,
                     token_hash=_hash(token), created_by=created_by,
                     expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours))
    db.add(inv)
    db.commit()
    return inv, token


def accept_invitation(db: Session, token: str, user_id: str) -> Membership:
    inv = db.scalar(select(Invitation).where(Invitation.token_hash == _hash(token or "")))
    if inv is None or inv.accepted_by is not None:
        raise ValueError("invitation not valid")
    if inv.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise ValueError("invitation expired")
    inv.accepted_by = user_id
    db.commit()
    return add_member(db, inv.org_id, user_id, inv.role)


def list_invitations(db: Session, org_id: str) -> list[dict]:
    rows = (db.query(Invitation).filter(Invitation.org_id == org_id)
            .order_by(Invitation.created_at.desc()).all())
    return [{"id": i.id, "role": i.role,
             "expires_at": i.expires_at.isoformat(),
             "accepted": i.accepted_by is not None} for i in rows]


def revoke_invitation(db: Session, org_id: str, invitation_id: str) -> bool:
    inv = db.get(Invitation, invitation_id)
    if inv is None or inv.org_id != org_id or inv.accepted_by is not None:
        return False
    db.delete(inv)
    db.commit()
    return True


# ── processes ────────────────────────────────────────────────────────────────

def create_process(db: Session, org_id: str, name: str, description: str = "",
                   run_quota_per_day: int = 0) -> Process:
    if not (name or "").strip():
        raise ValueError("process name required")
    p = Process(id=secrets.token_hex(12), org_id=org_id, name=name.strip()[:160],
                description=(description or "")[:2000],
                run_quota_per_day=max(0, int(run_quota_per_day)))
    db.add(p)
    db.commit()
    return p


def list_processes(db: Session, org_id: str) -> list[Process]:
    return list(db.scalars(select(Process).where(Process.org_id == org_id)
                           .order_by(Process.created_at)))


def attach_workflow_to_process(db: Session, process_id: str, workflow_id: str) -> bool:
    """Workflows point at a process via Setting rows (keeps Workflow model untouched)."""
    from backend.models import Setting
    row = db.get(Setting, f"workflow_process:{workflow_id}")
    if row is None:
        row = Setting(key=f"workflow_process:{workflow_id}", value_json=json.dumps(process_id))
        db.add(row)
    else:
        row.value_json = json.dumps(process_id)
    db.commit()
    return True


def workflow_process_map(db: Session, workflow_ids: list[str]) -> dict[str, str]:
    from backend.models import Setting
    out: dict[str, str] = {}
    for wid in workflow_ids:
        row = db.get(Setting, f"workflow_process:{wid}")
        if row is not None:
            try:
                out[wid] = json.loads(row.value_json)
            except Exception:
                out[wid] = row.value_json
    return out
