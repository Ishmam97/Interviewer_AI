"""
Regression tests for the AI-pipeline fail-loud contract.

Business rule: when the LLM provider errors (bad key, 404 model-not-found,
rate limit, malformed JSON), the analysis MUST raise so the background task
marks the Firestore doc `status: failed`. It must NOT swallow the error and
return an all-zero report that gets persisted as `completed` — that shows the
user an empty report and hides real outages.

These tests would have failed before the fix (the services returned zero-filled
defaults on any exception).
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.resume_analyzer_service import ResumeAnalyzerService
from app.services.dream_job_analyzer_service import DreamJobAnalyzerService


def _service_with_failing_client(service_cls):
    svc = service_cls(api_key="unused-in-test")
    svc._client = MagicMock()
    svc._client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("Error code: 404 - Model not found")
    )
    return svc


def _service_with_bad_json_client(service_cls):
    svc = service_cls(api_key="unused-in-test")
    bad = MagicMock()
    bad.choices = [MagicMock()]
    bad.choices[0].message.content = "not-json{{{"
    bad.usage = None
    svc._client = MagicMock()
    svc._client.chat.completions.create = AsyncMock(return_value=bad)
    return svc


class TestResumeAnalyzerFailLoud:
    async def test_provider_error_raises_not_zeros(self):
        svc = _service_with_failing_client(ResumeAnalyzerService)
        with pytest.raises(Exception):
            await svc.analyze("Some resume text", "resume.pdf")

    async def test_malformed_json_raises(self):
        svc = _service_with_bad_json_client(ResumeAnalyzerService)
        with pytest.raises(Exception):
            await svc.analyze("Some resume text", "resume.pdf")


class TestDreamJobAnalyzerFailLoud:
    async def test_provider_error_raises_not_zeros(self):
        svc = _service_with_failing_client(DreamJobAnalyzerService)
        with pytest.raises(Exception):
            await svc.analyze(
                jd_text="A job description",
                resume_parsed_sections={"skills": ["Python"]},
                resume_text="resume text",
            )

    async def test_malformed_json_raises(self):
        svc = _service_with_bad_json_client(DreamJobAnalyzerService)
        with pytest.raises(Exception):
            await svc.analyze(
                jd_text="A job description",
                resume_parsed_sections={"skills": ["Python"]},
                resume_text="resume text",
            )
