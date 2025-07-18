from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import tempfile
import uuid
from datetime import datetime

from app.services.interview_system import InterviewSystem
from app.models.interview_models import InterviewState
from app.models.interview_models import InterviewConfig as CoreInterviewConfig
from app.database.supabase import SupabaseManager
from app.core.config import settings

# Pydantic models for API
class InterviewConfigAPI(BaseModel):
    max_questions: int = 5
    chunk_size: int = 800
    chunk_overlap: int = 150
    rag_k_results: int = 3
    temperature: float = 0.3
    model_name: str = "gpt-4o-mini"
    index_path: str = "./vector_stores/interview_faiss_index"

class StartInterviewRequest(BaseModel):
    config: Optional[InterviewConfigAPI] = None

class AnswerRequest(BaseModel):
    session_id: str
    answer: str

class UserCredentials(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None

class InterviewResponse(BaseModel):
    session_id: str
    current_question: Optional[str]
    is_complete: bool
    current_question_idx: int
    total_questions: int
    score: Optional[float] = None

class AnalysisResponse(BaseModel):
    session_id: str
    score: float
    analysis: str
    is_complete: bool
    next_question: Optional[str] = None

# Initialize FastAPI app
app = FastAPI(
    title="AI Interview Assistant Backend API",
    description="Backend microservice for AI-driven mock interviews",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()

# Global variables (consider using dependency injection for production)
supabase_manager = SupabaseManager()
active_sessions: Dict[str, Dict[str, Any]] = {}

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user from JWT token"""
    # For now, we'll skip JWT validation and use a simple approach
    # In production, implement proper JWT validation
    try:
        user = supabase_manager.get_current_user()
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        return user
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")

def create_interview_system(config: InterviewConfigAPI = None) -> InterviewSystem:
    """Create and configure interview system"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured")
    
    # Convert API config to core config
    if config:
        core_config = CoreInterviewConfig(
            max_questions=config.max_questions,
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            rag_k_results=config.rag_k_results,
            temperature=config.temperature,
            model_name=config.model_name,
            index_path=config.index_path
        )
    else:
        core_config = CoreInterviewConfig()
    
    return InterviewSystem(api_key, core_config)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# Test endpoint for development (bypasses auth)
@app.post("/test/interview/start", response_model=InterviewResponse)
async def test_start_interview(
    resume: UploadFile = File(...),
    job_description: UploadFile = File(...),
    max_questions: int = Form(3),
    model_name: str = Form("gpt-4o-mini")
):
    """Start a new interview session (test endpoint without auth)"""
    try:
        # Save uploaded files temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf" if resume.filename.endswith('.pdf') else ".txt") as resume_file:
            resume_content = await resume.read()
            resume_file.write(resume_content)
            resume_path = resume_file.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as job_file:
            job_content = await job_description.read()
            job_file.write(job_content)
            job_path = job_file.name

        # Create interview system with simple config
        config = InterviewConfigAPI(
            max_questions=max_questions,
            model_name=model_name
        )
        interview_system = create_interview_system(config)
        
        # Start interview
        session_id = str(uuid.uuid4())
        interview_state = interview_system.start_interactive_interview(resume_path, job_path)
        
        # Store session
        active_sessions[session_id] = {
            "interview_system": interview_system,
            "interview_state": interview_state,
            "user_id": "test_user",
            "created_at": datetime.now().isoformat()
        }
        
        # Get first question
        question = interview_system.get_next_question(interview_state)
        
        return InterviewResponse(
            session_id=session_id,
            current_question=question,
            is_complete=False,
            current_question_idx=interview_state.get('current_question_idx', 0),
            total_questions=len(interview_state.get('interview_plan', []))
        )
        
    except Exception as e:
        # Clean up temporary files
        try:
            os.unlink(resume_path)
            os.unlink(job_path)
        except:
            pass
        raise HTTPException(status_code=500, detail=f"Interview start failed: {e}")

# Test endpoint for answer submission (bypasses auth)
@app.post("/test/interview/answer", response_model=AnalysisResponse)
async def test_submit_answer(request: AnswerRequest):
    """Submit an answer to the current question (test endpoint without auth)"""
    try:
        if request.session_id not in active_sessions:
            raise HTTPException(status_code=404, detail="Interview session not found")
        
        session = active_sessions[request.session_id]
        interview_system = session["interview_system"]
        interview_state = session["interview_state"]
        
        # Process the answer
        updated_state = interview_system.process_candidate_answer(interview_state, request.answer)
        session["interview_state"] = updated_state
        
        # Get latest score
        latest_note = updated_state.get('interview_notes', [])[-1] if updated_state.get('interview_notes') else None
        score = latest_note.get('score', 0) if latest_note else 0
        analysis = latest_note.get('analysis', '') if latest_note else ''
        
        # Check if interview is complete
        is_complete = updated_state.get('current_question_idx', 0) >= len(updated_state.get('interview_plan', []))
        
        # Get next question if not complete
        next_question = None
        if not is_complete:
            next_question = interview_system.get_next_question(updated_state)
        
        return AnalysisResponse(
            session_id=request.session_id,
            score=score,
            analysis=analysis,
            is_complete=is_complete,
            next_question=next_question
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process answer: {e}")

# Authentication endpoints
@app.post("/auth/signup")
async def signup(credentials: UserCredentials):
    """Sign up a new user"""
    try:
        result = supabase_manager.sign_up(
            credentials.email, 
            credentials.password, 
            credentials.full_name or ""
        )
        if result.get("success"):
            return {"message": "User created successfully", "user": result.get("user")}
        else:
            raise HTTPException(status_code=400, detail=result.get("error", "Signup failed"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/signin")
async def signin(credentials: UserCredentials):
    """Sign in an existing user"""
    try:
        result = supabase_manager.sign_in(credentials.email, credentials.password)
        if result.get("success"):
            return {"message": "Signed in successfully", "user": result.get("user")}
        else:
            raise HTTPException(status_code=401, detail=result.get("error", "Login failed"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/signout")
async def signout(current_user=Depends(get_current_user)):
    """Sign out current user"""
    try:
        result = supabase_manager.sign_out()
        return {"message": "Signed out successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Interview endpoints
@app.post("/interview/start", response_model=InterviewResponse)
async def start_interview(
    request: StartInterviewRequest,
    resume: UploadFile = File(...),
    job_description: UploadFile = File(...),
    current_user=Depends(get_current_user)
):
    """Start a new interview session"""
    try:
        # Save uploaded files temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf" if resume.filename.endswith('.pdf') else ".txt") as resume_file:
            resume_content = await resume.read()
            resume_file.write(resume_content)
            resume_path = resume_file.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as job_file:
            job_content = await job_description.read()
            job_file.write(job_content)
            job_path = job_file.name

        # Create interview system
        config = request.config or InterviewConfigAPI()
        interview_system = create_interview_system(config)
        
        # Start interview
        session_id = str(uuid.uuid4())
        interview_state = interview_system.start_interactive_interview(resume_path, job_path)
        
        # Store session
        active_sessions[session_id] = {
            "interview_system": interview_system,
            "interview_state": interview_state,
            "user_id": current_user.id,
            "created_at": datetime.now().isoformat()
        }
        
        # Get first question
        question = interview_system.get_next_question(interview_state)
        
        # Save to database
        session_data = {
            "user_id": current_user.id,
            "status": "active",
            "total_questions": len(interview_state.get('interview_plan', [])),
            "current_question_idx": interview_state.get('current_question_idx', 0),
            "interview_state": interview_state
        }
        supabase_manager.create_interview_session(current_user.id, session_data)
        
        # Clean up temp files
        os.unlink(resume_path)
        os.unlink(job_path)
        
        return InterviewResponse(
            session_id=session_id,
            current_question=question,
            is_complete=False,
            current_question_idx=interview_state.get('current_question_idx', 0),
            total_questions=len(interview_state.get('interview_plan', []))
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start interview: {e}")

@app.post("/interview/answer", response_model=AnalysisResponse)
async def submit_answer(
    request: AnswerRequest,
    current_user=Depends(get_current_user)
):
    """Submit an answer to the current question"""
    try:
        if request.session_id not in active_sessions:
            raise HTTPException(status_code=404, detail="Interview session not found")
        
        session = active_sessions[request.session_id]
        interview_system = session["interview_system"]
        interview_state = session["interview_state"]
        
        # Process the answer
        updated_state = interview_system.process_candidate_answer(interview_state, request.answer)
        session["interview_state"] = updated_state
        
        # Get latest score
        latest_note = updated_state.get('interview_notes', [])[-1] if updated_state.get('interview_notes') else None
        score = latest_note.get('score', 0) if latest_note else 0
        analysis = latest_note.get('analysis', '') if latest_note else ''
        
        # Check if interview is complete
        is_complete = updated_state.get('current_question_idx', 0) >= len(updated_state.get('interview_plan', []))
        
        # Get next question if not complete
        next_question = None
        if not is_complete:
            next_question = interview_system.get_next_question(updated_state)
        
        # Update database
        session_data = {
            "current_question_idx": updated_state.get('current_question_idx', 0),
            "interview_state": updated_state,
            "status": "complete" if is_complete else "active"
        }
        # Note: You'll need to implement update method in SupabaseManager
        
        return AnalysisResponse(
            session_id=request.session_id,
            score=score,
            analysis=analysis,
            is_complete=is_complete,
            next_question=next_question
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process answer: {e}")

@app.get("/interview/{session_id}/report")
async def get_interview_report(
    session_id: str,
    current_user=Depends(get_current_user)
):
    """Generate and retrieve interview report"""
    try:
        if session_id not in active_sessions:
            raise HTTPException(status_code=404, detail="Interview session not found")
        
        session = active_sessions[session_id]
        interview_system = session["interview_system"]
        interview_state = session["interview_state"]
        
        # Generate final report
        final_state = interview_system.generate_final_report(interview_state)
        
        # Save report to database
        report_data = {
            "user_id": current_user.id,
            "session_id": session_id,
            "title": f"Interview Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "content": final_state.get('interview_report', ''),
            "overall_score": session.get("overall_score", 0)
        }
        
        report_id = supabase_manager.save_interview_report(
            current_user.id, 
            session_id, 
            report_data
        )
        
        return {
            "report_id": report_id,
            "content": final_state.get('interview_report', ''),
            "session_id": session_id
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {e}")

@app.get("/interview/sessions")
async def get_user_sessions(
    current_user=Depends(get_current_user),
    limit: int = 50
):
    """Get user's interview sessions"""
    try:
        sessions = supabase_manager.get_user_interview_sessions(current_user.id, limit)
        return {"sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve sessions: {e}")

@app.get("/reports")
async def get_user_reports(
    current_user=Depends(get_current_user),
    limit: int = 50
):
    """Get user's interview reports"""
    try:
        reports = supabase_manager.get_user_reports(current_user.id, limit)
        return {"reports": reports}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve reports: {e}")

@app.get("/dashboard/stats")
async def get_dashboard_stats(current_user=Depends(get_current_user)):
    """Get user dashboard statistics"""
    try:
        stats = supabase_manager.get_user_dashboard_stats(current_user.id)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve stats: {e}")

# Admin endpoints (optional)
@app.get("/admin/health")
async def admin_health():
    """Admin health check with database connection test"""
    try:
        db_status = supabase_manager.test_connection()
        return {
            "api_status": "healthy",
            "database_status": db_status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "api_status": "healthy",
            "database_status": {"success": False, "error": str(e)},
            "timestamp": datetime.now().isoformat()
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.server:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )
