# app.py

import streamlit as st
import os
import tempfile
from typing import Optional, Dict, Any
from datetime import datetime
from src.core.interview_system import InterviewSystem
from src.core.models import InterviewConfig # Removed InterviewState if not directly used
from src.database.supabase import SupabaseManager
from dotenv import load_dotenv
import markdown
import json

load_dotenv()

# Page configuration (remains the same)
st.set_page_config(
    page_title="AI Interview Assistant",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS (remains the same)
st.markdown("""
<style>
    .main-header { background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); padding: 2rem; border-radius: 10px; margin-bottom: 2rem; color: white; text-align: center; }
    [data-testid="stForm"]{ background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); padding: 2rem; border-radius: 10px; border: 1px solid #e9ecef; margin: 2rem auto; max-width: 700px; }
    .interview-card { background: #f8f9fa; padding: 1.5rem; border-radius: 8px; border-left: 4px solid #667eea; margin: 1rem 0; color: black; }
    .question-box { background: #e3f2fd; padding: 1rem; border-radius: 8px; border-left: 4px solid #2196f3; margin: 1rem 0; color: black; }
    .response-box { background: #f3e5f5; padding: 1rem; border-radius: 8px; border-left: 4px solid #9c27b0; margin: 1rem 0; color: black; }
    .score-display { background: #e8f5e8; padding: 0.5rem 1rem; border-radius: 20px; display: inline-block; font-weight: bold; color: #2e7d32; }
    .user-info { background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); padding: 1rem; border-radius: 8px; margin-bottom: 1rem; }
    .stButton > button { width: 100%; background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 8px; padding: 0.5rem 1rem; font-weight: bold; }
    .dashboard-metric { background: white; padding: 1rem; border-radius: 8px; border: 1px solid #e9ecef; margin: 0.5rem 0; text-align: center; color: green; }
    .report-viewer { background: #ffffff; padding: 1.5rem; border-radius: 8px; border: 1px solid #dee2e6; margin-top: 1rem; color: black;}
    .report-viewer h4 { color: #4a4a4a; margin-top: 1rem; margin-bottom: 0.5rem; }
    .report-viewer pre { background-color: #f1f1f1; padding: 10px; border-radius: 4px; white-space: pre-wrap; word-wrap: break-word; }
    .completion-report-display { margin-top: 1.5rem; padding: 1.5rem; background-color: #f9f9f9; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# --- Helper function to display a report (used on completion and dashboard) ---
def display_report_details_component(report_details: Dict[str, Any]):
    """Helper function to render report details within a styled div."""
    if not report_details:
        st.error("Report data is not available.")
        return 
    html_parts = ['<div class="report-viewer">']

    html_parts.append(f"<h3>📄 Report: {report_details.get('title', 'Untitled Report')}</h3>")
    html_parts.append(f"<p><small>Generated on: {str(report_details.get('created_at', 'N/A'))[:16]}</small></p>")
    if report_details.get('session_id'):
        html_parts.append(f"<p><small>Associated Session ID: {report_details.get('session_id')}</small></p>")

    if report_details.get('summary'):
        html_parts.append("<h4>Summary:</h4>")
        summary_data = report_details['summary']
        if isinstance(summary_data, (dict, list)):
            summary_str = json.dumps(summary_data, indent=2)
            html_parts.append(f"<pre>{summary_str}</pre>")
        else:
            import html
            html_parts.append(f"<pre>{html.escape(str(summary_data))}</pre>")
    
    if report_details.get('scores'):
        html_parts.append("<h4>Scores:</h4>")
        scores_data = report_details['scores']
        if isinstance(scores_data, (dict, list)):
            scores_str = json.dumps(scores_data, indent=2)
            html_parts.append(f"<pre>{scores_str}</pre>")
        else:
            import html
            html_parts.append(f"<pre>{html.escape(str(scores_data))}</pre>")

    if report_details.get('recommendations'):
        html_parts.append("<h4>Recommendations:</h4>")
        import html
        html_parts.append(f"<p>{html.escape(str(report_details['recommendations']))}</p>")
    
    if report_details.get('report_content'):
        html_parts.append("<h4>Full Report Content:</h4>")
        try:
            html_report_content = markdown.markdown(str(report_details['report_content']))
            html_parts.append(html_report_content)
        except Exception as e:
            import html #
            st.warning(f"Note: Could not render full report content as rich Markdown, displaying as plain text. Error: {e}") #
            html_parts.append(f"<pre>{html.escape(str(report_details['report_content']))}</pre>") #

    html_parts.append('</div>') 
    
    final_html = "".join(html_parts)
    st.markdown(final_html, unsafe_allow_html=True)

def initialize_session_state():
    if 'supabase_manager' not in st.session_state:
        try:
            st.session_state.supabase_manager = SupabaseManager()
        except Exception as e:
            st.error(f"❌ Critical Error: Could not initialize Supabase Manager. {e}")
            st.stop() 
    
    if 'user' not in st.session_state: st.session_state.user = None
    if 'interview_system' not in st.session_state: st.session_state.interview_system = None
    if 'interview_state' not in st.session_state: st.session_state.interview_state = {} 
    if 'current_session_id' not in st.session_state: st.session_state.current_session_id = None
    if 'interview_started' not in st.session_state: st.session_state.interview_started = False
    if 'current_question' not in st.session_state: st.session_state.current_question = ""
    if 'current_question_idx' not in st.session_state: st.session_state.current_question_idx = 0 # Add this line
    if 'conversation_history' not in st.session_state: st.session_state.conversation_history = []
    if 'interview_complete' not in st.session_state: st.session_state.interview_complete = False
    if 'files_uploaded' not in st.session_state: st.session_state.files_uploaded = False
    if 'auth_mode' not in st.session_state: st.session_state.auth_mode = 'signin'
    if 'selected_report_id_to_display' not in st.session_state: st.session_state.selected_report_id_to_display = None
    if 'last_generated_report_id' not in st.session_state: st.session_state.last_generated_report_id = None

def check_authentication(): #
    if not st.session_state.user:
        try:
            user_response = st.session_state.supabase_manager.get_current_user()
            if user_response and user_response.user:
                st.session_state.user = user_response.user
                return True
        except:
            pass # Fail silently
    return st.session_state.user is not None

def show_auth_page():
    st.markdown("""
        <div class="main-header">
            <h1>🎯 AI Interview Assistant</h1>
            <p>Sign in to access your personalized interview experience</p>
        </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔑 Sign In", key="switch_signin_btn", use_container_width=True):
            st.session_state.auth_mode = 'signin'
            st.rerun()
    with col2:
        if st.button("📝 Sign Up", key="switch_signup_btn", use_container_width=True):
            st.session_state.auth_mode = 'signup'
            st.rerun()
    
    if st.session_state.auth_mode == 'signup':
        st.subheader("Create Account")
        with st.form("signup_form"):
            full_name = st.text_input("Full Name", key="signup_fullname")
            email = st.text_input("Email Address", key="signup_email")
            password = st.text_input("Password", type="password", key="signup_password")
            confirm_password = st.text_input("Confirm Password", type="password", key="signup_confirmpass")
            signup_button = st.form_submit_button("Create Account")
            
            if signup_button:
                if not all([full_name, email, password, confirm_password]):
                    st.error("Please fill in all fields")
                elif password != confirm_password:
                    st.error("Passwords do not match")
                elif len(password) < 6:
                    st.error("Password must be at least 6 characters long")
                else:
                    with st.spinner("Creating account..."):
                        result = st.session_state.supabase_manager.sign_up(email, password, full_name)
                        if result.get('success'):
                            st.success("✅ Account created! Please check your email to verify.")
                            st.session_state.auth_mode = 'signin'
                            st.rerun()
                        else:
                            st.error(f"❌ Error: {result.get('error', 'Unknown signup error')}")
    
    else:  # signin mode
        st.subheader("Sign In")
        with st.form("signin_form"):
            email = st.text_input("Email Address", key="signin_email")
            password = st.text_input("Password", type="password", key="signin_password")
            signin_button = st.form_submit_button("Sign In")
            
            if signin_button:
                if not email or not password:
                    st.error("Please enter email and password")
                else:
                    with st.spinner("Signing in..."):
                        result = st.session_state.supabase_manager.sign_in(email, password)
                        if result.get('success'):
                            st.session_state.user = result.get('user')
                            st.success("✅ Signed in successfully!")
                            st.rerun()
                        else:
                            st.error(f"❌ Error: {result.get('error', 'Unknown signin error')}")


def show_user_dashboard(): #
    if not st.session_state.user:
        st.warning("User not found. Please sign in again.")
        return

    user_id = st.session_state.user.id
    stats = st.session_state.supabase_manager.get_user_dashboard_stats(user_id)

    st.markdown("### 📊 Your Interview Dashboard")
    col1, col2, col3, col4 = st.columns(4) #
    with col1: st.markdown(f"""<div class="dashboard-metric"><h3>{stats.get('total_sessions', 0)}</h3><p>Total Sessions</p></div>""", unsafe_allow_html=True) #
    with col2: st.markdown(f"""<div class="dashboard-metric"><h3>{stats.get('completed_sessions', 0)}</h3><p>Completed</p></div>""", unsafe_allow_html=True) #
    with col3: st.markdown(f"""<div class="dashboard-metric"><h3>{stats.get('overall_avg_score', 0)}</h3><p>Average Score</p></div>""", unsafe_allow_html=True) #
    with col4: st.markdown(f"""<div class="dashboard-metric"><h3>{stats.get('total_questions_answered', 0)}</h3><p>Questions Answered</p></div>""", unsafe_allow_html=True) #

    st.markdown("---")
    st.markdown("### 📝 Recent Interview Sessions")
    if stats.get('sessions'): #
        for session in stats['sessions']: #
            if isinstance(session, dict):
                session_id_disp = str(session.get('id', 'N/A'))[:8]
                session_status_disp = str(session.get('status', 'N/A')).title() #
                session_title_disp = session.get('title', 'Untitled Session')
                session_created_disp = str(session.get('created_at', 'N/A'))[:10]
                
                expander_title = f"{session_title_disp} (ID: {session_id_disp}...) - {session_status_disp} on {session_created_disp}"
                with st.expander(expander_title):
                    # Session details display logic
                    scol1, scol2 = st.columns(2)
                    with scol1:
                        st.write(f"**Status:** {session_status_disp}")
                        if session.get('total_questions') is not None:
                            st.write(f"**Questions:** {session.get('total_questions')}")
                    with scol2:
                        if session.get('average_score') is not None:
                            st.write(f"**Avg. Score:** {session.get('average_score')}/10")
                        st.write(f"**Created:** {session_created_disp}")
                    
                    # Action buttons for sessions
                    # Consider adding view/delete for sessions if needed, similar to reports
            else:
                st.warning(f"Skipping malformed session entry: {session}") #
    else:
        st.info("No interview sessions found yet.") #

    st.markdown("---")
    st.markdown("### 📜 Your Interview Reports") #
    user_reports = st.session_state.supabase_manager.get_user_reports(user_id) #

    if not user_reports:
        st.info("You have no saved interview reports yet.") #
    else:
        report_options = {
            f"{idx + 1}. {report.get('title', 'Untitled Report')} ({str(report.get('created_at', ''))[:10]})": report.get('id') 
            for idx, report in enumerate(user_reports)
        }
        
        selected_report_label = st.selectbox(
            "Select a report to view:", 
            options=list(report_options.keys()), 
            index=None,
            placeholder="Choose a report...",
            key="dashboard_report_selectbox"
        )

        if selected_report_label:
            st.session_state.selected_report_id_to_display = report_options[selected_report_label] #

        if st.session_state.selected_report_id_to_display:
            report_id = st.session_state.selected_report_id_to_display
            # Display report details using the helper function
            with st.spinner("Loading report details..."): #
                report_details_data = st.session_state.supabase_manager.get_report(report_id) #
            
            if report_details_data:
                display_report_details_component(report_details_data)
                
                st.markdown("---")
                if st.button("🗑️ Delete This Report from Dashboard", key=f"delete_dashboard_report_{report_id}", type="primary"): #
                    with st.spinner("Deleting report..."):
                        if st.session_state.supabase_manager.delete_report(report_id):
                            st.success("Report deleted successfully!")
                            st.session_state.selected_report_id_to_display = None 
                            st.rerun()
                        else:
                            st.error("Failed to delete report.")
            else:
                st.error(f"Could not load details for report ID: {report_id}")
                st.session_state.selected_report_id_to_display = None

def setup_interview_system() -> Optional[InterviewSystem]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.error("❌ Please set OPENAI_API_KEY environment variable.")
        return None
    
    try:
        user_settings: Dict[str, Any] = {} 
        if st.session_state.user and hasattr(st.session_state.user, 'id'):
             user_settings = st.session_state.supabase_manager.get_user_settings(st.session_state.user.id) or {} 
        
        config = InterviewConfig(
            max_questions=st.session_state.max_questions_slider,
            chunk_size=user_settings.get('chunk_size', 500),
            chunk_overlap=user_settings.get('chunk_overlap', 50),
            rag_k_results=user_settings.get('rag_k_results', 3),
            temperature=user_settings.get('temperature', 0.3),
            model_name=st.session_state.model_choice_selectbox,
            index_path="./vector_stores/interview_faiss_index" 
        )
        return InterviewSystem(api_key, config)
    except Exception as e:
        st.error(f"❌ Error initializing interview system: {e}")
        return None
    
def save_uploaded_file(uploaded_file, file_type: str) -> str:
    temp_dir = tempfile.mkdtemp()
    file_name = getattr(uploaded_file, 'name', 'unknown_file')
    file_path = os.path.join(temp_dir, f"{file_type}_{file_name}")
    with open(file_path, "wb") as f: f.write(uploaded_file.getbuffer())
    return file_path

def save_session_to_supabase():
    if not st.session_state.get('interview_state') or not st.session_state.user: return
    user_id = st.session_state.user.id
    state = st.session_state.interview_state
    
    # Safely get current_question_idx for the default title
    current_q_idx_for_title = st.session_state.get('current_question_idx', 0)

    session_data = { #
        'status': 'completed' if st.session_state.get('interview_complete') else 'in_progress',
        'title': state.get('title', f"Interview Session @ Question {current_q_idx_for_title}"),
        'interview_plan': state.get('interview_plan', []),
        'current_question_idx': state.get('current_question_idx', 0),
        'interview_notes': state.get('interview_notes', []),
        'conversation_history': state.get('conversation_history', st.session_state.get('conversation_history', [])),
        'resume_content': state.get('resume_content', ''),
        'job_description': state.get('job_description', ''),
        'total_questions': len(state.get('interview_plan', [])),
        'average_score': None, 
        'final_report': state.get('interview_report', '')
    }

    notes = session_data['interview_notes'] 
    if isinstance(notes, list) and notes:
        scores = [note.get('score', 0) for note in notes if isinstance(note, dict)]
        if scores: session_data['average_score'] = round(sum(scores) / len(scores), 1)
    
    try:
        if st.session_state.current_session_id:
            success = st.session_state.supabase_manager.update_interview_session(st.session_state.current_session_id, session_data) #
            if success: st.toast("✅ Session updated.", icon="👍")
        else:
            session_id = st.session_state.supabase_manager.create_interview_session(user_id, session_data) #
            if session_id:
                st.session_state.current_session_id = session_id
                st.toast("✅ Session saved.", icon="💾")
    except Exception as e:
        st.error(f"❌ Error saving session state: {e}")

def display_interview_progress(): #
    if st.session_state.interview_state and isinstance(st.session_state.interview_state, dict): #
        current_idx = st.session_state.interview_state.get('current_question_idx', 0) #
        interview_plan = st.session_state.interview_state.get('interview_plan', []) #
        total_questions = len(interview_plan) if isinstance(interview_plan, list) else 0 #
        
        if total_questions > 0: #
            progress = (current_idx / total_questions) if total_questions > 0 else 0 #
            st.progress(progress) #
            st.write(f"Question {current_idx} of {total_questions}") #
            
            interview_notes = st.session_state.interview_state.get('interview_notes', []) #
            if isinstance(interview_notes, list) and interview_notes: #
                scores = [note.get('score', 0) for note in interview_notes if isinstance(note, dict)] #
                if scores: #
                    avg_score = sum(scores) / len(scores) #
                    st.markdown(f'<div class="score-display">Average Score: {avg_score:.1f}/10</div>', unsafe_allow_html=True) #

def display_conversation_history(): #
    if st.session_state.conversation_history and isinstance(st.session_state.conversation_history, list): #
        st.subheader("📝 Interview Conversation") #
        
        for i, exchange in enumerate(st.session_state.conversation_history): #
            if isinstance(exchange, dict): 
                with st.container(): #
                    st.markdown(f"""<div class="question-box"><strong>🤖 Interviewer:</strong><br>{exchange.get('question', 'N/A')}</div>""", unsafe_allow_html=True) #
                    st.markdown(f"""<div class="response-box"><strong>👤 You:</strong><br>{exchange.get('response', 'N/A')}</div>""", unsafe_allow_html=True) #
                    if 'score' in exchange: #
                        st.markdown(f'<div class="score-display">Score: {exchange.get("score", 0)}/10</div>', unsafe_allow_html=True) #
                    st.markdown("---") #
            else:
                st.warning(f"Skipping malformed conversation entry: {exchange}") #


def main():
    initialize_session_state()
    if not check_authentication():
        show_auth_page()
        return

    user_email = getattr(st.session_state.user, 'email', "N/A") #
    st.markdown(f"""<div class="main-header"><h1>🎯 AI Interview Assistant</h1><p>Welcome back, {user_email}!</p></div>""", unsafe_allow_html=True) #

    with st.sidebar: #
        st.markdown(f"""<div class="user-info"><strong>👾 {user_email}</strong></div>""", unsafe_allow_html=True) #
        if st.button("🚪 Sign Out", use_container_width=True, key="signout_button"):  #
            if hasattr(st.session_state, 'supabase_manager') and st.session_state.supabase_manager: #
                st.session_state.supabase_manager.sign_out() #
            keys_to_clear = list(st.session_state.keys()) #
            for key in keys_to_clear: #
                if key not in ['supabase_manager', 'auth_mode']: 
                    del st.session_state[key] #
            st.session_state.auth_mode = 'signin' 
            st.rerun() #

        st.markdown("---") #
        st.header("⚙️ Configuration") #
        user_s = st.session_state.supabase_manager.get_user_settings(st.session_state.user.id) if st.session_state.user and hasattr(st.session_state.user, 'id') else {} #
        max_q = st.slider("Max Questions", 3, 15, user_s.get('max_questions',5), key="max_questions_slider") #
        models = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"] #
        current_model_idx = models.index(user_s.get('model_name', 'gpt-4o-mini')) if user_s.get('model_name', 'gpt-4o-mini') in models else 0 #
        model_c = st.selectbox("AI Model", models, index=current_model_idx, key="model_choice_selectbox") #

        if st.button("💾 Save Settings", use_container_width=True, key="save_settings_button"): #
            if st.session_state.user and hasattr(st.session_state.user, 'id'): #
                settings_to_save = {'max_questions': max_q, 'model_name': model_c} #
                if st.session_state.supabase_manager.update_user_settings(st.session_state.user.id, settings_to_save): #
                    st.success("Settings saved!") #
                else: st.error("Error saving settings.") #
            else: st.warning("User not found. Cannot save settings.") #
        
        st.markdown("---") #
        st.header("📄 Upload Documents") #
        resume_file = st.file_uploader("Upload Resume (PDF/TXT)", type=['pdf', 'txt'], key="resume_upload") #
        job_desc_file = st.file_uploader("Upload Job Description (TXT)", type=['txt'], key="job_desc_upload") #
        if resume_file and job_desc_file: #
            if not st.session_state.get('files_uploaded_message_shown', False): 
                 st.success("✅ Files ready for interview!") #
                 st.session_state.files_uploaded_message_shown = True 
            st.session_state.files_uploaded = True #
        else:
            st.session_state.files_uploaded = False #
            st.session_state.files_uploaded_message_shown = False 

    tab1, tab2 = st.tabs(["🎯 Interview", "📊 Dashboard"]) #

    with tab1:
        if not st.session_state.get('files_uploaded'):
            st.markdown("""<div class="interview-card">
                <h3>🚀 Getting Started</h3>
                <p>To begin your interview experience:</p>
                <ol>
                    <li>Upload your resume (PDF or TXT format)</li>
                    <li>Upload the job description (TXT format)</li>
                    <li>Configure your interview settings in the sidebar</li>
                    <li>Click "Start Interview" to begin</li>
                </ol>
            </div>""", unsafe_allow_html=True) # Shortened for brevity
        else:
            if not st.session_state.get('interview_started') and not st.session_state.get('interview_complete'): #
                _, col_btn, _ = st.columns([1,2,1]) #
                with col_btn: #
                    if st.button("🚀 Start Interview", key="start_interview_main_button", use_container_width=True): #
                        st.session_state.current_session_id = None
                        st.session_state.last_generated_report_id = None 
                        st.session_state.conversation_history = [] 
                        st.session_state.interview_state = {}
                        st.session_state.current_question_idx = 0
                        st.session_state.interview_started = False
                        st.session_state.interview_complete = False
                        
                        with st.spinner("🔧 Initializing AI Interview System with current settings..."):
                            fresh_interview_system = setup_interview_system()
                            if not fresh_interview_system:
                                st.error("❌ Critical Error: Failed to initialize interview system. Check settings (e.g., API key).")
                                st.stop() # Stop if system can't be set up
                            st.session_state.interview_system = fresh_interview_system

                        if not st.session_state.interview_system:
                            st.error("Interview system could not be initialized. Check OpenAI API key and settings.")
                            return # Exit if it's still not initialized

                        with st.spinner("📋 Preparing your personalized interview..."): #
                            try:
                                resume_path = save_uploaded_file(resume_file, "resume") #
                                job_desc_path = save_uploaded_file(job_desc_file, "job_desc") #
                                st.session_state.interview_state = st.session_state.interview_system.start_interactive_interview(resume_path, job_desc_path) #
                                st.session_state.interview_started = True #
                                st.rerun() #
                            except Exception as e:
                                st.error(f"❌ Error starting interview: {e}") #
                                # return # Consider if you want to stop or allow retry
            
            if st.session_state.get('interview_started') and not st.session_state.interview_system:
                 with st.spinner("🔧 Re-initializing AI Interview System..."):
                    st.session_state.interview_system = setup_interview_system()
                 if not st.session_state.interview_system:
                    st.error("Failed to re-initialize interview system during an ongoing interview. Please try restarting the interview.")
                    st.session_state.interview_started = False # Mark as not started to avoid issues
                    st.rerun()

            if st.session_state.get('interview_started') and not st.session_state.get('interview_complete'): #
                display_interview_progress() #
                save_session_to_supabase() 
                if st.session_state.interview_state: #
                    question = st.session_state.interview_system.get_next_question(st.session_state.interview_state) #
                    if question: #
                        st.session_state.current_question = question #
                        st.markdown(f"""<div class="question-box"><h4>🤖 Interviewer Question:</h4><p style="font-size: 1.1em; margin-bottom: 0;">{question}</p></div>""", unsafe_allow_html=True) #
                        with st.form(key="response_form", clear_on_submit=True): #
                            candidate_response = st.text_area("Your Answer:", height=150, placeholder="Type your response here...", key="candidate_input") #
                            form_col1, _, form_col3 = st.columns([1,1,1]) #
                            with form_col1: submit_response = st.form_submit_button("📤 Submit Answer") #
                            with form_col3: end_interview = st.form_submit_button("⏹️ End Interview") #
                        
                        if submit_response and candidate_response.strip(): #
                            with st.spinner("🔍 Analyzing your response..."): #
                                try:
                                    st.session_state.interview_state = st.session_state.interview_system.process_candidate_answer(st.session_state.interview_state, candidate_response) #
                                    latest_note = st.session_state.interview_state.get('interview_notes', [])[-1] if st.session_state.interview_state.get('interview_notes') else None #
                                    st.session_state.conversation_history.append({ #
                                        'question': st.session_state.current_question, #
                                        'response': candidate_response, #
                                        'score': latest_note.get('score', 0) if latest_note else 0 #
                                    })
                                    st.success(f"✅ Response recorded! Score: {latest_note.get('score', 0) if latest_note else 0}/10") #
                                    save_session_to_supabase() #
                                    st.rerun() #
                                except Exception as e:
                                    st.error(f"❌ Error processing response: {e}") #
                        
                        if end_interview: #
                            st.session_state.interview_complete = True #
                            save_session_to_supabase() #
                            st.rerun() #
                    else: # No more questions
                        st.session_state.interview_complete = True #
                        save_session_to_supabase() #
                        st.rerun() #

            if st.session_state.get('interview_complete'): #
                st.balloons() #
                st.markdown("""<div class="main-header"><h2>🎉 Interview Completed!</h2><p>Great job! Here is your comprehensive report.</p></div>""", unsafe_allow_html=True) #

                current_interview_state = st.session_state.get('interview_state', {}) #
                report_generated_this_run = False

                # Generate and save report if not already done or if last_generated_report_id is not set for this completion
                if isinstance(current_interview_state, dict) and not st.session_state.get('last_generated_report_id'):
                    with st.spinner("📊 Generating and saving your comprehensive interview report..."): #
                        final_state = st.session_state.interview_system.generate_final_report(current_interview_state) #
                        st.session_state.interview_state = final_state #
                        
                        save_session_to_supabase()  # Save updated session state with report string

                        if st.session_state.user and hasattr(st.session_state.user, 'id'): #
                            report_content_str = final_state.get('interview_report', '') #
                            if report_content_str: 
                                report_title = f"Interview Report for {user_email} on {datetime.now().strftime('%Y-%m-%d')}"
                                if st.session_state.current_session_id:
                                    report_title = f"Report for Session ({str(st.session_state.current_session_id)[:8]}) - {datetime.now().strftime('%Y-%m-%d')}"
                                
                                report_data_for_db = { #
                                    'title': report_title,
                                    'report_content': report_content_str, #
                                    'summary': final_state.get('report_summary_json', {}), 
                                    'scores': final_state.get('report_scores_json', {}), 
                                    'recommendations': final_state.get('report_recommendations_text', '') 
                                }
                                saved_report_id = st.session_state.supabase_manager.save_interview_report( #
                                    user_id=st.session_state.user.id, #
                                    session_id=st.session_state.current_session_id, 
                                    report_data=report_data_for_db #
                                )
                                if saved_report_id: #
                                    st.session_state.last_generated_report_id = saved_report_id # Store the new report ID
                                    report_generated_this_run = True
                                    st.toast(f"📝 Report saved (ID: {saved_report_id[:8]})!", icon="📄") #
                                else:
                                    st.error("Failed to save the detailed interview report to the database.") #
                            else:
                                st.warning("Report content was empty, not saving to dedicated reports table.") #
                        else:
                            st.warning("User information not found. Cannot save report.") #
                
                # Fetch and display the report
                report_to_display_id = st.session_state.get('last_generated_report_id')
                if report_to_display_id:
                    with st.spinner("Loading your report..."):
                        report_details_data = st.session_state.supabase_manager.get_report(report_to_display_id)
                    
                    if report_details_data:
                        with st.container(): # New container for the direct report display
                             st.markdown("### Your Generated Interview Report") # Removed anchor=False
                             display_report_details_component(report_details_data)
                    else:
                        st.error("Could not retrieve the generated report for display.")
                elif not report_generated_this_run : # If report wasn't generated now (e.g. page reload after completion)
                     st.info("Report already generated. You can find it in the dashboard or start a new interview.")


                # New Interview button 
                st.markdown("---")
                _, btn_col, _ = st.columns([1,2,1])
                with btn_col:
                    if st.button("🔄 Start New Interview", key="start_new_interview_button_main", use_container_width=True):
                        keys_to_reset = [ 
                            'interview_state', 'interview_started', 'current_question', 
                            'conversation_history', 'interview_complete', 'current_session_id', 
                            'files_uploaded', 'resume_upload', 'job_desc_upload', 
                            'selected_report_id_to_display', 'files_uploaded_message_shown',
                            'last_generated_report_id' # Reset this too
                        ]
                        for key in keys_to_reset: 
                            if key in st.session_state: del st.session_state[key]
                        st.session_state.files_uploaded = False 
                        st.rerun()

    with tab2:
        show_user_dashboard()

if __name__ == "__main__":
    main() #