from typing import List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema.output_parser import StrOutputParser
from src.prompts.prompts import REPORT_PROMPT


class ReportGenerator:
    """Handles generation of comprehensive interview reports"""
    
    def __init__(self, llm: ChatOpenAI):
        self.llm = llm
        self.report_prompt = ChatPromptTemplate.from_template(REPORT_PROMPT)
        self.chain = self.report_prompt | self.llm | StrOutputParser()
    
    def generate_report(self, resume_content: str, job_description: str, 
                       interview_notes: List[Dict[str, Any]]) -> str:
        """Generate comprehensive interview report"""
        print("📊 Generating interview report...")
        
        notes_text = self._format_interview_notes(interview_notes)
        
        try:
            report = self.chain.invoke({
                'resume_content': resume_content[:2048],  # Truncate for token limits
                'job_description': job_description[:1024],  # Truncate for token limits
                'interview_notes': notes_text
            })
            
            print("✅ Interview report generated successfully!")
            return report
            
        except Exception as e:
            print(f"❌ Error generating report: {e}")
            return f"Report generation failed: {e}"
    
    def _format_interview_notes(self, interview_notes: List[Dict[str, Any]]) -> str:
        """Format interview notes for the report prompt"""
        notes_text = ""
        for i, note in enumerate(interview_notes, 1):
            notes_text += f"\nQuestion {i}: {note['question']}\n"
            notes_text += f"Response: {note['response']}\n"
            notes_text += f"Score: {note['score']}/10\n"
            notes_text += f"Analysis: {note['analysis']}\n"
            notes_text += "-" * 50 + "\n"
        return notes_text
    
    def calculate_overall_score(self, interview_notes: List[Dict[str, Any]]) -> float:
        """Calculate overall interview score"""
        if not interview_notes:
            return 0.0
        
        scores = [note.get('score', 5) for note in interview_notes]
        return sum(scores) / len(scores)
    
    def get_summary_stats(self, interview_notes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get summary statistics from interview notes"""
        if not interview_notes:
            return {}
        
        scores = [note.get('score', 5) for note in interview_notes]
        categories = [note.get('question_category', 'general') for note in interview_notes]
        
        return {
            'total_questions': len(interview_notes),
            'average_score': sum(scores) / len(scores),
            'highest_score': max(scores),
            'lowest_score': min(scores),
            'categories_covered': list(set(categories))
        }