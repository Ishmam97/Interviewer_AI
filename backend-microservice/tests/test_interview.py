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
        assert r.json() == {"sessions": [], "next_cursor": None}

    def test_get_sessions_returns_list(self):
        fb = _make_firebase_mock()
        fb.get_user_interview_sessions.return_value = [
            {"id": "s1", "title": "Session 1", "status": "completed"},
        ]
        with authed_client(fb) as c:
            r = c.get("/interview/sessions")
        assert r.status_code == 200
        assert len(r.json()["sessions"]) == 1

    def test_sessions_page_full_returns_next_cursor(self):
        """A full page (len == limit) signals there may be more — next_cursor
        must carry the last doc's created_at so the client can page on."""
        fb = _make_firebase_mock()
        fb.get_user_interview_sessions.return_value = [
            {"id": "s1", "created_at": "2026-01-01T00:00:00"},
            {"id": "s2", "created_at": "2026-01-02T00:00:00"},
        ]
        with authed_client(fb) as c:
            r = c.get("/interview/sessions?limit=2")
        assert r.status_code == 200
        assert r.json()["next_cursor"] == "2026-01-02T00:00:00"

    def test_sessions_page_short_returns_no_next_cursor(self):
        """Fewer results than the limit means the list is exhausted."""
        fb = _make_firebase_mock()
        fb.get_user_interview_sessions.return_value = [
            {"id": "s1", "created_at": "2026-01-01T00:00:00"},
        ]
        with authed_client(fb) as c:
            r = c.get("/interview/sessions?limit=50")
        assert r.status_code == 200
        assert r.json()["next_cursor"] is None

    def test_sessions_cursor_forwarded_to_firebase(self):
        """The `cursor` query param must reach FirebaseManager as start_after
        so pagination actually advances instead of always returning page one."""
        fb = _make_firebase_mock()
        fb.get_user_interview_sessions.return_value = []
        with authed_client(fb) as c:
            c.get("/interview/sessions?cursor=2026-01-01T00:00:00")
        fb.get_user_interview_sessions.assert_called_once_with(
            "test-uid-123", 50, start_after="2026-01-01T00:00:00"
        )

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
        assert r.json() == {"reports": [], "next_cursor": None}

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
        firebase_mock.get_report_by_session.return_value = None
        r = client.get("/interview/nonexistent-session/report")
        assert r.status_code == 404

    def test_report_from_firestore(self):
        fb = _make_firebase_mock()
        fb.get_report_by_session.return_value = {
            "id": "report-1",
            "session_id": "session-abc",
            "report_content": "Great performance overall.",
        }
        with authed_client(fb) as c:
            r = c.get("/interview/session-abc/report")
        assert r.status_code == 200
        assert r.json()["content"] == "Great performance overall."

    def test_report_lookup_does_not_scan_recent_reports_list(self):
        """Regression for #32a: the route must not linearly scan
        get_user_reports (only the 50 most-recent reports) to find a match —
        that 404s for any interview older than a user's 50 latest reports.
        It must instead query directly by (user_id, session_id)."""
        fb = _make_firebase_mock()
        # Simulate the old bug scenario: the target report is NOT among the
        # 50 most-recent (get_user_reports returns none matching), but a
        # direct query for it succeeds.
        fb.get_user_reports.return_value = []
        fb.get_report_by_session.return_value = {
            "id": "report-old",
            "session_id": "old-session",
            "report_content": "An old but valid report.",
        }
        with authed_client(fb) as c:
            r = c.get("/interview/old-session/report")
        assert r.status_code == 200
        assert r.json()["content"] == "An old but valid report."
        fb.get_report_by_session.assert_called_once_with("test-uid-123", "old-session")


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

    def test_start_uses_session_scoped_faiss_index_path(self):
        """Regression: every interview must get its own FAISS index_path.

        Before this fix, InterviewConfig.index_path defaulted to a single
        shared path, so a later session's setup_rag_system() could silently
        load a PREVIOUS (possibly different user's) session's index instead
        of rebuilding — leaking that user's resume/JD into this RAG context.
        """
        fb = _make_firebase_mock()

        configs_seen = []

        def _capture_config(**kwargs):
            configs_seen.append(kwargs["config"])
            return _mock_interview_system()

        with patch("app.server._create_interview_system", side_effect=_capture_config):
            with authed_client(fb) as c:
                r1 = c.post(
                    "/interview/start",
                    data={"max_questions": "2"},
                    files=make_upload_files(),
                )
                r2 = c.post(
                    "/interview/start",
                    data={"max_questions": "2"},
                    files=make_upload_files(),
                )

        assert r1.status_code == 200 and r2.status_code == 200
        session_id_1 = r1.json()["session_id"]
        session_id_2 = r2.json()["session_id"]
        assert session_id_1 != session_id_2

        assert len(configs_seen) == 2
        path_1, path_2 = configs_seen[0].index_path, configs_seen[1].index_path
        assert path_1 != path_2
        assert session_id_1 in path_1
        assert session_id_2 in path_2

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
        assert "expired" in r.json()["detail"].lower()

    def test_answer_missing_fields(self, client):
        r = client.post("/interview/answer", json={"session_id": "abc"})
        assert r.status_code == 422

    def test_answer_success_offloads_blocking_calls(self, client):
        """process_candidate_answer / get_next_question run synchronous LLM+FAISS
        calls; they must be invoked via asyncio.to_thread rather than directly
        on the event loop. A MagicMock works identically either way, so this
        also verifies the happy path still returns the right shape."""
        from app.server import _active_sessions

        mock_sys = MagicMock()
        mock_sys.process_candidate_answer.return_value = {
            "interview_notes": [{"score": 8, "analysis": "Good answer"}],
            "current_question_idx": 1,
            "interview_plan": [{"question": "Q1"}, {"question": "Q2"}],
        }
        mock_sys.get_next_question.return_value = "Q2"

        _active_sessions["test-session-1"] = {
            "interview_system": mock_sys,
            "interview_state": {"current_question_idx": 0, "interview_plan": []},
            "user_id": "test-uid-123",
            "created_at": "2026-01-01T00:00:00",
        }
        try:
            r = client.post("/interview/answer", json={
                "session_id": "test-session-1",
                "answer": "My answer",
            })
        finally:
            _active_sessions.pop("test-session-1", None)

        assert r.status_code == 200
        body = r.json()
        assert body["score"] == 8
        assert body["is_complete"] is False
        assert body["next_question"] == "Q2"
        mock_sys.process_candidate_answer.assert_called_once()
        mock_sys.get_next_question.assert_called_once()
