"""Tests for /profile and /profile/resume endpoints."""

from contextlib import contextmanager
from unittest.mock import patch
from fastapi.testclient import TestClient
from tests.conftest import _make_firebase_mock, FAKE_USER


@contextmanager
def authed_client(fb):
    with patch("app.server.get_firebase_manager", return_value=fb):
        from app.server import app, get_current_user
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c
        app.dependency_overrides.clear()


class TestProfile:
    def test_get_profile(self):
        fb = _make_firebase_mock()
        fb.get_user_profile.return_value = {
            "uid": "test-uid-123",
            "email": "test@example.com",
            "full_name": "Test User",
            "profile_complete": True,
        }
        with authed_client(fb) as c:
            r = c.get("/profile")
        assert r.status_code == 200
        assert r.json()["profile"]["email"] == "test@example.com"

    def test_get_profile_not_found(self):
        fb = _make_firebase_mock()
        fb.get_user_profile.return_value = None
        with authed_client(fb) as c:
            r = c.get("/profile")
        assert r.status_code == 404

    def test_update_profile(self, client):
        r = client.put("/profile", json={"full_name": "Updated Name"})
        assert r.status_code == 200
        assert r.json()["message"] == "Profile updated successfully"

    def test_get_resume_analysis_none(self, client, firebase_mock):
        firebase_mock.get_resume_data.return_value = None
        r = client.get("/profile/resume/analysis")
        assert r.status_code == 404

    def test_get_resume_analysis_exists(self):
        fb = _make_firebase_mock()
        fb.get_resume_data.return_value = {
            "resume_analysis": {"skills": ["Python", "FastAPI"]},
            "filename": "resume.pdf",
        }
        with authed_client(fb) as c:
            r = c.get("/profile/resume/analysis")
        assert r.status_code == 200
        assert "resume_analysis" in r.json()

    def test_upload_resume_invalid_extension(self, client):
        r = client.post(
            "/profile/resume",
            files={"resume": ("resume.exe", b"data", "application/octet-stream")},
        )
        assert r.status_code == 400

    def test_upload_resume_empty(self, client):
        r = client.post(
            "/profile/resume",
            files={"resume": ("resume.txt", b"", "text/plain")},
        )
        assert r.status_code == 400

    def test_upload_resume_create_analysis_failure_returns_500(self, client, firebase_mock):
        """If create_resume_analysis fails, the route must not enqueue a background
        task against a doc that doesn't exist — the client would then poll a
        status that 404s forever with no way to recover."""
        firebase_mock.create_resume_analysis.return_value = False
        r = client.post(
            "/profile/resume",
            files={"resume": ("resume.txt", b"Some resume content", "text/plain")},
        )
        assert r.status_code == 500
        firebase_mock.update_resume_analysis.assert_not_called()
