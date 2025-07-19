# AI Interview Assistant Backend Microservice

A FastAPI-based backend microservice for the AI Interview Assistant application.

## Features

- **FastAPI Framework**: High-performance async API with automatic OpenAPI documentation
- **AI-Powered Interviews**: Uses OpenAI models for intelligent interview questioning
- **Vector Search**: FAISS-based semantic search for context-aware questions
- **Database Integration**: Supabase for user management and data persistence
- **Authentication**: JWT-based authentication with Supabase Auth
- **File Upload**: Support for resume and job description uploads
- **Real-time Processing**: Streaming responses for better user experience

## Project Structure

```
backend-microservice/
├── app/
│   ├── api/                 # API route handlers
│   ├── core/                # Core configuration
│   ├── database/            # Database connections and models
│   ├── models/              # Pydantic models
│   ├── services/            # Business logic services
│   ├── utils/               # Utility functions
│   └── server.py            # FastAPI application
├── data/                    # Data storage
│   ├── resumes/            # Resume uploads
│   └── job_descriptions/   # Job description uploads
├── vector_stores/          # Vector database storage
├── logs/                   # Application logs
├── reports/               # Generated reports
├── tests/                 # Unit tests
├── Dockerfile             # Docker configuration
├── docker-compose.yml     # Docker compose configuration
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## Quick Start

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- OpenAI API key
- Supabase project credentials

### Environment Variables

Create a `.env` file in the root directory:

```bash
# Environment
ENVIRONMENT=development
DEBUG=true
HOST=0.0.0.0
PORT=8000

# Security
SECRET_KEY=your-secret-key-here

# Database (Supabase)
SUPABASE_URL=your-supabase-url
SUPABASE_ANON_KEY=your-supabase-anon-key
SUPABASE_SERVICE_KEY=your-supabase-service-key

# AI/ML
OPENAI_API_KEY=your-openai-api-key
DEFAULT_MODEL=gpt-4.1-nano-2025-04-14

# Interview Configuration
MAX_QUESTIONS=5
CHUNK_SIZE=800
CHUNK_OVERLAP=150
RAG_K_RESULTS=3
TEMPERATURE=0.3
```

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd backend-microservice
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run with Docker**
   ```bash
   docker-compose up --build
   ```

4. **Or run directly**
   ```bash
   uvicorn app.server:app --host 0.0.0.0 --port 8000 --reload
   ```

### API Documentation

Once the server is running, access the API documentation at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### Authentication
- `POST /api/v1/auth/signup` - Register new user
- `POST /api/v1/auth/signin` - User login
- `POST /api/v1/auth/signout` - User logout

### Interview Management
- `POST /api/v1/interview/start` - Start new interview session
- `POST /api/v1/interview/answer` - Submit answer to current question
- `GET /api/v1/interview/{session_id}/report` - Get interview report
- `GET /api/v1/interview/sessions` - Get user's interview sessions

### Test Endpoints (Development)
- `POST /test/interview/start` - Start interview without authentication
- `POST /test/interview/answer` - Submit answer without authentication

### Utility
- `GET /health` - Health check endpoint
- `GET /admin/health` - Admin health check with database status

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_interview.py

# Run with coverage
pytest --cov=app tests/
```

### Code Quality

```bash
# Format code
black app/

# Lint code
flake8 app/

# Type checking
mypy app/
```

### Database Setup

The application uses Supabase for data persistence. Make sure you have:
1. Created a Supabase project
2. Set up the required tables (users, interview_sessions, reports)
3. Configured the environment variables

## Deployment

### Docker Deployment

```bash
# Build and run
docker-compose up --build -d

# View logs
docker-compose logs -f backend

# Stop services
docker-compose down
```

### Production Considerations

- Set `ENVIRONMENT=production` and `DEBUG=false`
- Use proper secret keys
- Configure CORS origins for your frontend domain
- Set up proper logging and monitoring
- Use a reverse proxy (nginx) for SSL termination
- Consider using a managed database service

## Architecture

The backend follows a clean architecture pattern:

1. **API Layer** (`app/api/`): FastAPI route handlers
2. **Service Layer** (`app/services/`): Business logic
3. **Data Layer** (`app/database/`): Database operations
4. **Models** (`app/models/`): Data structures
5. **Utils** (`app/utils/`): Utility functions

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run tests and ensure they pass
6. Submit a pull request

## License

This project is licensed under the MIT License.
