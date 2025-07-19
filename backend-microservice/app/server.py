from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Form, Request
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
    model_name: str = "gpt-4.1-nano-2025-04-14"
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

# Add request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"[MIDDLEWARE] {request.method} {request.url}")
    
    # Only log authorization header presence/absence for non-OPTIONS requests
    if request.method != "OPTIONS":
        auth_header = request.headers.get("authorization")
        if auth_header:
            print(f"[MIDDLEWARE] Authorization header present")
        else:
            print(f"[MIDDLEWARE] No authorization header found")
    
    response = await call_next(request)
    print(f"[MIDDLEWARE] Response status: {response.status_code}")
    return response

# Initialize services
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("OPENAI_API_KEY environment variable is required")

interview_system = InterviewSystem(openai_api_key)
supabase_manager = SupabaseManager()
security = HTTPBearer(auto_error=False)

print("[STARTUP] Server initialized with security and middleware")

# Global variables (consider using dependency injection for production)
active_sessions: Dict[str, Dict[str, Any]] = {}

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user from JWT token"""
    # For development: Accept dummy token and return mock user
    if settings.ENVIRONMENT == "development" and credentials.credentials == "dummy-token":
        # Return a mock user object for development
        return type('User', (), {
            'id': '176d665a-4932-4934-a03d-5519301517f5',
            'email': 'iasolaiman@ualr.edu',
            'name': 'iasolaiman'
        })()

    # Try to validate JWT using Supabase JWKS
    token = credentials.credentials
    
    try:
        # First try simple JWT decode without verification for debugging
        import jwt
        unverified_payload = jwt.decode(token, options={"verify_signature": False})
        
        # For now, if we can decode the JWT (even unverified), accept it
        # This is for development - in production you'd want full verification
        if unverified_payload.get('aud') == 'authenticated':
            return type('User', (), unverified_payload)()
        
        # Try full verification
        from jwt import PyJWKClient
        SUPABASE_PROJECT_ID = os.getenv("SUPABASE_PROJECT_ID") or "ikaebwiruhrnsgjinojh"
        JWKS_URL = f"https://{SUPABASE_PROJECT_ID}.supabase.co/auth/v1/keys"
        
        jwks_client = PyJWKClient(JWKS_URL)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        decoded = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience="authenticated",
            options={"verify_aud": True}
        )
        return type('User', (), decoded)()
        
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid authentication token: {str(e)}")

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
    model_name: str = Form("gpt-4.1-nano-2025-04-14")
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
            error_message = result.get("error", "Signup failed")
            # Return appropriate status codes based on error type
            if "Password should contain" in error_message:
                raise HTTPException(status_code=422, detail=error_message)
            elif "already registered" in error_message.lower():
                raise HTTPException(status_code=409, detail=error_message)
            else:
                raise HTTPException(status_code=400, detail=error_message)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/auth/signin")
async def signin(credentials: UserCredentials):
    """Sign in an existing user"""
    try:
        result = supabase_manager.sign_in(credentials.email, credentials.password)
        if result.get("success"):
            return {
                "message": "Signed in successfully", 
                "user": result.get("user"),
                "session": result.get("session")
            }
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

@app.get("/auth/me")
async def get_current_user_info(current_user=Depends(get_current_user)):
    """Get current user information"""
    try:
        # Return user info from the JWT token
        return {
            "user": {
                "id": getattr(current_user, 'sub', getattr(current_user, 'id', None)),
                "email": getattr(current_user, 'email', None),
                "name": getattr(current_user, 'name', getattr(current_user, 'user_metadata', {}).get('full_name', None))
            }
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

# Interview endpoints
@app.post("/interview/start", response_model=InterviewResponse)
async def start_interview(
    resume: UploadFile = File(...),
    job_description: UploadFile = File(...),
    max_questions: int = Form(3),
    model_name: str = Form("gpt-4.1-nano-2025-04-14"),
    temperature: float = Form(0.3),
    current_user=Depends(get_current_user)
):
    """Start a new interview session"""
    user_id = getattr(current_user, 'sub', getattr(current_user, 'id', None))
    print(f"Starting interview for user: {user_id}")
    print(f"Config: max_questions={max_questions}, model={model_name}, temp={temperature}")
    
    resume_path = None
    job_path = None
    
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
        config = InterviewConfigAPI(
            max_questions=max_questions,
            model_name=model_name,
            temperature=temperature
        )
        interview_system = create_interview_system(config)
        
        # Start interview
        session_id = str(uuid.uuid4())
        interview_state = interview_system.start_interactive_interview(resume_path, job_path)
        
        # Get user ID
        user_id = getattr(current_user, 'sub', getattr(current_user, 'id', None))
        
        # Prepare session data for database
        session_data = {
            "user_id": user_id,
            "status": "in_progress",
            "total_questions": len(interview_state.get('interview_plan', [])),
            "current_question_idx": interview_state.get('current_question_idx', 0),
            "interview_plan": interview_state.get('interview_plan', []),
            "interview_notes": interview_state.get('interview_notes', []),
            "conversation_history": interview_state.get('conversation_history', []),
            "resume_content": resume.filename,
            "job_description": job_description.filename,
            "title": f"Interview Session {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        }
        
        # Save session to database FIRST with proper session_id
        print(f"🔄 Creating session in DB with ID: {session_id}")
        try:
            # Use a direct insert with the specific session_id
            db_response = supabase_manager.client.table('interview_sessions').insert({
                "id": session_id,
                **session_data,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }).execute()
            
            if db_response.data:
                print(f"✅ Session created successfully in DB with ID: {session_id}")
                
                # Store session in memory only after DB success
                active_sessions[session_id] = {
                    "interview_system": interview_system,
                    "interview_state": interview_state,
                    "user_id": user_id,
                    "created_at": datetime.now().isoformat()
                }
            else:
                print(f"❌ Session creation failed - no data returned from DB")
                raise HTTPException(status_code=500, detail="Failed to create session in database")
                
        except Exception as db_error:
            print(f"❌ Exception during session creation: {db_error}")
            import traceback
            print(f"❌ Creation traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Failed to create session: {str(db_error)}")
        
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
        import traceback
        print(f"❌ Error in start_interview: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to start interview: {str(e)}")
        
    finally:
        # Clean up temp files
        try:
            if resume_path:
                os.unlink(resume_path)
            if job_path:
                os.unlink(job_path)
        except Exception as cleanup_error:
            print(f"⚠️ Failed to clean up temporary files: {cleanup_error}")

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
        user_id = getattr(current_user, 'sub', getattr(current_user, 'id', None))
        
        print(f"📝 Processing answer for session {request.session_id}")
        print(f"📋 Current question index: {interview_state.get('current_question_idx', 0)}")
        print(f"📋 Total questions in plan: {len(interview_state.get('interview_plan', []))}")
        
        # Process the answer
        updated_state = interview_system.process_candidate_answer(interview_state, request.answer)
        session["interview_state"] = updated_state
        
        # Get latest score
        latest_note = updated_state.get('interview_notes', [])[-1] if updated_state.get('interview_notes') else None
        score = latest_note.get('score', 0) if latest_note else 0
        analysis = latest_note.get('analysis', '') if latest_note else ''
        
        # Check if interview is complete - use the configured max_questions, not just plan length
        current_idx = updated_state.get('current_question_idx', 0)
        total_questions = len(updated_state.get('interview_plan', []))
        is_complete = current_idx >= total_questions
        
        print(f"📊 After processing: current_idx={current_idx}, total_questions={total_questions}, is_complete={is_complete}")
        
        # Update progress in the database
        try:
            progress = round((current_idx / total_questions) * 100, 2)
            session_update_data = {
                "current_question_idx": current_idx,
                "progress": progress,
                "last_activity": datetime.now()
            }
            print(f"🔄 Updating session progress in DB: {session_update_data}")
            supabase_manager.update_interview_session(request.session_id, session_update_data, user_id)
        except Exception as e:
            print(f"⚠️ Failed to update session progress: {e}")
        
        # Get next question if not complete
        next_question = None
        if not is_complete:
            next_question = interview_system.get_next_question(updated_state)
            print(f"❓ Next question: {next_question[:100] if next_question else 'None'}...")
        else:
            print("🎯 Interview complete! Generating final report...")
            
            # Generate final report when interview is complete
            try:
                final_state = interview_system.generate_final_report(updated_state)
                session["interview_state"] = final_state
                
                # Calculate overall score from all notes
                all_scores = [note.get('score', 0) for note in final_state.get('interview_notes', []) if note.get('score') is not None]
                overall_score = sum(all_scores) / len(all_scores) if all_scores else 0
                session["overall_score"] = overall_score
                
                # Save final session to database
                final_session_data = {
                    "status": "completed",
                    "current_question_idx": current_idx,
                    "total_questions": total_questions,
                    "average_score": overall_score,
                    "final_report": final_state.get('interview_report', ''),
                    "interview_notes": final_state.get('interview_notes', []),
                    "conversation_history": final_state.get('conversation_history', [])
                }
                
                print(f"💾 Saving completed session to DB...")
                session_updated = supabase_manager.update_interview_session(request.session_id, final_session_data, user_id)
                if session_updated:
                    print(f"✅ Session updated successfully in DB")
                else:
                    print(f"⚠️ Session update failed - session might not exist in DB")
                
                print(f"✅ Interview completed with overall score: {overall_score}")
                
                # Save report to database
                report_data = {
                    "user_id": user_id,
                    "session_id": request.session_id,
                    "title": f"Interview Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    "report_content": final_state.get('interview_report', ''),
                    "summary": {"overall_score": overall_score, "total_questions": total_questions},
                    "scores": {"individual_scores": all_scores, "average": overall_score}
                }
                
                print(f"🔄 Attempting to save report to DB for completed interview...")
                report_id = supabase_manager.save_interview_report(
                    user_id, 
                    request.session_id, 
                    report_data
                )
                
                if report_id:
                    print(f"✅ Report saved successfully to DB with ID: {report_id}")
                else:
                    print(f"❌ Report save failed - check supabase logs above")
                    
            except Exception as report_error:
                print(f"⚠️ Error generating final report: {report_error}")
                # Continue with the response even if report generation fails
        
        return AnalysisResponse(
            session_id=request.session_id,
            score=score,
            analysis=analysis,
            is_complete=is_complete,
            next_question=next_question
        )
        
    except Exception as e:
        print(f"❌ Error in submit_answer: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
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
        
        # Get user ID
        user_id = getattr(current_user, 'sub', getattr(current_user, 'id', None))
        # Save report to database
        report_data = {
            "user_id": user_id,
            "session_id": session_id,
            "title": f"Interview Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "report_content": final_state.get('interview_report', ''),
            "overall_score": session.get("overall_score", 0)
        }
        
        print(f"🔄 Attempting to save report to DB for user: {user_id}, session: {session_id}")
        print(f"📋 Report data - title: {report_data['title']}, content length: {len(report_data['report_content'])}")
        
        report_id = supabase_manager.save_interview_report(
            user_id, 
            session_id, 
            report_data
        )
        
        if report_id:
            print(f"✅ Report saved successfully to DB with ID: {report_id}")
        else:
            print(f"❌ Report save returned None - check supabase logs above")
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
        user_id = getattr(current_user, 'sub', getattr(current_user, 'id', None))
        print(f"🔍 Fetching sessions for user: {user_id}")
        
        sessions = supabase_manager.get_user_interview_sessions(user_id, limit)
        print(f"🔍 Raw sessions from DB: {type(sessions)} - {sessions}")
        
        # Ensure we always return an array, even if empty or None
        if not isinstance(sessions, list):
            print(f"⚠️ Sessions is not a list, type: {type(sessions)}, converting to empty array")
            sessions = []
        
        response = {"sessions": sessions}
        print(f"🔍 Final response: {response}")
        return response
    except Exception as e:
        print(f"❌ Error fetching sessions: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        # Return empty array on error to prevent frontend crashes
        return {"sessions": []}

@app.get("/reports")
async def get_user_reports(
    current_user=Depends(get_current_user),
    limit: int = 50
):
    """Get user's interview reports"""
    try:
        user_id = getattr(current_user, 'sub', getattr(current_user, 'id', None))
        reports = supabase_manager.get_user_reports(user_id, limit)
        
        # Ensure we always return an array, even if empty or None
        if not isinstance(reports, list):
            reports = []
            
        return {"reports": reports}
    except Exception as e:
        print(f"❌ Error fetching reports: {e}")
        # Return empty array on error to prevent frontend crashes
        return {"reports": []}

@app.get("/dashboard/stats")
async def get_dashboard_stats(current_user=Depends(get_current_user)):
    """Get user dashboard statistics"""
    try:
        user_id = getattr(current_user, 'sub', getattr(current_user, 'id', None))
        stats = supabase_manager.get_user_dashboard_stats(user_id)
        
        # Ensure we always return a valid stats object
        if not isinstance(stats, dict):
            stats = {
                "total_interviews": 0,
                "completed_interviews": 0,
                "average_score": 0
            }
            
        return stats
    except Exception as e:
        print(f"❌ Error fetching dashboard stats: {e}")
        # Return default stats on error
        return {
            "total_interviews": 0,
            "completed_interviews": 0,
            "average_score": 0,
            "total_reports": 0
        }

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
