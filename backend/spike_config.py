"""Stage 0 spike configuration. Loopback-only, token-authenticated.

Production hardening (keyring storage, rotate-on-start, scopes) lands in Milestone A;
these constants exist so the spike never depends on machine-specific state.
"""
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# ── Data directory resolution + persistence visibility ───────────────────────
# AUTOSTACK_DATA_DIR overrides the default local path.
# In container deployments (Railway) this is /data (the Dockerfile default),
# which MUST be a mounted volume — without one, every redeploy wipes the
# database (users, workflows, registry, audit all live in DATA_DIR/spike.db).
_env_data = os.environ.get("AUTOSTACK_DATA_DIR", "").strip()
DATA_DIR: Path = Path(_env_data) if _env_data else REPO_ROOT / "artifacts" / "spike"

# Recorded before mkdir so boot logs can distinguish "DB was already there"
# (persistent volume reused) from "DB newly created" (fresh/empty volume).
DB_PATH = DATA_DIR / "spike.db"
DB_EXISTED_AT_BOOT = DB_PATH.is_file()

DATA_DIR.mkdir(parents=True, exist_ok=True)
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def data_dir_configured() -> bool:
    """True when AUTOSTACK_DATA_DIR was explicitly set (i.e. the deployment
    deliberately chose a data location — the prerequisite for it being a
    mounted persistent volume). Read live (falling back to the boot-time
    capture) so operators can verify behavior without restarting; never
    contains the path itself — safe for health/system responses."""
    return bool(os.environ.get("AUTOSTACK_DATA_DIR", "").strip() or _env_data)


def persistence_summary() -> dict:
    """Deployment-persistence facts that are safe to expose (no paths, no
    contents): whether the data dir was explicitly configured, whether the
    database file existed at boot (volume reused vs fresh), and whether a
    persistence guard is active."""
    guard_active = bool(
        os.environ.get("AUTOSTACK_REQUIRE_PERSISTENT_DATA", "").strip() == "1"
        or _looks_like_railway()
    )
    return {
        "data_dir_configured": data_dir_configured(),
        "db_exists": DB_EXISTED_AT_BOOT,
        "persistence_guard": guard_active,
    }


def _looks_like_railway() -> bool:
    """Railway injects its service identity into the environment. Used only to
    pick loud persistence messaging on managed deploys; never grants rights."""
    return bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PROJECT_ID"))


def check_persistent_data() -> str | None:
    """Fail-closed persistence guard (launch requirement: data must survive
    Railway redeploys).

    The DB lives in DATA_DIR/spike.db. deploy/Dockerfile.worker sets
    AUTOSTACK_DATA_DIR=/data, but /data is only durable when the operator
    mounts a Railway VOLUME there. On Railway (or whenever
    AUTOSTACK_REQUIRE_PERSISTENT_DATA=1) we refuse to boot a container whose
    data location cannot be trusted as persistent, rather than silently
    starting with an empty DB that the next redeploy will wipe.

    Returns None when persistence is trusted; otherwise a human-readable
    reason. Never inspects file contents — only flags and the presence of an
    explicit data dir."""
    require = os.environ.get("AUTOSTACK_REQUIRE_PERSISTENT_DATA", "").strip() == "1"
    if not (require or _looks_like_railway()):
        return None
    if not data_dir_configured():
        return (
            "AUTOSTACK_DATA_DIR is not set. Persistent storage is required on this "
            "deployment, but the worker would fall back to a container-local "
            "directory that redeploys wipe. Operator steps: (1) attach a Railway "
            "Volume mounted at /data, (2) set AUTOSTACK_DATA_DIR=/data on the "
            "service, (3) redeploy, (4) register the owner account once — after "
            "that, users/workflows/audit survive rebuilds.")
    if not DB_EXISTED_AT_BOOT:
        if os.environ.get("AUTOSTACK_ALLOW_EMPTY_DATA_DIR", "").strip() == "1":
            return None  # first deploy on a genuinely new volume — operator opted in
        return (
            f"Data directory is configured but {DB_PATH} did not exist at boot — "
            "the volume looks EMPTY, so this may be a first deploy (fine — register "
            "the owner once) or a volume attached to the wrong mount point (data "
            "loss risk on redeploy). AUTOSTACK_REQUIRE_PERSISTENT_DATA=1 refuses "
            "to continue on an empty data dir; to boot a genuinely new deployment, "
            "set AUTOSTACK_ALLOW_EMPTY_DATA_DIR=1 for the first deploy only.")
    return None


def _persistence_boot_report() -> None:
    """Startup visibility + enforcement: log the resolved data location facts
    once at import (no secrets), then fail fast when the persistence guard
    trips. Under pytest the function is exercised directly by tests, so import
    stays warning-only (never kills the suite on operator env vars)."""
    rail = " railway" if _looks_like_railway() else ""
    state = "existing" if DB_EXISTED_AT_BOOT else "NEW"
    guard_active = bool(
        os.environ.get("AUTOSTACK_REQUIRE_PERSISTENT_DATA", "").strip() == "1"
        or _looks_like_railway()
    )
    print(
        f"[autostack:persistence]{rail} AUTOSTACK_DATA_DIR={'set' if data_dir_configured() else 'UNSET'} "
        f"data_dir={DATA_DIR} db_path={DB_PATH} db_{state} (existed_at_boot={DB_EXISTED_AT_BOOT}) "
        f"persistence_guard={'active' if guard_active else 'inactive'}",
        flush=True)
    reason = check_persistent_data()
    if reason:
        banner = (
            "\n" + "=" * 78 + "\n"
            "CRITICAL AUTOSTACK STARTUP ERROR: PERSISTENCE GUARD TRIPPED\n"
            "=" * 78 + "\n"
            f"  Environment:        {'Railway' if _looks_like_railway() else 'Production / Guarded'}\n"
            f"  AUTOSTACK_DATA_DIR: {'set (' + str(DATA_DIR) + ')' if data_dir_configured() else 'UNSET'}\n"
            f"  DB_PATH:            {DB_PATH}\n"
            f"  DB Existed At Boot: {DB_EXISTED_AT_BOOT}\n"
            f"  Persistence Guard:  ACTIVE\n"
            "-" * 78 + "\n"
            f"REASON:\n  {reason}\n"
            "-" * 78 + "\n"
            "OPERATOR FIX FOR RAILWAY:\n"
            "  1. Attach a persistent volume mounted at /data on the worker service.\n"
            "  2. In Railway service Variables, set:\n"
            "       AUTOSTACK_DATA_DIR=/data\n"
            "  3. For FIRST DEPLOY on a new/empty volume only, temporarily set:\n"
            "       AUTOSTACK_ALLOW_EMPTY_DATA_DIR=1\n"
            "  4. Redeploy -> worker starts -> register the owner account once.\n"
            "  5. Once /data/spike.db exists, remove AUTOSTACK_ALLOW_EMPTY_DATA_DIR.\n"
            "=" * 78 + "\n"
        )
        print(banner, file=sys.stderr, flush=True)
        if "pytest" not in sys.modules:
            raise SystemExit(
                "AutoStack worker refusing to start: data at this location cannot be "
                "trusted as persistent. Follow the steps in the message above (README: "
                "'Railway persistence').")


_persistence_boot_report()

WORKER_HOST = "127.0.0.1"
WORKER_PORT = 8747
WORKER_URL = f"http://{WORKER_HOST}:{WORKER_PORT}"

NODERED_HOST = "127.0.0.1"
NODERED_PORT = 18790
NODERED_URL = f"http://{NODERED_HOST}:{NODERED_PORT}"

# Session token with STABLE persistence (QA round-2 finding): env wins for
# tests/explicit runs; otherwise the token is reused from artifacts/spike/token
# (gitignored) so restarts never silently 401 the whole stack.
def new_token() -> str:
    return secrets.token_urlsafe(32)


def _load_or_persist_token() -> str:
    env = os.environ.get("AUTOSTACK_TOKEN")
    if env:
        return env
    token_file = DATA_DIR / "token"
    if token_file.is_file():
        value = token_file.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = new_token()
    token_file.write_text(value, encoding="utf-8")
    try:
        token_file.chmod(0o600)
    except OSError:
        pass
    return value


SPIKE_TOKEN = _load_or_persist_token()

# Fixture aliases used by the spike workflow.
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
BEFORE_CSV = FIXTURES_DIR / "clients-before.csv"
AFTER_CSV = FIXTURES_DIR / "clients-after.csv"
RUN_DATE = "2026-09-20"  # C001 and C003 are due on/before this date (expected: 2 drafts)
