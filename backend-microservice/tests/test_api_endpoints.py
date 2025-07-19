"""
Comprehensive Test Suite for AI Interview Assistant API
Tests all endpoints including auth, interview flow, and admin endpoints
"""

import pytest
import requests
import json
import os
import tempfile
from typing import Dict, Any
from pathlib import Path
import time

class APITestSuite:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.auth_token = None
        self.test_session_id = None
        self.test_user_email = "test.user@example.com"
        self.test_user_password = "testpassword123"
        self.test_user_name = "Test User"
        
        # Test data paths
        self.test_resume_path = "data/resumes/resume.pdf"
        self.test_job_desc_path = "data/job_descriptions/job_desc.txt"
        
    def setup_test_files(self):
        """Create test files for upload"""
        # Create test resume content
        test_resume_content = """
        John Doe
        Software Engineer
        
        Experience:
        - 5 years Python development
        - FastAPI and Django experience
        - Machine Learning projects
        - AWS cloud deployment
        
        Skills:
        - Python, JavaScript, SQL
        - FastAPI, React, PostgreSQL
        - Docker, Kubernetes
        - OpenAI API integration
        """
        
        # Create test job description content
        test_job_content = """
        Senior Python Developer - AI/ML Focus
        
        Requirements:
        - 3+ years Python experience
        - FastAPI framework experience
        - Machine Learning knowledge
        - API development skills
        - Cloud deployment experience
        
        Responsibilities:
        - Build AI-powered applications
        - Develop REST APIs
        - Integrate with ML models
        - Deploy to cloud platforms
        """
        
        # Create temporary files
        self.temp_resume = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        self.temp_resume.write(test_resume_content)
        self.temp_resume.close()
        
        self.temp_job_desc = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        self.temp_job_desc.write(test_job_content)
        self.temp_job_desc.close()
        
        return self.temp_resume.name, self.temp_job_desc.name
    
    def cleanup_test_files(self):
        """Clean up temporary test files"""
        try:
            os.unlink(self.temp_resume.name)
            os.unlink(self.temp_job_desc.name)
        except:
            pass
    
    def test_health_check(self):
        """Test health check endpoint"""
        print("🔍 Testing health check endpoint...")
        response = self.session.get(f"{self.base_url}/health")
        
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        data = response.json()
        assert "status" in data and data["status"] == "healthy"
        assert "timestamp" in data
        
        print("✅ Health check passed")
        return True
    
    def test_admin_health(self):
        """Test admin health check endpoint"""
        print("🔍 Testing admin health check endpoint...")
        response = self.session.get(f"{self.base_url}/admin/health")
        
        assert response.status_code == 200, f"Admin health check failed: {response.status_code}"
        data = response.json()
        assert "api_status" in data and data["api_status"] == "healthy"
        assert "database_status" in data
        assert "timestamp" in data
        
        print("✅ Admin health check passed")
        return True
    
    def test_signup(self):
        """Test user signup endpoint"""
        print("🔍 Testing user signup...")
        
        signup_data = {
            "email": self.test_user_email,
            "password": self.test_user_password,
            "full_name": self.test_user_name
        }
        
        response = self.session.post(
            f"{self.base_url}/auth/signup",
            json=signup_data
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "message" in data
            assert "user" in data
            print("✅ Signup successful")
            return True
        else:
            print(f"⚠️  Signup failed: {response.status_code} - {response.text}")
            return False
    
    def test_signin(self):
        """Test user signin endpoint"""
        print("🔍 Testing user signin...")
        
        signin_data = {
            "email": self.test_user_email,
            "password": self.test_user_password
        }
        
        response = self.session.post(
            f"{self.base_url}/auth/signin",
            json=signin_data
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "message" in data
            assert "user" in data
            
            # Extract token if available
            if "access_token" in data:
                self.auth_token = data["access_token"]
                self.session.headers.update({
                    "Authorization": f"Bearer {self.auth_token}"
                })
            
            print("✅ Signin successful")
            return True
        else:
            print(f"⚠️  Signin failed: {response.status_code} - {response.text}")
            return False
    
    def test_interview_start_no_auth(self):
        """Test interview start endpoint without authentication"""
        print("🔍 Testing interview start (no auth)...")
        
        resume_path, job_desc_path = self.setup_test_files()
        
        try:
            with open(resume_path, 'rb') as resume_file, open(job_desc_path, 'rb') as job_file:
                files = {
                    'resume': ('resume.txt', resume_file, 'text/plain'),
                    'job_description': ('job_desc.txt', job_file, 'text/plain')
                }
                
                data = {
                    'max_questions': 3,
                    'model_name': 'gpt-4.1-nano-2025-04-14'
                }
                
                response = self.session.post(
                    f"{self.base_url}/test/interview/start",
                    files=files,
                    data=data
                )
                
                if response.status_code == 200:
                    data = response.json()
                    assert "session_id" in data
                    assert "current_question" in data
                    assert "is_complete" in data
                    assert "current_question_idx" in data
                    assert "total_questions" in data
                    
                    self.test_session_id = data["session_id"]
                    print(f"✅ Interview start successful - Session ID: {self.test_session_id}")
                    print(f"📝 First question: {data['current_question']}")
                    return True
                else:
                    print(f"❌ Interview start failed: {response.status_code} - {response.text}")
                    return False
                    
        finally:
            self.cleanup_test_files()
    
    def test_interview_start_with_auth(self):
        """Test interview start endpoint with authentication"""
        print("🔍 Testing interview start (with auth)...")
        
        if not self.auth_token:
            print("⚠️  No auth token available, skipping authenticated test")
            return False
        
        resume_path, job_desc_path = self.setup_test_files()
        
        try:
            with open(resume_path, 'rb') as resume_file, open(job_desc_path, 'rb') as job_file:
                files = {
                    'resume': ('resume.txt', resume_file, 'text/plain'),
                    'job_description': ('job_desc.txt', job_file, 'text/plain')
                }
                
                # Include config in request body
                request_data = {
                    "config": {
                        "max_questions": 3,
                        "model_name": "gpt-4.1-nano-2025-04-14",
                        "temperature": 0.3
                    }
                }
                
                response = self.session.post(
                    f"{self.base_url}/interview/start",
                    files=files,
                    data={"request": json.dumps(request_data)}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    assert "session_id" in data
                    assert "current_question" in data
                    print("✅ Authenticated interview start successful")
                    return True
                else:
                    print(f"❌ Authenticated interview start failed: {response.status_code} - {response.text}")
                    return False
                    
        finally:
            self.cleanup_test_files()
    
    def test_submit_answer(self):
        """Test answer submission endpoint"""
        print("🔍 Testing answer submission...")
        
        if not self.test_session_id:
            print("⚠️  No session ID available, skipping answer test")
            return False
        
        answer_data = {
            "session_id": self.test_session_id,
            "answer": "I have 5 years of experience with Python and have worked extensively with FastAPI. I've built several REST APIs and integrated them with machine learning models. I'm also experienced with cloud deployment using AWS."
        }
        
        response = self.session.post(
            f"{self.base_url}/interview/answer",
            json=answer_data
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "session_id" in data
            assert "score" in data
            assert "analysis" in data
            assert "is_complete" in data
            
            print(f"✅ Answer submitted successfully - Score: {data.get('score', 'N/A')}")
            print(f"📊 Analysis: {data.get('analysis', 'N/A')[:100]}...")
            return True
        else:
            print(f"❌ Answer submission failed: {response.status_code} - {response.text}")
            return False
    
    def test_get_sessions(self):
        """Test get user sessions endpoint"""
        print("🔍 Testing get user sessions...")
        
        if not self.auth_token:
            print("⚠️  No auth token available, skipping sessions test")
            return False
        
        response = self.session.get(f"{self.base_url}/interview/sessions")
        
        if response.status_code == 200:
            data = response.json()
            assert "sessions" in data
            print(f"✅ Sessions retrieved - Count: {len(data.get('sessions', []))}")
            return True
        else:
            print(f"❌ Get sessions failed: {response.status_code} - {response.text}")
            return False
    
    def test_get_reports(self):
        """Test get user reports endpoint"""
        print("🔍 Testing get user reports...")
        
        if not self.auth_token:
            print("⚠️  No auth token available, skipping reports test")
            return False
        
        response = self.session.get(f"{self.base_url}/reports")
        
        if response.status_code == 200:
            data = response.json()
            assert "reports" in data
            print(f"✅ Reports retrieved - Count: {len(data.get('reports', []))}")
            return True
        else:
            print(f"❌ Get reports failed: {response.status_code} - {response.text}")
            return False
    
    def test_get_dashboard_stats(self):
        """Test get dashboard stats endpoint"""
        print("🔍 Testing get dashboard stats...")
        
        if not self.auth_token:
            print("⚠️  No auth token available, skipping dashboard stats test")
            return False
        
        response = self.session.get(f"{self.base_url}/dashboard/stats")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Dashboard stats retrieved")
            return True
        else:
            print(f"❌ Get dashboard stats failed: {response.status_code} - {response.text}")
            return False
    
    def test_get_interview_report(self):
        """Test get interview report endpoint"""
        print("🔍 Testing get interview report...")
        
        if not self.test_session_id or not self.auth_token:
            print("⚠️  No session ID or auth token available, skipping report test")
            return False
        
        response = self.session.get(f"{self.base_url}/interview/{self.test_session_id}/report")
        
        if response.status_code == 200:
            data = response.json()
            assert "content" in data
            assert "session_id" in data
            print("✅ Interview report retrieved")
            return True
        else:
            print(f"❌ Get interview report failed: {response.status_code} - {response.text}")
            return False
    
    def test_signout(self):
        """Test user signout endpoint"""
        print("🔍 Testing user signout...")
        
        if not self.auth_token:
            print("⚠️  No auth token available, skipping signout test")
            return False
        
        response = self.session.post(f"{self.base_url}/auth/signout")
        
        if response.status_code == 200:
            data = response.json()
            assert "message" in data
            print("✅ Signout successful")
            return True
        else:
            print(f"❌ Signout failed: {response.status_code} - {response.text}")
            return False
    
    def run_all_tests(self):
        """Run all API tests"""
        print("AI Interview Assistant API Test Suite")
        print("=" * 50)
        print(f"Testing API at: {self.base_url}")
        print("Make sure the API is running before executing tests")
        print()
        
        test_results = {}
        
        # Basic health checks
        test_results["health_check"] = self.test_health_check()
        test_results["admin_health"] = self.test_admin_health()
        
        # Authentication tests
        test_results["signup"] = self.test_signup()
        test_results["signin"] = self.test_signin()
        
        # Interview flow tests
        test_results["interview_start_no_auth"] = self.test_interview_start_no_auth()
        test_results["interview_start_with_auth"] = self.test_interview_start_with_auth()
        test_results["submit_answer"] = self.test_submit_answer()
        
        # Data retrieval tests
        test_results["get_sessions"] = self.test_get_sessions()
        test_results["get_reports"] = self.test_get_reports()
        test_results["get_dashboard_stats"] = self.test_get_dashboard_stats()
        test_results["get_interview_report"] = self.test_get_interview_report()
        
        # Cleanup
        test_results["signout"] = self.test_signout()
        
        # Summary
        print("\n" + "=" * 50)
        print("📊 Test Results Summary:")
        print("=" * 50)
        
        passed = sum(1 for result in test_results.values() if result)
        total = len(test_results)
        
        for test_name, result in test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{test_name:<25} {status}")
        
        print(f"\nOverall: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All tests passed!")
        else:
            print("⚠️  Some tests failed. Check the logs above for details.")
        
        return test_results


def main():
    """Main function to run the test suite"""
    import argparse
    
    parser = argparse.ArgumentParser(description="AI Interview Assistant API Test Suite")
    parser.add_argument(
        "--url", 
        default="http://localhost:8000",
        help="Base URL for the API (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--test",
        choices=[
            "health", "admin_health", "signup", "signin", "interview_start", 
            "submit_answer", "sessions", "reports", "dashboard", "report", "signout", "all"
        ],
        default="all",
        help="Specific test to run (default: all)"
    )
    
    args = parser.parse_args()
    
    # Create test suite
    test_suite = APITestSuite(base_url=args.url)
    
    # Run specific test or all tests
    if args.test == "all":
        test_suite.run_all_tests()
    else:
        # Run specific test
        test_method = f"test_{args.test}"
        if hasattr(test_suite, test_method):
            getattr(test_suite, test_method)()
        else:
            print(f"Test method {test_method} not found")


if __name__ == "__main__":
    main()
