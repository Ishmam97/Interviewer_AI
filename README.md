# AI Interview Assistant
## Overview

The AI Interview Assistant is a web-based application designed to conduct AI-driven mock interviews. It leverages large language models (LLMs), LangGraph for workflow management, Streamlit for the user interface, LangChain for AI integrations, and Supabase for database operations. The application allows users to upload resumes and job descriptions, participate in interactive interviews, receive real-time feedback, and generate detailed performance reports. It supports user authentication, session management, and personalized interview experiences.

Try the demo: https://interviewerai-ishmamdemo.streamlit.app/

## Features

User Authentication: Secure sign-up and sign-in functionality using Supabase Auth.
Document Upload: Upload resumes (PDF/TXT) and job descriptions (TXT) to tailor interviews.
Interactive Interviews: AI-generated questions based on resume and job description, with real-time scoring and feedback.
Session Management: Save and resume interview sessions via Supabase.
Report Generation: Comprehensive reports with summaries, scores, and recommendations stored in Supabase.
Dashboard: View interview history, performance metrics, and saved reports.
Configurable Settings: Customize interview parameters like maximum questions and AI model selection.
RAG Integration: Uses FAISS for Retrieval-Augmented Generation to provide context-aware questions and analysis.

## Project Structure
├── app.py                      # Main Streamlit application
├── config
│   ├── config.py               # Configuration management
│   └── __init__.py
├── data
│   ├── job_descriptions
│   │   └── job_desc.txt        # Sample job description
│   └── resumes
│       ├── _resume.pdf
│       └── resume.pdf          # Sample resume
├── interview_faiss_index
│   ├── index.faiss             # FAISS index for RAG
│   └── index.pkl
├── interview_sessions          # Directory for session data
├── logs                        # Directory for logs
├── main-old.py                 # Legacy main script
├── main.py                     # CLI-based main script
├── README.md                   # This file
├── reports
│   ├── interview_report_*.txt  # Generated reports
├── requirements.txt            # Python dependencies
├── src
│   ├── components
│   │   ├── document_processor.py  # Document processing logic
│   │   ├── interview_planner.py   # Interview plan generation
│   │   ├── rag_system.py         # RAG system for context retrieval
│   │   ├── report_generator.py   # Report generation logic
│   │   ├── response_analyzer.py  # Response analysis and scoring
│   │   └── __init__.py
│   ├── core
│   │   ├── interview_system.py   # Core interview logic
│   │   ├── models.py            # Data models
│   │   ├── workflow_manager.py  # LangGraph workflow
│   │   └── __init__.py
│   ├── database
│   │   ├── supabase.py         # Supabase database operations
│   │   └── __init__.py
│   ├── prompts
│   │   ├── prompts.py          # Prompt templates
│   │   └── __init__.py
│   └── utils
│       ├── utils.py           # Utility functions
│       └── __init__.py
└── vector_stores
    └── interview_faiss_index   # FAISS index storage
        ├── index.faiss
        └── index.pkl

Supabase Schema
The application uses the following Supabase tables:

profiles: Stores user profile data (id, full_name, avatar_url, created_at, updated_at).
user_settings: Stores user preferences (id, user_id, max_questions, model_name, temperature, chunk_size, chunk_overlap, created_at, updated_at).
interview_sessions: Stores interview session data (id, user_id, title, status, interview_plan, current_question_idx, interview_notes, conversation_history, resume_content, job_description, total_questions, average_score, final_report, created_at, updated_at).
interview_reports: Stores generated reports (id, user_id, session_id, title, report_content, summary, scores, recommendations, created_at, updated_at).

Prerequisites

Python 3.9+
Supabase account with configured project (set SUPABASE_URL and SUPABASE_ANON_KEY environment variables)
OpenAI API key (set OPENAI_API_KEY environment variable)
Dependencies listed in requirements.txt

Installation

Clone the repository:git clone <repository-url>
cd ai-interview-assistant


Create a virtual environment and activate it:python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate


Install dependencies:pip install -r requirements.txt


Set up environment variables:Create a .env file in the project root and add:OPENAI_API_KEY=your_openai_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_supabase_anon_key



Usage
Web Interface (Streamlit)

Run the Streamlit app:streamlit run app.py


Open the provided URL in your browser (typically http://localhost:8501).
Sign up or sign in using the authentication page.
Upload a resume and job description in the sidebar.
Configure interview settings (e.g., max questions, AI model).
Start the interview, answer questions, and review the generated report.
Use the dashboard to view past sessions and reports.

Command Line Interface

Run the CLI script:python main.py


Choose options from the menu:
Interactive Interview Mode: Conduct a mock interview with provided resume and job description files.
Rebuild FAISS Index: Rebuild the FAISS index for RAG.
Exit: Close the application.



Configuration

config.py: Manages system-wide settings (e.g., file paths, interview parameters).
User Settings: Stored in Supabase user_settings table, configurable via the Streamlit sidebar.
Default Settings:
Max questions: 5
Model: gpt-4.1-nano-2025-04-14 (update as needed)
Temperature: 0.3
Chunk size: 800
Chunk overlap: 150
RAG k results: 3



Development

Adding New Features:
Extend InterviewSystem (src/core/interview_system.py) for core logic.
Update InterviewWorkflowManager (src/core/workflow_manager.py) for new workflow nodes.
Modify app.py for UI changes, ensuring consistency with Supabase schema.


Testing:
Use SupabaseManager.test_connection() to verify database connectivity.
Validate configurations with ConfigManager.validate_config().


Extending Prompts:
Add new prompt templates in src/prompts/prompts.py.


Database Changes:
Update supabase.py for new table operations.
Ensure schema consistency in Supabase.



Known Issues

Ensure environment variables are correctly set to avoid authentication errors.
Large resumes or job descriptions may exceed token limits; adjust chunk_size and chunk_overlap in settings.
Report content must be non-empty when saving to interview_reports to avoid database errors.

Contributing

Fork the repository.
Create a feature branch (git checkout -b feature/your-feature).
Commit changes (git commit -m "Add your feature").
Push to the branch (git push origin feature/your-feature).
Open a pull request.

License
This project is licensed under the MIT License.
Contact
For issues or feature requests, please open an issue on the repository or contact the development team.
