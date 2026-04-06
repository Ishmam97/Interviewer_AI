# Interviewer AI — Project Context

## Project Overview

**Interviewer AI** is a full-stack web application that conducts AI-driven mock interviews. Users upload a resume and job description, then engage in an interactive interview session where AI-generated questions are asked, answers are scored in real time, and a comprehensive performance report is generated at the end.

The system combines:
- **Frontend**: React + Vite + TypeScript SPA with shadcn/ui components, Tailwind CSS, and React Router
- **Backend**: FastAPI microservice with Firebase Auth + Firestore and OpenAI/Gemini AI integrations
- **RAG**: FAISS vector store for Retrieval-Augmented Generation to provide context-aware questions
- **Workflow orchestration**: LangGraph manages state transitions across interview stages

A live demo is available at: https://interviewerai-ishmamdemo.streamlit.app/

---

## Repository Structure

```
Interviewer_AI/
├── frontend/                     # React + Vite + TypeScript SPA
│   ├── src/
│   │   ├── components/           # UI components (AuthForm, Dashboard, InterviewInterface, etc.)
│   │   ├── pages/                # Route pages (Index.tsx)
│   │   ├── services/             # API client (api.js), Firebase config
│   │   ├── hooks/                # Custom React hooks
│   │   └── lib/                  # Shared utilities
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   └── Dockerfile.dev
├── backend-microservice/         # FastAPI backend
│   ├── app/
│   │   ├── server.py             # FastAPI app, all route definitions
│   │   ├── core/config.py        # Pydantic settings from .env
│   │   ├── database/firebase_db.py  # Firebase Auth + Firestore operations
│   │   ├── services/             # Business logic (interview_system, document_processor, rag_system, etc.)
│   │   ├── models/               # Pydantic schemas
│   │   └── api/                  # API routers
│   ├── tests/                    # Pytest test suite
│   ├── requirements.txt
│   └── Dockerfile
├── vector_stores/                # FAISS index (Docker volume)
├── interview_sessions/           # Session data (Docker volume)
├── reports/                      # Generated reports (Docker volume)
├── docker-compose.yml            # Orchestrates frontend + backend
├── firestore.rules               # Firestore security rules
├── requirements.txt              # Root Python dependencies
└── SPEC_SHEET.md                 # Full product & implementation spec
```

---

## Architecture

### Request Flow

1. **Frontend** (`frontend/src/services/api.js`) makes REST calls to the backend at `http://localhost:8000`
2. **Firebase ID token** (obtained at sign-in) is stored in `localStorage` and sent as `Authorization: Bearer <token>`
3. **FastAPI** verifies the token via `firebase_admin.auth.verify_id_token()` (`ENVIRONMENT=development` + token `dummy-token` bypasses verification)
4. **Active interview sessions** live in the in-memory `_active_sessions` dict in `server.py` and are synced to Firestore; if a request lands on a different instance the session is reconstructed from Firestore

### AI Pipeline

| Component | Technology |
|-----------|------------|
| LLM | OpenAI (`gpt-4.1-nano-2025-04-14` default) or Gemini; swappable via `api_provider` setting |
| Embeddings | `text-embedding-3-small` (OpenAI) or Ollama `granite-embedding:30m` |
| Vector store | FAISS index at `./vector_stores/interview_faiss_index` |
| Workflow | LangGraph manages transitions: document processing → planning → Q&A → report generation |
| Report generation | Synchronous at interview completion (Cloud Functions compatibility) |

### Firebase / Firestore Collections

| Collection | Purpose | Doc ID |
|------------|---------|--------|
| `profiles` | User profile data | Firebase UID |
| `user_settings` | Per-user model/interview config | Firebase UID |
| `interview_sessions` | Session state, conversation history, scores, final report | Auto-generated |
| `interview_reports` | Completed report records | Auto-generated |

---

## Key Backend Routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Health check |
| POST | `/auth/signup` | No | Create Firebase user |
| POST | `/auth/signin` | No | Sign in user |
| GET | `/auth/me` | Yes | Get current user info |
| GET | `/profile` | Yes | Get user profile |
| PUT | `/profile` | Yes | Update profile |
| POST | `/profile/resume` | Yes | Upload resume for analysis |
| GET | `/settings` | Yes | Get user settings |
| PUT | `/settings` | Yes | Update settings (model, temperature, API key) |
| POST | `/interview/start` | Yes | Start new interview session |
| POST | `/interview/answer` | Yes | Submit answer, get next question + score |
| GET | `/interview/sessions` | Yes | List user's interview sessions |
| GET | `/interview/{session_id}/report` | Yes | Get final report |
| POST | `/interview/prepare` | Yes | Live interview via Gemini File API |
| POST | `/analyze/resume` | Yes | Analyze uploaded resume |

---

## Key Frontend Components

| File | Description |
|------|-------------|
| `src/pages/Index.tsx` | Root page; manages auth state, section routing, interview setup |
| `src/services/api.js` | `ApiService` class wrapping all backend REST calls (singleton `apiService`) |
| `src/components/InterviewInterface.tsx` | Live interview Q&A UI |
| `src/components/Dashboard.tsx` | Session history and reports |
| `src/components/AuthForm.tsx` | Sign-up / sign-in form |
| `src/components/FileUpload.tsx` | Resume and job description upload |
| `src/components/FullReportViewer.tsx` | Modal displaying full report content |

UI components use shadcn/ui under `components/ui/`.

---

## Building and Running

### With Docker (recommended)

```bash
docker-compose up --build
# Backend:  http://localhost:8000
# Frontend: http://localhost:8080
```

### Frontend (standalone)

```bash
cd frontend
npm install          # or: bun install
npm run dev          # Dev server on http://localhost:8080
npm run build        # Production build
npm run lint         # ESLint
npm test             # Vitest
```

### Backend (standalone)

```bash
cd backend-microservice
pip install -r requirements.txt
# Requires .env with OPENAI_API_KEY, FIREBASE_API_KEY, FIREBASE_SERVICE_ACCOUNT_PATH
uvicorn app.server:app --host 0.0.0.0 --port 8000 --reload
```

### Backend tests

```bash
cd backend-microservice
pytest tests/
```

---

## Environment Variables

### Backend `.env` (at `backend-microservice/.env`)

```env
OPENAI_API_KEY=
FIREBASE_PROJECT_ID=interviewer-ea164
FIREBASE_API_KEY=FIREBASE_API_KEY_PLACEHOLDER
FIREBASE_SERVICE_ACCOUNT_PATH=./firebase-service-account.json
ENVIRONMENT=development   # set to "production" to enforce token verification
DEBUG=false
```

### Firebase config (project `interviewer-ea164`)

```
authDomain: interviewer-ea164.firebaseapp.com
storageBucket: interviewer-ea164.firebasestorage.app
appId: 1:452095792083:web:3337139b726fa56164d526
```

### Frontend `.env` (at `frontend/.env`)

See `frontend/.env.example` for required variables.

---

## Important Implementation Notes

- **Auth in dev**: `ENVIRONMENT=development` + token `dummy-token` returns a hardcoded mock user. In production, `firebase_admin.auth.verify_id_token()` validates the Firebase ID token.
- **Service account**: `firebase-service-account.json` must exist at `backend-microservice/firebase-service-account.json` (never commit it). Falls back to Application Default Credentials if missing.
- **Sign-up flow**: Backend creates the Firebase Auth user, then calls the Firebase Identity Toolkit REST API to exchange the custom token for a real ID token, which is returned in `session.access_token`.
- **Session persistence**: Sessions are written to Firestore *before* being cached in memory. If the session is not in the in-memory cache, `_reconstruct_session()` rebuilds state from Firestore (without the FAISS index).
- **FAISS index**: Rebuilt from uploaded documents at interview start; persisted across Docker restarts via volume mount.
- **Frontend routing**: All navigation is state-based inside `Index.tsx` (`activeSection`), not URL-based; React Router only has the root and 404 routes.
- **Single report per session**: Enforced in `save_interview_report` by checking existing records and updating instead of inserting duplicates.
- **Async report generation**: Final report generation and persistence are scheduled with `BackgroundTasks` from FastAPI so users see a loading animation while computation finishes.
- **Port conflicts**: Common issue — `Bind for 0.0.0.0:8000 failed: port is already allocated`. Ensure port 8000 is free (`lsof -i :8000`) or change host port mapping in compose.

---

## Development Conventions

- **Python backend**: Uses Pydantic models for request/response schemas. Type hints throughout. Logging via standard `logging` module.
- **Frontend**: TypeScript with React functional components. shadcn/ui for component library. Tailwind CSS for styling. ESLint for linting. Vitest for testing.
- **API client**: Singleton `apiService` instance in `frontend/src/services/api.js`; all backend calls go through it. JWT is attached to every authenticated request.
- **Testing**: Backend uses `pytest`. Frontend uses `vitest` with `@testing-library/react`. Test files live in `backend-microservice/tests/` and `frontend/src/__tests__/`.

---

## Known Issues & Gaps

- Route prefix inconsistency: Some docs reference `/api/v1/...` but the implementation uses unprefixed paths
- Consider Celery/RQ + Redis for production-grade task queue (retries, monitoring)
- DB schema hardening: add unique constraint on `(user_id, session_id)` in `interview_reports`
- Pagination/filters needed on sessions endpoint for large histories
- Expand unit/integration test coverage
