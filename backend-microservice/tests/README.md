# API Test Suite Documentation

This directory contains comprehensive test suites for the AI Interview Assistant API.

## Test Files

### 1. `test_api_endpoints.py`
A comprehensive test suite that tests all API endpoints including:
- Health checks
- Authentication (signup, signin, signout)
- Interview flow (start, answer submission, reports)
- Data retrieval (sessions, reports, dashboard stats)

### 2. `test_api_pytest.py`
Pytest-based test suite with:
- Structured test classes
- Proper fixtures and setup/teardown
- Parameterized tests
- Integration tests
- Error handling tests

### 3. `run_api_tests.py` (in root directory)
Simple test runner script that executes the main test suite.

## Running Tests

### Option 1: Simple Test Runner
```bash
# From the project root
python run_api_tests.py
```

### Option 2: Direct Python Execution
```bash
# From the project root
python -m tests.test_api_endpoints
```

### Option 3: Pytest
```bash
# Install pytest dependencies first
pip install -r tests/requirements.txt

# Run all tests
pytest tests/test_api_pytest.py -v

# Run specific test
pytest tests/test_api_pytest.py::TestAPIEndpoints::test_health_check -v

# Run with coverage
pytest tests/test_api_pytest.py --cov=api --cov-report=html
```

### Option 4: Individual Test Methods
```bash
# Run specific tests
python -m tests.test_api_endpoints --test health
python -m tests.test_api_endpoints --test interview_start
python -m tests.test_api_endpoints --test all
```

## Test Configuration

### Environment Variables
Set these environment variables to control test behavior:

```bash
export SKIP_AUTH_TESTS=true  # Skip authentication tests if Supabase not configured
export API_BASE_URL=http://localhost:8000  # Override API URL
```

### API Server
Make sure the API server is running before executing tests:

```bash
# Start the API server
docker-compose up -d

# Or run directly
cd api && python server.py
```

## Test Coverage

The test suite covers:

### ✅ Health Endpoints
- `/health` - Basic health check
- `/admin/health` - Admin health check with database status

### ✅ Authentication Endpoints
- `/auth/signup` - User registration
- `/auth/signin` - User login
- `/auth/signout` - User logout

### ✅ Interview Endpoints
- `/test/interview/start` - Start interview (no auth)
- `/interview/start` - Start interview (with auth)
- `/interview/answer` - Submit answer
- `/interview/{session_id}/report` - Get interview report

### ✅ Data Retrieval Endpoints
- `/interview/sessions` - Get user sessions
- `/reports` - Get user reports
- `/dashboard/stats` - Get dashboard statistics

### ✅ Error Handling
- Invalid parameters
- Missing required fields
- Authentication errors
- File upload errors
- Session not found errors

## Test Data

Tests use dynamically generated test data:
- **Resume**: Realistic resume content with relevant experience
- **Job Description**: Matching job requirements
- **Answers**: Contextual responses to interview questions

## Expected Behavior

### Successful Tests
- All endpoints should return appropriate HTTP status codes
- Response data should match expected schema
- Authentication flow should work correctly
- Interview flow should progress properly

### Expected Failures (with Supabase not configured)
- Authentication endpoints may fail with 500 errors
- Authenticated endpoints will be skipped
- Database-dependent features may not work

## Debugging

### Common Issues

1. **API Not Running**
   ```
   ConnectionError: Failed to establish a new connection
   ```
   Solution: Start the API server first

2. **Authentication Failures**
   ```
   500 - Database error: Email address is invalid
   ```
   Solution: Configure Supabase or set `SKIP_AUTH_TESTS=true`

3. **File Upload Errors**
   ```
   422 - Validation error
   ```
   Solution: Check file upload format and required fields

### Debug Mode
Run tests with verbose output:
```bash
python -m tests.test_api_endpoints --url http://localhost:8000
pytest tests/test_api_pytest.py -v -s
```

## Adding New Tests

### For new endpoints:
1. Add test method to `TestAPIEndpoints` class
2. Follow naming convention: `test_<endpoint_name>`
3. Include proper assertions
4. Handle both success and failure cases

### For integration tests:
1. Add to `TestInterviewFlow` class
2. Test complete workflows
3. Include setup and teardown

### Example new test:
```python
def test_new_endpoint(self):
    """Test new endpoint"""
    response = self.session.get(f"{API_BASE_URL}/new/endpoint")
    
    assert response.status_code == 200
    data = response.json()
    assert "expected_field" in data
```

## Continuous Integration

These tests can be integrated into CI/CD pipelines:

```yaml
# GitHub Actions example
- name: Run API Tests
  run: |
    docker-compose up -d
    sleep 10  # Wait for API to start
    python run_api_tests.py
    docker-compose down
```

## Performance Testing

For performance testing, consider using:
- `pytest-benchmark` for response time testing
- `locust` for load testing
- `httpx` for async testing

## Security Testing

Additional security tests can be added for:
- SQL injection prevention
- XSS protection
- Authentication bypass attempts
- Rate limiting
- Input validation
