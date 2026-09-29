"""Launch-prep regression tests: SQLite/Railway durability guard + health fields.

The persistence guard (backend/spike_config.py) fails fast at boot when the
data location cannot be trusted as persistent (Railway deploys, or explicitly
via AUTOSTACK_REQUIRE_PERSISTENT_DATA=1). Import of backend.spike_config stays
warning-only under pytest (the module checks sys.modules), so these tests
exercise check_persistent_data() directly.
"""
from __future__ import annotations

import os

from fastapi.testclient import TestClient

import pytest


@pytest.fixture()
def spike_env(monkeypatch):
    """Clean persistence-related env for deterministic assertions."""
    for var in ("AUTOSTACK_DATA_DIR", "AUTOSTACK_REQUIRE_PERSISTENT_DATA",
                "AUTOSTACK_ALLOW_EMPTY_DATA_DIR",
                "RAILWAY_ENVIRONMENT", "RAILWAY_PROJECT_ID"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


# ── check_persistent_data ────────────────────────────────────────────────────

def test_guard_silent_locally(spike_env):
    """No Railway vars + no explicit require flag -> local dev boots untouched."""
    from backend import spike_config as cfg
    assert cfg.check_persistent_data() is None


def test_guard_requires_data_dir_on_railway(spike_env):
    """Railway without AUTOSTACK_DATA_DIR -> refuse, with operator steps."""
    from backend import spike_config as cfg
    spike_env.setenv("RAILWAY_ENVIRONMENT", "production")
    reason = cfg.check_persistent_data()
    assert reason is not None
    assert "AUTOSTACK_DATA_DIR" in reason
    assert "Volume" in reason and "/data" in reason


def test_guard_requires_data_dir_when_forced(spike_env):
    """AUTOSTACK_REQUIRE_PERSISTENT_DATA=1 guards any managed host, not just Railway."""
    from backend import spike_config as cfg
    spike_env.setenv("AUTOSTACK_REQUIRE_PERSISTENT_DATA", "1")
    reason = cfg.check_persistent_data()
    assert reason is not None
    assert "AUTOSTACK_DATA_DIR" in reason


def test_guard_refuses_empty_data_dir_on_railway(spike_env):
    """Railway + DATA_DIR set but DB absent -> empty-volume refusal; the
    AUTOSTACK_ALLOW_EMPTY_DATA_DIR=1 first-deploy hatch clears it."""
    from backend import spike_config as cfg
    spike_env.setenv("RAILWAY_ENVIRONMENT", "production")
    spike_env.setenv("AUTOSTACK_DATA_DIR", "/data")
    # Simulate a fresh volume: the module captured db_exists at import, so a
    # genuinely-absent file at /data on the CI machine is unlikely — force the
    # boot fact for the test instead of depending on container state.
    monkeypatch = spike_env
    monkeypatch.setattr(cfg, "DB_EXISTED_AT_BOOT", False, raising=False)
    reason = cfg.check_persistent_data()
    assert reason is not None
    assert "did not exist at boot" in reason
    assert "AUTOSTACK_ALLOW_EMPTY_DATA_DIR" in reason

    monkeypatch.setenv("AUTOSTACK_ALLOW_EMPTY_DATA_DIR", "1")
    assert cfg.check_persistent_data() is None


def test_guard_trusted_when_db_exists(spike_env):
    """Railway + DATA_DIR + existing DB -> persistence trusted, no warning."""
    from backend import spike_config as cfg
    spike_env.setenv("RAILWAY_ENVIRONMENT", "production")
    spike_env.setenv("AUTOSTACK_DATA_DIR", "/data")
    spike_env.setattr(cfg, "DB_EXISTED_AT_BOOT", True, raising=False)
    assert cfg.check_persistent_data() is None


# ── persistence_summary / health fields ─────────────────────────────────────

def test_persistence_summary_shape(spike_env):
    from backend import spike_config as cfg
    spike_env.setenv("AUTOSTACK_DATA_DIR", "/data")
    spike_env.setenv("AUTOSTACK_REQUIRE_PERSISTENT_DATA", "1")
    summary = cfg.persistence_summary()
    assert summary == {"data_dir_configured": True, "db_exists": cfg.DB_EXISTED_AT_BOOT,
                       "persistence_guard": True}
    # Booleans only — never paths or contents.
    assert all(isinstance(v, bool) for v in summary.values())


def test_health_reports_persistence_fields(spike_env):
    """/api/health gains data_dir_configured / db_exists (booleans, no paths)."""
    from backend.db import Base, get_db
    from backend import db as db_mod
    from backend import roadmap_routes
    from backend.app import app

    TestingSession = db_mod.SessionLocal
    app.dependency_overrides[get_db] = lambda: iter([TestingSession()])
    for module in (db_mod, roadmap_routes):
        if hasattr(module, "SessionLocal"):
            module.SessionLocal = TestingSession

    with TestClient(app) as client:
        res = client.get("/api/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["service"] == "autostack-worker"
        assert isinstance(body["data_dir_configured"], bool)
        assert isinstance(body["db_exists"], bool)
        assert isinstance(body["persistence_guard"], bool)
