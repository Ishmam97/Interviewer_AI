import json
from typing import List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema.output_parser import StrOutputParser
from prompts import PLANNING_PROMPT


class InterviewPlanner:
    """Handles interview planning and question generation"""
    
    def __init__(self, llm: ChatOpenAI):
        self.llm = llm
        self.planning_prompt = ChatPromptTemplate.from_template(PLANNING_PROMPT)
        self.chain = self.planning_prompt | self.llm | StrOutputParser()
    
    def create_interview_plan(self, resume_content: str, job_description: str) -> List[Dict[str, Any]]:
        """Create a comprehensive interview plan using AI planning"""
        print("🎯 Creating interview plan...")
        

        plan_response = self.chain.invoke({
            'resume_content': resume_content,
            'job_description': job_description
        })
        
        # Clean the response to extract JSON
        plan_response = self._clean_json_response(plan_response)
        
        # Parse the JSON response
        interview_plan = json.loads(plan_response)
        
        # Validate the plan structure
        if not isinstance(interview_plan, list) or len(interview_plan) == 0:
            raise ValueError("Invalid interview plan format")
        
        print(f"✅ Created plan with {len(interview_plan)} questions")
        return interview_plan
    
    def _clean_json_response(self, response: str) -> str:
        """Clean AI response to extract valid JSON"""
        response = response.strip()
        if response.startswith('```json'):
            response = response[7:-3]
        elif response.startswith('```'):
            response = response[3:-3]
        return response
    
    def get_next_question(self, interview_plan: List[Dict[str, Any]], current_idx: int) -> str:
        """Get the next question from the interview plan"""
        if current_idx >= len(interview_plan):
            return None
        return interview_plan[current_idx]['question']