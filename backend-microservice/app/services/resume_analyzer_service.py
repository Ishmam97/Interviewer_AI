"""
Resume Analyzer Service — multi-step AI analysis pipeline using the AIML API.
"""

import asyncio
import json
import logging
import time
from openai import AsyncOpenAI
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Model IDs are config-driven (see core/config.py) so a provider change or a
# retired model ID is an env edit, not a code change.
_AIML_BASE_URL = settings.AIML_BASE_URL
_PARSE_MODEL = settings.RESUME_PARSE_MODEL
_SECTION_MODEL = settings.RESUME_SECTION_MODEL
_HOLISTIC_MODEL = settings.RESUME_HOLISTIC_MODEL

# Per-request timeout for AIML API calls (seconds)
_API_TIMEOUT = 320.0
# Overall analysis timeout (seconds)
_ANALYSIS_TIMEOUT = 480.0

_SECTIONS = ["contact", "summary", "experience", "education", "skills", "certifications", "projects"]

_SECTION_DISPLAY = {
    "contact": "Contact",
    "summary": "Summary",
    "experience": "Experience",
    "education": "Education",
    "skills": "Skills",
    "certifications": "Certifications",
    "projects": "Projects",
}


class ResumeAnalyzerService:
    def __init__(self, api_key: str):
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=_AIML_BASE_URL,
            # Configure httpx timeout to prevent hanging requests
            http_client=httpx.AsyncClient(
                timeout=httpx.Timeout(_API_TIMEOUT, connect=30.0)
            ),
        )

    # ── Public ──────────────────────────────────────────────────────────────────

    async def analyze(
        self,
        resume_text: str,
        filename: str,
        analysis_id: str = None,
        fb=None,
    ) -> dict:
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        analysis_start = time.monotonic()

        def _add(u):
            if u:
                usage["prompt_tokens"] += getattr(u, "prompt_tokens", 0) or 0
                usage["completion_tokens"] += getattr(u, "completion_tokens", 0) or 0
                usage["total_tokens"] += getattr(u, "total_tokens", 0) or 0

        def _step(step_name: str):
            if fb and analysis_id:
                try:
                    fb.update_resume_analysis(analysis_id, {"current_step": step_name})
                except Exception as e:
                    logger.warning(f"Failed to update step {step_name}: {e}")

        logger.info(f"[resume_analysis] Starting analysis for '{filename}' (id={analysis_id})")

        # Step 1: Parse sections
        _step("parsing_document")
        t0 = time.monotonic()
        logger.info(f"[resume_analysis:{analysis_id}] Step 1/3 — parsing_document (model={_PARSE_MODEL})")
        try:
            parsed_sections = await asyncio.wait_for(
                self._parse_sections(resume_text, _add),
                timeout=_API_TIMEOUT,
            )
            logger.info(f"[resume_analysis:{analysis_id}] Step 1/3 done in {time.monotonic() - t0:.1f}s")
        except asyncio.TimeoutError:
            logger.error(f"[resume_analysis:{analysis_id}] Step 1/3 timed out after {_API_TIMEOUT}s")
            raise
        except Exception as e:
            logger.error(f"[resume_analysis:{analysis_id}] Step 1/3 failed: {e}")
            raise

        # Step 2: Analyze sections (7 parallel calls)
        _step("analyzing_sections")
        t0 = time.monotonic()
        logger.info(f"[resume_analysis:{analysis_id}] Step 2/3 — analyzing_sections ({len(_SECTIONS)} parallel calls, model={_SECTION_MODEL})")
        try:
            section_results = await asyncio.wait_for(
                self._analyze_sections(parsed_sections, _add),
                timeout=_API_TIMEOUT,
            )
            logger.info(f"[resume_analysis:{analysis_id}] Step 2/3 done in {time.monotonic() - t0:.1f}s")
        except asyncio.TimeoutError:
            logger.error(f"[resume_analysis:{analysis_id}] Step 2/3 timed out after {_API_TIMEOUT}s")
            raise
        except Exception as e:
            logger.error(f"[resume_analysis:{analysis_id}] Step 2/3 failed: {e}")
            raise

        # Step 3: Holistic review
        _step("holistic_review")
        t0 = time.monotonic()
        logger.info(f"[resume_analysis:{analysis_id}] Step 3/3 — holistic_review (model={_HOLISTIC_MODEL})")
        try:
            holistic = await asyncio.wait_for(
                self._holistic_review(resume_text, _add),
                timeout=_API_TIMEOUT,
            )
            logger.info(f"[resume_analysis:{analysis_id}] Step 3/3 done in {time.monotonic() - t0:.1f}s")
        except asyncio.TimeoutError:
            logger.error(f"[resume_analysis:{analysis_id}] Step 3/3 timed out after {_API_TIMEOUT}s")
            raise
        except Exception as e:
            logger.error(f"[resume_analysis:{analysis_id}] Step 3/3 failed: {e}")
            raise

        total_elapsed = time.monotonic() - analysis_start
        logger.info(
            f"[resume_analysis:{analysis_id}] Completed in {total_elapsed:.1f}s — "
            f"tokens: prompt={usage['prompt_tokens']}, completion={usage['completion_tokens']}, "
            f"total={usage['total_tokens']}"
        )

        _step("saving_results")

        return {
            "overall": {
                "score": holistic.get("overall_score", 0),
                "quality_score": holistic.get("quality_score", 0),
                "summary": holistic.get("summary", ""),
                "strengths": holistic.get("strengths", []),
                "weaknesses": holistic.get("weaknesses", []),
                "top_tips": holistic.get("top_tips", []),
                "lackings": holistic.get("lackings", []),
                "suggestions": holistic.get("suggestions", []),
            },
            "sections": section_results,
            "ats": holistic.get("ats", {
                "score": 0,
                "keywords_found": [],
                "keywords_missing": [],
                "formatting_issues": [],
            }),
            "parsed_sections": parsed_sections,
            "lackings": holistic.get("lackings", []),
            "quality_score": holistic.get("quality_score", 0),
            "usage": {
                "prompt_tokens": usage["prompt_tokens"],
                "completion_tokens": usage["completion_tokens"],
                "total_tokens": usage["total_tokens"],
                "completion_tokens_details": None,
                "prompt_tokens_details": None,
            },
        }

    # ── Steps ───────────────────────────────────────────────────────────────────

    async def _parse_sections(self, resume_text: str, add_usage) -> dict:
        prompt = (
            "Extract structured information from this resume. Return a JSON object with exactly these keys:\n"
            '{"name": "string", '
            '"contact": {"email": "string or null", "phone": "string or null", '
            '"linkedin": "string or null", "location": "string or null"}, '
            '"summary": "string or null", '
            '"experience": [{"title": "string", "company": "string", "duration": "string", "bullets": ["string"]}], '
            '"education": [{"degree": "string", "institution": "string", "year": "string"}], '
            '"skills": ["string"], "certifications": ["string"], '
            '"projects": [{"name": "string", "description": "string"}]}\n\nResume:\n'
            + resume_text
        )
        try:
            resp = await self._client.chat.completions.create(
                model=_PARSE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            add_usage(resp.usage)
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            # Re-raise: a failed parse means the whole analysis must fail loudly
            # (status=failed) rather than persist an empty resume as "completed".
            logger.error(f"Section parsing failed: {e}")
            raise

    async def _analyze_one_section(self, section_name: str, content, add_usage) -> dict:
        content_str = json.dumps(content) if not isinstance(content, str) else (content or "")
        prompt = (
            f'Analyze the "{section_name}" section of a resume.\n'
            f"Section content:\n{content_str}\n\n"
            "Return a JSON object with exactly these keys:\n"
            '{"found": true, "score": 0-100, "content_snippet": "first 100 chars or null", '
            '"strengths": ["string"], "weaknesses": ["string"], "tips": ["string"], '
            '"suggestions": [{"id": "unique_string", "text": "actionable suggestion", "status": "pending"}]}'
        )
        try:
            resp = await self._client.chat.completions.create(
                model=_SECTION_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            add_usage(resp.usage)
            data = json.loads(resp.choices[0].message.content)
            return {
                "name": _SECTION_DISPLAY.get(section_name, section_name.capitalize()),
                "found": data.get("found", False),
                "score": data.get("score"),
                "content_snippet": data.get("content_snippet"),
                "strengths": data.get("strengths", []),
                "weaknesses": data.get("weaknesses", []),
                "tips": data.get("tips", []),
                "suggestions": data.get("suggestions", []),
            }
        except Exception as e:
            # Re-raise so a provider/parse failure fails the whole analysis rather
            # than silently scoring a section 0. (A legitimately-absent section is
            # returned by the model as found=false, not raised here.)
            logger.error(f"Section analysis failed for {section_name}: {e}")
            raise

    async def _analyze_sections(self, parsed: dict, add_usage) -> list:
        section_contents = {
            "contact": parsed.get("contact", {}),
            "summary": parsed.get("summary", ""),
            "experience": parsed.get("experience", []),
            "education": parsed.get("education", []),
            "skills": parsed.get("skills", []),
            "certifications": parsed.get("certifications", []),
            "projects": parsed.get("projects", []),
        }
        tasks = [
            self._analyze_one_section(name, content, add_usage)
            for name, content in section_contents.items()
        ]
        return list(await asyncio.gather(*tasks))

    async def _holistic_review(self, resume_text: str, add_usage) -> dict:
        prompt = (
            "Perform a holistic review of this resume. Return a JSON object with exactly these keys:\n"
            '{"overall_score": 0-100, "quality_score": 0-100, "summary": "2-3 sentence narrative", '
            '"strengths": ["string"], "weaknesses": ["string"], "top_tips": ["string"], '
            '"lackings": ["string"], '
            '"ats": {"score": 0-100, "keywords_found": ["string"], "keywords_missing": ["string"], '
            '"formatting_issues": ["string"]}, '
            '"suggestions": [{"id": "unique_string", "text": "high-level suggestion", '
            '"section": "overall", "status": "pending"}]}\n\nResume:\n'
            + resume_text
        )
        try:
            resp = await self._client.chat.completions.create(
                model=_HOLISTIC_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            add_usage(resp.usage)
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            # Re-raise: without a holistic review there is no meaningful report,
            # so fail the analysis instead of persisting all-zero scores.
            logger.error(f"Holistic review failed: {e}")
            raise
