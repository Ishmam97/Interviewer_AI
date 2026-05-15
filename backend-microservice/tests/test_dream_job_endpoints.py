"""
Tests for Dream Job REST endpoints.

Scope: happy path for every endpoint + key error paths.
Uses the same pattern as test_suggestion_apply.py:
  - `_make_firebase_mock()` from conftest for a fully-mocked Firebase
  - `app.dependency_overrides[get_current_user] = lambda: FAKE_USER`
  - `patch("app.server.get_firebase_manager", return_value=fb)`

All tests are synchronous (pytest-asyncio not installed; endpoints are driven
via FastAPI's synchronous TestClient).
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import _make_firebase_mock, FAKE_USER

# ── Shared fixtures ───────────────────────────────────────────────────────────

FAKE_UID = "test-uid-123"
FAKE_DREAM_JOB_ID = "dj-abc-123"
FAKE_ANALYSIS_ID = "analysis-123"

DUMMY_RESUME_ANALYSIS = {
    "id": FAKE_ANALYSIS_ID,
    "analysis_id": FAKE_ANALYSIS_ID,
    "user_id": FAKE_UID,
    "status": "completed",
    "filename": "resume.pdf",
    "overall": {"score": 80},
    "sections": [],
    "ats": {},
    "lackings": [],
    "quality_score": 80,
}

DUMMY_DREAM_JOB_DOC = {
    "id": FAKE_DREAM_JOB_ID,
    "dream_job_id": FAKE_DREAM_JOB_ID,
    "uid": FAKE_UID,
    "company": "Acme Corp",
    "role_title": "Senior Python Engineer",
    "jd_text": "We need Python, FastAPI, PostgreSQL.",
    "jd_normalized": {
        "role_title": "Senior Python Engineer",
        "company": "Acme Corp",
        "seniority": "Senior",
        "must_have_skills": ["Python", "FastAPI"],
        "nice_to_have_skills": ["Redis"],
        "responsibilities": ["Design APIs"],
        "keywords": ["Python", "FastAPI"],
    },
    "source": "manual",
    "source_url": None,
    "resume_analysis_id": FAKE_ANALYSIS_ID,
    "status": "completed",
    "current_step": "completed",
    "error": None,
    "result": {
        "fit_score": 82,
        "interview_chance": 70,
        "fit_summary": "Strong match.",
        "matching_strengths": ["Python", "FastAPI"],
        "gaps": [],
        "points_to_improve": [],
        "resume_tailoring_plan": [],
        "suggested_projects": [],
        "ats_keyword_coverage": {"matched": ["Python"], "missing": []},
    },
    "usage": {"prompt_tokens": 300, "completion_tokens": 150, "total_tokens": 450},
    "created_at": "2026-05-04T00:00:00",
    "updated_at": "2026-05-04T00:01:00",
}

DUMMY_DREAM_JOB_SUMMARY = {
    "id": FAKE_DREAM_JOB_ID,
    "dream_job_id": FAKE_DREAM_JOB_ID,
    "company": "Acme Corp",
    "role_title": "Senior Python Engineer",
    "source": "manual",
    "source_url": None,
    "resume_analysis_id": FAKE_ANALYSIS_ID,
    "status": "completed",
    "current_step": "completed",
    "fit_score": 82,
    "interview_chance": 70,
    "created_at": "2026-05-04T00:00:00",
    "updated_at": "2026-05-04T00:01:00",
}


@contextmanager
def authed_client(fb):
    """Authenticated TestClient with mocked Firebase."""
    with patch("app.server.get_firebase_manager", return_value=fb):
        from app.server import app, get_current_user
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c
        app.dependency_overrides.clear()


# ── POST /dream-job/from-link ─────────────────────────────────────────────────

class TestDreamJobFromLink:

    def test_from_link_success(self):
        """Happy path: successful URL parse returns prefill fields."""
        parsed_result = {
            "company": "Acme Corp",
            "role_title": "Data Engineer",
            "location": "Remote",
            "jd_text": "We need Spark and Python.",
            "source": "greenhouse",
            "source_url": "https://boards.greenhouse.io/acme/jobs/99",
            "error": None,
        }
        fb = _make_firebase_mock()
        with authed_client(fb) as c:
            with patch(
                "app.services.job_link_parser.parse_job_url", new=AsyncMock(return_value=parsed_result)
            ) as _mock_parser:
                r = c.post(
                    "/dream-job/from-link",
                    json={"url": "https://boards.greenhouse.io/acme/jobs/99"},
                )
        assert r.status_code == 200
        data = r.json()
        assert data["role_title"] == "Data Engineer"
        assert data["company"] == "Acme Corp"
        assert data["jd_text"] == "We need Spark and Python."
        assert data["error"] is None

    def test_from_link_url_rejected_returns_400(self):
        """SSRF-blocked URL → 400."""
        fb = _make_firebase_mock()
        with authed_client(fb) as c:
            with patch(
                "app.services.job_link_parser.parse_job_url",
                new=AsyncMock(return_value={
                    "company": None, "role_title": None, "location": None,
                    "jd_text": "", "source": "generic",
                    "source_url": "http://localhost/admin", "error": "url_rejected",
                }),
            ):
                r = c.post(
                    "/dream-job/from-link",
                    json={"url": "http://localhost/admin"},
                )
        assert r.status_code == 400

    def test_from_link_linkedin_blocked_returns_warning(self):
        """LinkedIn blocked → 200 with error=linkedin_blocked so frontend can handle."""
        fb = _make_firebase_mock()
        with authed_client(fb) as c:
            with patch(
                "app.services.job_link_parser.parse_job_url",
                new=AsyncMock(return_value={
                    "company": None, "role_title": None, "location": None,
                    "jd_text": "", "source": "linkedin",
                    "source_url": "https://linkedin.com/jobs/view/1", "error": "linkedin_blocked",
                }),
            ):
                r = c.post(
                    "/dream-job/from-link",
                    json={"url": "https://linkedin.com/jobs/view/1"},
                )
        assert r.status_code == 200
        assert r.json()["error"] == "linkedin_blocked"


# ── POST /dream-job ───────────────────────────────────────────────────────────

class TestCreateDreamJob:

    def test_create_dream_job_happy_path(self):
        """Valid request creates a Firestore doc and queues background task."""
        fb = _make_firebase_mock()
        fb.get_resume_analysis_by_id.return_value = DUMMY_RESUME_ANALYSIS
        fb.create_dream_job.return_value = True

        with authed_client(fb) as c:
            with patch("app.server._run_dream_job_analysis_bg") as mock_bg:
                r = c.post("/dream-job", json={
                    "company": "Acme Corp",
                    "role_title": "Senior Python Engineer",
                    "jd_text": "We need Python, FastAPI.",
                    "source": "manual",
                    "resume_analysis_id": FAKE_ANALYSIS_ID,
                })

        assert r.status_code == 200
        data = r.json()
        assert "dream_job_id" in data
        assert data["status"] == "pending"
        fb.create_dream_job.assert_called_once()

    def test_create_dream_job_resume_not_found_returns_404(self):
        """If resume analysis doesn't exist → 404."""
        fb = _make_firebase_mock()
        fb.get_resume_analysis_by_id.return_value = None

        with authed_client(fb) as c:
            r = c.post("/dream-job", json={
                "company": "Acme",
                "role_title": "Engineer",
                "jd_text": "Python needed.",
                "source": "manual",
                "resume_analysis_id": "nonexistent-id",
            })
        assert r.status_code == 404

    def test_create_dream_job_wrong_owner_returns_403(self):
        """Resume owned by a different user → 403."""
        fb = _make_firebase_mock()
        fb.get_resume_analysis_by_id.return_value = {
            **DUMMY_RESUME_ANALYSIS,
            "user_id": "other-user-uid",
        }

        with authed_client(fb) as c:
            r = c.post("/dream-job", json={
                "company": "Acme",
                "role_title": "Engineer",
                "jd_text": "Python needed.",
                "source": "manual",
                "resume_analysis_id": FAKE_ANALYSIS_ID,
            })
        assert r.status_code == 403

    def test_create_dream_job_resume_not_completed_returns_400(self):
        """Resume still processing → 400."""
        fb = _make_firebase_mock()
        fb.get_resume_analysis_by_id.return_value = {
            **DUMMY_RESUME_ANALYSIS,
            "status": "processing",
        }

        with authed_client(fb) as c:
            r = c.post("/dream-job", json={
                "company": "Acme",
                "role_title": "Engineer",
                "jd_text": "Python needed.",
                "source": "manual",
                "resume_analysis_id": FAKE_ANALYSIS_ID,
            })
        assert r.status_code == 400


# ── GET /dream-job/{id}/status ────────────────────────────────────────────────

class TestGetDreamJobStatus:

    def test_status_happy_path(self):
        """Returns status + current_step for own job."""
        fb = _make_firebase_mock()
        fb.get_dream_job_by_id.return_value = {
            **DUMMY_DREAM_JOB_DOC,
            "status": "analyzing",
            "current_step": "analyzing_fit",
        }

        with authed_client(fb) as c:
            r = c.get(f"/dream-job/{FAKE_DREAM_JOB_ID}/status")

        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "analyzing"
        assert data["current_step"] == "analyzing_fit"
        assert "dream_job_id" in data

    def test_status_not_found_returns_404(self):
        fb = _make_firebase_mock()
        fb.get_dream_job_by_id.return_value = None

        with authed_client(fb) as c:
            r = c.get("/dream-job/nonexistent/status")
        assert r.status_code == 404

    def test_status_wrong_owner_returns_403(self):
        fb = _make_firebase_mock()
        fb.get_dream_job_by_id.return_value = {**DUMMY_DREAM_JOB_DOC, "uid": "other-uid"}

        with authed_client(fb) as c:
            r = c.get(f"/dream-job/{FAKE_DREAM_JOB_ID}/status")
        assert r.status_code == 403


# ── GET /dream-job/{id} ───────────────────────────────────────────────────────

class TestGetDreamJob:

    def test_get_dream_job_happy_path(self):
        """Returns full doc for own job."""
        fb = _make_firebase_mock()
        fb.get_dream_job_by_id.return_value = DUMMY_DREAM_JOB_DOC

        with authed_client(fb) as c:
            r = c.get(f"/dream-job/{FAKE_DREAM_JOB_ID}")

        assert r.status_code == 200
        data = r.json()
        assert data["company"] == "Acme Corp"
        assert data["result"]["fit_score"] == 82

    def test_get_dream_job_not_found_returns_404(self):
        fb = _make_firebase_mock()
        fb.get_dream_job_by_id.return_value = None

        with authed_client(fb) as c:
            r = c.get(f"/dream-job/{FAKE_DREAM_JOB_ID}")
        assert r.status_code == 404

    def test_get_dream_job_wrong_owner_returns_403(self):
        fb = _make_firebase_mock()
        fb.get_dream_job_by_id.return_value = {**DUMMY_DREAM_JOB_DOC, "uid": "other-uid"}

        with authed_client(fb) as c:
            r = c.get(f"/dream-job/{FAKE_DREAM_JOB_ID}")
        assert r.status_code == 403


# ── GET /dream-jobs ───────────────────────────────────────────────────────────

class TestListDreamJobs:

    def test_list_dream_jobs_happy_path(self):
        """Returns list of summary records for the user."""
        fb = _make_firebase_mock()
        fb.list_user_dream_jobs.return_value = [DUMMY_DREAM_JOB_SUMMARY]

        with authed_client(fb) as c:
            r = c.get("/dream-jobs")

        assert r.status_code == 200
        data = r.json()
        assert "dream_jobs" in data
        assert len(data["dream_jobs"]) == 1
        assert data["dream_jobs"][0]["company"] == "Acme Corp"
        assert data["dream_jobs"][0]["fit_score"] == 82
        fb.list_user_dream_jobs.assert_called_once_with(FAKE_UID)

    def test_list_dream_jobs_empty(self):
        """Returns empty list when user has no dream jobs."""
        fb = _make_firebase_mock()
        fb.list_user_dream_jobs.return_value = []

        with authed_client(fb) as c:
            r = c.get("/dream-jobs")

        assert r.status_code == 200
        assert r.json()["dream_jobs"] == []


# ── DELETE /dream-job/{id} ────────────────────────────────────────────────────

class TestDeleteDreamJob:

    def test_delete_dream_job_happy_path(self):
        """Successfully deletes own dream job."""
        fb = _make_firebase_mock()
        fb.delete_dream_job.return_value = True

        with authed_client(fb) as c:
            r = c.delete(f"/dream-job/{FAKE_DREAM_JOB_ID}")

        assert r.status_code == 200
        data = r.json()
        assert data["dream_job_id"] == FAKE_DREAM_JOB_ID
        fb.delete_dream_job.assert_called_once_with(FAKE_DREAM_JOB_ID, FAKE_UID)

    def test_delete_dream_job_not_found_returns_404(self):
        """Deleting non-existent or foreign dream job → 404."""
        fb = _make_firebase_mock()
        fb.delete_dream_job.return_value = False

        with authed_client(fb) as c:
            r = c.delete(f"/dream-job/nonexistent")
        assert r.status_code == 404
