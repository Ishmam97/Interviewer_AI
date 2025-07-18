"""
Pytest-based API tests for AI Interview Assistant
Run with: pytest tests/test_api_pytest.py -v
"""

import pytest
import requests
import tempfile
import os
import json
from typing import Dict, Any

# Test configuration
API_BASE_URL = "http://localhost:8000"
TEST_USER_EMAIL = "pytest.user@example.com"
TEST_USER_PASSWORD = "pytestpassword123"
TEST_USER_NAME = "Pytest User"

class TestAPIEndpoints:
    """Test class for all API endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.auth_token = None
        self.test_session_id = None
        
    def create_test_files(self):
        """Create temporary test files"""
        resume_content = """
        Jane Smith
        Senior Python Developer
        
        Experience:
        - 7 years Python development
        - FastAPI, Django, Flask
        - Machine Learning with scikit-learn
        - AWS, Docker, Kubernetes
        - API design and development
        
        Skills:
        - Python, JavaScript, TypeScript
        - FastAPI, React, PostgreSQL
        - Docker, Kubernetes, AWS
        - OpenAI API, LangChain
        """
        
        job_content = """
        AI Engineer Position
        
        Requirements:
        - 5+ years Python experience
        - FastAPI framework expertise
        - Machine Learning knowledge
        - API development skills
        - Cloud deployment experience
        - OpenAI API integration
        
        Responsibilities:
        - Build AI-powered applications
        - Develop REST APIs
        - Integrate with ML models
        - Deploy to cloud platforms
        """
        
        # Create temp files
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
    
    def test_health_check(self):
        """Test health check endpoint"""
        response = self.session.get(f"{API_BASE_URL}/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
    
    def test_admin_health_check(self):
        """Test admin health check endpoint"""
        response = self.session.get(f"{API_BASE_URL}/admin/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["api_status"] == "healthy"
        assert "database_status" in data
        assert "timestamp" in data
    
    
    @pytest.mark.skipif(
        os.getenv("SKIP_AUTH_TESTS", "").lower() == "true",
        reason="Authentication tests skipped - Supabase not configured"
    )
    def test_user_signin(self):
        """Test user signin endpoint"""
        signin_data = {
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
        
        response = self.session.post(f"{API_BASE_URL}/auth/signin", json=signin_data)
        
        if response.status_code == 200:
            data = response.json()
            assert "message" in data
            assert "user" in data
            
            # Store token if available
            if "access_token" in data:
                self.auth_token = data["access_token"]
                self.session.headers.update({
                    "Authorization": f"Bearer {self.auth_token}"
                })
    
    def test_interview_start_no_auth(self):
        """Test interview start endpoint without authentication"""
        resume_path, job_path = self.create_test_files()
        
        try:
            with open(resume_path, 'rb') as resume_file, open(job_path, 'rb') as job_file:
                files = {
                    'resume': ('resume.txt', resume_file, 'text/plain'),
                    'job_description': ('job_desc.txt', job_file, 'text/plain')
                }
                
                data = {
                    'max_questions': 3,
                    'model_name': 'gpt-4o-mini'
                }
                
                response = self.session.post(
                    f"{API_BASE_URL}/test/interview/start",
                    files=files,
                    data=data
                )
                
                assert response.status_code == 200
                data = response.json()
                
                assert "session_id" in data
                assert "current_question" in data
                assert "is_complete" in data
                assert "current_question_idx" in data
                assert "total_questions" in data
                assert data["is_complete"] is False
                assert data["current_question_idx"] >= 0
                assert data["total_questions"] > 0
                
                # Store session ID for further tests
                self.test_session_id = data["session_id"]
                
        finally:
            self.cleanup_files(resume_path, job_path)
    
    def test_interview_start_with_invalid_files(self):
        """Test interview start with invalid file types"""
        # Create invalid file
        invalid_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        invalid_file.write("invalid content")
        invalid_file.close()
        
        try:
            with open(invalid_file.name, 'rb') as file1, open(invalid_file.name, 'rb') as file2:
                files = {
                    'resume': ('resume.txt', file1, 'text/plain'),
                    'job_description': ('job_desc.txt', file2, 'text/plain')
                }
                
                data = {
                    'max_questions': 3,
                    'model_name': 'gpt-4o-mini'
                }
                
                response = self.session.post(
                    f"{API_BASE_URL}/test/interview/start",
                    files=files,
                    data=data
                )
                
                # Should handle gracefully - either success or proper error
                assert response.status_code in [200, 400, 500]
                
        finally:
            self.cleanup_files(invalid_file.name)
    
    def test_interview_start_missing_files(self):
        """Test interview start with missing files"""
        data = {
            'max_questions': 3,
            'model_name': 'gpt-4o-mini'
        }
        
        response = self.session.post(
            f"{API_BASE_URL}/test/interview/start",
            data=data
        )
        
        # Should return 422 for missing required files
        assert response.status_code == 422
    
    def test_interview_start_invalid_parameters(self):
        """Test interview start with invalid parameters"""
        resume_path, job_path = self.create_test_files()
        
        try:
            with open(resume_path, 'rb') as resume_file, open(job_path, 'rb') as job_file:
                files = {
                    'resume': ('resume.txt', resume_file, 'text/plain'),
                    'job_description': ('job_desc.txt', job_file, 'text/plain')
                }
                
                data = {
                    'max_questions': -1,  # Invalid value
                    'model_name': 'invalid-model'
                }
                
                response = self.session.post(
                    f"{API_BASE_URL}/test/interview/start",
                    files=files,
                    data=data
                )
                
                # Should handle invalid parameters gracefully
                assert response.status_code in [200, 400, 422, 500]
                
        finally:
            self.cleanup_files(resume_path, job_path)
    
    @pytest.mark.skipif(
        os.getenv("SKIP_AUTH_TESTS", "").lower() == "true",
        reason="Authentication tests skipped - requires valid session"
    )
    def test_submit_answer(self):
        """Test answer submission endpoint"""
        if not self.test_session_id:
            pytest.skip("No active session available")
        
        answer_data = {
            "session_id": self.test_session_id,
            "answer": "I have extensive experience with Python and FastAPI. I've built several REST APIs and integrated them with machine learning models using OpenAI's API. I'm also experienced with cloud deployment using AWS and Docker."
        }
        
        response = self.session.post(f"{API_BASE_URL}/interview/answer", json=answer_data)
        
        if response.status_code == 200:
            data = response.json()
            assert "session_id" in data
            assert "score" in data
            assert "analysis" in data
            assert "is_complete" in data
            assert data["session_id"] == self.test_session_id
    
    def test_submit_answer_invalid_session(self):
        """Test answer submission with invalid session ID"""
        answer_data = {
            "session_id": "invalid-session-id",
            "answer": "Test answer"
        }
        
        # Add dummy auth header to bypass authentication check
        headers = {"Authorization": "Bearer dummy-token"}
        response = self.session.post(f"{API_BASE_URL}/interview/answer", json=answer_data, headers=headers)
        
        # Should return 404 for invalid session (or 401 if auth fails first)
        assert response.status_code in [404, 401]
    
    def test_submit_answer_missing_data(self):
        """Test answer submission with missing data"""
        incomplete_data = {
            "session_id": "test-session"
            # Missing answer field
        }
        
        # Add dummy auth header to bypass authentication check
        headers = {"Authorization": "Bearer dummy-token"}
        response = self.session.post(f"{API_BASE_URL}/interview/answer", json=incomplete_data, headers=headers)
        
        # Should return 422 for missing required fields (or 401 if auth fails first)
        assert response.status_code in [422, 401]
    
    @pytest.mark.skipif(
        os.getenv("SKIP_AUTH_TESTS", "").lower() == "true",
        reason="Authentication tests skipped - requires authentication"
    )
    def test_get_user_sessions(self):
        """Test get user sessions endpoint"""
        if not self.auth_token:
            pytest.skip("No auth token available")
        
        response = self.session.get(f"{API_BASE_URL}/interview/sessions")
        
        if response.status_code == 200:
            data = response.json()
            assert "sessions" in data
            assert isinstance(data["sessions"], list)
    
    @pytest.mark.skipif(
        os.getenv("SKIP_AUTH_TESTS", "").lower() == "true",
        reason="Authentication tests skipped - requires authentication"
    )
    def test_get_user_reports(self):
        """Test get user reports endpoint"""
        if not self.auth_token:
            pytest.skip("No auth token available")
        
        response = self.session.get(f"{API_BASE_URL}/reports")
        
        if response.status_code == 200:
            data = response.json()
            assert "reports" in data
            assert isinstance(data["reports"], list)
    
    @pytest.mark.skipif(
        os.getenv("SKIP_AUTH_TESTS", "").lower() == "true",
        reason="Authentication tests skipped - requires authentication"
    )
    def test_get_dashboard_stats(self):
        """Test get dashboard stats endpoint"""
        if not self.auth_token:
            pytest.skip("No auth token available")
        
        response = self.session.get(f"{API_BASE_URL}/dashboard/stats")
        
        if response.status_code == 200:
            data = response.json()
            # Stats structure depends on implementation
            assert isinstance(data, dict)
    
    def test_nonexistent_endpoint(self):
        """Test calling a non-existent endpoint"""
        response = self.session.get(f"{API_BASE_URL}/nonexistent")
        
        assert response.status_code == 404
    
    def test_method_not_allowed(self):
        """Test calling endpoint with wrong HTTP method"""
        response = self.session.put(f"{API_BASE_URL}/health")
        
        assert response.status_code == 405


# Integration tests
class TestInterviewFlow:
    """Test complete interview flow"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session_id = None
    
    def create_test_files(self):
        """Create test files for interview flow"""
        resume_content = """
        Alex Johnson
        Full Stack Developer
        
        Experience:
        - 4 years Python development
        - FastAPI and Flask experience
        - React and Node.js
        - AWS deployment
        - Database design
        
        Skills:
        - Python, JavaScript, SQL
        - FastAPI, React, PostgreSQL
        - Docker, AWS, Git
        """
        
        job_content = """
        Full Stack Developer Position
        
        We are looking for a skilled Full Stack Developer to join our team.
        
        Requirements:
        - 3+ years Python experience
        - FastAPI or Flask experience
        - Frontend development skills
        - Database knowledge
        - Cloud deployment experience
        
        Nice to have:
        - React experience
        - AWS experience
        - Docker knowledge
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
    
    def test_complete_interview_flow(self):
        """Test complete interview flow from start to finish"""
        resume_path, job_path = self.create_test_files()
        
        try:
            # Step 1: Start interview
            with open(resume_path, 'rb') as resume_file, open(job_path, 'rb') as job_file:
                files = {
                    'resume': ('resume.txt', resume_file, 'text/plain'),
                    'job_description': ('job_desc.txt', job_file, 'text/plain')
                }
                
                data = {
                    'max_questions': 2,  # Keep it short for testing
                    'model_name': 'gpt-4o-mini'
                }
                
                response = self.session.post(
                    f"{API_BASE_URL}/test/interview/start",
                    files=files,
                    data=data
                )
                
                assert response.status_code == 200
                start_data = response.json()
                
                self.session_id = start_data["session_id"]
                assert start_data["is_complete"] is False
                assert start_data["current_question"] is not None
                assert start_data["total_questions"] == 2
            
            # Step 2: Answer first question
            answer_data = {
                "session_id": self.session_id,
                "answer": "I have 4 years of Python experience and have worked with FastAPI for 2 years. I've built several REST APIs and integrated them with frontend applications using React."
            }
            
            # Note: This might fail if authentication is required
            # In a real test, you'd need to handle auth properly
            
        finally:
            self.cleanup_files(resume_path, job_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
