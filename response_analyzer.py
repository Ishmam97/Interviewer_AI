from datetime import datetime
from typing import Dict, Any, List, Optional
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema.output_parser import StrOutputParser
from prompts import ANALYSIS_PROMPT


class ResponseAnalyzer:
    """Handles analysis of candidate responses"""
    
    def __init__(self, llm: ChatOpenAI):
        self.llm = llm
        self.analysis_prompt = ChatPromptTemplate.from_template(ANALYSIS_PROMPT)
        self.chain = self.analysis_prompt | self.llm | StrOutputParser()
    
    def analyze_response(self, question: str, response: str, rag_context: str, 
                        conversation_history: List[Dict[str, str]]) -> str:
        """Analyze candidate response using RAG context"""
        print("🔬 Analyzing response...")
        
        if not response:
            return "No response provided"
        
        conversation_text = self._format_conversation_history(conversation_history)
        
        try:
            analysis = self.chain.invoke({
                'question': question,
                'response': response,
                'rag_context': rag_context,
                'conversation_history': conversation_text
            })
            return analysis
            
        except Exception as e:
            print(f"❌ Error analyzing response: {e}")
            return f"Analysis failed: {e}"
    
    def _format_conversation_history(self, conversation_history: List[Dict[str, str]]) -> str:
        """Format conversation history for prompt"""
        return "\n".join([
            f"{msg['role']}: {msg['content']}" 
            for msg in conversation_history[-6:]  # Last 6 exchanges
        ])
    
    def extract_score(self, analysis: str) -> int:
        """Extract numerical score from analysis"""
        score = 5  # default
        for line in analysis.split('\n'):
            if line.startswith('SCORE:'):
                try:
                    score = int(line.split(':')[1].strip().split()[0])
                except:
                    score = 5
                break
        return score
    
    def create_interview_note(self, question: str, response: str, analysis: str, 
                            question_category: str) -> Dict[str, Any]:
        """Create structured interview note"""
        score = self.extract_score(analysis)
        
        return {
            'question': question,
            'response': response,
            'timestamp': datetime.now().isoformat(),
            'score': score,
            'analysis': analysis,
            'question_category': question_category
        }