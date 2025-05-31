from typing import List, Dict, Any, Optional, TypedDict
from dataclasses import dataclass, field
from datetime import datetime


class InterviewState(TypedDict):
    resume_content: str
    job_description: str
    interview_plan: List[Dict[str, Any]]
    current_question_idx: int
    current_question: str
    candidate_response: str
    interview_notes: List[Dict[str, Any]]
    conversation_history: List[Dict[str, str]]
    interview_report: str
    rag_context: str
    next_action: str
    is_complete: bool