"""
FastAPI backend for AI Interview Assistant (Firebase + Gemini)
"""

import asyncio
import logging
import os
import tempfile
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import (
    Depends, File, Form, FastAPI, HTTPException, Request,
    UploadFile, WebSocket, WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import settings
from app.database.firebase_db import FirebaseManager

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Interview Assistant",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"{request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response


# ── Firebase singleton ────────────────────────────────────────────────────────

_firebase_manager: Optional[FirebaseManager] = None


def get_firebase_manager() -> FirebaseManager:
    global _firebase_manager
    if _firebase_manager is None:
        _firebase_manager = FirebaseManager()
    return _firebase_manager


# ── Auth ──────────────────────────────────────────────────────────────────────

_security = HTTPBearer(auto_error=False)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authentication token")
    fb = get_firebase_manager()
    decoded = fb.verify_id_token(credentials.credentials)
    if not decoded:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token")
    return type("User", (), {
        "uid": decoded.get("uid", ""),
        "sub": decoded.get("uid", ""),
        "email": decoded.get("email", ""),
        "name": decoded.get("name", decoded.get("email", "").split("@")[0]),
        "user_metadata": decoded,
    })()


def _get_user_id(user) -> str:
    return getattr(user, "uid", getattr(user, "sub", ""))


# ── Pydantic models ───────────────────────────────────────────────────────────

class UserCredentials(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None


class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    job_title: Optional[str] = None
    years_experience: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    target_roles: Optional[List[str]] = None
    profile_complete: Optional[bool] = None


class AnswerRequest(BaseModel):
    session_id: str
    answer: str


class InterviewResponse(BaseModel):
    session_id: str
    current_question: Optional[str] = None
    is_complete: bool = False
    current_question_idx: int = 0
    total_questions: int = 0


class AnalysisResponse(BaseModel):
    session_id: str
    score: float = 0
    analysis: str = ""
    is_complete: bool = False
    next_question: Optional[str] = None


# ── In-memory stores ──────────────────────────────────────────────────────────

_active_sessions: Dict[str, Any] = {}   # LangGraph sessions (legacy REST flow)
_live_sessions: Dict[str, Any] = {}     # Gemini File API sessions (live WS flow)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _validate_upload(upload: UploadFile, field: str, max_bytes: int = 10 * 1024 * 1024) -> bytes:
    content = await upload.read()
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"{field} exceeds 10 MB limit")
    filename = (upload.filename or "").lower()
    if not (filename.endswith(".pdf") or filename.endswith(".txt")):
        raise HTTPException(status_code=400, detail=f"{field} must be a PDF or TXT file")
    return content


async def _run_resume_analysis(resume_text: str) -> dict:
    """Run AI analysis on resume text using Gemini."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {}
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        prompt = (
            "Analyze this resume and return a JSON object with keys: "
            "summary (string), skills (list of strings), experience_years (number), "
            "education (string), strengths (list of strings). Resume:\n\n" + resume_text[:3000]
        )
        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        import json
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"Resume analysis failed: {e}")
        return {}


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# ── Auth endpoints ────────────────────────────────────────────────────────────

@app.post("/auth/signup")
async def signup(credentials: UserCredentials):
    fb = get_firebase_manager()
    result = fb.create_user(credentials.email, credentials.password, credentials.full_name or "")
    if not result.get("success"):
        error = result.get("error", "Signup failed")
        if "already" in error.lower() or "exists" in error.lower():
            raise HTTPException(status_code=409, detail=error)
        raise HTTPException(status_code=400, detail=error)
    session = result.get("session", {})
    return {
        "message": "Account created",
        "user": result.get("user"),
        "session": session,
        "needs_setup": True,
    }


@app.post("/auth/signin")
async def signin(credentials: UserCredentials):
    fb = get_firebase_manager()
    result = fb.sign_in_with_email_password(credentials.email, credentials.password)
    if not result.get("success"):
        raise HTTPException(status_code=401, detail=result.get("error", "Sign in failed"))

    uid = result["user"]["uid"]
    profile = fb.get_user_profile(uid) or {}
    needs_setup = profile.get("profile_complete") is False

    return {
        "message": "Signed in",
        "user": result["user"],
        "session": result.get("session", {}),
        "needs_setup": needs_setup,
    }


@app.post("/auth/signout")
async def signout(current_user=Depends(get_current_user)):
    return {"message": "Signed out"}


@app.post("/auth/google")
async def google_signin(credentials: HTTPAuthorizationCredentials = Depends(_security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing token")
    fb = get_firebase_manager()
    decoded = fb.verify_id_token(credentials.credentials)
    if not decoded:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    uid = decoded.get("uid", "")
    email = decoded.get("email", "")
    name = decoded.get("name", email.split("@")[0])

    result = fb.get_or_create_user_profile(uid, email, name)
    profile = result["data"]
    # Only require setup for brand-new users or when profile_complete is explicitly False.
    needs_setup = result["is_new"] or profile.get("profile_complete") is False

    return {
        "user": {"id": uid, "email": email, "name": name},
        "needs_setup": needs_setup,
    }


@app.get("/auth/me")
async def get_current_user_info(current_user=Depends(get_current_user)):
    return {
        "user": {
            "id": _get_user_id(current_user),
            "email": getattr(current_user, "email", None),
            "name": getattr(current_user, "name", None),
        }
    }


# ── Profile ───────────────────────────────────────────────────────────────────

@app.get("/profile")
async def get_profile(current_user=Depends(get_current_user)):
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()
    profile = fb.get_user_profile(uid)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile.pop("resume_text", None)
    return {"profile": profile}


@app.put("/profile")
async def update_profile(request: ProfileUpdateRequest, current_user=Depends(get_current_user)):
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()
    update_data = {k: v for k, v in request.dict().items() if v is not None}
    if not fb.update_user_profile_full(uid, update_data):
        raise HTTPException(status_code=500, detail="Failed to update profile")
    return {"message": "Profile updated successfully"}


@app.post("/profile/resume")
async def upload_resume(resume: UploadFile = File(...), current_user=Depends(get_current_user)):
    uid = _get_user_id(current_user)
    resume_path = None
    try:
        resume_bytes = await _validate_upload(resume, "resume")
        suffix = ".pdf" if (resume.filename or "").lower().endswith(".pdf") else ".txt"
        with tempfile.NamedTemporaryFile(delete=False, dir="/tmp", suffix=suffix) as f:
            f.write(resume_bytes)
            resume_path = f.name

        from langchain_community.document_loaders import PyPDFLoader, TextLoader
        if resume_path.endswith(".pdf"):
            loader = PyPDFLoader(resume_path)
        else:
            loader = TextLoader(resume_path, encoding="utf-8")
        docs = loader.load()
        resume_text = "\n".join(d.page_content for d in docs)

        analysis = await _run_resume_analysis(resume_text)

        fb = get_firebase_manager()
        fb.store_resume_data(uid, resume_text, resume.filename, analysis)

        return {"message": "Resume uploaded and analyzed", "analysis": analysis, "filename": resume.filename}
    except HTTPException:
        raise
    except Exception as e:
        import traceback; logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to process resume: {e}")
    finally:
        if resume_path:
            try: os.unlink(resume_path)
            except OSError: pass


@app.get("/profile/resume/analysis")
async def get_resume_analysis(current_user=Depends(get_current_user)):
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()
    data = fb.get_resume_data(uid)
    if not data or not data.get("resume_analysis"):
        raise HTTPException(status_code=404, detail="No resume analysis found. Upload a resume first.")
    return data


# ── Legacy REST interview (LangGraph) ─────────────────────────────────────────

@app.post("/interview/start", response_model=InterviewResponse)
async def start_interview(
    resume: UploadFile = File(...),
    job_description: UploadFile = File(...),
    max_questions: int = Form(3),
    model_name: str = Form("gemini-2.5-flash"),
    temperature: float = Form(0.3),
    current_user=Depends(get_current_user),
):
    from app.services.interview_system import InterviewSystem
    from app.services.models import InterviewConfig

    user_id = _get_user_id(current_user)
    resume_path = job_path = None
    try:
        resume_bytes = await _validate_upload(resume, "resume")
        job_bytes = await _validate_upload(job_description, "job_description")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf" if (resume.filename or "").endswith(".pdf") else ".txt") as f:
            f.write(resume_bytes); resume_path = f.name
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(job_bytes); job_path = f.name

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="Gemini API key not configured")

        config = InterviewConfig(max_questions=max_questions, model_name=model_name, temperature=temperature)
        system = InterviewSystem(api_key, config)
        interview_state = system.start_interactive_interview(resume_path, job_path)

        session_id = str(uuid.uuid4())
        _active_sessions[session_id] = {
            "interview_system": system,
            "interview_state": interview_state,
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
        }

        question = system.get_next_question(interview_state)
        return InterviewResponse(
            session_id=session_id,
            current_question=question,
            is_complete=False,
            current_question_idx=interview_state.get("current_question_idx", 0),
            total_questions=len(interview_state.get("interview_plan", [])),
        )
    finally:
        for p in [resume_path, job_path]:
            if p:
                try: os.unlink(p)
                except OSError: pass


@app.post("/interview/answer", response_model=AnalysisResponse)
async def submit_answer(request: AnswerRequest, current_user=Depends(get_current_user)):
    if request.session_id not in _active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = _active_sessions[request.session_id]
    system = session["interview_system"]
    state = session["interview_state"]

    updated = system.process_candidate_answer(state, request.answer)
    session["interview_state"] = updated

    note = updated.get("interview_notes", [])[-1] if updated.get("interview_notes") else {}
    score = note.get("score", 0)
    analysis = note.get("analysis", note.get("observations", ""))

    current_idx = updated.get("current_question_idx", 0)
    total = len(updated.get("interview_plan", []))
    is_complete = current_idx >= total

    next_question = None
    if not is_complete:
        next_question = system.get_next_question(updated)

    return AnalysisResponse(
        session_id=request.session_id,
        score=score,
        analysis=analysis,
        is_complete=is_complete,
        next_question=next_question,
    )


@app.get("/interview/sessions")
async def get_interview_sessions(current_user=Depends(get_current_user), limit: int = 50):
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()
    try:
        sessions = fb.get_user_interview_sessions(uid, limit) or []
    except Exception:
        sessions = []
    return {"sessions": sessions}


@app.get("/interview/sessions/{session_id}")
async def get_interview_session(session_id: str, current_user=Depends(get_current_user)):
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()
    session = fb.get_interview_session(uid, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/interview/sessions/{session_id}/report")
async def get_interview_report(session_id: str, current_user=Depends(get_current_user)):
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()
    session = fb.get_interview_session(uid, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# ── Resume Analyzer ───────────────────────────────────────────────────────────

@app.post("/analyze/resume")
async def analyze_resume(resume: UploadFile = File(...), current_user=Depends(get_current_user)):
    resume_path = None
    try:
        resume_bytes = await _validate_upload(resume, "resume")
        suffix = ".pdf" if (resume.filename or "").lower().endswith(".pdf") else ".txt"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(resume_bytes); resume_path = f.name

        from langchain_community.document_loaders import PyPDFLoader, TextLoader
        loader = PyPDFLoader(resume_path) if resume_path.endswith(".pdf") else TextLoader(resume_path, encoding="utf-8")
        docs = loader.load()
        resume_text = "\n".join(d.page_content for d in docs)
        analysis = await _run_resume_analysis(resume_text)
        return {"analysis": analysis}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if resume_path:
            try: os.unlink(resume_path)
            except OSError: pass


# ── Live Interview — Gemini File API + streaming chat ─────────────────────────

@app.post("/interview/prepare")
async def prepare_live_interview(
    resume: UploadFile = File(...),
    job_description: UploadFile = File(...),
    interview_type: str = Form("Job Interview"),
    max_questions: int = Form(5),
    current_user=Depends(get_current_user),
):
    from app.services.gemini_file_service import GeminiFileService

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")

    uid = _get_user_id(current_user)
    session_id = str(uuid.uuid4())
    svc = GeminiFileService(api_key=api_key, model=settings.GEMINI_MODEL)

    resume_bytes = await _validate_upload(resume, "resume")
    jd_bytes = await _validate_upload(job_description, "job_description")

    with tempfile.TemporaryDirectory() as tmp:
        resume_path = os.path.join(tmp, resume.filename or "resume.pdf")
        jd_path = os.path.join(tmp, job_description.filename or "job_description.txt")
        with open(resume_path, "wb") as f: f.write(resume_bytes)
        with open(jd_path, "wb") as f: f.write(jd_bytes)

        resume_file = await svc.upload_file(resume_path, f"resume_{session_id}")
        jd_file = await svc.upload_file(jd_path, f"jd_{session_id}")

    question_plan = await svc.generate_question_plan(
        resume_file=resume_file,
        jd_file=jd_file,
        num_questions=max_questions,
        interview_type=interview_type,
    )

    _live_sessions[session_id] = {
        "user_id": uid,
        "interview_type": interview_type,
        "question_plan": question_plan,
        "resume_file_uri": resume_file.uri,
        "resume_mime_type": resume_file.mime_type or "application/pdf",
        "jd_file_uri": jd_file.uri,
        "jd_mime_type": jd_file.mime_type or "text/plain",
        "resume_file_name": resume_file.name,
        "jd_file_name": jd_file.name,
        "created_at": datetime.now().isoformat(),
    }

    return {
        "session_id": session_id,
        "question_count": len(question_plan),
        "interview_type": interview_type,
        "questions_preview": [q["question"] for q in question_plan],
    }


@app.websocket("/ws/interview/{session_id}")
async def live_interview_websocket(websocket: WebSocket, session_id: str):
    from app.services.live_interview_agent import LiveInterviewAgent
    from app.services.gemini_file_service import GeminiFileService

    await websocket.accept()

    # Auth
    try:
        auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=15)
        token = auth_msg.get("token", "")
        fb = get_firebase_manager()
        decoded = fb.verify_id_token(token)
        if not decoded:
            await websocket.send_json({"type": "error", "message": "Invalid token"})
            await websocket.close()
            return
        uid = decoded.get("uid") or decoded.get("user_id")
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": f"Auth failed: {exc}"})
        await websocket.close()
        return

    # Load session
    session = _live_sessions.get(session_id)
    if not session:
        await websocket.send_json({"type": "error", "message": "Session not found. Call /interview/prepare first."})
        await websocket.close()
        return

    if session["user_id"] != uid:
        await websocket.send_json({"type": "error", "message": "Unauthorised session"})
        await websocket.close()
        return

    await websocket.send_json({"type": "authenticated"})
    await websocket.send_json({
        "type": "ready",
        "session_id": session_id,
        "question_count": len(session["question_plan"]),
        "interview_type": session["interview_type"],
    })

    api_key = os.getenv("GEMINI_API_KEY")

    agent = LiveInterviewAgent(api_key=api_key)
    transcript = await agent.run(
        websocket=websocket,
        session_id=session_id,
        question_plan=session["question_plan"],
        interview_type=session["interview_type"],
        resume_file_uri=session["resume_file_uri"],
        resume_mime_type=session["resume_mime_type"],
        jd_file_uri=session["jd_file_uri"],
        jd_mime_type=session["jd_mime_type"],
    )

    if not transcript:
        logger.warning("Interview ended with empty transcript — skipping analysis.")
        _live_sessions.pop(session_id, None)
        return

    # Post-interview: analyze + save
    try:
        svc = GeminiFileService(api_key=api_key, model=settings.GEMINI_MODEL)

        class _FakeFile:
            def __init__(self, uri, mime):
                self.uri = uri
                self.mime_type = mime

        report_data = await svc.analyze_transcript(
            transcript=transcript,
            resume_file=_FakeFile(session["resume_file_uri"], session["resume_mime_type"]),
            jd_file=_FakeFile(session["jd_file_uri"], session["jd_mime_type"]),
        )

        fb = get_firebase_manager()
        fb.create_interview_session(
            user_id=uid,
            session_id=session_id,
            session_data={
                "title": f"{session['interview_type']} — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "status": "completed",
                "interview_plan": session["question_plan"],
                "conversation_history": transcript,
                "total_questions": len(session["question_plan"]),
                "average_score": report_data.get("overall_score", 0),
                "final_report": report_data.get("summary", ""),
                "report_data": report_data,
                "interview_type": session["interview_type"],
            },
        )

        await websocket.send_json({"type": "report_ready", "session_id": session_id})

    except Exception as exc:
        logger.error(f"Post-interview analysis failed: {exc}")

    finally:
        _live_sessions.pop(session_id, None)


if __name__ == "__main__":
    uvicorn.run(
        "app.server:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info",
    )
