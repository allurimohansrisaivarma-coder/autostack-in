"""Node catalog + graph validation.

The catalog is the single source of truth for node types, params, and permissions.
validate_graph() rejects unknown nodes/params and cycles BEFORE anything can deploy (S9 posture:
invalid structure never reaches the runtime). This is the same catalog the editors and the
flow compiler (Milestone B) will code against.
"""
from __future__ import annotations

from dataclasses import dataclass, field

MAX_ROWS = 1000  # contracts.md parser budget


@dataclass(frozen=True)
class NodeSpec:
    type: str
    params: dict[str, type]  # name -> python type
    required: tuple[str, ...]
    outputs: tuple[str, ...]
    permission: str | None = None
    errors: tuple[str, ...] = field(default_factory=tuple)


CATALOG: dict[str, NodeSpec] = {
    spec.type: spec
    for spec in [
        NodeSpec("file.read_table", {"alias": str, "max_rows": int}, ("alias",), ("rows",), "read-content",
                 ("unsupported-format", "too-large", "bad-ids")),
        NodeSpec("data.filter", {"from": str, "where": str}, ("from", "where"), ("rows",)),
        # Aggregation node (safe catalog): counts rows in the current table into a
        # structured summary. Read-only by construction — no effect, no journal
        # claim — so it can sit anywhere in a graph (e.g. before an approval gate
        # to give the approver context in the audit trail).
        NodeSpec("data.aggregate", {"field": str}, (), ("summary",)),
        NodeSpec("file.update_rows", {"alias": str, "filename": str, "set": str, "purpose": str,
                                       "key_field": str},
                 ("alias", "filename", "set", "purpose"), ("updated",), "write-target",
                 ("lock", "conflict", "idempotent-claimed")),
        # File operations (n8n-style, scoped to declared resource aliases): a copy is
        # a whole-file staged write with backup; an archive adds a dated sibling and
        # never touches the source. Filenames are plain names inside the alias —
        # resolve_resource() rejects traversal/junctions at the safeio layer.
        NodeSpec("file.copy", {"from_alias": str, "from_filename": str,
                                "to_alias": str, "to_filename": str},
                 ("from_alias", "from_filename", "to_alias", "to_filename"), ("copied",), "write-target",
                 ("lock", "conflict", "idempotent-claimed")),
        NodeSpec("file.archive", {"alias": str, "filename": str},
                 ("alias", "filename"), ("archived",), "write-target",
                 ("lock", "conflict", "idempotent-claimed")),
        # Row operations (exactly-once, journaled like update_rows): append adds
        # keyed rows (duplicate keys are skipped by the journal); soft_delete
        # rewrites a status-style field instead of destroying data — rollback can
        # restore the prior value from the audit trail.
        NodeSpec("rows.append", {"alias": str, "filename": str, "rows": str,
                                  "purpose": str, "key_field": str},
                 ("alias", "filename", "rows", "purpose"), ("appended",), "write-target",
                 ("lock", "conflict", "idempotent-claimed")),
        NodeSpec("rows.soft_delete", {"alias": str, "filename": str, "field": str,
                                        "value": str, "purpose": str, "key_field": str},
                 ("alias", "filename", "field", "value", "purpose"), ("soft_deleted",), "write-target",
                 ("lock", "conflict", "idempotent-claimed")),
        NodeSpec("draft.create", {"record_key": str, "template_id": str, "destination": str},
                 ("record_key", "template_id", "destination"), ("draft_id",), "draft-create",
                 ("claimed", "invalid-row")),
        NodeSpec("notify.desktop", {"title_key": str}, ("title_key",), ("notified",), "notify"),
        # Roadmap §E: control-flow + human-gate nodes (same validation as the rest).
        NodeSpec("control.branch", {"condition": str}, ("condition",), ("taken",)),
        NodeSpec("approval.gate", {"prompt": str}, ("prompt",), ("gate_id",), "activate"),
        # Transform/Set (n8n core, plan-scoped): only the approved plan's fields
        # can be mapped — `set` entries are `field=value` literals, validated
        # against the plan's field mappings, so no code or arbitrary paths.
        NodeSpec("data.transform", {"set": str, "rename": str}, (), ("rows",)),
        # Merge (n8n core): combines branch outputs for downstream nodes. The
        # executor union-joins row dicts seen so far — a pure in-memory combine,
        # no external service.
        NodeSpec("control.merge", {}, (), ("rows",)),
        # Wait (n8n core, bounded): a bounded pause before continuing. The cap is
        # a catalog constant (max 30 s, validated at bind time) so a graph can
        # never stall a run indefinitely.
        NodeSpec("control.wait", {"seconds": int}, ("seconds",), ("waited",)),
        # Allowlisted HTTP (n8n HTTP Request, locked down): the WORKFLOW carries a
        # static host allowlist (set at bind time, stored with the version), and
        # the node may only call those hosts with the approved method/path. No
        # user- or model-supplied URLs at run time; the sandboxed executor uses
        # urllib with a hard timeout and a bounded response size.
        NodeSpec("node.http", {"host": str, "method": str, "path": str, "body_key": str},
                 ("host", "method", "path"), ("response",), "allowlisted-host",
                 ("host-not-allowlisted", "timeout", "bad-response")),
    ]
}

# Bounded wait cap (catalog-level contract; the executor enforces it too).
MAX_WAIT_SECONDS = 30

# Static outbound HTTP allowlist: hosts a workflow may ever call. Even a
# per-workflow allowlist cannot exceed this deployment-level allowlist.
HTTP_HOST_ALLOWLIST = {
    "127.0.0.1",        # local worker/bridge self-calls
    "localhost",
}

VALID_ON_FAIL = {"halt", "continue", "error_branch"}


def validate_graph(graph: dict) -> list[str]:
    """Return a list of validation errors (empty = valid)."""
    errors: list[str] = []
    nodes = graph.get("nodes", [])
    node_ids = [n.get("id") for n in nodes]
    if len(node_ids) != len(set(node_ids)):
        errors.append("duplicate node ids")
    known = set()
    for node in nodes:
        nid = node.get("id")
        ntype = node.get("type")
        if not nid or not ntype:
            errors.append(f"node missing id/type: {node!r}")
            continue
        spec = CATALOG.get(ntype)
        if spec is None:
            errors.append(f"unknown node type: {ntype}")
            continue
        known.add(nid)
        params = node.get("params", {})
        for name in spec.required:
            if name not in params:
                errors.append(f"{nid}: missing required param '{name}'")
        for name, value in params.items():
            if name not in spec.params:
                errors.append(f"{nid}: unknown param '{name}' for {ntype}")
            elif spec.params[name] is int and not isinstance(value, int):
                errors.append(f"{nid}: param '{name}' must be int")
            elif spec.params[name] is str and not isinstance(value, str):
                errors.append(f"{nid}: param '{name}' must be str")
        if node.get("on_fail") not in (None, *VALID_ON_FAIL):
            errors.append(f"{nid}: invalid on_fail {node.get('on_fail')!r}")
        retry = node.get("retry")
        if retry is not None:
            if not isinstance(retry, dict) or not isinstance(retry.get("attempts", 0), int) or retry.get("attempts", 0) > 3:
                errors.append(f"{nid}: retry.attempts must be int <= 3")
        # Bounded wait: a graph may pause at most MAX_WAIT_SECONDS (never stall).
        if ntype == "control.wait":
            secs = params.get("seconds")
            if isinstance(secs, int) and not (0 <= secs <= MAX_WAIT_SECONDS):
                errors.append(f"{nid}: control.wait seconds must be 0..{MAX_WAIT_SECONDS}")
        # Allowlisted HTTP: the host must be in BOTH the workflow's declared
        # per-workflow allowlist (graph-level) and the deployment allowlist.
        if ntype == "node.http":
            host = str(params.get("host", "")).strip().lower()
            wf_hosts = {h.strip().lower() for h in (graph.get("http_allow_hosts") or [])
                        if isinstance(h, str)}
            if host not in HTTP_HOST_ALLOWLIST or host not in wf_hosts:
                errors.append(f"{nid}: host '{host or '(missing)'}' is not on the " +
                              "workflow's HTTP allowlist")
        # Merge is a join point: it must have at least one incoming edge (a merge
        # with no inputs would silently pass an empty table downstream).
        if ntype == "control.merge":
            incoming = sum(1 for e in graph.get("edges", [])
                           if e.get("to") == nid and e.get("from") in known)
            if incoming < 1:
                errors.append(f"{nid}: control.merge needs at least one incoming edge")
    edges = graph.get("edges", [])
    for edge in edges:
        if edge.get("from") not in known or edge.get("to") not in known:
            errors.append(f"edge references unknown node: {edge!r}")
    # Cycle detection (Kahn's algorithm).
    indegree = {nid: 0 for nid in known}
    adjacency: dict[str, list[str]] = {nid: [] for nid in known}
    for edge in edges:
        f, t = edge.get("from"), edge.get("to")
        if f in known and t in known:
            adjacency[f].append(t)
            indegree[t] += 1
    queue = [nid for nid, deg in indegree.items() if deg == 0]
    visited = 0
    while queue:
        current = queue.pop()
        visited += 1
        for nxt in adjacency[current]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    if visited != len(known):
        errors.append("graph contains a cycle")
    return errors
