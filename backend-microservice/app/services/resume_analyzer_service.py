"""
Resume Analyzer Service — multi-step AI analysis pipeline using the AIML API.
"""

import asyncio
import json
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_AIML_BASE_URL = "https://api.aimlapi.com/v1"
_PARSE_MODEL = "openai/gpt-5-nano-2025-08-07"
_SECTION_MODEL = "openai/gpt-5-nano-2025-08-07"
_HOLISTIC_MODEL = "moonshot/kimi-k2-0905-preview"

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
        self._client = AsyncOpenAI(api_key=api_key, base_url=_AIML_BASE_URL)

    # ── Public ──────────────────────────────────────────────────────────────────

    async def analyze(
        self,
        resume_text: str,
        filename: str,
        analysis_id: str = None,
        fb=None,
    ) -> dict:
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

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

        _step("parsing_document")
        parsed_sections = await self._parse_sections(resume_text, _add)

        _step("analyzing_sections")
        section_results = await self._analyze_sections(parsed_sections, _add)

        _step("holistic_review")
        holistic = await self._holistic_review(resume_text, _add)

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
            logger.error(f"Section parsing failed: {e}")
            return {
                "name": "",
                "contact": {"email": None, "phone": None, "linkedin": None, "location": None},
                "summary": None,
                "experience": [],
                "education": [],
                "skills": [],
                "certifications": [],
                "projects": [],
            }

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
            logger.error(f"Section analysis failed for {section_name}: {e}")
            return {
                "name": _SECTION_DISPLAY.get(section_name, section_name.capitalize()),
                "found": False,
                "score": None,
                "content_snippet": None,
                "strengths": [],
                "weaknesses": [],
                "tips": [],
                "suggestions": [],
            }

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
            logger.error(f"Holistic review failed: {e}")
            return {
                "overall_score": 0,
                "quality_score": 0,
                "summary": "",
                "strengths": [],
                "weaknesses": [],
                "top_tips": [],
                "lackings": [],
                "ats": {"score": 0, "keywords_found": [], "keywords_missing": [], "formatting_issues": []},
                "suggestions": [],
            }
