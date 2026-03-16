from typing import Dict, Optional
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from app.services.models import InterviewState, InterviewConfig
from app.services.document_processor import DocumentProcessor
from app.services.rag_system import RAGSystem
from app.services.interview_planner import InterviewPlanner
from app.services.response_analyzer import ResponseAnalyzer
from app.services.report_generator import ReportGenerator
from app.services.workflow_manager import InterviewWorkflowManager


class InterviewSystem:
    """Main interview system that orchestrates all components"""

    def __init__(self, gemini_api_key: str, config: Optional[InterviewConfig] = None):
        self.config = config or InterviewConfig()

        self.llm = ChatGoogleGenerativeAI(
            temperature=self.config.temperature,
            model=self.config.model_name,
            google_api_key=gemini_api_key,
        )

        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-2-preview",
            google_api_key=gemini_api_key,
        )

        self.document_processor = DocumentProcessor(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        )

        self.rag_system = RAGSystem(
            embeddings=self.embeddings,
            index_path=self.config.index_path,
        )

        self.planner = InterviewPlanner(self.llm, config=self.config)
        self.analyzer = ResponseAnalyzer(self.llm)
        self.report_generator = ReportGenerator(self.llm)

        self.workflow_manager = InterviewWorkflowManager(self)

    def setup_rag_system(self, resume_path: str, job_desc_path: str, force_rebuild: bool = False) -> Dict[str, str]:
        if not force_rebuild and self.rag_system.load_existing_index():
            documents = self.document_processor.load_documents(resume_path, job_desc_path)
            return self.document_processor.extract_content(documents)

        documents = self.document_processor.load_documents(resume_path, job_desc_path)
        splits = self.document_processor.split_documents(documents)
        self.rag_system.create_index(splits)
        return self.document_processor.extract_content(documents)

    def start_interactive_interview(self, resume_path: str, job_desc_path: str) -> InterviewState:
        doc_content = self.setup_rag_system(resume_path, job_desc_path)
        state = InterviewState(
            resume_content=doc_content["resume_content"],
            job_description=doc_content["job_description"],
            interview_plan=[], current_question_idx=0, current_question="",
            candidate_response="", interview_notes=[], conversation_history=[],
            interview_report="", rag_context="", next_action="", is_complete=False,
        )
        state = self.workflow_manager._process_documents(state)
        state = self.workflow_manager._create_interview_plan(state)
        return state

    def get_next_question(self, state: InterviewState) -> Optional[str]:
        if state["current_question_idx"] >= len(state["interview_plan"]):
            return None
        state = self.workflow_manager._generate_next_question(state)
        return state["current_question"] if not state.get("is_complete") else None

    def process_candidate_answer(self, state: InterviewState, answer: str) -> InterviewState:
        state["candidate_response"] = answer
        state = self.workflow_manager._retrieve_context(state)
        state = self.workflow_manager._analyze_response(state)
        state = self.workflow_manager._take_notes(state)
        return state

    def generate_final_report(self, state: InterviewState) -> InterviewState:
        return self.workflow_manager._generate_report(state)
