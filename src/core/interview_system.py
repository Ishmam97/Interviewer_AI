from typing import Dict, Optional
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from src.core.models import InterviewState, InterviewConfig
from src.components.document_processor import DocumentProcessor
from src.components.rag_system import RAGSystem
from src.components.interview_planner import InterviewPlanner
from src.components.response_analyzer import ResponseAnalyzer
from src.components.report_generator import ReportGenerator
from src.core.workflow_manager import InterviewWorkflowManager


class InterviewSystem:
    """Main interview system that orchestrates all components"""
    
    def __init__(self, openai_api_key: str, config: Optional[InterviewConfig] = None):
        self.config = config or InterviewConfig()
        
        # Initialize core components
        self.llm = ChatOpenAI(
            temperature=self.config.temperature,
            model=self.config.model_name,
            api_key=openai_api_key
        )
        
        self.embeddings = OpenAIEmbeddings(api_key=openai_api_key, model="text-embedding-3-small")
        
        # Initialize specialized components
        self.document_processor = DocumentProcessor(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap
        )
        
        self.rag_system = RAGSystem(
            embeddings=self.embeddings,
            index_path=self.config.index_path
        )
        
        self.planner = InterviewPlanner(self.llm)
        self.analyzer = ResponseAnalyzer(self.llm)
        self.report_generator = ReportGenerator(self.llm)
        
        # Initialize workflow manager
        self.workflow_manager = InterviewWorkflowManager(self)
    
    def setup_rag_system(self, resume_path: str, job_desc_path: str, force_rebuild: bool = False) -> Dict[str, str]:
        """Initialize the RAG system with resume and job description"""
        
        # Try to load existing index first (unless force rebuild)
        if not force_rebuild and self.rag_system.load_existing_index():
            # Still need to load document content for state
            documents = self.document_processor.load_documents(resume_path, job_desc_path)
            return self.document_processor.extract_content(documents)
        
        # Build new index
        print("🔧 Building new FAISS index...")
        documents = self.document_processor.load_documents(resume_path, job_desc_path)
        splits = self.document_processor.split_documents(documents)
        self.rag_system.create_index(splits)
        
        return self.document_processor.extract_content(documents)

# Create automated interview process for demo - WIP
    def conduct_full_interview(self, resume_path: str, job_desc_path: str) -> InterviewState:
        """Conduct a complete automated interview"""
        print("🚀 Starting Interview Process...")
        
        try:
            # Setup RAG system
            doc_content = self.setup_rag_system(resume_path, job_desc_path)
            
            # Initialize state
            initial_state = InterviewState(
                resume_content=doc_content['resume_content'],
                job_description=doc_content['job_description'],
                interview_plan=[],
                current_question_idx=0,
                current_question="",
                candidate_response="",
                interview_notes=[],
                conversation_history=[],
                interview_report="",
                rag_context="",
                next_action="",
                is_complete=False
            )
            
            # Execute workflow
            result = self.workflow_manager.execute_workflow(initial_state)
            return result
            
        except Exception as e:
            print(f"❌ Error conducting interview: {e}")
            return {"error": str(e)}
    
    def start_interactive_interview(self, resume_path: str, job_desc_path: str) -> InterviewState:
        """Start an interactive interview session"""
        print("🚀 Starting Interactive Interview...")
        
        # Setup RAG system
        doc_content = self.setup_rag_system(resume_path, job_desc_path)
        
        # Initialize state for interactive mode
        state = InterviewState(
            resume_content=doc_content['resume_content'],
            job_description=doc_content['job_description'],
            interview_plan=[],
            current_question_idx=0,
            current_question="",
            candidate_response="",
            interview_notes=[],
            conversation_history=[],
            interview_report="",
            rag_context="",
            next_action="",
            is_complete=False
        )
        
        # Process documents and create plan
        state = self.workflow_manager._process_documents(state)
        state = self.workflow_manager._create_interview_plan(state)
        
        return state
    
    def get_next_question(self, state: InterviewState) -> Optional[str]:
        """Get the next question for interactive mode"""
        if state['current_question_idx'] >= len(state['interview_plan']):
            return None
        
        state = self.workflow_manager._generate_next_question(state)
        return state['current_question'] if not state.get('is_complete') else None
    
    def process_candidate_answer(self, state: InterviewState, answer: str) -> InterviewState:
        """Process a candidate's answer and update state"""
        state['candidate_response'] = answer
        
        # Run analysis pipeline
        state = self.workflow_manager._retrieve_context(state)
        state = self.workflow_manager._analyze_response(state)
        state = self.workflow_manager._take_notes(state)
        
        return state
    
    def generate_final_report(self, state: InterviewState) -> InterviewState:
        """Generate the final interview report"""
        return self.workflow_manager._generate_report(state)
