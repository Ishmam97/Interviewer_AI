"""
Tests for dream_job_analyzer_service.py and job_link_parser.py.

Scope (per task spec): happy path + one error path per component.
Edge-case expansion is left for test-eng.

All tests are synchronous and use asyncio.run() to drive async functions,
since pytest-asyncio is not installed in this environment.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ── Fixtures ──────────────────────────────────────────────────────────────────

DUMMY_JD_TEXT = (
    "We are looking for a Senior Python Engineer to join our backend team. "
    "Must have: Python, FastAPI, PostgreSQL. "
    "Nice to have: Redis, Docker, Kubernetes. "
    "Responsibilities: design APIs, mentor juniors, lead code reviews."
)

DUMMY_RESUME_SECTIONS = {
    "name": "Alice Smith",
    "summary": "Python developer with 5 years of FastAPI experience.",
    "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
    "experience": [
        {
            "title": "Software Engineer",
            "company": "TechCorp",
            "duration": "2020 - Present",
            "bullets": ["Built REST APIs", "Deployed on AWS"],
        }
    ],
    "education": [{"degree": "B.S. CS", "institution": "MIT", "year": "2019"}],
    "projects": [],
    "certifications": [],
}

DUMMY_RESUME_TEXT = "Alice Smith\nSenior Python developer\nFastAPI, PostgreSQL, Docker"

DUMMY_JD_NORMALIZED = {
    "role_title": "Senior Python Engineer",
    "company": "Acme Corp",
    "seniority": "Senior",
    "must_have_skills": ["Python", "FastAPI", "PostgreSQL"],
    "nice_to_have_skills": ["Redis", "Docker", "Kubernetes"],
    "responsibilities": ["Design APIs", "Mentor juniors"],
    "keywords": ["Python", "FastAPI", "REST", "API"],
}

DUMMY_FIT_ANALYSIS = {
    "fit_score": 82,
    "interview_chance": 70,
    "fit_summary": "Strong match on core Python/FastAPI stack. Missing Redis experience.",
    "matching_strengths": ["Python", "FastAPI", "PostgreSQL"],
    "gaps": [
        {"skill": "Redis", "importance": "Medium", "time_to_learn": "2 weeks"},
        {"skill": "Kubernetes", "importance": "Low", "time_to_learn": "1 month"},
    ],
    "points_to_improve": ["Add quantified metrics to experience bullets"],
    "resume_tailoring_plan": [
        {
            "section": "summary",
            "action": "Mention senior-level leadership",
            "rationale": "JD emphasises mentoring",
        }
    ],
    "suggested_projects": [
        {
            "title": "Redis Cache Layer",
            "description": "Add caching to an existing FastAPI project",
            "skills_demonstrated": ["Redis", "FastAPI"],
        }
    ],
    "ats_keyword_coverage": {
        "matched": ["Python", "FastAPI", "PostgreSQL"],
        "missing": ["Redis", "Kubernetes"],
    },
}


def _make_openai_mock(normalize_response: dict, fit_response: dict):
    """Return an AsyncOpenAI mock whose create() alternates between two responses."""
    responses = [normalize_response, fit_response]
    call_count = {"n": 0}

    async def _create(**kwargs):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = json.dumps(responses[idx])
        mock_resp.usage = MagicMock()
        mock_resp.usage.prompt_tokens = 200
        mock_resp.usage.completion_tokens = 100
        mock_resp.usage.total_tokens = 300
        return mock_resp

    mock_client = MagicMock()
    mock_client.chat.completions.create = _create
    return mock_client


# ── DreamJobAnalyzerService tests ─────────────────────────────────────────────

class TestDreamJobAnalyzerService:

    def test_analyze_happy_path(self):
        """analyze() returns jd_normalized, fit_analysis, and usage on success."""
        from app.services.dream_job_analyzer_service import DreamJobAnalyzerService

        svc = DreamJobAnalyzerService(api_key="test-key")
        svc._client = _make_openai_mock(DUMMY_JD_NORMALIZED, DUMMY_FIT_ANALYSIS)

        result = asyncio.run(svc.analyze(
            jd_text=DUMMY_JD_TEXT,
            resume_parsed_sections=DUMMY_RESUME_SECTIONS,
            resume_text=DUMMY_RESUME_TEXT,
            dream_job_id="dj-abc123",
        ))

        assert "jd_normalized" in result
        assert "fit_analysis" in result
        assert "usage" in result

        assert result["jd_normalized"]["role_title"] == "Senior Python Engineer"
        assert result["fit_analysis"]["fit_score"] == 82
        assert result["fit_analysis"]["interview_chance"] == 70
        assert len(result["fit_analysis"]["matching_strengths"]) > 0
        # 2 LLM calls × 300 tokens each = 600
        assert result["usage"]["total_tokens"] == 600

    def test_analyze_updates_firestore_steps(self):
        """analyze() calls fb.update_dream_job with expected step names."""
        from app.services.dream_job_analyzer_service import DreamJobAnalyzerService

        svc = DreamJobAnalyzerService(api_key="test-key")
        svc._client = _make_openai_mock(DUMMY_JD_NORMALIZED, DUMMY_FIT_ANALYSIS)

        fb_mock = MagicMock()
        fb_mock.update_dream_job = MagicMock(return_value=True)

        asyncio.run(svc.analyze(
            jd_text=DUMMY_JD_TEXT,
            resume_parsed_sections=DUMMY_RESUME_SECTIONS,
            resume_text=DUMMY_RESUME_TEXT,
            dream_job_id="dj-abc123",
            fb=fb_mock,
        ))

        step_names = [
            call.args[1]["current_step"]
            for call in fb_mock.update_dream_job.call_args_list
        ]
        assert "normalizing_jd" in step_names
        assert "analyzing_fit" in step_names
        assert "saving_results" in step_names

    def test_analyze_writes_analyzing_status_during_pass2(self):
        """analyze() must write status='analyzing' when entering the Kimi fit pass."""
        from app.services.dream_job_analyzer_service import DreamJobAnalyzerService

        svc = DreamJobAnalyzerService(api_key="test-key")
        svc._client = _make_openai_mock(DUMMY_JD_NORMALIZED, DUMMY_FIT_ANALYSIS)

        fb_mock = MagicMock()
        fb_mock.update_dream_job = MagicMock(return_value=True)

        asyncio.run(svc.analyze(
            jd_text=DUMMY_JD_TEXT,
            resume_parsed_sections=DUMMY_RESUME_SECTIONS,
            resume_text=DUMMY_RESUME_TEXT,
            dream_job_id="dj-1",
            fb=fb_mock,
        ))

        statuses_written = [
            call.args[1].get("status")
            for call in fb_mock.update_dream_job.call_args_list
            if "status" in call.args[1]
        ]
        assert "normalizing" in statuses_written
        assert "analyzing" in statuses_written

    def test_normalize_jd_error_returns_empty_structure(self):
        """If the LLM call fails, _normalize_jd returns a safe empty structure."""
        from app.services.dream_job_analyzer_service import DreamJobAnalyzerService

        svc = DreamJobAnalyzerService(api_key="test-key")

        async def _failing_create(**kwargs):
            raise RuntimeError("API down")

        svc._client = MagicMock()
        svc._client.chat.completions.create = _failing_create

        result = asyncio.run(svc._normalize_jd(DUMMY_JD_TEXT, lambda u: None))

        assert result["role_title"] == ""
        assert result["must_have_skills"] == []
        assert result["keywords"] == []

    def test_fit_analysis_error_returns_zero_scores(self):
        """If Kimi call fails, _fit_analysis returns safe zero-scored structure."""
        from app.services.dream_job_analyzer_service import DreamJobAnalyzerService

        svc = DreamJobAnalyzerService(api_key="test-key")

        async def _failing_create(**kwargs):
            raise RuntimeError("Kimi timeout")

        svc._client = MagicMock()
        svc._client.chat.completions.create = _failing_create

        result = asyncio.run(svc._fit_analysis(
            DUMMY_RESUME_SECTIONS,
            DUMMY_JD_NORMALIZED,
            DUMMY_JD_TEXT,
            DUMMY_RESUME_TEXT,
            lambda u: None,
        ))

        assert result["fit_score"] == 0
        assert result["interview_chance"] == 0
        assert result["matching_strengths"] == []
        assert result["gaps"] == []


# ── job_link_parser tests ─────────────────────────────────────────────────────


# Fake getaddrinfo that returns a routable public IP so the SSRF guard passes in tests.
_PUBLIC_ADDR_INFO = [(2, 1, 6, "", ("1.1.1.1", 0))]


class TestJobLinkParser:

    def test_greenhouse_happy_path(self):
        """parse_job_url routes to Greenhouse handler for greenhouse.io URLs."""
        mock_data = {
            "title": "Backend Engineer",
            "content": "<p>We need a backend engineer skilled in Python.</p>",
            "departments": [{"name": "Engineering"}],
            "offices": [{"name": "New York, NY"}],
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/12345",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_redirect = False  # prevent _safe_get redirect loop
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        async def _fake_get(url, **kwargs):
            return mock_response

        mock_http_client = AsyncMock()
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)
        mock_http_client.get = _fake_get

        with patch("httpx.AsyncClient", return_value=mock_http_client), \
             patch("socket.getaddrinfo", return_value=_PUBLIC_ADDR_INFO):
            from app.services import job_link_parser
            import importlib
            importlib.reload(job_link_parser)
            result = asyncio.run(job_link_parser.parse_job_url(
                "https://boards.greenhouse.io/acme/jobs/12345"
            ))

        assert result["source"] == "greenhouse"
        assert result["role_title"] == "Backend Engineer"
        assert "python" in result["jd_text"].lower()
        assert result["error"] is None

    def test_linkedin_returns_error_on_block(self):
        """parse_job_url returns linkedin_blocked error for LinkedIn URLs that fail."""
        import httpx as _httpx

        async def _blocked_get(url, **kwargs):
            raise _httpx.HTTPStatusError(
                "999 blocked",
                request=MagicMock(),
                response=MagicMock(status_code=999),
            )

        mock_http_client = AsyncMock()
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)
        mock_http_client.get = _blocked_get

        with patch("httpx.AsyncClient", return_value=mock_http_client), \
             patch("socket.getaddrinfo", return_value=_PUBLIC_ADDR_INFO):
            from app.services import job_link_parser
            import importlib
            importlib.reload(job_link_parser)
            result = asyncio.run(job_link_parser.parse_job_url(
                "https://www.linkedin.com/jobs/view/12345"
            ))

        assert result["source"] == "linkedin"
        assert result["error"] == "linkedin_blocked"
        assert result["jd_text"] == ""

    def test_generic_fallback_returns_og_data(self):
        """parse_job_url uses og:* tags for unknown URLs."""
        html = (
            "<html><head>"
            '<meta property="og:title" content="Data Scientist" />'
            '<meta property="og:site_name" content="Acme Corp" />'
            '<meta property="og:description" content="Join our data team." />'
            "</head><body><p>More detail here.</p></body></html>"
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_redirect = False  # prevent _safe_get redirect loop
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        async def _fake_get(url, **kwargs):
            return mock_response

        mock_http_client = AsyncMock()
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)
        mock_http_client.get = _fake_get

        with patch("httpx.AsyncClient", return_value=mock_http_client), \
             patch("socket.getaddrinfo", return_value=_PUBLIC_ADDR_INFO):
            from app.services import job_link_parser
            import importlib
            importlib.reload(job_link_parser)
            result = asyncio.run(job_link_parser.parse_job_url(
                "https://careers.somecompany.com/job/123"
            ))

        assert result["source"] == "generic"
        assert result["role_title"] == "Data Scientist"
        assert result["company"] == "Acme Corp"

    def test_parse_job_url_rejects_localhost(self):
        """SSRF guard: localhost URL must be rejected without making any HTTP call."""
        from app.services import job_link_parser
        import importlib
        importlib.reload(job_link_parser)
        result = asyncio.run(job_link_parser.parse_job_url("http://localhost:8000/admin"))
        assert result["error"] == "url_rejected"

    def test_parse_job_url_rejects_metadata_ip(self):
        """SSRF guard: AWS metadata IP must be rejected without making any HTTP call."""
        from app.services import job_link_parser
        import importlib
        importlib.reload(job_link_parser)
        result = asyncio.run(
            job_link_parser.parse_job_url("http://169.254.169.254/latest/meta-data/")
        )
        assert result["error"] == "url_rejected"
