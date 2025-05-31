from langgraph.graph import StateGraph, END
from src.core.models import InterviewState

class InterviewWorkflowManager:
    """Manages the LangGraph workflow for interviews"""
    
    def __init__(self, interview_system):
        self.interview_system = interview_system
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow"""
        workflow = StateGraph(InterviewState)
        
        # Add nodes
        workflow.add_node("document_processor", self._process_documents)
        workflow.add_node("planner", self._create_interview_plan)
        workflow.add_node("question_generator", self._generate_next_question)
        workflow.add_node("response_analyzer", self._analyze_response)
        workflow.add_node("note_taker", self._take_notes)
        workflow.add_node("report_generator", self._generate_report)
        workflow.add_node("rag_retriever", self._retrieve_context)
        
        # Define the flow
        workflow.set_entry_point("document_processor")
        
        workflow.add_edge("document_processor", "planner")
        workflow.add_edge("planner", "question_generator")
        workflow.add_edge("question_generator", "rag_retriever")
        workflow.add_edge("rag_retriever", "response_analyzer")
        workflow.add_edge("response_analyzer", "note_taker")
        
        # Conditional routing
        workflow.add_conditional_edges(
            "note_taker",
            self._should_continue_interview,
            {
                "continue": "question_generator",
                "complete": "report_generator",
            }
        )
        
        workflow.add_edge("report_generator", END)
        
        return workflow.compile()
    
    def _process_documents(self, state: InterviewState) -> InterviewState:
        """Process and prepare documents for the interview"""
        print("📄 Processing documents...")
        
        # Initialize basic state if not already set
        if not state.get('conversation_history'):
            state['conversation_history'] = []
        if not state.get('interview_notes'):
            state['interview_notes'] = []
        if not state.get('current_question_idx'):
            state['current_question_idx'] = 0
        
        state['next_action'] = 'plan'
        return state
    
    def _create_interview_plan(self, state: InterviewState) -> InterviewState:
        """Create interview plan using the interview system"""
        interview_plan = self.interview_system.planner.create_interview_plan(
            state['resume_content'], 
            state['job_description']
        )
        state['interview_plan'] = interview_plan
        state['next_action'] = 'generate_question'
        return state
    
    def _generate_next_question(self, state: InterviewState) -> InterviewState:
        """Generate the next interview question"""
        print(f"❓ Generating question {state['current_question_idx'] + 1}...")
        
        if state['current_question_idx'] >= len(state['interview_plan']):
            state['is_complete'] = True
            state['next_action'] = 'complete'
            return state
        
        current_q = state['interview_plan'][state['current_question_idx']]
        state['current_question'] = current_q['question']
        
        print(f"Next question: {state['current_question']}")
        return state
    
    def _retrieve_context(self, state: InterviewState) -> InterviewState:
        """Retrieve relevant context using RAG"""
        print("🔍 Retrieving relevant context...")
        
        search_query = f"{state['current_question']} {state.get('candidate_response', '')}"
        state['rag_context'] = self.interview_system.rag_system.get_context(search_query)
        
        return state
    
    def _analyze_response(self, state: InterviewState) -> InterviewState:
        """Analyze candidate response"""
        if not state.get('candidate_response'):
            return state
        
        analysis = self.interview_system.analyzer.analyze_response(
            state['current_question'],
            state['candidate_response'],
            state['rag_context'],
            state['conversation_history']
        )
        
        state['current_analysis'] = analysis
        return state
    
    def _take_notes(self, state: InterviewState) -> InterviewState:
        """Take structured notes on the interview exchange"""
        print("📝 Taking notes...")
        
        if not state.get('candidate_response'):
            return state
        
        # Create interview note
        note = self.interview_system.analyzer.create_interview_note(
            state['current_question'],
            state['candidate_response'],
            state.get('current_analysis', ''),
            state['interview_plan'][state['current_question_idx']].get('category', 'general')
        )
        
        state['interview_notes'].append(note)
        
        # Update conversation history
        state['conversation_history'].extend([
            {'role': 'interviewer', 'content': state['current_question']},
            {'role': 'candidate', 'content': state['candidate_response']}
        ])
        
        # Move to next question
        state['current_question_idx'] += 1
        
        return state
    
    def _should_continue_interview(self, state: InterviewState) -> str:
        """Determine if interview should continue"""
        if state['current_question_idx'] >= len(state['interview_plan']):
            return "complete"
        return "continue"
    
    def _generate_report(self, state: InterviewState) -> InterviewState:
        """Generate comprehensive interview report"""
        report = self.interview_system.report_generator.generate_report(
            state['resume_content'],
            state['job_description'],
            state['interview_notes']
        )
        
        state['interview_report'] = report
        state['is_complete'] = True
        
        return state
    
    def execute_workflow(self, initial_state: InterviewState) -> InterviewState:
        """Execute the complete interview workflow"""
        return self.graph.invoke(initial_state)
