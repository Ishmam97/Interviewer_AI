# Interviewer AI — Full Product & Implementation Spec

Last updated: 2025-11-16

## Overview

Interviewer AI is a web app for AI-driven mock interviews. It provides:

- User authentication via Supabase Auth
- Resume and job description ingestion
- Dynamic interview flow with AI-generated questions and real-time scoring
- Persistent session storage in Supabase
- Single-source-of-truth report object per session with update semantics
- Dashboard to review sessions and open full reports
- Dockerized frontend and backend services

This spec documents the implemented features across frontend and backend, the current behavior, key data flows, file locations, and notable implementation details.

---

## Architecture

- Frontend: React/Next (project `frontend/`), components for Auth, Dashboard, and Full Report viewer
- Backend: FastAPI app in `backend-microservice/app/server.py`
- Data store: Supabase (PostgREST) for auth and persistence
- AI: OpenAI Chat Completions for content generation/scoring
- Vector search: FAISS index under `vector_stores/`
- Containers: Docker + docker-compose to run frontend and backend services

Data flow at a glance:

1. User authenticates; frontend stores JWT (Supabase access token)
2. User uploads resume/JD and starts interview -> backend creates session in DB and returns first question
3. User answers questions -> backend analyzes, updates progress in DB, returns next question
4. On completion, backend generates the final report and upserts it in Supabase (asynchronously)
5. Dashboard lists sessions; "View Report" opens a modal with the full report text

---

## Backend (FastAPI)

Location: `backend-microservice/app/server.py`

### Key Routes (public contract)

- GET `/health` — Health check (no auth)
- POST `/interview/start` — Start a new interview session (auth)
- POST `/interview/answer` — Submit answer, get next question (auth)
- GET `/interview/{session_id}/report` — Get final report; generates if session active, otherwise fetches latest saved (auth)
- GET `/interview/sessions` — Return user’s sessions (auth)

Note: Some documentation references `/api/v1/...`; the current implementation uses the unprefixed paths shown above in `server.py`.

### Authentication

- Dependency `get_current_user` reads `Authorization: Bearer <token>`
- Token is a Supabase JWT (access_token). The backend does light validation and associates requests with `user_id` via the token’s `sub`/`id` claim.

### Interview lifecycle

- Session store: In-memory `active_sessions` map with per-session state and `interview_system` instance
- DB persistence: Supabase table `interview_sessions` holds durable state

#### Start: `POST /interview/start`
- Validates user and inputs (resume, job description; multipart form)
- Creates the session immediately in DB (source of truth)
- Initializes in-memory state
- Returns: `session_id`, `first_question`, and configuration echoes

Files involved:
- `backend-microservice/app/server.py` (route logic)
- `backend-microservice/app/database/supabase.py` (session creation)

#### Answer: `POST /interview/answer`
- Processes the latest answer via `interview_system.process_candidate_answer`
- Updates `current_question_idx`, calculates `progress` and persists to DB via `supabase_manager.update_interview_session`
- Returns: `{ session_id, next_question, score, analysis, is_complete }`
- When `is_complete == true`:
  - Uses FastAPI `BackgroundTasks` to:
    - Call `interview_system.generate_final_report`
    - Compute overall score from notes
    - Persist final session fields and report to Supabase
    - Save/update a single report record via `save_interview_report` (see below)

Files involved:
- `backend-microservice/app/server.py` (route + BackgroundTasks)
- `backend-microservice/app/core/...` (interview logic: planner, analyzer; see `src/` in root for core logic if re-used)
- `backend-microservice/app/database/supabase.py` (session update)

#### Report: `GET /interview/{session_id}/report`
- If session is still active in memory:
  - Generates a fresh final report, saves/updates in DB, returns `{report_id, content, session_id}`
- If session not active (e.g., server restart, user refreshed page):
  - Fetches the most recent saved report from `interview_reports` by `(user_id, session_id)`
  - Returns `{report_id, content, session_id}` or 404 if none found

Files involved:
- `backend-microservice/app/server.py` (route logic and Supabase fallback fetch)

### Supabase Integration

Location: `backend-microservice/app/database/supabase.py`

Core operations:

- `create_interview_session(user_id, payload)` — Inserts into `interview_sessions`
- `get_interview_session(session_id)` — Loads a single session
- `update_interview_session(session_id, update_fields, user_id)` — PATCH on `interview_sessions` with fallback safeguards
- `save_interview_report(user_id, session_id, report_data)` — Upsert-like behavior:
  - Validates session existence and non-empty report content
  - Queries `interview_reports` for existing `{user_id, session_id}`
  - If found, `UPDATE` existing record; else `INSERT`
  - Returns the report id

Important note: Report is single-source-of-truth per session. The function ensures updates instead of creating duplicates, matching the product requirement.

### Logging & Observability

- Middleware logs: method, URL, auth header presence, response status
- Route-level logs for session updates, question generation, report generation and persistence
- Frontend debug logs were pruned for production signal-to-noise improvements (see Frontend section)

### Async processing

- Final report generation and persistence are scheduled with `BackgroundTasks` from `fastapi`
- This ensures the frontend loading animation is displayed while the backend computes and persists the report, improving perceived performance
- For production-grade workloads, consider a task queue (Celery, RQ) for retries and durability

---

## Database (Supabase)

Tables (as used by the app):

- `profiles`: Basic user profile
- `user_settings`: Preferences (max questions, model, temperature, etc.)
- `interview_sessions`: Persistent session data (JSONB for plan/notes/history)
  - Columns include: `id`, `user_id`, `title`, `status`, `interview_plan` (JSONB), `current_question_idx`, `interview_notes` (JSONB), `conversation_history` (JSONB), `resume_content`, `job_description`, `total_questions`, `average_score`, `final_report`, timestamps
- `interview_reports`: One report per `(user_id, session_id)`
  - Columns: `id`, `user_id`, `session_id`, `title`, `report_content` (TEXT), `summary` (JSONB), `scores` (JSONB), `recommendations` (TEXT), timestamps

Key behaviors implemented:

- Session-first persistence: sessions are created in DB before in-memory lifecycle proceeds
- Idempotent report saves: first fetch existing, then update or insert
- Session progress updates on each answer; final session update on completion includes averages and notes

Suggested indexes (if not already present):

- On `interview_reports (user_id, session_id) UNIQUE`
- On `interview_sessions (user_id, created_at)` for listing

---

## Frontend

Location: `frontend/`

### Major components

- `src/components/AuthForm.tsx` — Sign-in/Sign-up UI, interacts with backend auth endpoints; stores JWT on success
- `src/components/Dashboard.tsx` — Unified Sessions view (Reports tab removed)
  - Lists interview sessions
  - For completed sessions shows a “View Report” button
  - Clicking opens the `FullReportViewer` modal
- `src/components/FullReportViewer.tsx` — Displays full report content (uses `content` field from backend payload)

### API client

- `src/services/api.js`
  - `getAuthHeaders()` and `getAuthHeadersForFormData()` handle JWT header
  - `startInterview(resumeFile, jobDescriptionFile, config)` — multipart upload, relies on browser-set boundary; no manual `Content-Type`
  - `submitAnswer(sessionId, answer)` — posts answer, receives next question and interim scores
  - `getInterviewReport(sessionId)` — returns `{ report_id, content, session_id }`
  - `validateToken()` — verifies session with backend and keeps JWT fresh
  - Extraneous `console.log` noise removed for production readiness; only essential errors remain

### UX and state

- Interview flow presents one question at a time with immediate scoring feedback
- On completing the last question:
  - Backend kicks off report generation in the background
  - Frontend shows completion animation/loading while the report is being generated and persisted
- The Dashboard no longer has a separate Reports tab; the sessions table includes a “View Report” button for each completed session
- The Full report modal reads `reportData={selectedReport.content}` — ensuring correct field mapping

---

## Vector Store & RAG

- FAISS index lives under `vector_stores/interview_faiss_index/`
- The backend uses this for context retrieval when forming questions and analyses
- The index can be rebuilt (see root `README.md` and CLI tools, if used)

---

## Deployment & Operations

### Docker

- Backend image: `interviewer-backend` built from `backend-microservice/Dockerfile`
- Frontend image: `interviewer-frontend` built from `frontend/Dockerfile.dev`
- `docker-compose.yml` at repo root orchestrates both services
- Common issue: `Bind for 0.0.0.0:8000 failed: port is already allocated`
  - Ensure port 8000 is free (`lsof -i :8000`)
  - Or change host port mapping in compose for backend (e.g., `8001:8000`) and update frontend API base URL
- Compose warning: `version` field is obsolete; safe to remove

### Environment variables

Back-end `.env` (see `backend-microservice/README.md`):
- OpenAI keys, Supabase URL/keys, default model, interview parameters

### Health endpoints

- `GET /health` — returns 200 when app is up
- `GET /admin/health` (if present in codebase) — includes DB checks

---

## API Contracts (current)

### Start Interview

Request (multipart/form-data)
```
resume: file | text (optional)
job_description: file | text (optional)
max_questions: number
model_name: string
temperature: number
```

Response
```json
{
  "session_id": "uuid",
  "first_question": "string",
  "total_questions": 5
}
```

### Submit Answer

Request
```json
{
  "session_id": "uuid",
  "answer": "string"
}
```

Response
```json
{
  "session_id": "uuid",
  "next_question": "string | null",
  "score": 0,
  "analysis": "string",
  "is_complete": false
}
```

### Get Report

Response
```json
{
  "report_id": "uuid",
  "session_id": "uuid",
  "content": "markdown/text of the final report"
}
```

---

## Notable Implementation Decisions

- Single report per session: enforced in `save_interview_report` by checking existing records and updating instead of inserting
- Asynchronous finalization: BackgroundTasks so users see a loading animation while the heavy work finishes
- Resilience to restarts: Report endpoint fetches last saved report when in-memory session is gone
- Reduced frontend console noise: production-friendly logs

---

## Known Gaps & Next Steps

- Consistency of route prefix (`/api/v1`) vs root paths: standardize and add a global `API_PREFIX`
- Task execution reliability: consider Celery/RQ + Redis for retries and monitoring
- DB schema hardening: add constraints/unique index on `(user_id, session_id)` in `interview_reports`
- Pagination/filters on sessions endpoint for large histories
- Role-based access checks on all resources (defense-in-depth)
- Expand unit/integration test coverage (see `backend-microservice/tests/` scaffold)

---

## File Map (primary)

- Backend
  - `backend-microservice/app/server.py` — FastAPI app and routes
  - `backend-microservice/app/database/supabase.py` — Supabase client helpers
  - `backend-microservice/app/models/` — Pydantic schemas
  - `backend-microservice/app/services/` — Business logic (interview, RAG, scoring)
- Frontend
  - `frontend/src/components/AuthForm.tsx` — Auth UI
  - `frontend/src/components/Dashboard.tsx` — Sessions list with View Report
  - `frontend/src/components/FullReportViewer.tsx` — Report modal
  - `frontend/src/services/api.js` — API client
- Shared / Assets
  - `vector_stores/interview_faiss_index/` — FAISS data
  - `reports/` — Generated local reports (if persisted to disk during dev)

---

## Changelog (recent highlights)

- Ensure report upsert: `save_interview_report` now updates existing reports instead of duplicating
- Async report generation on completion via `BackgroundTasks`
- `AnalysisResponse` includes `session_id` to match frontend expectations
- `GET /interview/{session_id}/report` gracefully fetches most recent saved report when session isn’t active
- Frontend Dashboard: removed Reports tab; added "View Report" per session; `FullReportViewer` wired to `content`
- Frontend API client: removed verbose logging; safer FormData headers

---

If you want this spec exported or versioned in a different format (PDF/HTML), we can add a simple script to automate it.
