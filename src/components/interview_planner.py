import json
from typing import List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema.output_parser import StrOutputParser
from src.prompts.prompts import PLANNING_PROMPT


class InterviewPlanner:
    """Handles interview planning and question generation"""
    
    def __init__(self, llm: ChatOpenAI, config=None):
        self.llm = llm
        self.config = config  # Store config reference
        self.planning_prompt = ChatPromptTemplate.from_template(PLANNING_PROMPT)
        self.chain = self.planning_prompt | self.llm | StrOutputParser()
    
    def create_interview_plan(self, resume_content: str, job_description: str) -> List[Dict[str, Any]]:
        """Create a comprehensive interview plan using AI planning"""
        print("🎯 Creating interview plan...")
        
        # Get number of questions from config, default to 3
        number_of_questions = 3
        if self.config and hasattr(self.config, 'max_questions'):
            number_of_questions = self.config.max_questions
        
        print(f"📊 Planning {number_of_questions} questions based on configuration")
        
        try:
            plan_response = self.chain.invoke({
                'resume_content': resume_content,
                'job_description': job_description,
                'number_of_questions': number_of_questions
            })
            
            # Clean the response to extract JSON
            plan_response = self._clean_json_response(plan_response)
            
            # Parse the JSON response
            interview_plan = json.loads(plan_response)
            
            # Validate the plan structure
            if not isinstance(interview_plan, list) or len(interview_plan) == 0:
                raise ValueError("Invalid interview plan format")
            
            # Limit to configured number of questions if AI returned more
            if len(interview_plan) > number_of_questions+2:  # Allow some buffer for AI variability
                interview_plan = interview_plan[:number_of_questions]
                print(f"⚠️ Trimmed plan to {number_of_questions} questions as per configuration")
            
            print(f"✅ Created plan with {len(interview_plan)} questions")
            return interview_plan
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"❌ Error parsing interview plan: {e}")
            return self._get_fallback_questions(number_of_questions)
        except Exception as e:
            print(f"❌ Unexpected error creating plan: {e}")
            return self._get_fallback_questions(number_of_questions)
    
    def _clean_json_response(self, response: str) -> str:
        """Clean AI response to extract valid JSON"""
        response = response.strip()
        if response.startswith('```json'):
            response = response[7:-3]
        elif response.startswith('```'):
            response = response[3:-3]
        return response
    
    def _get_fallback_questions(self, number_of_questions: int = 3) -> List[Dict[str, Any]]:
        """Provide fallback questions when AI planning fails"""
        print(f"✅ Using fallback question set with {number_of_questions} questions")
        
        all_fallback_questions = [
            {
                "question": "Tell me about your background and experience relevant to this role.",
                "category": "experience",
                "priority": 5,
                "expected_skills": ["communication"],
                "follow_up_prompts": ["Can you elaborate on specific projects?"]
            },
            {
                "question": "What technical skills do you have that match this position?",
                "category": "technical",
                "priority": 4,
                "expected_skills": ["technical_knowledge"],
                "follow_up_prompts": ["Can you provide specific examples?"]
            },
            {
                "question": "Describe a challenging problem you solved recently.",
                "category": "problem_solving",
                "priority": 4,
                "expected_skills": ["analytical_thinking"],
                "follow_up_prompts": ["What was your approach?"]
            },
            {
                "question": "Why are you interested in this position and our company?",
                "category": "behavioral",
                "priority": 3,
                "expected_skills": ["motivation", "cultural_fit"],
                "follow_up_prompts": ["What specifically attracts you to this role?"]
            },
            {
                "question": "Where do you see yourself in the next 3-5 years?",
                "category": "behavioral",
                "priority": 2,
                "expected_skills": ["career_planning", "ambition"],
                "follow_up_prompts": ["How does this role fit into your plans?"]
            }
        ]
        
        # Return only the requested number of questions
        return all_fallback_questions[:number_of_questions]
    
    def get_next_question(self, interview_plan: List[Dict[str, Any]], current_idx: int) -> str:
        """Get the next question from the interview plan"""
        if current_idx >= len(interview_plan):
            return None
        return interview_plan[current_idx]['question']