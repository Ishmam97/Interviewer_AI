"""
FastAPI backend for AI Interview Assistant (Firebase + Gemini)
"""

import asyncio
import json
import logging
import os
import tempfile
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import (
    BackgroundTasks, Depends, File, Form, FastAPI, HTTPException, Request,
    UploadFile, WebSocket, WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import settings
from app.database.firebase_db import FirebaseManager

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

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
async def set_coop_header(request: Request, call_next):
    """Set Cross-Origin-Opener-Policy header to allow OAuth popups."""
    response = await call_next(request)
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Suppress health checks at INFO level — they dominate the logs
    if request.url.path == "/health":
        start = time.monotonic()
        response = await call_next(request)
        elapsed = time.monotonic() - start
        logger.debug(f"{request.method} {request.url.path} — {response.status_code} ({elapsed*1000:.0f}ms)")
        return response

    start = time.monotonic()
    response = await call_next(request)
    elapsed = time.monotonic() - start
    logger.info(f"{request.method} {request.url.path} — {response.status_code} ({elapsed*1000:.0f}ms)")
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


class SettingsUpdateRequest(BaseModel):
    max_questions: Optional[int] = None
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    api_provider: Optional[str] = None   # "openai", "gemini", "anthropic"
    user_api_key: Optional[str] = None   # empty string = use system key
    base_url: Optional[str] = None       # custom base URL (e.g. for AIML API)


class AnswerRequest(BaseModel):
    session_id: str
    answer: str


class PasswordUpdateRequest(BaseModel):
    new_password: str


class SuggestionActionRequest(BaseModel):
    action: str  # "accept" or "reject"


class BulkSuggestionRequest(BaseModel):
    suggestion_ids: List[str]  # original suggestion IDs to mark as accepted
    section: str               # lowercase section key, e.g. "experience"


class SectionUndoRequest(BaseModel):
    section: str  # section key to undo, e.g. "experience"


class SuggestionUndoRequest(BaseModel):
    pass


class DreamJobFromLinkRequest(BaseModel):
    url: str


class DreamJobCreateRequest(BaseModel):
    company: str
    role_title: str
    jd_text: str
    source: str  # "manual" | "link"
    source_url: Optional[str] = None
    resume_analysis_id: str


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
    if len(content) == 0:
        raise HTTPException(status_code=400, detail=f"{field} file is empty")
    filename = (upload.filename or "").lower()
    if not (filename.endswith(".pdf") or filename.endswith(".txt")):
        raise HTTPException(status_code=400, detail=f"{field} must be a PDF or TXT file")
    return content

def _create_interview_system(
    api_key: str,
    config,
    provider: str,
    base_url,
    system_api_key,
    system_base_url,
):
    """Construct an InterviewSystem. Extracted as a seam so routes stay testable
    (tests patch this instead of the heavy LLM/RAG constructor)."""
    from app.services.interview_system import InterviewSystem

    return InterviewSystem(
        api_key=api_key,
        config=config,
        provider=provider,
        base_url=base_url,
        system_api_key=system_api_key,
        system_base_url=system_base_url,
    )


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


@app.get("/admin/health")
async def admin_health_check():
    """Deep health check: reports API status plus database connectivity.

    Used by uptime monitoring to distinguish "process up" from "process up but
    Firestore unreachable". Never raises — always returns 200 with a status body.
    """
    database_status = "unknown"
    try:
        fb = get_firebase_manager()
        conn = fb.test_connection()
        database_status = "healthy" if conn.get("success") else "unhealthy"
    except Exception as e:
        logger.error(f"Admin health check DB probe failed: {e}")
        database_status = "unhealthy"
    return {
        "api_status": "healthy",
        "database_status": database_status,
        "timestamp": datetime.now().isoformat(),
    }


# ── Auth endpoints ────────────────────────────────────────────────────────────

@app.post("/auth/signup")
async def signup(credentials: UserCredentials):
    fb = get_firebase_manager()
    result = fb.sign_up(credentials.email, credentials.password, credentials.full_name or "")
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
    result = fb.sign_in(credentials.email, credentials.password)
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
    uid = _get_user_id(current_user)
    providers: List[str] = []
    try:
        from firebase_admin import auth as _fb_auth
        record = _fb_auth.get_user(uid)
        providers = [p.provider_id for p in (record.provider_data or [])]
    except Exception as e:
        logger.warning(f"Could not load provider info for {uid}: {e}")
    return {
        "user": {
            "id": uid,
            "email": getattr(current_user, "email", None),
            "name": getattr(current_user, "name", None),
            "providers": providers,
            "has_password": "password" in providers,
        }
    }


@app.post("/auth/password")
async def set_password(
    request: PasswordUpdateRequest,
    current_user=Depends(get_current_user),
):
    """Set or update the password for the current Firebase user.

    Lets users who signed up via Google add a password credential to the same
    Firebase account, so they can sign in with either method afterwards.
    """
    new_password = (request.new_password or "").strip()
    if len(new_password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 6 characters",
        )
    uid = _get_user_id(current_user)
    try:
        from firebase_admin import auth as _fb_auth
        _fb_auth.update_user(uid, password=new_password)
    except Exception as e:
        logger.error(f"Failed to update password for {uid}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update password")
    return {"message": "Password updated"}


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


async def _run_resume_analysis_bg(uid: str, resume_text: str, filename: str, analysis_id: str):
    """Background task: run full resume analysis and persist to Firestore."""
    from app.services.resume_analyzer_service import ResumeAnalyzerService, _ANALYSIS_TIMEOUT
    fb = get_firebase_manager()
    logger.info(f"[resume_analysis:{analysis_id}] Background task started for user {uid}, file='{filename}'")
    try:
        svc = ResumeAnalyzerService(api_key=settings.OPENAI_API_KEY)
        analysis = await asyncio.wait_for(
            svc.analyze(resume_text, filename, analysis_id=analysis_id, fb=fb),
            timeout=_ANALYSIS_TIMEOUT,
        )

        logger.info(f"[resume_analysis:{analysis_id}] Analysis complete, persisting to Firestore…")
        fb.update_resume_analysis(analysis_id, {
            "status": "completed",
            "current_step": "completed",
            "overall": analysis["overall"],
            "sections": analysis["sections"],
            "ats": analysis["ats"],
            "lackings": analysis.get("lackings", []),
            "quality_score": analysis.get("quality_score", 0),
        })
        fb.save_resume_parsed_sections(uid, analysis_id, filename, analysis.get("parsed_sections", {}))
        fb.save_token_usage(uid, "resume_analysis", analysis_id, analysis.get("usage", {}))
        fb.store_resume_data(uid, resume_text, filename, analysis_id, analysis)
        logger.info(f"[resume_analysis:{analysis_id}] All results saved to Firestore successfully")
    except asyncio.TimeoutError:
        logger.error(f"[resume_analysis:{analysis_id}] Timed out after {_ANALYSIS_TIMEOUT}s")
        fb.update_resume_analysis(analysis_id, {
            "status": "failed",
            "current_step": "timeout",
        })
    except Exception as e:
        import traceback
        logger.error(f"[resume_analysis:{analysis_id}] Failed: {e}\n{traceback.format_exc()}")
        fb.update_resume_analysis(analysis_id, {
            "status": "failed",
            "current_step": "failed",
        })


@app.post("/profile/resume")
async def upload_resume(
    background_tasks: BackgroundTasks,
    resume: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
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

        analysis_id = str(uuid.uuid4())
        fb = get_firebase_manager()
        fb.create_resume_analysis(uid, analysis_id, resume.filename)

        background_tasks.add_task(_run_resume_analysis_bg, uid, resume_text, resume.filename, analysis_id)

        return {"analysis_id": analysis_id, "status": "processing", "message": "Resume analysis started"}
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


@app.get("/resume/analysis/{analysis_id}/status")
async def get_analysis_status(analysis_id: str, current_user=Depends(get_current_user)):
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()
    doc = fb.get_resume_analysis_by_id(analysis_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if doc.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")

    response = {
        "analysis_id": analysis_id,
        "status": doc.get("status"),
        "current_step": doc.get("current_step"),
        "filename": doc.get("filename"),
    }
    if doc.get("status") == "completed":
        response["analysis"] = {
            "overall": doc.get("overall"),
            "sections": doc.get("sections"),
            "ats": doc.get("ats"),
            "lackings": doc.get("lackings", []),
            "quality_score": doc.get("quality_score", 0),
        }
    return response


@app.post("/profile/resume/suggestions/{suggestion_id}")
async def update_suggestion(
    suggestion_id: str,
    request: SuggestionActionRequest,
    current_user=Depends(get_current_user),
):
    if request.action not in ("accept", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'accept' or 'reject'")
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()

    profile_data = fb.get_resume_data(uid)
    if not profile_data:
        raise HTTPException(status_code=404, detail="No resume data found.")
    analysis_id = profile_data.get("current_analysis_id")
    if not analysis_id:
        raise HTTPException(status_code=404, detail="No resume analysis found.")

    analysis = fb.get_resume_analysis_by_id(analysis_id)
    if not analysis or analysis.get("status") != "completed":
        raise HTTPException(status_code=404, detail="Completed resume analysis not found.")

    new_status = "accepted" if request.action == "accept" else "rejected"
    updated = False
    matched_suggestion = None
    section_name = None

    for s in analysis.get("overall", {}).get("suggestions", []):
        if s.get("id") == suggestion_id:
            s["status"] = new_status
            updated = True
            matched_suggestion = s
            section_name = "overall"

    for sec in analysis.get("sections", []):
        for s in sec.get("suggestions", []):
            if s.get("id") == suggestion_id:
                s["status"] = new_status
                updated = True
                matched_suggestion = s
                section_name = sec.get("name", "").lower()

    if not updated:
        raise HTTPException(status_code=404, detail="Suggestion not found.")

    fb.update_resume_analysis(analysis_id, {
        "overall": analysis.get("overall", {}),
        "sections": analysis.get("sections", []),
    })

    # If accepted, apply the suggestion to the resume data in the profile
    applied_changes = None
    if request.action == "accept" and matched_suggestion:
        applied_changes = await _apply_suggestion_to_resume(
            fb, uid, suggestion_id, matched_suggestion.get("text", ""), section_name
        )

    result = {
        "message": "Suggestion updated",
        "suggestion_id": suggestion_id,
        "status": new_status,
    }
    if applied_changes:
        result["applied_changes"] = applied_changes

    return result


async def _apply_suggestion_to_resume(
    fb: FirebaseManager,
    user_id: str,
    suggestion_id: str,
    suggestion_text: str,
    section_name: str,
) -> Optional[dict]:
    """Use the LLM to apply an accepted suggestion to the user's edited_resume_data.

    Saves a snapshot before applying so the change can be undone.
    Returns a dict describing what was changed, or None if nothing could be applied.
    """
    logger.info(f"[ApplySuggestion] Starting: user={user_id}, suggestion={suggestion_id}, section={section_name}")

    # Get current edited_resume_data from profile (or parsed_sections from analysis)
    profile = fb.get_user_profile(user_id)
    if not profile:
        logger.warning(f"[ApplySuggestion] No profile found for user {user_id}")
        return None

    edited_data = profile.get("edited_resume_data")
    if not edited_data:
        logger.info(f"[ApplySuggestion] No edited_resume_data in profile, falling back to parsed_sections")
        # Fall back to parsed_sections — stored in a separate collection
        analysis_id = profile.get("current_analysis_id")
        if not analysis_id:
            logger.warning(f"[ApplySuggestion] No current_analysis_id in profile for user {user_id}")
            return None
        # parsed_sections lives in resume_parsed_sections/{analysis_id}, not in the analysis doc
        parsed_doc = fb.db.collection("resume_parsed_sections").document(analysis_id).get()
        if parsed_doc.exists:
            parsed_data = parsed_doc.to_dict()
            edited_data = parsed_data.get("parsed_sections", {})
            if edited_data:
                logger.info(f"[ApplySuggestion] Loaded parsed_sections from resume_parsed_sections/{analysis_id} (keys: {list(edited_data.keys())})")
        if not edited_data:
            logger.warning(f"[ApplySuggestion] No parsed_sections found for analysis {analysis_id}")
            return None
    else:
        logger.info(f"[ApplySuggestion] Using edited_resume_data from profile (keys: {list(edited_data.keys())})")

    # Save a snapshot of the current state for undo
    snapshot_ref = fb.db.collection("suggestion_snapshots").document(f"{user_id}:{suggestion_id}")
    snapshot_ref.set({
        "user_id": user_id,
        "suggestion_id": suggestion_id,
        "snapshot_data": edited_data,
        "created_at": datetime.now().isoformat(),
    })
    logger.info(f"[ApplySuggestion] Snapshot saved for {user_id}:{suggestion_id}")

    # Get the API key to use for the LLM call
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        logger.warning("No OPENAI_API_KEY configured — cannot apply suggestion to resume.")
        return None

    client = AsyncOpenAI(api_key=api_key)

    section_context = ""
    if section_name and section_name != "overall":
        section_data = edited_data.get(section_name)
        if section_data is not None:
            section_context = json.dumps({section_name: section_data}, indent=2, ensure_ascii=False)
        else:
            # Try to find by display name mapping
            display_map = {
                "contact": "contact", "summary": "summary", "experience": "experience",
                "education": "education", "skills": "skills", "certifications": "certifications",
                "projects": "projects",
            }
            key = display_map.get(section_name)
            if key and key in edited_data:
                section_context = json.dumps({key: edited_data[key]}, indent=2, ensure_ascii=False)

    full_context = json.dumps(edited_data, indent=2, ensure_ascii=False)

    prompt = (
        f"You are editing a resume based on an accepted suggestion.\n\n"
        f"Current resume (JSON):\n{full_context}\n\n"
        f"{f'Relevant section context:\n{section_context}\n\n' if section_context else ''}"
        f"Suggestion: {suggestion_text}\n\n"
        f"Return a JSON object with the updated resume structure. "
        f"Only modify the fields necessary to address the suggestion. "
        f"Keep the same overall structure and all other fields intact.\n\n"
        f"If the suggestion is about adding notes or improvements that don't fit "
        f"into existing fields, add a '_notes' key at the top level with an array of note strings.\n\n"
        f"Return ONLY valid JSON, no markdown or explanations."
    )

    try:
        llm_model = "openai/gpt-4.1-mini-2025-04-14"
        logger.info(f"[ApplySuggestion] Calling OpenAI with model={llm_model}")
        response = await client.chat.completions.create(
            model=llm_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        usage = response.usage
        logger.info(
            f"[ApplySuggestion][TokenUsage] model={llm_model} "
            f"prompt_tokens={usage.prompt_tokens if usage else '?'} "
            f"completion_tokens={usage.completion_tokens if usage else '?'} "
            f"total_tokens={usage.total_tokens if usage else '?'} "
            f"section={section_name} suggestion_id={suggestion_id}"
        )
        updated_data = json.loads(response.choices[0].message.content)
        logger.info(f"[ApplySuggestion] Parsed updated resume JSON (keys: {list(updated_data.keys())})")

        # Save back to the profile
        fb.update_user_profile_full(user_id, {"edited_resume_data": updated_data})
        logger.info(f"[ApplySuggestion] Saved updated resume to profile.edited_resume_data")

        # Return a summary of what changed
        changes = {"section": section_name or "overall", "suggestion_applied": suggestion_text}
        if "_notes" in updated_data:
            changes["notes_added"] = updated_data["_notes"]
        return changes
    except Exception as e:
        logger.error(f"[ApplySuggestion] Failed to apply suggestion: {e}", exc_info=True)
        return None


async def _apply_bulk_suggestions_to_section(
    fb: FirebaseManager,
    user_id: str,
    analysis_id: str,
    section_key: str,
    suggestion_items: list,  # [{"id": ..., "text": ...}, ...]
) -> Optional[dict]:
    """Apply multiple suggestions to a single section in one focused LLM call.

    Uses a section-scoped prompt so the model only sees and returns the relevant
    section — faster, cheaper, and less likely to corrupt other sections.
    Saves per-suggestion snapshots so each can be individually undone.
    Returns {"updated_section": <new_section_data>} or None on failure.
    """
    logger.info(
        f"[BulkApply] Starting: user={user_id}, analysis={analysis_id}, "
        f"section={section_key}, n={len(suggestion_items)}"
    )

    # Load working_parsed_sections from the per-analysis collection
    parsed_doc = fb.db.collection("resume_parsed_sections").document(analysis_id).get()
    if not parsed_doc.exists:
        logger.warning(f"[BulkApply] No resume_parsed_sections doc for {analysis_id}")
        return None

    parsed_data = parsed_doc.to_dict()
    working = parsed_data.get("working_parsed_sections") or parsed_data.get("parsed_sections") or {}
    if not working:
        logger.warning(f"[BulkApply] Empty parsed sections for {analysis_id}")
        return None

    # Resolve the section key (handle capitalised names from section.name)
    _key_map = {
        "contact": "contact", "summary": "summary", "experience": "experience",
        "education": "education", "skills": "skills",
        "certifications": "certifications", "projects": "projects",
    }
    resolved_key = _key_map.get(section_key.lower(), section_key.lower())
    section_data = working.get(resolved_key)
    if section_data is None:
        logger.warning(f"[BulkApply] Section '{resolved_key}' not found in working_parsed_sections (keys: {list(working.keys())})")
        return None

    # Save a section-level snapshot (keyed by analysis:section) for group undo
    snapshot_key = f"{analysis_id}:{resolved_key}"
    fb.db.collection("section_snapshots").document(snapshot_key).set({
        "user_id": user_id,
        "analysis_id": analysis_id,
        "section_key": resolved_key,
        "snapshot_section": section_data,
        "suggestion_ids": [item["id"] for item in suggestion_items],
        "created_at": datetime.now().isoformat(),
    })
    logger.info(f"[BulkApply] Saved section snapshot for undo: {snapshot_key}")

    api_key = settings.OPENAI_API_KEY
    if not api_key:
        logger.warning("[BulkApply] No OPENAI_API_KEY — cannot call LLM.")
        return None

    client = AsyncOpenAI(api_key=api_key)

    numbered_suggestions = "\n".join(
        f"{i + 1}. {item['text']}" for i, item in enumerate(suggestion_items)
    )
    section_json = json.dumps({resolved_key: section_data}, indent=2, ensure_ascii=False)

    prompt = (
        f"You are a professional resume editor. "
        f"Apply ALL of the following suggestions to improve ONLY the \"{resolved_key}\" section.\n\n"
        f"Current \"{resolved_key}\" section:\n{section_json}\n\n"
        f"Suggestions to apply (apply every one of them):\n{numbered_suggestions}\n\n"
        f"Return a JSON object with exactly ONE key: \"{resolved_key}\".\n"
        f"The value must be the fully updated {resolved_key} data with all suggestions incorporated.\n"
        f"Preserve the existing data structure and types exactly.\n"
        f"Do NOT include any other sections, fields, or keys.\n"
        f"Return ONLY valid JSON."
    )

    try:
        logger.info(f"[BulkApply] Calling LLM for section='{resolved_key}' with {len(suggestion_items)} suggestions")
        llm_model = "openai/gpt-4.1-mini-2025-04-14"
        response = await client.chat.completions.create(
            model=llm_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        usage = response.usage
        logger.info(
            f"[BulkApply][TokenUsage] model={llm_model} "
            f"prompt_tokens={usage.prompt_tokens if usage else '?'} "
            f"completion_tokens={usage.completion_tokens if usage else '?'} "
            f"total_tokens={usage.total_tokens if usage else '?'} "
            f"section={resolved_key} suggestions={len(suggestion_items)}"
        )
        result_data = json.loads(response.choices[0].message.content)
        logger.info(f"[BulkApply] LLM returned keys: {list(result_data.keys())}")

        updated_section = result_data.get(resolved_key)
        if updated_section is None:
            logger.error(f"[BulkApply] LLM response missing key '{resolved_key}': {result_data}")
            return None

        # Merge the updated section back into working_parsed_sections
        new_working = dict(working)
        new_working[resolved_key] = updated_section
        fb.db.collection("resume_parsed_sections").document(analysis_id).update({
            "working_parsed_sections": new_working,
            "updated_at": datetime.now().isoformat(),
        })
        logger.info(f"[BulkApply] Saved updated '{resolved_key}' to resume_parsed_sections/{analysis_id}")

        return {"updated_section": updated_section, "section_key": resolved_key, "previous_section": section_data}
    except Exception as e:
        logger.error(f"[BulkApply] LLM call failed: {e}", exc_info=True)
        return None


def _restore_suggestion_snapshot(
    fb: FirebaseManager,
    user_id: str,
    suggestion_id: str,
) -> Optional[dict]:
    """Restore the edited_resume_data from the snapshot saved before accepting a suggestion.

    Returns the restored data, or None if no snapshot exists.
    """
    snapshot_id = f"{user_id}:{suggestion_id}"
    snapshot_doc = fb.db.collection("suggestion_snapshots").document(snapshot_id).get()

    if not snapshot_doc.exists:
        logger.warning(f"No snapshot found for suggestion {suggestion_id}, user {user_id}")
        return None

    snapshot_data = snapshot_doc.to_dict().get("snapshot_data")
    if not snapshot_data:
        logger.warning(f"Snapshot for {suggestion_id} has no data")
        return None

    # Restore the snapshot as the current edited_resume_data
    fb.update_user_profile_full(user_id, {"edited_resume_data": snapshot_data})

    # Delete the snapshot so it can't be undone again
    fb.db.collection("suggestion_snapshots").document(snapshot_id).delete()

    return snapshot_data


@app.post("/profile/resume/suggestions/{suggestion_id}/undo")
async def undo_suggestion(
    suggestion_id: str,
    current_user=Depends(get_current_user),
):
    """Undo an accepted suggestion, restoring the resume to its pre-accept state."""
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()

    profile_data = fb.get_resume_data(uid)
    if not profile_data:
        raise HTTPException(status_code=404, detail="No resume data found.")
    analysis_id = profile_data.get("current_analysis_id")
    if not analysis_id:
        raise HTTPException(status_code=404, detail="No resume analysis found.")

    analysis = fb.get_resume_analysis_by_id(analysis_id)
    if not analysis or analysis.get("status") != "completed":
        raise HTTPException(status_code=404, detail="Completed resume analysis not found.")

    # Find the suggestion and verify it's currently accepted
    found = False
    is_accepted = False

    for s in analysis.get("overall", {}).get("suggestions", []):
        if s.get("id") == suggestion_id:
            found = True
            is_accepted = s.get("status") == "accepted"

    if not found:
        for sec in analysis.get("sections", []):
            for s in sec.get("suggestions", []):
                if s.get("id") == suggestion_id:
                    found = True
                    is_accepted = s.get("status") == "accepted"

    if not found:
        raise HTTPException(status_code=404, detail="Suggestion not found.")
    if not is_accepted:
        raise HTTPException(status_code=400, detail="Suggestion has not been accepted — nothing to undo.")

    # Restore the pre-accept state
    restored = _restore_suggestion_snapshot(fb, uid, suggestion_id)
    if not restored:
        raise HTTPException(status_code=404, detail="No undo snapshot found. Changes may have already been overwritten.")

    # Revert the suggestion status back to pending
    for s in analysis.get("overall", {}).get("suggestions", []):
        if s.get("id") == suggestion_id:
            s["status"] = "pending"

    for sec in analysis.get("sections", []):
        for s in sec.get("suggestions", []):
            if s.get("id") == suggestion_id:
                s["status"] = "pending"

    fb.update_resume_analysis(analysis_id, {
        "overall": analysis.get("overall", {}),
        "sections": analysis.get("sections", []),
    })

    return {"message": "Suggestion undone. Resume restored to previous state.", "suggestion_id": suggestion_id}


@app.post("/profile/resumes/{analysis_id}/suggestions/bulk")
async def apply_bulk_suggestions(
    analysis_id: str,
    request: BulkSuggestionRequest,
    current_user=Depends(get_current_user),
):
    """Accept multiple suggestions at once and apply them to the given section in one LLM call."""
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()

    analysis = fb.get_resume_analysis_by_id(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")
    if analysis.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Analysis is not yet completed")

    # Mark each suggestion as accepted in the analysis doc
    suggestion_items = []  # [{"id": ..., "text": ...}]
    ids_to_accept = set(request.suggestion_ids)
    remaining = set(ids_to_accept)

    for s in analysis.get("overall", {}).get("suggestions", []):
        if s.get("id") in ids_to_accept:
            s["status"] = "accepted"
            suggestion_items.append({"id": s["id"], "text": s.get("text", "")})
            remaining.discard(s["id"])

    for sec in analysis.get("sections", []):
        for s in sec.get("suggestions", []):
            if s.get("id") in ids_to_accept:
                s["status"] = "accepted"
                suggestion_items.append({"id": s["id"], "text": s.get("text", "")})
                remaining.discard(s["id"])

    if not suggestion_items:
        raise HTTPException(status_code=404, detail="No matching suggestions found")

    fb.update_resume_analysis(analysis_id, {
        "overall": analysis.get("overall", {}),
        "sections": analysis.get("sections", []),
    })

    # Apply all suggestions to just that section in a single focused LLM call
    result = await _apply_bulk_suggestions_to_section(
        fb, uid, analysis_id, request.section, suggestion_items
    )

    return {
        "message": f"{len(suggestion_items)} suggestion(s) applied to '{request.section}'",
        "applied_count": len(suggestion_items),
        "not_found_ids": list(remaining),
        "updated_section": result.get("updated_section") if result else None,
        "section_key": result.get("section_key") if result else request.section,
        "previous_section": result.get("previous_section") if result else None,
    }


@app.post("/profile/resumes/{analysis_id}/suggestions/undo-section")
async def undo_section_suggestions(
    analysis_id: str,
    request: SectionUndoRequest,
    current_user=Depends(get_current_user),
):
    """Undo the last bulk-apply on a section, restoring the previous version and
    reverting all accepted suggestions in that section back to pending."""
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()

    analysis = fb.get_resume_analysis_by_id(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")

    section_key = request.section.lower()
    snapshot_key = f"{analysis_id}:{section_key}"
    snap_doc = fb.db.collection("section_snapshots").document(snapshot_key).get()

    if not snap_doc.exists:
        raise HTTPException(status_code=404, detail="No undo snapshot for this section.")

    snap = snap_doc.to_dict()
    previous_section = snap.get("snapshot_section")
    reverted_ids = snap.get("suggestion_ids", [])

    if previous_section is None:
        raise HTTPException(status_code=404, detail="Snapshot has no section data.")

    # Restore the section in working_parsed_sections
    parsed_doc = fb.db.collection("resume_parsed_sections").document(analysis_id).get()
    if parsed_doc.exists:
        parsed_data = parsed_doc.to_dict()
        working = parsed_data.get("working_parsed_sections") or parsed_data.get("parsed_sections") or {}
        working[section_key] = previous_section
        fb.db.collection("resume_parsed_sections").document(analysis_id).update({
            "working_parsed_sections": working,
            "updated_at": datetime.now().isoformat(),
        })

    # Revert accepted suggestions back to pending
    ids_set = set(reverted_ids)
    for s in analysis.get("overall", {}).get("suggestions", []):
        if s.get("id") in ids_set and s.get("status") == "accepted":
            s["status"] = "pending"
    for sec in analysis.get("sections", []):
        for s in sec.get("suggestions", []):
            if s.get("id") in ids_set and s.get("status") == "accepted":
                s["status"] = "pending"

    fb.update_resume_analysis(analysis_id, {
        "overall": analysis.get("overall", {}),
        "sections": analysis.get("sections", []),
    })

    # Delete the snapshot
    fb.db.collection("section_snapshots").document(snapshot_key).delete()

    return {
        "message": f"Undone {len(reverted_ids)} suggestion(s) in '{section_key}'",
        "reverted_ids": reverted_ids,
        "restored_section": previous_section,
        "section_key": section_key,
    }


# ── User Settings ─────────────────────────────────────────────────────────────

@app.get("/settings")
async def get_settings(current_user=Depends(get_current_user)):
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()
    s = fb.get_user_settings(uid) or {}
    # Never expose the raw key — mask it for the client
    raw_key = s.get("user_api_key", "")
    s["user_api_key_set"] = bool(raw_key)
    s.pop("user_api_key", None)
    return {"settings": s}


@app.put("/settings")
async def update_settings(request: SettingsUpdateRequest, current_user=Depends(get_current_user)):
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()
    update_data = {k: v for k, v in request.dict().items() if v is not None}
    if not fb.update_user_settings(uid, update_data):
        raise HTTPException(status_code=500, detail="Failed to update settings")
    return {"message": "Settings updated successfully"}


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

    # Resolve which API key / provider to use
    fb = get_firebase_manager()
    user_settings = fb.get_user_settings(user_id) or {}

    system_api_key = settings.OPENAI_API_KEY
    system_base_url = settings.OPENAI_BASE_URL or None

    user_api_key = user_settings.get("user_api_key", "")
    provider = user_settings.get("api_provider", "openai")
    user_base_url = user_settings.get("base_url", "") or None

    if user_api_key:
        resolved_key = user_api_key
        resolved_base_url = user_base_url
    else:
        # Fall back to system AIML/OpenAI key
        resolved_key = system_api_key
        resolved_base_url = system_base_url
        provider = "openai"

    if not resolved_key:
        raise HTTPException(status_code=500, detail="No API key configured. Add your key in Settings.")

    effective_model = model_name or user_settings.get("model_name", settings.DEFAULT_MODEL)

    resume_path = job_path = None
    try:
        resume_bytes = await _validate_upload(resume, "resume")
        job_bytes = await _validate_upload(job_description, "job_description")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf" if (resume.filename or "").endswith(".pdf") else ".txt") as f:
            f.write(resume_bytes); resume_path = f.name
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(job_bytes); job_path = f.name

        config = InterviewConfig(max_questions=max_questions, model_name=effective_model, temperature=temperature)
        system = InterviewSystem(
            api_key=resolved_key,
            config=config,
            provider=provider,
            base_url=resolved_base_url,
            system_api_key=system_api_key,
            system_base_url=system_base_url,
        )
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
    session = fb.get_interview_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/interview/sessions/{session_id}/report")
async def get_interview_report(session_id: str, current_user=Depends(get_current_user)):
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()
    session = fb.get_interview_session(session_id)
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


# ── Resume versioning ─────────────────────────────────────────────────────────

@app.get("/profile/resumes")
async def get_user_resumes(current_user=Depends(get_current_user)):
    """Return list of all resume analyses for the current user."""
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()
    analyses = fb.get_user_resume_analyses(uid) or []
    profile = fb.get_user_profile(uid) or {}
    active_id = profile.get("current_analysis_id")

    results = []
    for a in analyses:
        # Fetch parsed sections for quality_score if available
        parsed_doc = fb.db.collection("resume_parsed_sections").document(a["id"]).get()
        has_parsed = parsed_doc.exists

        results.append({
            "analysis_id": a["id"],
            "filename": a.get("filename", ""),
            "created_at": a.get("created_at", ""),
            "status": a.get("status", ""),
            "quality_score": a.get("quality_score", 0),
            "overall_score": a.get("overall", {}).get("overall_score", 0),
            "is_active": a["id"] == active_id,
            "has_parsed_sections": has_parsed,
        })

    return {"resumes": results}


@app.get("/profile/resumes/{analysis_id}")
async def get_resume_by_id(analysis_id: str, current_user=Depends(get_current_user)):
    """Get a specific resume analysis by ID with parsed sections."""
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()
    
    # Fetch the analysis document
    doc = fb.get_resume_analysis_by_id(analysis_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if doc.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    # Fetch parsed sections
    parsed_doc = fb.db.collection("resume_parsed_sections").document(analysis_id).get()
    parsed_sections = parsed_doc.to_dict().get("parsed_sections", {}) if parsed_doc.exists else {}
    
    response = {
        "analysis_id": analysis_id,
        "filename": doc.get("filename", ""),
        "created_at": doc.get("created_at", ""),
        "status": doc.get("status", ""),
        "resume_analysis": {
            "overall": doc.get("overall"),
            "sections": doc.get("sections"),
            "ats": doc.get("ats"),
            "lackings": doc.get("lackings", []),
            "quality_score": doc.get("quality_score", 0),
            "parsed_sections": parsed_sections,
            "usage": doc.get("usage"),
        },
    }
    return response


@app.delete("/profile/resumes/{analysis_id}")
async def delete_resume(analysis_id: str, current_user=Depends(get_current_user)):
    """Delete a resume version (with ownership check)."""
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()
    success = fb.delete_resume_analysis(analysis_id, uid)
    if not success:
        raise HTTPException(status_code=404, detail="Resume not found or access denied")
    return {"message": "Resume deleted successfully", "analysis_id": analysis_id}


@app.post("/profile/resumes/{analysis_id}/set-active")
async def set_active_resume(analysis_id: str, current_user=Depends(get_current_user)):
    """Set a specific resume analysis as the active one."""
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()
    success = fb.set_active_resume(uid, analysis_id)
    if not success:
        raise HTTPException(status_code=404, detail="Resume not found or access denied")
    return {"message": "Active resume updated", "analysis_id": analysis_id}


# ── Dream Job ─────────────────────────────────────────────────────────────────


async def _run_dream_job_analysis_bg(
    uid: str, dream_job_id: str, jd_text: str, resume_analysis_id: str
):
    """Background task: run full dream-job fit analysis and persist to Firestore."""
    from app.services.dream_job_analyzer_service import (
        DreamJobAnalyzerService,
        _ANALYSIS_TIMEOUT,
    )

    fb = get_firebase_manager()
    logger.info(
        f"[dream_job_analysis:{dream_job_id}] Background task started for user {uid}"
    )

    try:
        fb.update_dream_job(dream_job_id, {"status": "normalizing", "current_step": "starting"})

        # Retrieve resume parsed sections from Firestore
        parsed_doc = fb.get_resume_parsed_doc(resume_analysis_id)
        if parsed_doc:
            parsed_sections = (
                parsed_doc.get("working_parsed_sections")
                or parsed_doc.get("parsed_sections")
                or {}
            )
        else:
            parsed_sections = {}

        # Raw resume text is not persisted — reconstruct from parsed sections.
        # The Kimi fit prompt has the structured sections anyway, so this is sufficient.
        import json as _json
        resume_text = _json.dumps(parsed_sections, ensure_ascii=False)

        svc = DreamJobAnalyzerService(api_key=settings.OPENAI_API_KEY)
        analysis = await asyncio.wait_for(
            svc.analyze(
                jd_text=jd_text,
                resume_parsed_sections=parsed_sections,
                resume_text=resume_text,
                dream_job_id=dream_job_id,
                fb=fb,
            ),
            timeout=_ANALYSIS_TIMEOUT,
        )

        logger.info(
            f"[dream_job_analysis:{dream_job_id}] Analysis complete, persisting to Firestore…"
        )
        fb.update_dream_job(dream_job_id, {
            "status": "completed",
            "current_step": "completed",
            "jd_normalized": analysis["jd_normalized"],
            "result": analysis["fit_analysis"],
            "usage": analysis["usage"],
            "error": None,
        })
        fb.save_token_usage(uid, "dream_job_analysis", dream_job_id, analysis["usage"])
        logger.info(
            f"[dream_job_analysis:{dream_job_id}] All results saved to Firestore successfully"
        )

    except asyncio.TimeoutError:
        logger.error(
            f"[dream_job_analysis:{dream_job_id}] Timed out after {_ANALYSIS_TIMEOUT}s"
        )
        fb.update_dream_job(dream_job_id, {
            "status": "failed",
            "current_step": "timeout",
            "error": "Analysis timed out",
        })
    except Exception as e:
        import traceback as _tb
        logger.error(
            f"[dream_job_analysis:{dream_job_id}] Failed: {e}\n{_tb.format_exc()}"
        )
        fb.update_dream_job(dream_job_id, {
            "status": "failed",
            "current_step": "failed",
            "error": str(e),
        })


@app.post("/dream-job/from-link")
async def dream_job_from_link(
    request: DreamJobFromLinkRequest,
    current_user=Depends(get_current_user),
):
    """Fetch a job posting URL and return prefill data for the dream-job form."""
    from app.services import job_link_parser as _jlp
    result = await _jlp.parse_job_url(request.url)

    if result.get("error") == "url_rejected":
        raise HTTPException(status_code=400, detail="URL rejected: not a public job posting URL")
    if result.get("error") == "parse_failed":
        raise HTTPException(status_code=422, detail="Could not parse job posting from that URL")

    return {
        "company": result.get("company"),
        "role_title": result.get("role_title"),
        "location": result.get("location"),
        "jd_text": result.get("jd_text", ""),
        "source_url": result.get("source_url"),
        "source": result.get("source"),
        "error": result.get("error"),  # e.g. "linkedin_blocked" — UI can show warning
    }


@app.post("/dream-job")
async def create_dream_job(
    request: DreamJobCreateRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    """Create a dream-job document and queue the fit analysis in the background."""
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()

    # Verify resume_analysis_id belongs to this user
    resume_doc = fb.get_resume_analysis_by_id(request.resume_analysis_id)
    if not resume_doc:
        raise HTTPException(status_code=404, detail="Resume analysis not found")
    if resume_doc.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Resume analysis does not belong to you")
    if resume_doc.get("status") != "completed":
        raise HTTPException(
            status_code=400,
            detail="Resume analysis is not yet completed. Wait for it to finish first.",
        )

    dream_job_id = str(uuid.uuid4())
    if not fb.create_dream_job(
        uid=uid,
        dream_job_id=dream_job_id,
        company=request.company,
        role_title=request.role_title,
        jd_text=request.jd_text,
        source=request.source,
        source_url=request.source_url,
        resume_analysis_id=request.resume_analysis_id,
    ):
        raise HTTPException(status_code=500, detail="Failed to create dream job record")

    background_tasks.add_task(
        _run_dream_job_analysis_bg,
        uid,
        dream_job_id,
        request.jd_text,
        request.resume_analysis_id,
    )

    return {"dream_job_id": dream_job_id, "status": "pending"}


@app.get("/dream-job/{dream_job_id}/status")
async def get_dream_job_status(dream_job_id: str, current_user=Depends(get_current_user)):
    """Return lightweight status/progress for a dream-job analysis."""
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()
    doc = fb.get_dream_job_by_id(dream_job_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Dream job not found")
    if doc.get("uid") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")
    response = {
        "dream_job_id": dream_job_id,
        "status": doc.get("status"),
        "current_step": doc.get("current_step"),
    }
    if doc.get("error"):
        response["error"] = doc["error"]
    return response


@app.get("/dream-job/{dream_job_id}")
async def get_dream_job(dream_job_id: str, current_user=Depends(get_current_user)):
    """Return the full dream-job document (ownership verified)."""
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()
    doc = fb.get_dream_job_by_id(dream_job_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Dream job not found")
    if doc.get("uid") != uid:
        raise HTTPException(status_code=403, detail="Forbidden")
    return doc


@app.get("/dream-jobs")
async def list_dream_jobs(current_user=Depends(get_current_user)):
    """Return summary list of dream jobs for the authenticated user."""
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()
    return {"dream_jobs": fb.list_user_dream_jobs(uid)}


@app.delete("/dream-job/{dream_job_id}")
async def delete_dream_job(dream_job_id: str, current_user=Depends(get_current_user)):
    """Delete a dream-job document (ownership verified)."""
    uid = _get_user_id(current_user)
    fb = get_firebase_manager()
    if not fb.delete_dream_job(dream_job_id, uid):
        raise HTTPException(status_code=404, detail="Dream job not found or access denied")
    return {"message": "Dream job deleted", "dream_job_id": dream_job_id}


if __name__ == "__main__":
    uvicorn.run(
        "app.server:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info",
    )
