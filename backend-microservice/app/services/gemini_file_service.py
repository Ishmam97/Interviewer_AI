"""
Gemini File API service — uploads resume/JD files and generates interview plans
using file references instead of raw text extraction.
"""

import asyncio
import json
import pathlib
from typing import Optional

from google import genai
from google.genai import types


class GeminiFileService:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    # ── File Upload ─────────────────────────────────────────────────────────

    async def upload_file(self, file_path: str, display_name: str) -> types.File:
        """Upload a local file to the Gemini File API. Returns a File object."""
        path = pathlib.Path(file_path)
        suffix = path.suffix.lower()
        mime_type = "application/pdf" if suffix == ".pdf" else "text/plain"

        file_ref = await asyncio.wait_for(
            asyncio.to_thread(
                self.client.files.upload,
                file=path,
                config=types.UploadFileConfig(display_name=display_name, mime_type=mime_type),
            ),
            timeout=30,
        )
        return file_ref

    async def delete_file(self, file_name: str) -> None:
        """Delete an uploaded file from the Gemini File API."""
        try:
            await asyncio.to_thread(self.client.files.delete, name=file_name)
        except Exception as e:
            print(f"Warning: could not delete Gemini file {file_name}: {e}")

    # ── Interview Planning ───────────────────────────────────────────────────

    async def generate_question_plan(
        self,
        resume_file: types.File,
        jd_file: types.File,
        num_questions: int,
        interview_type: str,
    ) -> list:
        """
        Ask Gemini to read the uploaded resume + JD and produce a structured
        question plan.  Returns a list of question dicts.
        """
        prompt = (
            f"You are an expert interviewer. Based on the provided resume and job description, "
            f"create exactly {num_questions} targeted interview questions for a {interview_type}.\n\n"
            "Return ONLY a valid JSON array — no markdown fences, no commentary — with this schema:\n"
            '[\n'
            '  {\n'
            '    "question": "the question text",\n'
            '    "category": "technical|behavioral|experience|problem_solving",\n'
            '    "priority": 1,\n'
            '    "expected_skills": ["skill"],\n'
            '    "follow_up_prompts": ["optional follow-up"]\n'
            '  }\n'
            ']\n\n'
            "Focus on questions that directly assess the candidate's fit based on their actual resume."
        )

        contents = [
            types.Part(file_data=types.FileData(
                file_uri=resume_file.uri,
                mime_type=resume_file.mime_type or "application/pdf",
            )),
            types.Part(file_data=types.FileData(
                file_uri=jd_file.uri,
                mime_type=jd_file.mime_type or "text/plain",
            )),
            types.Part(text=prompt),
        ]

        response = await asyncio.wait_for(
            asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model,
                contents=contents,
            ),
            timeout=60,
        )

        return self._parse_plan(response.text, num_questions)

    # ── Post-Interview Analysis ──────────────────────────────────────────────

    async def analyze_transcript(
        self,
        transcript: list,
        resume_file: types.File,
        jd_file: types.File,
    ) -> dict:
        """
        Given a completed interview transcript, produce a structured report.
        transcript = [{"role": "interviewer"|"candidate", "text": "..."}]
        """
        formatted = "\n".join(
            f"[{t['role'].upper()}]: {t['text']}" for t in transcript
        )

        prompt = (
            "You reviewed the candidate's resume and job description above. "
            "Below is the full interview transcript.\n\n"
            f"{formatted}\n\n"
            "Provide a JSON report with this structure:\n"
            '{\n'
            '  "overall_score": 7.5,\n'
            '  "summary": "brief overall summary",\n'
            '  "strengths": ["strength 1", "strength 2"],\n'
            '  "areas_for_improvement": ["area 1"],\n'
            '  "recommendation": "strong hire | hire | maybe | no hire",\n'
            '  "question_scores": [\n'
            '    {"question": "...", "score": 8, "feedback": "brief feedback"}\n'
            '  ]\n'
            '}\n\n'
            "Return ONLY the JSON object, no markdown."
        )

        contents = [
            types.Part(file_data=types.FileData(
                file_uri=resume_file.uri,
                mime_type=resume_file.mime_type or "application/pdf",
            )),
            types.Part(file_data=types.FileData(
                file_uri=jd_file.uri,
                mime_type=jd_file.mime_type or "text/plain",
            )),
            types.Part(text=prompt),
        ]

        response = await asyncio.wait_for(
            asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model,
                contents=contents,
            ),
            timeout=90,
        )

        return self._parse_json(response.text, default={
            "overall_score": 0,
            "summary": "Analysis could not be generated.",
            "strengths": [],
            "areas_for_improvement": [],
            "recommendation": "unknown",
            "question_scores": [],
        })

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _parse_plan(self, text: str, num_questions: int) -> list:
        """Strip markdown and parse the question plan JSON."""
        data = self._parse_json(text, default=None)
        if isinstance(data, list) and data:
            return data[:num_questions]
        # Fallback questions
        return [
            {
                "question": "Tell me about your background and experience relevant to this role.",
                "category": "experience",
                "priority": 5,
                "expected_skills": ["communication"],
                "follow_up_prompts": [],
            }
        ] * min(num_questions, 5)

    @staticmethod
    def _parse_json(text: str, default):
        """Strip markdown fences and parse JSON."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        try:
            return json.loads(text)
        except Exception:
            return default
