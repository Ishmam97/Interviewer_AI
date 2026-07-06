"""
Tests for /interview/* , /reports , and /dashboard endpoints.
LLM / interview system calls are mocked so these run without Gemini.
"""

import pytest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from tests.conftest import make_upload_files, _make_firebase_mock, FAKE_USER


@contextmanager
def authed_client(fb):
    """Context manager: authenticated TestClient with mocked Firebase."""
    with patch("app.server.get_firebase_manager", return_value=fb):
        from app.server import app, get_current_user
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c
        app.dependency_overrides.clear()


@contextmanager
def unauthed_client(fb):
    """Context manager: unauthenticated TestClient — raises 401."""
    with patch("app.server.get_firebase_manager", return_value=fb):
        from app.server import app
        app.dependency_overrides.clear()
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# ── /interview/sessions ───────────────────────────────────────────────────────

class TestSessions:
    def test_get_sessions_empty(self, client):
        r = client.get("/interview/sessions")
        assert r.status_code == 200
        assert r.json() == {"sessions": []}

    def test_get_sessions_returns_list(self):
        fb = _make_firebase_mock()
        fb.get_user_interview_sessions.return_value = [
            {"id": "s1", "title": "Session 1", "status": "completed"},
        ]
        with authed_client(fb) as c:
            r = c.get("/interview/sessions")
        assert r.status_code == 200
        assert len(r.json()["sessions"]) == 1

    def test_sessions_unauthenticated(self):
        fb = _make_firebase_mock()
        fb.verify_id_token.return_value = None
        with unauthed_client(fb) as c:
            r = c.get(
                "/interview/sessions",
                headers={"Authorization": "Bearer bad-token"},
            )
        assert r.status_code == 401


# ── /reports ──────────────────────────────────────────────────────────────────

class TestReports:
    def test_get_reports_empty(self, client):
        r = client.get("/reports")
        assert r.status_code == 200
        assert r.json() == {"reports": []}

    def test_reports_unauthenticated(self):
        fb = _make_firebase_mock()
        fb.verify_id_token.return_value = None
        with unauthed_client(fb) as c:
            r = c.get("/reports", headers={"Authorization": "Bearer bad"})
        assert r.status_code == 401


# ── /dashboard/stats ─────────────────────────────────────────────────────────

class TestDashboard:
    def test_dashboard_stats(self):
        fb = _make_firebase_mock()
        fb.get_user_dashboard_stats.return_value = {
            "total_interviews": 5,
            "completed_interviews": 3,
            "average_score": 7.2,
            "total_reports": 3,
        }
        with authed_client(fb) as c:
            r = c.get("/dashboard/stats")
        assert r.status_code == 200
        body = r.json()
        assert body["total_interviews"] == 5
        assert "average_score" in body


# ── /interview/{session_id}/report ───────────────────────────────────────────

class TestReport:
    def test_report_not_found(self, client, firebase_mock):
        firebase_mock.get_user_reports.return_value = []
        r = client.get("/interview/nonexistent-session/report")
        assert r.status_code == 404

    def test_report_from_firestore(self):
        fb = _make_firebase_mock()
        fb.get_user_reports.return_value = [
            {
                "id": "report-1",
                "session_id": "session-abc",
                "report_content": "Great performance overall.",
            }
        ]
        with authed_client(fb) as c:
            r = c.get("/interview/session-abc/report")
        assert r.status_code == 200
        assert r.json()["content"] == "Great performance overall."


# ── /interview/start ──────────────────────────────────────────────────────────

def _mock_interview_system():
    sys = MagicMock()
    sys.start_interactive_interview.return_value = {
        "resume_content": "Alice resume",
        "job_description": "FastAPI job",
        "interview_plan": [
            {"question": "Tell me about FastAPI", "category": "technical"},
            {"question": "Describe a hard bug", "category": "behavioral"},
        ],
        "current_question_idx": 0,
        "interview_notes": [],
        "conversation_history": [],
        "interview_report": "",
        "rag_context": "",
        "next_action": "",
        "is_complete": False,
    }
    sys.get_next_question.return_value = "Tell me about FastAPI"
    return sys


class TestInterviewStart:
    def test_start_success(self):
        fb = _make_firebase_mock()
        mock_sys = _mock_interview_system()
        with patch("app.server._create_interview_system", return_value=mock_sys):
            with authed_client(fb) as c:
                r = c.post(
                    "/interview/start",
                    data={"max_questions": "2", "model_name": "gemini-2.0-flash", "temperature": "0.3"},
                    files=make_upload_files(),
                )
        assert r.status_code == 200
        body = r.json()
        assert "session_id" in body
        assert body["current_question"] == "Tell me about FastAPI"
        assert body["is_complete"] is False
        assert body["total_questions"] == 2

    def test_start_unauthenticated(self):
        fb = _make_firebase_mock()
        fb.verify_id_token.return_value = None
        with unauthed_client(fb) as c:
            r = c.post(
                "/interview/start",
                data={"max_questions": "2"},
                files=make_upload_files(),
                headers={"Authorization": "Bearer bad"},
            )
        assert r.status_code == 401

    def test_start_missing_files(self, client):
        r = client.post("/interview/start", data={"max_questions": "2"})
        assert r.status_code == 422

    def test_start_invalid_extension(self, client):
        r = client.post(
            "/interview/start",
            data={"max_questions": "2"},
            files={
                "resume": ("resume.exe", b"bad", "application/octet-stream"),
                "job_description": ("jd.txt", b"jd", "text/plain"),
            },
        )
        assert r.status_code == 400

    def test_start_empty_file(self, client):
        r = client.post(
            "/interview/start",
            data={"max_questions": "2"},
            files={
                "resume": ("resume.txt", b"", "text/plain"),
                "job_description": ("jd.txt", b"jd", "text/plain"),
            },
        )
        assert r.status_code == 400


# ── /interview/answer ─────────────────────────────────────────────────────────

class TestInterviewAnswer:
    def test_answer_unknown_session(self, client):
        r = client.post("/interview/answer", json={
            "session_id": "does-not-exist",
            "answer": "My answer",
        })
        assert r.status_code == 404

    def test_answer_missing_fields(self, client):
        r = client.post("/interview/answer", json={"session_id": "abc"})
        assert r.status_code == 422
