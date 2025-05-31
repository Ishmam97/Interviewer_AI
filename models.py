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

@dataclass
class InterviewQuestion:
    question: str
    category: str
    priority: int
    expected_skills: List[str]
    follow_up_prompts: List[str] = field(default_factory=list)

@dataclass
class InterviewNote:
    question: str
    response: str
    timestamp: datetime
    score: int
    observations: str
    relevant_skills: List[str]

@dataclass
class InterviewConfig:
    """Configuration for interview settings"""
    max_questions: int = 5
    chunk_size: int = 500
    chunk_overlap: int = 50
    rag_k_results: int = 3
    temperature: float = 0.3
    model_name: str = "gpt-4.1-nano-2025-04-14"
    index_path: str = "./interview_faiss_index"
