"""
Regression tests for background-task resource cleanup and cost-bounding.

Business rules covered:
- Each ResumeAnalyzerService / DreamJobAnalyzerService owns its own
  httpx.AsyncClient. The background-task handlers must close it exactly once,
  on both the success and failure paths — otherwise every analysis run leaks
  a connection/file descriptor (services/*.py:aclose()).
- max_questions is bounded on the interview-creation routes so a careless or
  malicious request can't drive unbounded LLM cost.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from app.server import _run_resume_analysis_bg, _run_dream_job_analysis_bg


class TestResumeAnalysisBgCleanup:
    async def test_closes_client_on_success(self):
        fb = MagicMock()
        mock_svc = MagicMock()
        mock_svc.analyze = AsyncMock(return_value={
            "overall": {}, "sections": [], "ats": {}, "lackings": [],
            "quality_score": 0, "parsed_sections": {}, "usage": {},
        })
        mock_svc.aclose = AsyncMock()

        with patch("app.server.get_firebase_manager", return_value=fb), \
             patch("app.services.resume_analyzer_service.ResumeAnalyzerService", return_value=mock_svc):
            await _run_resume_analysis_bg("uid", "resume text", "resume.pdf", "analysis-1")

        mock_svc.aclose.assert_awaited_once()

    async def test_closes_client_on_failure(self):
        fb = MagicMock()
        mock_svc = MagicMock()
        mock_svc.analyze = AsyncMock(side_effect=RuntimeError("provider down"))
        mock_svc.aclose = AsyncMock()

        with patch("app.server.get_firebase_manager", return_value=fb), \
             patch("app.services.resume_analyzer_service.ResumeAnalyzerService", return_value=mock_svc):
            await _run_resume_analysis_bg("uid", "resume text", "resume.pdf", "analysis-1")

        mock_svc.aclose.assert_awaited_once()
        failed_calls = [
            c for c in fb.update_resume_analysis.call_args_list
            if c.args[1].get("status") == "failed"
        ]
        assert failed_calls, "a provider failure must still mark the analysis failed"


class TestDreamJobAnalysisBgCleanup:
    async def test_closes_client_on_success(self):
        fb = MagicMock()
        fb.get_resume_parsed_doc.return_value = {"working_parsed_sections": {"skills": ["Python"]}}
        mock_svc = MagicMock()
        mock_svc.analyze = AsyncMock(return_value={
            "jd_normalized": {}, "fit_analysis": {}, "usage": {},
        })
        mock_svc.aclose = AsyncMock()

        with patch("app.server.get_firebase_manager", return_value=fb), \
             patch("app.services.dream_job_analyzer_service.DreamJobAnalyzerService", return_value=mock_svc):
            await _run_dream_job_analysis_bg("uid", "job-1", "jd text", "analysis-1")

        mock_svc.aclose.assert_awaited_once()

    async def test_closes_client_on_failure(self):
        fb = MagicMock()
        fb.get_resume_parsed_doc.return_value = {"working_parsed_sections": {}}
        mock_svc = MagicMock()
        mock_svc.analyze = AsyncMock(side_effect=RuntimeError("provider down"))
        mock_svc.aclose = AsyncMock()

        with patch("app.server.get_firebase_manager", return_value=fb), \
             patch("app.services.dream_job_analyzer_service.DreamJobAnalyzerService", return_value=mock_svc):
            await _run_dream_job_analysis_bg("uid", "job-1", "jd text", "analysis-1")

        mock_svc.aclose.assert_awaited_once()
        failed_calls = [
            c for c in fb.update_dream_job.call_args_list
            if c.args[1].get("status") == "failed"
        ]
        assert failed_calls, "a provider failure must still mark the dream job failed"


class TestMaxQuestionsBound:
    def test_interview_prepare_rejects_excessive_max_questions(self, client):
        r = client.post(
            "/interview/prepare",
            data={"interview_type": "Job Interview", "max_questions": "999"},
            files={
                "resume": ("resume.txt", b"resume", "text/plain"),
                "job_description": ("jd.txt", b"jd", "text/plain"),
            },
        )
        assert r.status_code == 422

    def test_interview_start_rejects_excessive_max_questions(self, client):
        r = client.post(
            "/interview/start",
            data={"max_questions": "999"},
            files={
                "resume": ("resume.txt", b"resume", "text/plain"),
                "job_description": ("jd.txt", b"jd", "text/plain"),
            },
        )
        assert r.status_code == 422
