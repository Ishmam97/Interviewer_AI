"""
Complete API Interview Flow Test
Tests the actual API endpoints for the complete interview process with real answer submission
"""

import requests
import tempfile
import os
import time
import json
from typing import Dict, Any, List

class CompleteAPIInterviewTest:
    """Test the complete API interview flow using real endpoints"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session_id = None
        self.total_questions = 0
        self.current_question_idx = 0
        self.is_complete = False
        self.test_results = []
        
    def create_test_files(self):
        """Create test files for the interview"""
        resume_content = """
        Michael Rodriguez
        Python Developer
        
        PROFESSIONAL EXPERIENCE:
        
        Senior Python Developer | TechStart Inc. | 2021-2024
        • Developed and maintained REST APIs using FastAPI and Django
        • Implemented microservices architecture serving 500K+ daily requests
        • Worked with PostgreSQL, MongoDB, and Redis for data storage
        • Deployed applications using Docker and AWS services
        • Mentored junior developers and conducted code reviews
        
        Python Developer | DataCorp Solutions | 2019-2021
        • Built data processing pipelines using Python and Apache Spark
        • Created web applications with Django and React integration
        • Implemented authentication systems and security measures
        • Optimized database queries and improved application performance
        
        Junior Software Engineer | WebDev Studio | 2018-2019
        • Developed frontend components using JavaScript and React
        • Integrated third-party APIs and payment systems
        • Participated in agile development processes
        • Learned Python and backend development fundamentals
        
        TECHNICAL SKILLS:
        • Languages: Python, JavaScript, TypeScript, SQL, HTML, CSS
        • Frameworks: FastAPI, Django, Flask, React, Node.js
        • Databases: PostgreSQL, MongoDB, MySQL, Redis
        • Cloud: AWS (EC2, S3, RDS, Lambda), Docker, Kubernetes
        • Tools: Git, Jenkins, pytest, Postman, Jira
        
        EDUCATION:
        Bachelor of Science in Computer Science
        State University | 2014-2018
        
        CERTIFICATIONS:
        • AWS Certified Developer - Associate
        • Python Institute Certified Python Developer
        """
        
        job_content = """
        Senior Python Developer - Backend Systems
        
        COMPANY: InnovateTech Solutions
        DEPARTMENT: Engineering
        EMPLOYMENT TYPE: Full-time
        LOCATION: Remote/Hybrid
        
        ROLE OVERVIEW:
        Join our engineering team as a Senior Python Developer focusing on backend systems 
        and API development. You'll be responsible for building scalable, high-performance 
        applications that serve millions of users worldwide.
        
        KEY RESPONSIBILITIES:
        • Design and develop REST APIs using FastAPI or Django
        • Build microservices architecture for scalable applications
        • Implement database schemas and optimize query performance
        • Deploy applications using Docker and cloud platforms
        • Collaborate with frontend developers on API integration
        • Write comprehensive tests and maintain code quality
        • Participate in code reviews and technical discussions
        • Mentor junior developers and share knowledge
        
        REQUIRED QUALIFICATIONS:
        • 4+ years of professional Python development experience
        • Strong experience with FastAPI, Django, or Flask frameworks
        • Proficiency in database design (PostgreSQL, MongoDB)
        • Experience with RESTful API design and development
        • Knowledge of containerization (Docker) and cloud platforms
        • Understanding of software testing principles and practices
        • Experience with version control systems (Git)
        • Strong problem-solving and debugging skills
        
        PREFERRED QUALIFICATIONS:
        • Experience with microservices architecture
        • Knowledge of message queues (RabbitMQ, Apache Kafka)
        • Familiarity with AWS, Azure, or GCP services
        • Experience with CI/CD pipelines and DevOps practices
        • Understanding of security best practices
        • Previous experience in a senior or lead role
        
        TECHNICAL ENVIRONMENT:
        • Backend: Python, FastAPI, Django
        • Databases: PostgreSQL, MongoDB, Redis
        • Infrastructure: Docker, Kubernetes, AWS
        • Tools: Git, Jenkins, pytest, Elasticsearch
        • Monitoring: Prometheus, Grafana, ELK stack
        
        WHAT WE OFFER:
        • Competitive salary and equity package
        • Comprehensive health and dental coverage
        • Flexible work arrangements (remote/hybrid)
        • Professional development budget
        • Modern tech stack and cutting-edge projects
        • Collaborative and innovative team culture
        """
        
        resume_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        resume_file.write(resume_content)
        resume_file.close()
        
        job_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        job_file.write(job_content)
        job_file.close()
        
        return resume_file.name, job_file.name
    
    def cleanup_files(self, *file_paths):
        """Clean up temporary files"""
        for file_path in file_paths:
            try:
                os.unlink(file_path)
            except:
                pass
    
    def start_interview(self, max_questions: int = 5) -> Dict[str, Any]:
        """Start the interview using the test endpoint"""
        print(f"🚀 Starting interview with {max_questions} questions...")
        
        resume_path, job_path = self.create_test_files()
        
        try:
            with open(resume_path, 'rb') as resume_file, open(job_path, 'rb') as job_file:
                files = {
                    'resume': ('resume.txt', resume_file, 'text/plain'),
                    'job_description': ('job_desc.txt', job_file, 'text/plain')
                }
                
                data = {
                    'max_questions': max_questions,
                    'model_name': 'gpt-4o-mini'
                }
                
                response = self.session.post(
                    f"{self.base_url}/test/interview/start",
                    files=files,
                    data=data
                )
                
                if response.status_code == 200:
                    result = response.json()
                    self.session_id = result["session_id"]
                    self.total_questions = result["total_questions"]
                    self.current_question_idx = result["current_question_idx"]
                    self.is_complete = result["is_complete"]
                    
                    print(f"✅ Interview started successfully!")
                    print(f"📋 Session ID: {self.session_id}")
                    print(f"📊 Total questions: {self.total_questions}")
                    print(f"🔢 Current question index: {self.current_question_idx}")
                    print(f"❓ First question: {result['current_question']}")
                    print("-" * 80)
                    
                    return result
                else:
                    raise Exception(f"Failed to start interview: {response.status_code} - {response.text}")
                    
        finally:
            self.cleanup_files(resume_path, job_path)
    
    def submit_answer(self, answer: str) -> Dict[str, Any]:
        """Submit an answer using the test endpoint"""
        if not self.session_id:
            raise Exception("No active interview session")
        
        print(f"💬 Submitting answer for question {self.current_question_idx + 1}:")
        print(f"   Answer: {answer}")
        
        answer_data = {
            "session_id": self.session_id,
            "answer": answer
        }
        
        response = self.session.post(
            f"{self.base_url}/test/interview/answer",
            json=answer_data
        )
        
        if response.status_code == 200:
            result = response.json()
            
            # Update local state
            self.current_question_idx += 1
            self.is_complete = result["is_complete"]
            
            print(f"📊 Score: {result['score']:.1f}/10")
            print(f"🔍 Analysis: {result['analysis']}")
            print(f"✅ Interview complete: {result['is_complete']}")
            
            if not result["is_complete"] and result["next_question"]:
                print(f"➡️  Next question: {result['next_question']}")
            
            print("-" * 80)
            return result
        else:
            raise Exception(f"Failed to submit answer: {response.status_code} - {response.text}")
    
    def run_yes_no_interview_test(self, max_questions: int = 5) -> Dict[str, Any]:
        """Run complete interview with alternating Yes/No answers"""
        print("🎯 Running Complete Yes/No Interview Test")
        print("=" * 80)
        
        # Start interview
        start_result = self.start_interview(max_questions)
        
        # Prepare alternating Yes/No answers with context
        yes_no_answers = [
            "Yes, I have 5 years of experience with Python development. I've worked extensively with FastAPI and Django frameworks to build REST APIs and web applications. I'm very comfortable with Python's ecosystem and best practices.",
            
            "No, I don't have direct experience with Kubernetes in production environments, but I have solid experience with Docker containerization and I understand the concepts of container orchestration. I'm eager to learn Kubernetes and believe my Docker experience provides a good foundation.",
            
            "Yes, I have extensive database experience with PostgreSQL and MongoDB. I've designed database schemas, optimized complex queries, and implemented proper indexing strategies. I'm comfortable with both SQL and NoSQL databases depending on the use case.",
            
            "No, I haven't worked with Apache Kafka specifically, but I have experience with other message queuing systems like RabbitMQ and Redis pub/sub. I understand the importance of asynchronous processing and event-driven architectures.",
            
            "Yes, I have strong experience with AWS services including EC2, S3, RDS, and Lambda. I've deployed applications using Docker on AWS and implemented CI/CD pipelines. I'm comfortable with cloud-native development and infrastructure as code."
        ]
        
        test_results = {
            "session_id": self.session_id,
            "total_questions": self.total_questions,
            "questions_and_answers": [],
            "scores": [],
            "final_score": 0,
            "interview_completed": False,
            "api_responses": []
        }
        
        # Answer each question
        for i, answer in enumerate(yes_no_answers):
            if i >= self.total_questions:
                break
            
            try:
                # Submit answer
                answer_result = self.submit_answer(answer)
                
                # Record results
                qa_result = {
                    "question_number": i + 1,
                    "answer": answer,
                    "answer_type": "Yes" if answer.lower().startswith("yes") else "No",
                    "score": answer_result["score"],
                    "analysis": answer_result["analysis"],
                    "is_complete": answer_result["is_complete"],
                    "next_question": answer_result.get("next_question"),
                    "api_response": answer_result
                }
                
                test_results["questions_and_answers"].append(qa_result)
                test_results["scores"].append(answer_result["score"])
                test_results["api_responses"].append(answer_result)
                
                # Check if interview is complete
                if answer_result["is_complete"]:
                    test_results["interview_completed"] = True
                    break
                    
                # Small delay between questions
                time.sleep(1)
                
            except Exception as e:
                print(f"❌ Error submitting answer {i + 1}: {e}")
                break
        
        # Calculate final score
        if test_results["scores"]:
            test_results["final_score"] = sum(test_results["scores"]) / len(test_results["scores"])
        
        return test_results
    
    def validate_interview_state(self, results: Dict[str, Any]) -> Dict[str, bool]:
        """Validate the interview state progression"""
        validation_results = {
            "session_id_consistent": True,
            "scores_progressive": True,
            "completion_correct": True,
            "question_progression": True,
            "answer_analysis_present": True
        }
        
        # Check session ID consistency
        for i, qa in enumerate(results["questions_and_answers"]):
            if qa["api_response"]["session_id"] != results["session_id"]:
                validation_results["session_id_consistent"] = False
                break
        
        # Check scores are reasonable
        for score in results["scores"]:
            if score < 0 or score > 10:
                validation_results["scores_progressive"] = False
                break
        
        # Check completion logic
        if results["interview_completed"]:
            last_qa = results["questions_and_answers"][-1]
            if not last_qa["is_complete"]:
                validation_results["completion_correct"] = False
        
        # Check question progression
        for i, qa in enumerate(results["questions_and_answers"]):
            if i < len(results["questions_and_answers"]) - 1:  # Not the last question
                if qa["is_complete"]:
                    validation_results["question_progression"] = False
                    break
                if not qa["next_question"]:
                    validation_results["question_progression"] = False
                    break
        
        # Check analysis presence
        for qa in results["questions_and_answers"]:
            if not qa["analysis"] or len(qa["analysis"]) < 10:
                validation_results["answer_analysis_present"] = False
                break
        
        return validation_results
    
    def print_test_results(self, results: Dict[str, Any], validation: Dict[str, bool]):
        """Print comprehensive test results"""
        print("\n🎯 COMPREHENSIVE TEST RESULTS")
        print("=" * 80)
        
        # Basic info
        print(f"Session ID: {results['session_id']}")
        print(f"Total Questions: {results['total_questions']}")
        print(f"Questions Answered: {len(results['questions_and_answers'])}")
        print(f"Interview Completed: {'✅ Yes' if results['interview_completed'] else '❌ No'}")
        print(f"Final Score: {results['final_score']:.1f}/10")
        print()
        
        # Validation results
        print("🔍 VALIDATION RESULTS:")
        print("-" * 30)
        for test_name, passed in validation.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{test_name.replace('_', ' ').title()}: {status}")
        print()
        
        # Question by question analysis
        print("📋 QUESTION-BY-QUESTION ANALYSIS:")
        print("-" * 50)
        for qa in results["questions_and_answers"]:
            print(f"Question {qa['question_number']} ({qa['answer_type']} Answer):")
            print(f"  Score: {qa['score']:.1f}/10")
            print(f"  Analysis: {qa['analysis'][:100]}...")
            print(f"  Complete: {qa['is_complete']}")
            if qa['next_question']:
                print(f"  Next: {qa['next_question'][:50]}...")
            print()
        
        # Score analysis
        if results["scores"]:
            print("📊 SCORE ANALYSIS:")
            print("-" * 20)
            print(f"Scores: {[f'{s:.1f}' for s in results['scores']]}")
            print(f"Average: {sum(results['scores']) / len(results['scores']):.1f}/10")
            print(f"Min: {min(results['scores']):.1f}/10")
            print(f"Max: {max(results['scores']):.1f}/10")
            print()
        
        # Yes/No answer analysis
        yes_answers = [qa for qa in results["questions_and_answers"] if qa["answer_type"] == "Yes"]
        no_answers = [qa for qa in results["questions_and_answers"] if qa["answer_type"] == "No"]
        
        if yes_answers and no_answers:
            yes_avg = sum(qa["score"] for qa in yes_answers) / len(yes_answers)
            no_avg = sum(qa["score"] for qa in no_answers) / len(no_answers)
            
            print("📈 YES/NO ANSWER COMPARISON:")
            print("-" * 30)
            print(f"Yes answers: {len(yes_answers)} (avg: {yes_avg:.1f}/10)")
            print(f"No answers: {len(no_answers)} (avg: {no_avg:.1f}/10)")
            print(f"Difference: {abs(yes_avg - no_avg):.1f} points")
        
        print("=" * 80)
    
    def run_comprehensive_test(self):
        """Run all tests and provide comprehensive results"""
        print("🎯 AI Interview Assistant - Comprehensive API Test")
        print("=" * 80)
        print("Testing complete interview flow with real API endpoints")
        print("Using alternating Yes/No answers to test state management")
        print()
        
        try:
            # Run the main test
            results = self.run_yes_no_interview_test(5)
            
            # Validate the results
            validation = self.validate_interview_state(results)
            
            # Print results
            self.print_test_results(results, validation)
            
            # Final assessment
            all_passed = all(validation.values())
            
            print("\n🏆 FINAL ASSESSMENT:")
            print("-" * 20)
            if all_passed:
                print("✅ ALL TESTS PASSED!")
                print("🎉 Interview API is working correctly with proper state management")
            else:
                print("⚠️  Some tests failed. Review the validation results above.")
                failed_tests = [test for test, passed in validation.items() if not passed]
                print(f"Failed tests: {failed_tests}")
            
            return results, validation
            
        except Exception as e:
            print(f"❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            return None, None


def main():
    """Main function to run the comprehensive test"""
    tester = CompleteAPIInterviewTest()
    results, validation = tester.run_comprehensive_test()
    
    if results and validation:
        # Return appropriate exit code
        if all(validation.values()):
            print("\n🎉 All tests passed successfully!")
            exit(0)
        else:
            print("\n⚠️  Some tests failed.")
            exit(1)
    else:
        print("\n❌ Test execution failed.")
        exit(1)


if __name__ == "__main__":
    main()
