"""
Turn-based streaming interview agent using the standard Gemini content API.

Architecture:
  Client WebSocket ↔ ChatInterviewAgent ↔ Gemini generateContent (streaming)

Uses generate_content_stream instead of the Live API so it works on any
Gemini API key without special Live API quota.
"""

import asyncio
from fastapi import WebSocket
from google import genai
from google.genai import types

CHAT_MODEL = "gemini-2.5-flash"

# Wall-clock cap on a single streamed generation. Without this, a hung
# upstream stream blocks the turn (and the websocket) indefinitely — the
# 300s receive timeout below only covers waiting for the candidate's next
# answer, not generation itself.
_STREAM_TIMEOUT = 90.0

# Cap on how many Content entries (after the opening turn) get resent to
# Gemini each turn. `contents` grows by one entry every turn; resending the
# whole thing verbatim makes per-request token cost — and therefore cost —
# grow quadratically with interview length. 8 entries is ~4 candidate/
# interviewer exchanges of recent context, which is enough for coherent
# follow-ups without re-billing the entire interview each turn.
_MAX_HISTORY_TURNS = 8


def _trim_history(contents: list) -> list:
    """Bound what gets resent to Gemini for a single turn.

    Always keeps `contents[0]` — it carries the resume/JD file parts the
    model needs to stay grounded — plus only the most recent
    `_MAX_HISTORY_TURNS` entries, dropping older middle turns. Returns a new
    list; never mutates `contents` (the caller keeps appending to the full
    history for the turn protocol/transcript).
    """
    if len(contents) <= _MAX_HISTORY_TURNS + 1:
        return contents
    return [contents[0]] + contents[-_MAX_HISTORY_TURNS:]

_SYSTEM_PROMPT = """\
You are a warm, professional AI interviewer conducting a {interview_type}.
The candidate's resume and the job description have been provided to you as files.

INTERVIEW PLAN — follow this exact sequence:
{question_plan}

INTERVIEWING RULES:
1. Open by greeting the candidate briefly and asking Question 1.
2. After each answer, give ONE short acknowledgement sentence (e.g. "Thank you, that's helpful.").
3. You may ask at most ONE brief follow-up if the answer is very vague or incomplete.
4. Then move to the next question in the plan.
5. Keep a professional yet friendly tone throughout.
6. After the candidate has answered ALL questions, thank them warmly, then output the
   exact token [INTERVIEW_COMPLETE] on its own line to signal the end.

Do NOT skip questions, do NOT add extra questions beyond the plan.
"""


class LiveInterviewAgent:
    """
    Turn-based streaming interview using Gemini generate_content_stream.
    Maintains full conversation history across turns so the model has context.
    Aliased as LiveInterviewAgent for compatibility with server.py imports.
    """

    def __init__(self, api_key: str, model: str = CHAT_MODEL):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    async def run(
        self,
        websocket: WebSocket,
        session_id: str,
        question_plan: list,
        interview_type: str,
        resume_file_uri: str,
        resume_mime_type: str,
        jd_file_uri: str,
        jd_mime_type: str,
    ) -> list:
        """
        Drive the full interview over the WebSocket.
        Streams AI text to the client in real-time.

        Returns the conversation transcript as a list of
        {"role": "interviewer"|"candidate", "text": str} dicts.
        """
        question_plan_text = "\n".join(
            f"  Q{i + 1} [{q.get('category', 'general')}]: {q['question']}"
            for i, q in enumerate(question_plan)
        )
        system_instruction = _SYSTEM_PROMPT.format(
            interview_type=interview_type,
            question_plan=question_plan_text,
        )

        contents: list = []
        transcript: list = []

        try:
            # ── Opening: prime with resume + JD files ────────────────────────
            contents.append(types.Content(
                role="user",
                parts=[
                    types.Part(file_data=types.FileData(
                        file_uri=resume_file_uri,
                        mime_type=resume_mime_type,
                    )),
                    types.Part(file_data=types.FileData(
                        file_uri=jd_file_uri,
                        mime_type=jd_mime_type,
                    )),
                    types.Part(text="Please begin the interview now."),
                ],
            ))

            opening = await self._stream_turn(system_instruction, contents, websocket)
            contents.append(types.Content(role="model", parts=[types.Part(text=opening)]))
            transcript.append({"role": "interviewer", "text": opening})

            # ── Main Q&A loop ─────────────────────────────────────────────────
            while True:
                try:
                    msg = await asyncio.wait_for(
                        websocket.receive_json(), timeout=300
                    )
                except asyncio.TimeoutError:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Session timed out after 5 minutes of inactivity.",
                    })
                    break

                msg_type = msg.get("type")

                if msg_type == "end":
                    break

                if msg_type != "answer":
                    continue

                answer_text = msg.get("text", "").strip()
                if not answer_text:
                    continue

                transcript.append({"role": "candidate", "text": answer_text})
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=answer_text)],
                ))

                ai_text = await self._stream_turn(system_instruction, contents, websocket)
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part(text=ai_text)],
                ))
                transcript.append({"role": "interviewer", "text": ai_text})

                if "[INTERVIEW_COMPLETE]" in ai_text:
                    await websocket.send_json({
                        "type": "complete",
                        "session_id": session_id,
                    })
                    break

        except Exception as exc:
            print(f"LiveInterviewAgent error: {exc}")
            try:
                await websocket.send_json({"type": "error", "message": str(exc)})
            except Exception:
                pass

        return transcript

    async def _stream_turn(
        self,
        system_instruction: str,
        contents: list,
        websocket: WebSocket,
    ) -> str:
        """Stream one AI turn to the WebSocket. Returns the full text.

        Wrapped in a wall-clock timeout so a hung upstream generation can't
        block the turn — and the whole websocket — indefinitely.
        """
        full_text = ""
        trimmed_contents = _trim_history(contents)

        async def _consume():
            nonlocal full_text
            async for chunk in await self.client.aio.models.generate_content_stream(
                model=self.model,
                contents=trimmed_contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                ),
            ):
                if chunk.text:
                    full_text += chunk.text
                    await websocket.send_json({
                        "type": "ai_text",
                        "text": chunk.text,
                        "done": False,
                    })

        try:
            await asyncio.wait_for(_consume(), timeout=_STREAM_TIMEOUT)
        except asyncio.TimeoutError:
            print(f"LiveInterviewAgent: generation timed out after {_STREAM_TIMEOUT}s")
            if not full_text:
                full_text = "I'm sorry, I'm having trouble responding right now. Let's continue."

        await websocket.send_json({"type": "ai_text", "text": "", "done": True})
        return full_text
