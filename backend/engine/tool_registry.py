"""Tool Registry: one catalog for native worker nodes and MCP tools at scale.

Design goals (autopilot/registry upgrade):
  - ONE shape for every callable capability: id, source, category, description,
    status, risk, sandbox policy.
  - Status is HONEST: "supported" means the worker's own validator accepts the
    node today; MCP tools arrive as "experimental"/"unavailable" until a real
    server is registered and probed — never invented capabilities.
  - Scale: thousands of tools must not blow up prompts or UI. The registry
    supports search + pagination for humans and top-k retrieval (ranked by a
    simple goal-term overlap score) for the AI autopilot — the model only ever
    sees a retrieved subset, never the whole catalog.
  - Allowlists: a per-org allowlist gates what may be used at all; a per-
    workflow allowlist narrows it further. Retrieval results are intersected
    with the caller's allowlist so the AI can propose nothing forbidden.
  - MCP: register_servers() accepts a server manifest; tools are registered
    lazily (the server is only described, not contacted — contact happens at
    registration time and is honestly "unavailable" until a live probe is
    wired in a future round).
"""
from __future__ import annotations

import hashlib
import json

from backend.engine.catalog import CATALOG

# Source prefixes
NATIVE = "native"

STATUS_RANK = {"supported": 0, "limited": 1, "experimental": 2, "unavailable": 3}

# Risk ladder — informational for now, consumed by future policy checks.
RISK_FOR_CATEGORY = {
    "read": "low",
    "data": "low",
    "logic": "low",
    "notify": "medium",      # drafts/notifications touch humans
    "write": "medium",       # file/row mutations
    "http": "high",          # egress — allowlisted only
    "governance": "medium",  # approval gates
    "mcp": "high",           # external servers default to high until probed
}

# Sandbox policy per category (mirrors the runner's default policy; http tools
# additionally require the per-workflow host allowlist).
SANDBOX_POLICY_FOR_CATEGORY = {
    "read": {"network": False, "filesystem": "alias_only"},
    "data": {"network": False, "filesystem": "alias_only"},
    "logic": {"network": False, "filesystem": "none"},
    "notify": {"network": False, "filesystem": "none"},
    "write": {"network": False, "filesystem": "alias_only"},
    "http": {"network": "allowlisted_hosts_only", "filesystem": "none"},
    "governance": {"network": False, "filesystem": "none"},
    "mcp": {"network": "server_defined", "filesystem": "none"},
}


def _category_for_group(group: str) -> str:
    """Map the worker catalog's display groups onto registry categories."""
    g = (group or "").lower()
    if "read" in g:
        return "read"
    if "write" in g or "file" in g:
        return "write"
    if "transform" in g or "data" in g:
        return "data"
    if "control" in g:
        return "logic"
    if "http" in g:
        return "http"
    if "notify" in g:
        return "notify"
    if "governance" in g or "approval" in g:
        return "governance"
    return "data"


def seed_native_tools() -> list[dict]:
    """Build the registry from the worker's own validated catalog — the same
    source the graph validator enforces, so a registered tool can never be a
    node the executor refuses. No behavior change for existing flows."""
    tools: list[dict] = []
    for type_name, spec in CATALOG.items():
        category = _category_for_group(type_name.split(".")[0] + " " + type_name)
        params = getattr(spec, "required", ()) or ()
        optional = (spec.params or {}).keys()
        tools.append({
            "id": f"native:{type_name}",
            "source": NATIVE,
            "category": category,
            "description": f"Native node {type_name} (params: {', '.join(list(params) + list(optional)) or 'none'})",
            "status": "supported",
            "risk": RISK_FOR_CATEGORY.get(category, "medium"),
            "sandbox_policy": SANDBOX_POLICY_FOR_CATEGORY.get(category, {"network": False}),
        })
    return tools


class ToolRegistry:
    """In-memory registry seeded from the worker catalog, extended at runtime
    with MCP tool registrations. Persistence (per-org allowlists) rides on the
    existing Setting JSON rows via the API layer."""

    def __init__(self) -> None:
        self._tools: dict[str, dict] = {}
        for t in seed_native_tools():
            self._tools[t["id"]] = t

    # ── registration ──────────────────────────────────────────────────────
    def register_mcp_server(self, server_name: str, tools: list[dict],
                            description: str = "") -> dict:
        """Register tools exposed by an MCP server. The server is stored
        honestly: tools land as 'experimental' (sandbox policy server-defined,
        network by default) and only a future live probe may promote them.
        Returns a summary; refuses nothing but marks everything unavailable
        when the manifest lacks a callable surface."""
        registered = []
        for t in tools or []:
            name = str(t.get("name") or "").strip()
            if not name:
                continue
            tid = f"mcp:{server_name}:{name}"
            self._tools[tid] = {
                "id": tid,
                "source": f"mcp:{server_name}",
                "category": str(t.get("category") or "mcp"),
                "description": str(t.get("description") or description or name)[:400],
                "status": "experimental",
                "risk": RISK_FOR_CATEGORY.get(str(t.get("category") or "mcp"), "high"),
                "sandbox_policy": dict(t.get("sandbox_policy")
                                       or SANDBOX_POLICY_FOR_CATEGORY["mcp"]),
            }
            registered.append(tid)
        return {"server": server_name, "tools_registered": len(registered),
                "tool_ids": registered,
                "note": "MCP tools register as experimental; a live probe must promote them before use"}

    # ── lookup / listing ──────────────────────────────────────────────────
    def get(self, tool_id: str) -> dict | None:
        return self._tools.get(tool_id)

    def count(self) -> int:
        return len(self._tools)

    def list(self, *, search: str = "", category: str = "", source: str = "",
             status: str = "", limit: int = 50, offset: int = 0) -> dict:
        """Human browsing: search + filters + pagination (scale-safe)."""
        q = (search or "").strip().lower()
        out = []
        for t in self._tools.values():
            if q and q not in t["id"].lower() and q not in t["description"].lower():
                continue
            if category and t["category"] != category:
                continue
            if source and not t["source"].startswith(source):
                continue
            if status and t["status"] != status:
                continue
            out.append(t)
        out.sort(key=lambda t: (STATUS_RANK.get(t["status"], 9), t["id"]))
        total = len(out)
        return {"tools": out[offset:offset + max(1, min(limit, 500))],
                "total": total, "offset": offset, "limit": limit}

    # ── AI retrieval (scale-safe) ─────────────────────────────────────────
    def retrieve(self, goal: str, *, allowlist: set[str] | None = None,
                 k: int = 12, categories: list[str] | None = None) -> list[dict]:
        """Top-k tools for an AI prompt, ranked by goal-term overlap against
        id + description (+ category boost). Only tools inside the caller's
        allowlist and with a usable status are ever returned, so the model can
        propose nothing forbidden or unavailable."""
        terms = {w for w in (goal or "").lower().replace(":", " ").split() if len(w) > 2}
        scored: list[tuple[int, dict]] = []
        for t in self._tools.values():
            if allowlist is not None and t["id"] not in allowlist:
                continue
            # The AI may only PROPOSE proven tools: experimental/unavailable
            # MCP tools never surface here (a live probe must promote them).
            if t["status"] not in ("supported", "limited"):
                continue
            if categories and t["category"] not in categories:
                continue
            hay = f"{t['id']} {t['description']} {t['category']}".lower()
            score = sum(1 for term in terms if term in hay)
            # Native supported tools win ties; experimental MCP only surfaces
            # when the goal names them (server or tool name match).
            if t["status"] == "supported":
                score += 1
            if score <= 0:
                continue
            scored.append((score, t))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
        return [t for _s, t in scored[:max(1, min(k, 50))]]

    def allowlist_for(self, org_allow: list[str] | None,
                      wf_allow: list[str] | None) -> set[str] | None:
        """Intersect org- and workflow-level allowlists. None means 'no
        restriction recorded' — the caller then sees native supported tools.
        An explicit empty list means 'nothing allowed' (honest zero)."""
        if org_allow is None and wf_allow is None:
            return None
        sets = []
        if org_allow is not None:
            sets.append({a for a in org_allow if a in self._tools})
        if wf_allow is not None:
            sets.append({a for a in wf_allow if a in self._tools})
        inter = set.intersection(*sets) if sets else set()
        # A tool absent from a recorded allowlist is forbidden; unknown ids are
        # simply ignored (they cannot exist in the registry).
        return inter

    def digest(self) -> str:
        """Content digest of the registry (change detection for caches)."""
        return hashlib.sha256(json.dumps(
            sorted(self._tools), sort_keys=True, default=str).encode()).hexdigest()[:16]


REGISTRY = ToolRegistry()
