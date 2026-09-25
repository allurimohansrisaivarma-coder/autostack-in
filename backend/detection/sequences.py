"""Ordered-sequence detection (Phase 4) — pure functions over event dicts.

Design rules from the plan (and README):
  - Evidence-based only: no fabricated confidence percentages, no similarity scores.
  - AutoStack-generated events (source == "autostack") NEVER qualify — the app must not
    detect patterns in its own runs.
  - Only completed, unambiguous instances count; a >=10-minute inactivity gap closes an
    instance (unfinished trailing work stays incomplete and is excluded).
  - A candidate = the same ordered action sequence completed >=3 times, spanning
    >=2 distinct record_keys (clients), on the same resource+compatible column set.
  - Duplicate suppression: identical (sequence, resource, record-scope) groups merge.

Pure module (no DB): app.py folds persisted events in, candidates out.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

GAP = timedelta(minutes=10)          # inactivity that closes an instance
THRESHOLD_OCCURRENCES = 3            # completed instances needed
THRESHOLD_CLIENTS = 2                # distinct record_keys needed

INCOMPLETE = "incomplete"
AMBIGUOUS = "ambiguous"


def _ts(ev: dict) -> datetime:
    return datetime.fromisoformat(ev["captured_at"].replace("Z", "+00:00"))


def eligible_events(events: list[dict]) -> list[dict]:
    """Ordered, qualifying events only: exclude our own runs and failed actions."""
    out = []
    for ev in events:
        if ev.get("source") == "autostack":
            continue
        if ev.get("outcome") != "success":
            continue
        out.append(ev)
    out.sort(key=_ts)
    return out


def build_instances(events: list[dict], now: str | None = None) -> list[dict]:
    """Group events into instances — one stream per record_key (clients working
    simultaneously are distinct instances, never one merged sequence).

    Closing semantics (README/plan): an instance FOLLOWED by another in its stream is
    complete ("ok"); the trailing instance is only closed by >=10 inactive minutes
    ("incomplete" when `now` proves the silence, otherwise "open" — not yet countable).
    Only "ok" instances count toward candidates: detection is honest and lags one
    instance rather than counting work that may still be in progress.
    """
    evs = eligible_events(events)
    if not evs:
        return []
    now_ts = _ts({"captured_at": now}) if now else None
    streams: dict[str, list[dict]] = defaultdict(list)
    for ev in evs:
        streams[ev.get("record_key") or ""].append(ev)
    instances: list[dict] = []
    for _, stream in sorted(streams.items()):
        chunks: list[list[dict]] = []
        current: list[dict] = [stream[0]]
        for prev, ev in zip(stream, stream[1:]):
            if _ts(ev) - _ts(prev) > GAP:
                chunks.append(current)
                current = [ev]
            else:
                current.append(ev)
        chunks.append(current)
        for idx, chunk in enumerate(chunks):
            last = idx == len(chunks) - 1
            if last:
                if now_ts is not None and (now_ts - _ts(chunk[-1])) > GAP:
                    status = INCOMPLETE
                else:
                    status = "open"
                instances.append(_finish(chunk, status=status))
            else:
                instances.append(_finish(chunk, status="ok"))
    return instances


def _finish(events: list[dict], *, status: str) -> dict:
    record_keys = sorted({e["record_key"] for e in events if e.get("record_key")})
    return {
        "events": events,
        "started_at": events[0]["captured_at"],
        "last_at": events[-1]["captured_at"],
        "duration_s": (_ts(events[-1]) - _ts(events[0])).total_seconds(),
        "record_keys": record_keys,
        "resource": events[0].get("resource", ""),
        "sequence": [e["action"] for e in events],
        "status": status,
    }


def sequence_key(sequence: list[str]) -> tuple:
    return tuple(sequence)


def detect_candidates(events: list[dict], now: str | None = None) -> list[dict]:
    """Fold events into evidence-based candidates.

    Returns candidates sorted by occurrences desc: {sequence, resource, occurrences,
    record_keys, instance_ids, first_seen, last_seen, evidence {steps, per_client}}.
    """
    instances = [i for i in build_instances(events, now=now) if i["status"] == "ok"]
    groups: dict[tuple, dict] = {}
    for idx, inst in enumerate(instances):
        if len(inst["events"]) < 1:
            continue
        key = (sequence_key(inst["sequence"]), inst["resource"])
        g = groups.setdefault(key, {
            "sequence": inst["sequence"], "resource": inst["resource"],
            "occurrences": 0, "record_keys": set(), "instance_ids": [],
            "first_seen": inst["started_at"], "last_seen": inst["last_at"],
            "per_client": defaultdict(int),
        })
        g["occurrences"] += 1
        for rk in inst["record_keys"]:
            g["record_keys"].add(rk)
            g["per_client"][rk] += 1
        g["instance_ids"].append(idx)
        if inst["started_at"] < g["first_seen"]:
            g["first_seen"] = inst["started_at"]
        if inst["last_at"] > g["last_seen"]:
            g["last_seen"] = inst["last_at"]

    candidates = []
    for g in groups.values():
        qualifies = (g["occurrences"] >= THRESHOLD_OCCURRENCES
                     and len(g["record_keys"]) >= THRESHOLD_CLIENTS)
        candidates.append({
            "sequence": g["sequence"],
            "resource": g["resource"],
            "qualifies": qualifies,
            "occurrences": g["occurrences"],
            "record_keys": sorted(g["record_keys"]),
            "instance_ids": g["instance_ids"],
            "first_seen": g["first_seen"],
            "last_seen": g["last_seen"],
            "evidence": {
                "steps": g["sequence"],
                "instances": g["occurrences"],
                "distinct_clients": len(g["record_keys"]),
                "per_client": dict(g["per_client"]),
            },
        })
    candidates.sort(key=lambda c: (-c["occurrences"], c["first_seen"]))
    return candidates
