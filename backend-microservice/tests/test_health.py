"""Tests for health-check and admin endpoints (no auth required)."""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert "timestamp" in body


def test_admin_health(client):
    r = client.get("/admin/health")
    assert r.status_code == 200
    body = r.json()
    assert body["api_status"] == "healthy"
    assert "database_status" in body


def test_unknown_route_returns_404(client):
    r = client.get("/does-not-exist")
    assert r.status_code == 404


def test_wrong_method_returns_405(client):
    r = client.put("/health")
    assert r.status_code == 405
