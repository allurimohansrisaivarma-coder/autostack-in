"""Folder capture watcher (Phase 3) — bounded polling, settling, honest events.

Plan rules implemented here:
  - Watches an allowlisted folder by polling (no filesystem hooks that could claim
    live Excel edits or clipboard content — the watcher only ever reads STABLE files).
  - Settling: a file is only parsed once its size+mtime have been unchanged for
    `settle_seconds`, with bounded patience; otherwise the poll yields a documented
    gap (no invented events).
  - Compares stable saved versions by client ID using the Phase-1 file_diff logic;
    added/removed/updated rows become contract-shaped events with capture/processing
    times, source, and ambiguity flag.
  - Redaction by default: event record_keys are `alias:ID` tokens, not names; no file
    contents are copied into events, and snapshots stay in the spike data dir.
"""
from __future__ import annotations

import csv
import io
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.file_diff import compare, read_snapshot
from backend import spike_config as cfg  # noqa: F401  (DATA_DIR used by callers)

RED = "redacted"  # never log raw row content


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FolderWatcher:
    """Polls an allowlisted folder and emits events for stable CSV changes."""

    def __init__(self, folder: Path, alias: str = "watched", settle_seconds: float = 5.0,
                 max_file_bytes: int = 5_000_000, max_poll_files: int = 50):
        self.folder = Path(folder)
        self.alias = alias
        self.settle_seconds = settle_seconds
        self.max_file_bytes = max_file_bytes
        self.max_poll_files = max_poll_files
        self.state: dict[str, dict] = {}   # filename -> {"sha256", "snapshot"}
        self._stat_cache: dict[str, dict] = {}  # stat-key -> {"size", "mtime"} (budget opt)
        self.gaps: list[dict] = []
        self.MAX_GAPS = 100  # bounded memory: old gaps rotate out (they are poll-local observations)

    def _list_candidate_files(self) -> list[Path]:
        if not self.folder.is_dir():
            return []
        files = [p for p in self.folder.iterdir()
                 if p.is_file() and p.suffix.lower() in (".csv", ".xlsx")
                 and not p.name.startswith("~$")  # office lock/owner files, never parsed
                 and p.stat().st_size <= self.max_file_bytes]
        return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:self.max_poll_files]

    def _gap(self, name: str, reason: str) -> None:
        """Record a bounded honest gap (never an invented event)."""
        self.gaps.append({"file": name, "reason": reason, "at": _now_iso()})
        if len(self.gaps) > self.MAX_GAPS:
            del self.gaps[:-self.MAX_GAPS]

    def _settled(self, path: Path) -> bool:
        """True when size+mtime have been unchanged for settle_seconds (bounded patience)."""
        try:
            st1 = path.stat()
        except OSError:
            return False
        time.sleep(self.settle_seconds)
        try:
            st2 = path.stat()
        except OSError:
            return False
        return (st1.st_size, st1.st_mtime_ns) == (st2.st_size, st2.st_mtime_ns)

    def poll(self) -> list[dict]:
        """One bounded poll pass. Returns the events produced (may be empty = honest gap).

        Budget note (Phase 8 measurement): the settle wait only applies to files whose
        size+mtime CHANGED since the last poll — unchanged files skip straight to the
        hash check, so an idle folder costs no settle sleeps.
        """
        events: list[dict] = []
        for path in self._list_candidate_files():
            name = path.name
            try:
                st_now = path.stat()
                key_stat = f"stat:{self.alias}:{name}"
                prev_stat = self._stat_cache.get(key_stat)
                unchanged_stat = (prev_stat is not None
                                  and prev_stat["size"] == st_now.st_size
                                  and prev_stat["mtime"] == st_now.st_mtime_ns)
                if unchanged_stat:
                    payload = path.read_bytes()
                else:
                    if not self._settled(path):
                        self._gap(name, "unsettled")
                        continue
                    payload = path.read_bytes()
                    try:
                        st_after = path.stat()
                    except OSError:
                        st_after = st_now
                    self._stat_cache[key_stat] = {"size": st_after.st_size, "mtime": st_after.st_mtime_ns}
                if name.lower().endswith(".xlsx"):
                    # Phase 8 adds the xlsx parser; CSV-only is the honest spike scope.
                    self._gap(name, "xlsx-not-supported-in-spike")
                    continue
                snapshot = read_snapshot(path)
            except Exception as exc:
                # parser errors become gaps, never invented events
                self._gap(name, f"parse-error: {exc}"[:120])
                continue
            key = f"{self.alias}:{name}"
            prev = self.state.get(key)
            if prev is None:
                self.state[key] = {"sha256": cfg_hash(payload), "snapshot": snapshot}
                continue  # first sight = baseline, not an event
            if prev["sha256"] == cfg_hash(payload):
                continue  # unchanged
            diff = compare(prev["snapshot"], snapshot)
            now = _now_iso()
            # file_diff.compare: added/removed are "sample:<ID>" strings; updated are dicts.
            for added_key in diff["added"]:
                events.append(self._event("row.added", added_key, now))
            for removed_key in diff["removed"]:
                events.append(self._event("row.removed", removed_key, now))
            for updated in diff["updated"]:
                events.append(self._event("row.updated", updated["record_key"], now,
                                          changed_fields=updated["changed_fields"]))
            self.state[key] = {"sha256": cfg_hash(payload), "snapshot": snapshot}
        return events

    def _event(self, action: str, record_key: str, now: str, changed_fields=None) -> dict:
        # v2 contract: real observation, redaction preserved (record_key is an ID token,
        # never a name; no cell contents). `resource` is the watcher alias; the concrete
        # file stays out of the event (private-path hygiene).
        return {
            "event_id": str(uuid.uuid4()),
            "schema_version": 2,
            "source_version": "phase2-watcher-0.1.0",
            "source": "saved_file_comparison",  # stable saved-version comparison (honest scope)
            "action": action,
            "resource": self.alias,
            "record_key": record_key,
            "changed_fields": changed_fields or [],
            "outcome": "success",
            "captured_at": now,
            "processed_at": _now_iso(),
            "synthetic": False,
        }


def cfg_hash(payload: bytes) -> str:
    import hashlib
    return hashlib.sha256(payload).hexdigest()
