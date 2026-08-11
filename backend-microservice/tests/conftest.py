"""
Shared pytest fixtures.

All external I/O (Firebase, Gemini LLM) is mocked so tests run without
credentials or real APIs.

Fixtures are function-scoped so each test gets a fresh mock state.
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# ── Minimal env so pydantic-settings doesn't blow up ──────────────────────────
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("FIREBASE_API_KEY", "test-firebase-key")
os.environ.setdefault("FIREBASE_PROJECT_ID", "test-project")
os.environ.setdefault("ENVIRONMENT", "test")

# ── Fake user returned by authenticated requests ─────────────────────────────
FAKE_USER = type("User", (), {
    "uid": "test-uid-123",
    "sub": "test-uid-123",
    "email": "test@example.com",
    "name": "Test User",
    "user_metadata": {},
})()


def _make_firebase_mock():
    fb = MagicMock()
    fb.verify_id_token.return_value = {
        "uid": "test-uid-123",
        "email": "test@example.com",
        "name": "Test User",
    }
    fb.get_interview_session.return_value = None
    fb.create_interview_session.return_value = "session-id-123"
    fb.update_interview_session.return_value = True
    fb.get_user_interview_sessions.return_value = []
    fb.get_user_reports.return_value = []
    fb.get_user_dashboard_stats.return_value = {
        "total_interviews": 0,
        "completed_interviews": 0,
        "average_score": 0,
        "total_reports": 0,
    }
    fb.test_connection.return_value = {"success": True}
    fb.sweep_stale_resume_analyses.return_value = 0
    fb.sweep_stale_dream_jobs.return_value = 0
    fb.get_user_profile.return_value = {
        "uid": "test-uid-123",
        "email": "test@example.com",
    }
    fb.update_user_profile_full.return_value = True
    fb.get_or_create_user_profile.return_value = {
        "data": {"uid": "test-uid-123"},
        "is_new": False,
    }
    fb.store_resume_data.return_value = True
    fb.get_resume_data.return_value = None
    fb.save_interview_report.return_value = "report-id-123"
    fb.sign_up.return_value = {
        "success": True,
        "user": {"uid": "test-uid-123", "email": "test@example.com"},
        "custom_token": "custom-token",
    }
    fb.sign_in.return_value = {
        "success": True,
        "user": {"uid": "test-uid-123", "email": "test@example.com"},
        "session": {"access_token": "id-token-abc"},
    }
    fb.exchange_custom_token.return_value = "id-token-abc"
    return fb


@pytest.fixture()
def firebase_mock():
    return _make_firebase_mock()


@pytest.fixture()
def client(firebase_mock):
    """
    Authenticated TestClient — get_current_user always returns FAKE_USER.
    Firebase is fully mocked.
    """
    with patch("app.server.get_firebase_manager", return_value=firebase_mock):
        from app.server import app, get_current_user
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c
        app.dependency_overrides.clear()


@pytest.fixture()
def unauthed_client(firebase_mock):
    """
    Unauthenticated TestClient — NO dependency override, so real token
    verification runs (mocked to return None → 401).
    """
    with patch("app.server.get_firebase_manager", return_value=firebase_mock):
        # Ensure no lingering overrides from a previous fixture in this process
        from app.server import app
        app.dependency_overrides.clear()
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# ── File upload helpers ───────────────────────────────────────────────────────

def make_upload_files(
    resume_text: str = "Alice Smith\nPython Developer\n5 years FastAPI",
    jd_text: str = "Python Engineer needed. FastAPI required.",
):
    return {
        "resume": ("resume.txt", resume_text.encode(), "text/plain"),
        "job_description": ("job_description.txt", jd_text.encode(), "text/plain"),
    }
