"""Tests for CORS preflight, origin validation, and health check contracts."""
from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from backend.app import app


@pytest.fixture()
def client():
    return TestClient(app)


def test_cors_preflight_vercel_production(client):
    """OPTIONS preflight from production Vercel frontend succeeds with Allow-Origin."""
    headers = {
        "Origin": "https://autostack-in.vercel.app",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
    }
    res = client.options("/api/auth/me", headers=headers)
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "https://autostack-in.vercel.app"
    methods = res.headers.get("access-control-allow-methods", "")
    assert "GET" in methods and "OPTIONS" in methods


def test_cors_preflight_vercel_preview(client):
    """OPTIONS preflight from any *.vercel.app preview domain matches regex."""
    headers = {
        "Origin": "https://autostack-preview-pr123.vercel.app",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type, authorization",
    }
    res = client.options("/api/candidates", headers=headers)
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "https://autostack-preview-pr123.vercel.app"


def test_cors_preflight_unauthorized_origin_rejected(client):
    """OPTIONS preflight from untrusted origin does not receive Allow-Origin."""
    headers = {
        "Origin": "https://untrusted-site.com",
        "Access-Control-Request-Method": "GET",
    }
    res = client.options("/api/auth/me", headers=headers)
    assert "access-control-allow-origin" not in res.headers


def test_cors_error_responses_still_carry_cors_headers(client):
    """When an unauthenticated request returns 401, CORS headers must still be present
    so the browser provides the real 401 error to the frontend rather than an opaque CORS failure."""
    res = client.get("/api/candidates", headers={"Origin": "https://autostack-in.vercel.app"})
    assert res.status_code == 401
    assert res.headers.get("access-control-allow-origin") == "https://autostack-in.vercel.app"


def test_health_endpoint_contract(client):
    """Health endpoint responds with 200, fast status: ok, and safe booleans only."""
    res = client.get("/api/health", headers={"Origin": "https://autostack-in.vercel.app"})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "https://autostack-in.vercel.app"
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "autostack-worker"
    assert "ts" in body
    assert isinstance(body["data_dir_configured"], bool)
    assert isinstance(body["db_exists"], bool)
    assert isinstance(body["persistence_guard"], bool)
    # Ensure no secrets or sensitive file system paths are exposed
    body_str = str(body).lower()
    assert "token" not in body_str
    assert "secret" not in body_str
    assert "\\" not in body_str


def test_demo_account_auth(client):
    """POST /api/auth/demo issues a valid session token for a demo operator."""
    res = client.post("/api/auth/demo", headers={"Origin": "https://autostack-in.vercel.app"})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "https://autostack-in.vercel.app"
    data = res.json()
    assert "token" in data
    assert data["username"] == "demo"
    assert data["is_demo"] is True

    # Token works with authenticated endpoints
    me_res = client.get("/api/auth/me", headers={
        "Authorization": f"Bearer {data['token']}",
        "Origin": "https://autostack-in.vercel.app",
    })
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["user"]["username"] == "demo"
    assert me_data["role"] in ("owner", "operator")

