"""Roadmap Phase C: teams, roles, invitations, business processes.

Role model (redesigned): a GitHub-PR-style ladder where Owner and Admin are
co-equal for product actions and everyone else proposes through change
requests:
  observer  — view only (dashboards, logs, registry); no writes
  operator  — drafts plans, proposes changes, runs APPROVED workflows
  approver  — operator + sandbox test / activation duties (compat tier)
  admin     — co-equal with owner for product/governance actions (create,
              edit, run, test, activate, publish, review/merge change
              requests, manage members); tier/billing stays owner-only
  owner     — everything, incl. tier changes / plan conversion
Invitations are expiring, token-based; revocation semantics follow README
("Revoking execution access stops dependent operations") — last owner cannot
be demoted, so an org can never lose its administrators.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Invitation, Membership, Org, Process, User

ROLES = ("observer", "operator", "approver", "admin", "owner")
ROLE_RANK = {"observer": 0, "operator": 1, "approver": 2, "admin": 3, "owner": 4}

# Distinct permissions → minimum role. "admin" covers day-to-day governance
# (members, roles, review/merge, publish, delete); org tier/billing stays at
# owner via the separate "org_lifecycle" permission.
PERMISSION_MIN_ROLE = {
    "observe": "observer",
    "run": "operator",
    "propose": "operator",
    "test": "approver",
    "activate": "approver",
    "publish": "admin",
    "admin": "admin",
    "org_lifecycle": "owner",
}


def role_allows(role: str, permission: str) -> bool:
    need = PERMISSION_MIN_ROLE.get(permission)
    if need is None:
        return False
    return ROLE_RANK.get(role, -1) >= ROLE_RANK[need]


def effective_role(db: Session, user) -> str:
    """The role that governs this user's API permissions: membership in their
    caller-org (shared workspace wins, else personal org). This is the single
    resolver used by BOTH auth paths (roadmap principal + legacy token guards).

    Bug fix (owner/tools access): the legacy guards resolved the role against
    the FIRST org row only, so an unaffiliated signup's owner — owner of their
    own personal workspace — was treated as a plain operator on the plan →
    generate → test → activate → publish routes and locked out of the tools.
    """
    from backend.models import Membership
    org = user_org(db, user)
    if org is None:
        return "owner" if user.is_admin else "operator"
    m = db.scalar(select(Membership).where(Membership.org_id == org.id,
                                           Membership.user_id == user.id))
    if m is not None:
        return m.role
    return "owner" if user.is_admin else "operator"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def primary_org(db: Session) -> Org:
    from backend.entitlements import get_or_create_org
    return get_or_create_org(db)


def ensure_personal_org(db: Session, user) -> Org:
    """Signup affiliation rule: an unaffiliated account becomes the OWNER of its
    own personal workspace (full feature access, solo tier) instead of being
    dropped into the shared workspace as a low-privileged member. Idempotent:
    returns the existing personal org when one is already linked."""
    existing = db.scalar(select(Membership).where(Membership.user_id == user.id))
    if existing is not None:
        org = db.get(Org, existing.org_id)
        if org is not None:
            return org
    org = Org(id=secrets.token_hex(12), name=f"{(user.display_name or user.username)}'s Workspace",
              tier="solo", local_only=False)
    db.add(org)
    db.commit()
    return org


def user_org(db: Session, user) -> Org | None:
    """The org whose role applies to this caller: a membership in the shared
    workspace wins (it is the collaboration surface); otherwise the user's own
    personal org. None when the account has no membership rows at all."""
    workspace = primary_org(db)
    rows = db.scalars(select(Membership).where(Membership.user_id == user.id)).all()
    if not rows:
        return None
    for m in rows:
        if m.org_id == workspace.id:
            return workspace
    return db.get(Org, rows[0].org_id)


def user_role(db: Session, user) -> str:
    """A user's effective role in the primary org (admin users are owners).

    Bug fix (create-flow audit): users without an explicit membership row are
    OPERATOR, not observer. Registration provisions 'operator' (the working
    default — observers are created deliberately by an owner), so a missing row
    can only mean a legacy/provisioned account; defaulting those to read-only
    locked every mutating route behind a false 403. Admin users stay owners.
    """
    from backend.models import Membership
    from sqlalchemy import select
    org = primary_org(db)
    m = db.scalar(select(Membership).where(Membership.org_id == org.id,
                                           Membership.user_id == user.id))
    if m is not None:
        return m.role
    if user.is_admin:
        return "owner"
    return "operator"


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


# ── org profile: organization types / sizes, departments, process types ──────
# (Product §5) The context model must cover far more than corporate back
# offices: corporate enterprises (by size), government agencies, and
# individuals/solo users. Process types are offered per (org type, size,
# department) so the create flow only ever shows coherent choices.

ORG_TYPES = ("corporate", "government", "individual", "nonprofit", "education",
             "healthcare", "legal", "manufacturing", "retail", "logistics", "other")

# Size only applies to organizations — individuals/solo users pick "solo".
ORG_SIZES = ("solo", "small", "medium", "large")

# Department/team catalog per organization type. Values are stable ids shown
# through the API; the frontend maps ids to labels.
DEPARTMENTS: dict[str, tuple[str, ...]] = {
    "corporate": (
        "finance", "operations", "procurement", "human_resources",
        "sales", "marketing", "legal", "it", "customer_support", "compliance",
    ),
    "government": (
        "administration", "revenue", "citizen_services", "licensing",
        "public_works", "health", "education", "social_services",
        "procurement", "compliance", "field_operations", "records",
    ),
    "individual": ("personal_productivity", "freelance", "consulting"),
    "nonprofit": ("programs", "fundraising", "volunteers", "grants", "admin"),
    "education": ("admissions", "academics", "student_services", "finance",
                  "examinations", "library", "it", "admin"),
    "healthcare": ("clinical_operations", "billing", "admin", "compliance",
                   "records", "supply_tracking"),
    "legal": ("litigation_support", "contracts", "compliance", "admin"),
    "manufacturing": ("production_planning", "quality", "procurement",
                      "maintenance", "logistics", "compliance"),
    "retail": ("store_operations", "merchandising", "ecommerce", "customer_support",
               "finance", "supply_chain"),
    "logistics": ("dispatch", "fleet", "warehouse", "customs", "customer_support", "finance"),
    "other": ("general", "finance", "operations", "admin"),
}

# Process types per department — filtered by (org_type, size, department).
# Process types per department — filtered by (org type, size, department).
# Broad common verbs are shared across departments (the "custom" escape hatch
# plus free-text "other process type" keeps the product out of one niche).
_COMMON_PROCESS_TYPES = ("client_followup", "data_entry", "scheduling", "notifications",
                         "document_generation", "reconciliation", "onboarding", "escalation",
                         "report_generation", "task_tracking", "approval_workflows", "custom")

def _pt(*extra: str) -> tuple[str, ...]:
    """Department process list: specific entries first, then the common verbs."""
    return tuple(dict.fromkeys((*extra, *_COMMON_PROCESS_TYPES)))

PROCESS_TYPES: dict[str, tuple[str, ...]] = {
    # corporate
    "finance": _pt("accounts_payable", "accounts_receivable", "invoice_po_matching",
                   "tax_filing", "expense_reimbursement", "payroll_processing", "audit_prep"),
    "operations": _pt("vendor_followup", "inventory_updates"),
    "procurement": _pt("vendor_onboarding", "purchase_orders", "quote_comparison",
                       "contract_renewals", "goods_receipt"),
    "human_resources": _pt("employee_onboarding", "leave_management", "payroll_queries",
                           "recruitment_pipeline", "exit_process"),
    "sales": _pt("lead_followup", "quote_generation", "order_processing", "collections"),
    "marketing": _pt("campaign_tracking", "content_approvals", "lead_nurture"),
    "legal": _pt("contract_review", "compliance_calendar"),
    "it": _pt("ticket_triage", "access_requests", "backup_verification", "asset_tracking"),
    "customer_support": _pt("ticket_followup", "sla_escalation", "feedback_triage",
                            "knowledge_base_updates"),
    "compliance": _pt("compliance_and_filing", "audit_prep", "document_drafting"),
    # government
    "administration": _pt("notice_generation", "records_requests"),
    "revenue": _pt("tax_filing", "return_processing", "payment_reconciliation"),
    "citizen_services": _pt("application_followup", "benefit_applications",
                            "eligibility_screening"),
    "licensing": _pt("license_renewal", "approval_workflows", "status_notifications"),
    "public_works": _pt("complaint_triage", "work_orders", "inspection_scheduling"),
    "health": _pt("patient_followup", "supply_tracking", "compliance_and_filing"),
    "education": _pt("enrollment_processing", "certification_issuance"),
    "social_services": _pt("case_followup", "eligibility_screening"),
    "field_operations": _pt("inspection_scheduling", "work_orders"),
    "records": _pt("data_entry_verification", "archival_updates"),
    # individual / solo
    "personal_productivity": _pt("personal_finance", "bill_reminders", "document_management"),
    "freelance": _pt("invoicing", "project_tracking", "quote_generation"),
    "consulting": _pt("client_reporting", "engagement_tracking", "proposal_generation"),
    # nonprofit
    "programs": _pt("beneficiary_tracking", "grant_reporting"),
    "fundraising": _pt("donor_followup", "campaign_tracking", "pledge_management"),
    "volunteers": _pt("volunteer_onboarding", "shift_scheduling", "hours_tracking"),
    "grants": _pt("grant_applications", "compliance_and_filing"),
    # education
    "admissions": _pt("application_followup", "enrollment_processing"),
    "academics": _pt("course_scheduling", "attendance_tracking", "grade_processing"),
    "student_services": _pt("counseling_appointments", "scholarship_processing",
                            "hostel_management"),
    "examinations": _pt("exam_scheduling", "result_processing", "certificate_issuance"),
    "library": _pt("overdue_notices", "membership_management"),
    # healthcare
    "clinical_operations": _pt("patient_followup", "appointment_scheduling",
                               "lab_result_routing"),
    "billing": _pt("claim_processing", "payment_reconciliation", "invoice_po_matching"),
    "supply_tracking": _pt("supply_tracking", "expiry_monitoring"),
    # legal
    "litigation_support": _pt("case_deadline_tracking", "document_drafting", "evidence_logging"),
    "contracts": _pt("contract_review", "contract_renewals", "compliance_calendar"),
    # manufacturing
    "production_planning": _pt("work_orders", "production_scheduling", "inventory_updates"),
    "quality": _pt("defect_tracking", "audit_prep", "compliance_and_filing"),
    "maintenance": _pt("preventive_maintenance", "breakdown_escalation"),
    # retail
    "store_operations": _pt("inventory_updates", "price_updates", "staff_scheduling"),
    "merchandising": _pt("campaign_tracking", "stock_replenishment"),
    "ecommerce": _pt("order_processing", "returns_processing", "customer_onboarding"),
    "supply_chain": _pt("purchase_orders", "goods_receipt", "reconciliation"),
    # logistics
    "dispatch": _pt("shipment_scheduling", "delivery_followup", "escalation_handling"),
    "fleet": _pt("maintenance_scheduling", "compliance_and_filing"),
    "warehouse": _pt("inventory_updates", "goods_receipt", "stock_replenishment"),
    "customs": _pt("customs_documentation", "compliance_and_filing"),
    # other
    "general": _pt("document_management"),
}

# Fallback for departments missing from PROCESS_TYPES (never an empty menu).
_DEFAULT_PROCESS_TYPES = ("report_generation", "task_tracking", "compliance_and_filing",
                          "approval_workflows", "document_management")

# Sizes available per org type: individuals are always solo (UI hides the picker).
ORG_SIZES_FOR_TYPE: dict[str, tuple[str, ...]] = {
    "corporate": ("small", "medium", "large"),
    "government": ("small", "medium", "large"),
    "nonprofit": ("small", "medium", "large"),
    "education": ("small", "medium", "large"),
    "healthcare": ("small", "medium", "large"),
    "legal": ("small", "medium", "large"),
    "manufacturing": ("small", "medium", "large"),
    "retail": ("small", "medium", "large"),
    "logistics": ("small", "medium", "large"),
    "other": ("small", "medium", "large"),
    "individual": ("solo",),
}


def valid_context(org_type: str | None, size: str | None, department: str | None,
                  process_type: str | None) -> list[str]:
    """Validate a full context tuple; returns a list of human-readable problems
    (empty = valid). Shared by the API validators and the UI catalog."""
    problems: list[str] = []
    if org_type not in ORG_TYPES:
        problems.append(f"unknown organization type: {org_type}")
        return problems
    if size not in ORG_SIZES_FOR_TYPE.get(org_type, ORG_SIZES):
        problems.append(f"invalid size '{size}' for organization type '{org_type}'")
    if department not in DEPARTMENTS.get(org_type, ()):  # unknown dept for this org type
        problems.append(f"unknown department '{department}' for organization type '{org_type}'")
        return problems
    allowed = PROCESS_TYPES.get(department, _DEFAULT_PROCESS_TYPES)
    if process_type not in allowed:
        problems.append(f"unknown process type '{process_type}' for department '{department}'")
    return problems


def process_types_for(org_type: str, size: str, department: str) -> list[str]:
    """Coherent process-type options for a (org type, size, department) choice.
    Department not in the catalog falls back to the generic set — the UI never
    shows an empty menu."""
    if department in PROCESS_TYPES:
        return list(PROCESS_TYPES[department])
    return list(_DEFAULT_PROCESS_TYPES)


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


def set_workflow_context(db: Session, workflow_id: str, org_type: str, size: str,
                         department: str, process_type: str,
                         *, extra: dict | None = None) -> None:
    """Persist the classification context of a workflow (create step 1).
    Stored as a Setting JSON row so the Workflow model stays untouched (same
    pattern as workflow_process). Invalid tuples are refused here too. The
    expanded context subsections (connectors, tools, trigger, sensitivity
    note, target outcome) ride along verbatim in `extra`."""
    from backend.models import Setting
    problems = valid_context(org_type, size, department, process_type)
    if problems:
        raise ValueError("; ".join(problems))
    payload_dict = {"org_type": org_type, "size": size,
                    "department": department, "process_type": process_type}
    for key in ("connectors", "tools", "trigger", "sensitivity_note", "outcome"):
        if extra and extra.get(key):
            payload_dict[key] = extra[key]
    payload = json.dumps(payload_dict)
    row = db.get(Setting, f"workflow_context:{workflow_id}")
    if row is None:
        row = Setting(key=f"workflow_context:{workflow_id}", value_json=payload)
        db.add(row)
    else:
        row.value_json = payload
    db.commit()


def workflow_context_map(db: Session, workflow_ids: list[str]) -> dict[str, dict]:
    """workflow_id -> {org_type, size, department, process_type} (missing = {})."""
    from backend.models import Setting
    out: dict[str, dict] = {}
    for wid in workflow_ids:
        row = db.get(Setting, f"workflow_context:{wid}")
        if row is None:
            continue
        try:
            out[wid] = json.loads(row.value_json)
        except Exception:
            continue
    return out
