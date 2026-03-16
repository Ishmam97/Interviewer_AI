# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Interview Assistant — a full-stack app for AI-driven mock interviews. Users upload a resume and job description, then conduct an interview with AI-generated, RAG-contextualized questions. Responses are scored and a final report is generated.

## Repository Structure

```
interviewer/
├── frontend/               # React + Vite + TypeScript SPA
├── backend-microservice/   # FastAPI backend (Docker, Firebase auth + Firestore + Gemini)
├── docker-compose.yml      # Runs both services locally
├── firestore.rules         # Firestore security rules
├── vector_stores/          # FAISS index (shared via Docker volume)
├── interview_sessions/     # Session data (shared via Docker volume)
└── reports/                # Generated reports (shared via Docker volume)
```

## Development Commands

### Run with Docker (recommended)
```bash
docker-compose up --build
# Backend: http://localhost:8000
# Frontend: http://localhost:8080
```

### Frontend (standalone)
```bash
cd frontend
npm install
npm run dev          # Dev server on http://localhost:8080
npm run build        # Production build
npm run lint         # ESLint
```

### Backend Microservice (standalone)
```bash
cd backend-microservice
pip install -r requirements.txt
# Requires .env with OPENAI_API_KEY, FIREBASE_API_KEY, FIREBASE_SERVICE_ACCOUNT_PATH
uvicorn app.server:app --host 0.0.0.0 --port 8000 --reload
```

### Firebase Functions (alternative deploy)
```bash
cd backend
firebase emulators:start   # Local emulators on ports 5001, 8080, 9099, 4000
```

### Backend tests
```bash
cd backend-microservice
pytest tests/
```

## Architecture

### Request Flow
1. Frontend (`frontend/src/services/api.js`) makes REST calls to `http://localhost:8000`
2. Firebase ID token (obtained at sign-in) is stored in `localStorage` and sent as `Authorization: Bearer <token>`
3. FastAPI verifies the token via `firebase_admin.auth.verify_id_token()` (`ENVIRONMENT=development` + token `dummy-token` bypasses this)
4. Active interview sessions live in the in-memory `_active_sessions` dict in `app/server.py` and are synced to Firestore; if a request lands on a different instance the session is reconstructed from Firestore

### Backend Microservice (`backend-microservice/app/`)
- **`server.py`** — FastAPI app, all route definitions, session management, Firebase auth middleware
- **`core/config.py`** — Pydantic settings loaded from `.env`
- **`database/firebase_db.py`** — `FirebaseManager`: all Firebase Auth and Firestore operations
- **`services/interview_system.py`** — Orchestrates all AI components
- **`services/document_processor.py`** — Parses PDF/TXT resumes and job descriptions
- **`services/rag_system.py`** — FAISS vector store for RAG context retrieval
- **`services/interview_planner.py`** — Generates interview question plans via LLM
- **`services/response_analyzer.py`** — Scores and analyzes candidate answers
- **`services/report_generator.py`** — Produces final interview report
- **`services/workflow_manager.py`** — LangGraph workflow connecting all steps

### Frontend (`frontend/src/`)
- **`pages/Index.tsx`** — Root page; manages auth state, section routing, interview setup
- **`services/api.js`** — `ApiService` class wrapping all backend REST calls (singleton `apiService`)
- **`components/InterviewInterface.tsx`** — Live interview Q&A UI
- **`components/Dashboard.tsx`** — Session history and reports
- **`components/AuthForm.tsx`** — Sign-up / sign-in form
- **`components/FileUpload.tsx`** — Resume and job description upload
- UI components are shadcn/ui under `components/ui/`

### AI Pipeline
- **LLM**: OpenAI (`gpt-4.1-nano-2025-04-14` default); can be swapped to Ollama via `use_ollama` flag in `interview_system.py`
- **Embeddings**: `text-embedding-3-small` (OpenAI) or Ollama `granite-embedding:30m`
- **`OPENAI_BASE_URL`**: optional override (e.g. `https://api.aimlapi.com/v1`) passed through to both LLM and embeddings
- **Vector store**: FAISS index at `./vector_stores/interview_faiss_index` (mounted as Docker volume)
- **Workflow**: LangGraph manages state transitions between document processing → planning → Q&A → report generation
- Report generation runs **synchronously** at interview completion (not as a background task, for Cloud Functions compatibility)

### Firebase / Firestore Collections
- `profiles` — user profile data (doc ID = Firebase UID)
- `user_settings` — per-user model/interview config (doc ID = Firebase UID)
- `interview_sessions` — session state, conversation history, scores, final report
- `interview_reports` — completed report records

## Environment Variables

Backend `.env` (at `backend-microservice/.env`):
```
OPENAI_API_KEY=
FIREBASE_PROJECT_ID=interviewer-ea164
FIREBASE_API_KEY=FIREBASE_API_KEY_PLACEHOLDER
FIREBASE_SERVICE_ACCOUNT_PATH=./firebase-service-account.json
ENVIRONMENT=development   # set to "production" to enforce token verification
DEBUG=false
```

Firebase config (project `interviewer-ea164`):
- authDomain: `interviewer-ea164.firebaseapp.com`
- storageBucket: `interviewer-ea164.firebasestorage.app`
- appId: `1:452095792083:web:3337139b726fa56164d526`

## Key Implementation Notes

- **Auth in dev**: `ENVIRONMENT=development` + token `dummy-token` returns a hardcoded mock user. In production, `firebase_admin.auth.verify_id_token()` validates the Firebase ID token.
- **Service account**: `firebase-service-account.json` must exist at `backend-microservice/firebase-service-account.json` (never commit it). Falls back to Application Default Credentials if missing.
- **Sign-up flow**: Backend creates the Firebase Auth user, then calls the Firebase Identity Toolkit REST API to exchange the custom token for a real ID token, which is returned in `session.access_token`.
- **Session persistence**: Sessions are written to Firestore *before* being cached in memory. If the session is not in the in-memory cache, `_reconstruct_session()` rebuilds state from Firestore (without the FAISS index).
- **FAISS index**: Rebuilt from uploaded documents at interview start; persisted across Docker restarts via volume mount.
- **Test endpoints**: `/test/interview/start` and `/test/interview/answer` skip auth for development use.
- **Frontend routing**: All navigation is state-based inside `Index.tsx` (`activeSection`), not URL-based; React Router only has the root and 404 routes.
