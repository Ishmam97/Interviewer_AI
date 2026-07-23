"""
Dream Job Analyzer Service — two-pass AI pipeline that scores resume-to-JD fit.

Pass 1 (cheap):  _normalize_jd  — GPT-5-nano extracts structured fields from raw JD text.
Pass 2 (holistic): _fit_analysis — Kimi-K2 produces the full fit report.

Mirrors resume_analyzer_service.py in style: same AIML API client, same timeout
constants, same token-usage tracking, and same per-step Firestore status updates.
"""

import asyncio
import json
import logging
import time
from openai import AsyncOpenAI
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Model IDs are config-driven (see core/config.py).
_AIML_BASE_URL = settings.AIML_BASE_URL
_NORMALIZE_MODEL = settings.DREAM_JOB_NORMALIZE_MODEL
_FIT_MODEL = settings.DREAM_JOB_FIT_MODEL

# Per-request timeout for AIML API calls (seconds). Kept well under
# _ANALYSIS_TIMEOUT since the SDK's own retry logic (max_retries below) can
# consume a multiple of this on transient failures.
_API_TIMEOUT = 60.0
# Overall analysis timeout (seconds) — two passes run sequentially, so this
# must comfortably exceed 2x _API_TIMEOUT.
_ANALYSIS_TIMEOUT = 180.0

# Caps user-supplied text (scraped JD, raw resume) before it's embedded in a
# prompt, to bound token cost regardless of upload/scrape size.
_MAX_TEXT_CHARS = 12000


class DreamJobAnalyzerService:
    def __init__(self, api_key: str):
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=_AIML_BASE_URL,
            max_retries=2,
            # Configure httpx timeout to prevent hanging requests
            http_client=httpx.AsyncClient(
                timeout=httpx.Timeout(_API_TIMEOUT, connect=10.0)
            ),
        )

    async def aclose(self):
        """Close the underlying HTTP client — each service instance owns its
        own httpx.AsyncClient, which otherwise leaks connections/file
        descriptors across the many short-lived instances created per
        background task."""
        await self._client.close()

    # ── Public ──────────────────────────────────────────────────────────────────

    async def analyze(
        self,
        jd_text: str,
        resume_parsed_sections: dict,
        resume_text: str,
        dream_job_id: str = None,
        fb=None,
    ) -> dict:
        """
        Run the full two-pass fit analysis.

        Returns a dict with keys: jd_normalized, fit_analysis, usage.
        """
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        analysis_start = time.monotonic()

        def _add(u):
            if u:
                usage["prompt_tokens"] += getattr(u, "prompt_tokens", 0) or 0
                usage["completion_tokens"] += getattr(u, "completion_tokens", 0) or 0
                usage["total_tokens"] += getattr(u, "total_tokens", 0) or 0

        _STEP_TO_STATUS = {
            "normalizing_jd": "normalizing",
            "analyzing_fit": "analyzing",
            # saving_results: no status update — stays "analyzing"
        }

        def _step(step_name: str):
            if fb and dream_job_id:
                update = {"current_step": step_name}
                new_status = _STEP_TO_STATUS.get(step_name)
                if new_status:
                    update["status"] = new_status
                try:
                    fb.update_dream_job(dream_job_id, update)
                except Exception as e:
                    logger.warning(f"Failed to update step {step_name}: {e}")

        logger.info(
            f"[dream_job_analysis] Starting analysis (id={dream_job_id})"
        )

        # Pass 1: Normalize JD
        _step("normalizing_jd")
        t0 = time.monotonic()
        logger.info(
            f"[dream_job_analysis:{dream_job_id}] Pass 1/2 — normalizing_jd "
            f"(model={_NORMALIZE_MODEL})"
        )
        try:
            jd_normalized = await asyncio.wait_for(
                self._normalize_jd(jd_text, _add),
                timeout=_API_TIMEOUT,
            )
            logger.info(
                f"[dream_job_analysis:{dream_job_id}] Pass 1/2 done in "
                f"{time.monotonic() - t0:.1f}s"
            )
        except asyncio.TimeoutError:
            logger.error(
                f"[dream_job_analysis:{dream_job_id}] Pass 1/2 timed out after {_API_TIMEOUT}s"
            )
            raise
        except Exception as e:
            logger.error(f"[dream_job_analysis:{dream_job_id}] Pass 1/2 failed: {e}")
            raise

        # Pass 2: Fit Analysis
        _step("analyzing_fit")
        t0 = time.monotonic()
        logger.info(
            f"[dream_job_analysis:{dream_job_id}] Pass 2/2 — analyzing_fit "
            f"(model={_FIT_MODEL})"
        )
        try:
            fit_analysis = await asyncio.wait_for(
                self._fit_analysis(
                    resume_parsed_sections, jd_normalized, jd_text, resume_text, _add
                ),
                timeout=_API_TIMEOUT,
            )
            logger.info(
                f"[dream_job_analysis:{dream_job_id}] Pass 2/2 done in "
                f"{time.monotonic() - t0:.1f}s"
            )
        except asyncio.TimeoutError:
            logger.error(
                f"[dream_job_analysis:{dream_job_id}] Pass 2/2 timed out after {_API_TIMEOUT}s"
            )
            raise
        except Exception as e:
            logger.error(f"[dream_job_analysis:{dream_job_id}] Pass 2/2 failed: {e}")
            raise

        total_elapsed = time.monotonic() - analysis_start
        logger.info(
            f"[dream_job_analysis:{dream_job_id}] Completed in {total_elapsed:.1f}s — "
            f"tokens: prompt={usage['prompt_tokens']}, "
            f"completion={usage['completion_tokens']}, "
            f"total={usage['total_tokens']}"
        )

        _step("saving_results")

        return {
            "jd_normalized": jd_normalized,
            "fit_analysis": fit_analysis,
            "usage": {
                "prompt_tokens": usage["prompt_tokens"],
                "completion_tokens": usage["completion_tokens"],
                "total_tokens": usage["total_tokens"],
            },
        }

    # ── Passes ──────────────────────────────────────────────────────────────────

    async def _normalize_jd(self, jd_text: str, add_usage) -> dict:
        """
        Pass 1 — cheap structured extraction from raw JD text.
        Returns the normalized JD dict.
        """
        prompt = (
            "Extract structured information from this job description. "
            "Return a JSON object with exactly these keys:\n"
            '{"role_title": "string", '
            '"company": "string or null", '
            '"seniority": "string", '
            '"must_have_skills": ["string"], '
            '"nice_to_have_skills": ["string"], '
            '"responsibilities": ["string"], '
            '"keywords": ["string"]}\n\n'
            "Job Description:\n" + jd_text[:_MAX_TEXT_CHARS]
        )
        try:
            resp = await self._client.chat.completions.create(
                model=_NORMALIZE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=1200,
            )
            add_usage(resp.usage)
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            # Re-raise so a provider/parse failure fails the analysis (status=failed)
            # instead of feeding an empty JD into the fit pass and scoring fit 0.
            logger.error(f"JD normalization failed: {e}")
            raise

    async def _fit_analysis(
        self,
        resume_parsed_sections: dict,
        jd_normalized: dict,
        jd_text: str,
        resume_text: str,
        add_usage,
    ) -> dict:
        """
        Pass 2 — holistic fit analysis using Kimi-K2.
        Returns the full fit report dict.
        """
        prompt = (
            "You are an expert resume reviewer and hiring manager. "
            "Analyze how well this candidate's resume matches the given job description "
            "and produce a detailed fit report.\n\n"
            "RESUME (parsed sections):\n"
            + json.dumps(resume_parsed_sections, indent=2)[:_MAX_TEXT_CHARS]
            + "\n\nRESUME (raw text):\n"
            + resume_text[:_MAX_TEXT_CHARS]
            + "\n\nJOB DESCRIPTION (normalized):\n"
            + json.dumps(jd_normalized, indent=2)[:_MAX_TEXT_CHARS]
            + "\n\nJOB DESCRIPTION (raw):\n"
            + jd_text[:_MAX_TEXT_CHARS]
            + "\n\nReturn a JSON object with exactly these keys:\n"
            '{"fit_score": <integer 0-100>, '
            '"interview_chance": <integer 0-100>, '
            '"fit_summary": "2-3 sentences", '
            '"matching_strengths": ["string"], '
            '"gaps": [{"skill": "string", "importance": "High|Medium|Low", '
            '"time_to_learn": "string"}], '
            '"points_to_improve": ["string"], '
            '"resume_tailoring_plan": [{"section": "string", "action": "string", '
            '"rationale": "string"}], '
            '"suggested_projects": [{"title": "string", "description": "string", '
            '"skills_demonstrated": ["string"]}], '
            '"ats_keyword_coverage": {"matched": ["string"], "missing": ["string"]}}'
        )
        try:
            resp = await self._client.chat.completions.create(
                model=_FIT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=3000,
            )
            add_usage(resp.usage)
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            # Re-raise: without a fit report there is nothing meaningful to show,
            # so fail the analysis rather than persist a fit_score of 0.
            logger.error(f"Fit analysis failed: {e}")
            raise
