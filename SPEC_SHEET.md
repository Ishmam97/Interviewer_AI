# Interviewer AI — Full Product & Implementation Spec

Last updated: 2026-04-05

## Overview

Interviewer AI is a web app for AI-driven mock interviews. It provides:

- User authentication via Firebase Auth (email/password + Google OAuth)
- Resume upload, multi-step AI analysis, and an interactive suggestions system
- Dynamic interview flow with AI-generated questions and real-time scoring
- Persistent session storage in Firestore
- Single-source-of-truth report object per session with update semantics
- Dashboard to review sessions and open full reports
- Dockerized frontend and backend services

This spec documents the implemented features across frontend and backend, the current behavior, key data flows, file locations, and notable implementation details.

---

## Architecture

- Frontend: React + Vite + TypeScript SPA (`frontend/`)
- Backend: FastAPI app in `backend-microservice/app/server.py`
- Data store: Firebase Auth + Firestore for auth and persistence
- AI: OpenAI-compatible API (AIML API) for analysis; configurable `OPENAI_BASE_URL`
- Vector search: FAISS index under `vector_stores/`
- Containers: Docker + docker-compose to run frontend and backend services

Data flow at a glance:

1. User authenticates with Firebase (email/password or Google); frontend stores Firebase ID token
2. User uploads resume → async AI analysis pipeline starts (3 steps, polling for status)
3. User reviews analysis, accepts/rejects improvement suggestions → accepted suggestions trigger an AI resume edit
4. User uploads resume/JD and starts interview → backend creates session in Firestore and returns first question
5. User answers questions → backend analyzes, updates progress in Firestore, returns next question
6. On completion, backend generates the final report and persists it to Firestore (synchronously)
7. Dashboard lists sessions; "View Report" opens a modal with the full report text

---

## Backend (FastAPI)

Location: `backend-microservice/app/server.py`

### Key Routes (public contract)

#### Auth
- `POST /auth/signup` — Create Firebase user; returns Firebase ID token
- `POST /auth/signin` — Sign in with email/password via Firebase Identity Toolkit; returns ID token
- `POST /auth/google` — Exchange Firebase Google ID token for backend session; creates profile if new
- `GET /auth/validate` — Validate token and return user info

#### Profile & Resume
- `POST /profile/resume` — Upload resume; triggers async analysis pipeline; returns `{ analysis_id, status: "processing" }`
- `GET /profile/resume/analysis` — Fetch current resume analysis for the authenticated user
- `GET /resume/analysis/{analysis_id}/status` — Poll analysis progress (`status`, `current_step`)
- `POST /profile/resume/suggestions/{suggestion_id}` — Accept or reject a suggestion; accept triggers AI resume edit
- `POST /profile/resume/suggestions/{suggestion_id}/undo` — Undo an accepted suggestion, restoring the previous resume state

#### Interview
- `POST /interview/start` — Start a new interview session (auth)
- `POST /interview/answer` — Submit answer, get next question (auth)
- `GET /interview/sessions` — Return user's sessions (auth)
- `GET /interview/sessions/{session_id}` — Return single session (auth)
- `GET /interview/sessions/{session_id}/report` — Get final report; generates if session active, otherwise fetches saved (auth)

#### Settings
- `GET /settings` — Retrieve user settings
- `PUT /settings` — Update user settings

#### Misc
- `GET /health` — Health check (no auth)

### Authentication

- Dependency `get_current_user` reads `Authorization: Bearer <token>`
- Token is a Firebase ID token verified via `firebase_admin.auth.verify_id_token()`
- In `ENVIRONMENT=development`, the token `dummy-token` returns a hardcoded mock user (bypasses Firebase)
- `uid` is taken from the `uid` claim of the decoded token


### Resume Analyzer Pipeline

Location: `backend-microservice/app/services/resume_analyzer_service.py`

Resume analysis runs as a 3-step async pipeline triggered at upload and executed in a `BackgroundTask`.

#### Step 1 — Parse Document (`parsing_document`)
- Model: `openai/gpt-5-nano-2025-08-07` via AIML API
- Extracts structured JSON: `name`, `contact`, `summary`, `experience`, `education`, `skills`, `certifications`, `projects`
- Stored in `resume_parsed_sections/{analysis_id}` as `parsed_sections`

#### Step 2 — Analyze Sections (`analyzing_sections`)
- Model: `openai/gpt-5-nano-2025-08-07`
- 7 parallel LLM calls, one per section: contact, summary, experience, education, skills, certifications, projects
- Each section returns: `found`, `score` (0–100), `content_snippet`, `strengths`, `weaknesses`, `tips`, `suggestions`
- Each suggestion shape: `{ id: unique_string, text: string, status: "pending" }`

#### Step 3 — Holistic Review (`holistic_review`)
- Model: `moonshot/kimi-k2-0905-preview` via AIML API
- Returns: `overall_score`, `quality_score`, `summary`, `strengths`, `weaknesses`, `top_tips`, `lackings`
- Includes ATS analysis: `{ score, keywords_found, keywords_missing, formatting_issues }`
- Includes overall-level `suggestions` with the same `{ id, text, status }` shape

#### Status updates
- `current_step` is updated on the `resume_analyses/{analysis_id}` doc between steps
- Frontend polls `GET /resume/analysis/{analysis_id}/status` until `status == "completed"`

#### Analysis result shape
```json
{
  "overall": {
    "score": 0,
    "quality_score": 0,
    "summary": "...",
    "strengths": ["..."],
    "weaknesses": ["..."],
    "top_tips": ["..."],
    "lackings": ["..."],
    "suggestions": [{ "id": "...", "text": "...", "status": "pending" }]
  },
  "sections": [
    {
      "name": "Experience",
      "found": true,
      "score": 0,
      "content_snippet": "...",
      "strengths": ["..."],
      "weaknesses": ["..."],
      "tips": ["..."],
      "suggestions": [{ "id": "...", "text": "...", "status": "pending" }]
    }
  ],
  "ats": {
    "score": 0,
    "keywords_found": ["..."],
    "keywords_missing": ["..."],
    "formatting_issues": ["..."]
  },
  "lackings": ["..."],
  "quality_score": 0,
  "usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 }
}
```

### Suggestions Feature — Accept / Reject / Undo

Suggestions are collected from both `overall.suggestions` and each section's `suggestions` array.
Each has `status`: `"pending"` | `"accepted"` | `"rejected"`.

#### Accept: `POST /profile/resume/suggestions/{suggestion_id}` — `{ "action": "accept" }`

Backend flow:
1. Loads `resume_analyses` doc; sets suggestion `status = "accepted"`; persists to Firestore
2. Calls `_apply_suggestion_to_resume(fb, uid, suggestion_id, text, section_name)`:
   - Loads `edited_resume_data` from `profiles/{uid}`; falls back to `parsed_sections` from `resume_parsed_sections/{analysis_id}` if not yet set
   - Saves a pre-edit snapshot to `suggestion_snapshots/{uid}:{suggestion_id}` for undo
   - Calls OpenAI (`openai/gpt-4.1-mini-2025-04-14`) with the full resume JSON + suggestion text, instructing it to return updated JSON touching only relevant fields
   - Parses response; saves back to `profiles/{uid}.edited_resume_data`
   - Returns `{ section, suggestion_applied, notes_added? }`
3. Returns `{ suggestion_id, status: "accepted", applied_changes: { section, suggestion_applied } }`

Frontend behavior:
- Optimistic update to `"accepted"` immediately; reverts on failure
- Toast: "Suggestion applied to resume — view changes in Profile page"

#### Reject: `POST /profile/resume/suggestions/{suggestion_id}` — `{ "action": "reject" }`

Backend flow:
1. Sets `status = "rejected"` in Firestore; **no AI call made; resume data unchanged**
2. Returns `{ suggestion_id, status: "rejected" }`

Frontend behavior:
- Card turns red with strikethrough text; action buttons disabled

#### Undo: `POST /profile/resume/suggestions/{suggestion_id}/undo`

Backend flow:
1. Validates suggestion is currently `"accepted"` (400 if not)
2. Calls `_undo_suggestion_on_resume`:
   - Loads snapshot from `suggestion_snapshots/{uid}:{suggestion_id}`
   - Restores `profiles/{uid}.edited_resume_data` to snapshot value
   - Deletes the snapshot document (one-shot — re-accepting creates a new snapshot)
3. Sets suggestion `status = "pending"` in analysis doc
4. Returns `{ message: "Suggestion undone. Resume restored to previous state.", suggestion_id }`

Frontend behavior:
- Optimistic revert to `"pending"`; rolls back to `"accepted"` on failure with error toast

#### Key design notes
- `edited_resume_data` in `profiles/{uid}` is the **live editable resume JSON** — starts from `parsed_sections` and accumulates changes from all accepted suggestions
- Each snapshot is keyed `{uid}:{suggestion_id}`, providing one level of undo per suggestion
- Re-accepting a suggestion overwrites its existing snapshot — no multi-level undo
- Rejecting is a pure status flag; the resume data is untouched

### Interview Lifecycle

- Session store: In-memory `_active_sessions` dict with per-session `interview_system` instance
- DB persistence: Firestore collection `interview_sessions`

#### Start: `POST /interview/start`
- Validates inputs; creates session in Firestore before initializing in-memory state
- Returns: `session_id`, `first_question`, `total_questions`

#### Answer: `POST /interview/answer`
- Processes answer; updates `current_question_idx` and `progress`; persists to Firestore
- Returns: `{ session_id, next_question, score, analysis, is_complete }`
- When `is_complete == true`: generates final report **synchronously** (not via BackgroundTask) for Cloud Functions compatibility

#### Report: `GET /interview/sessions/{session_id}/report`
- Active session: generates fresh report, saves to Firestore
- Not in memory: fetches most recent saved report from `interview_reports` by `(user_id, session_id)`
- Fallback: reconstructs session from Firestore via `_reconstruct_session()` (without FAISS index)

### Logging & Observability

- COOP middleware sets `Cross-Origin-Opener-Policy: same-origin-allow-popups` on all responses (required for Google OAuth popup)
- HTTP middleware logs all requests at INFO; `/health` at DEBUG
- Resume analysis logs each step with model name, elapsed time, and token usage

---

## Database (Firestore)

Collections:

- `profiles/{uid}` — User profile, resume metadata
  - Key fields: `resume_filename`, `current_analysis_id`, `resume_summary` (name/contact/skills subset), `edited_resume_data` (full live resume JSON), `resume_updated_at`
- `user_settings/{uid}` — Per-user config: `max_questions`, `model_name`, `temperature`, etc.
- `resume_analyses/{analysis_id}` — Analysis results and suggestion statuses
  - Fields: `user_id`, `filename`, `status`, `current_step`, `overall` (scores + suggestions), `sections[]` (per-section analysis + suggestions), `ats`, `lackings`, `quality_score`, `usage`
- `resume_parsed_sections/{analysis_id}` — Raw parse output (`parsed_sections` key); fallback source for `edited_resume_data`
- `suggestion_snapshots/{uid}:{suggestion_id}` — Pre-accept resume snapshots for one-shot undo; deleted after undo
- `interview_sessions/{session_id}` — Interview state, conversation history, scores
- `interview_reports/{report_id}` — Final interview reports (one per session)

---

## Frontend

Location: `frontend/src/`

### Major components

- `src/components/AuthForm.tsx` — Sign-in/Sign-up + Google OAuth; stores Firebase ID token in `localStorage`
- `src/components/ResumeAnalyzer.tsx` — Resume upload, analysis display (tabs: Overview, Sections, Suggestions, ATS), suggestion interaction
- `src/components/Dashboard.tsx` — Interview sessions list; "View Report" opens `FullReportViewer` modal
- `src/components/FullReportViewer.tsx` — Renders full report content (`content` field)
- `src/lib/firebase.ts` — Firebase app, Auth, and `GoogleAuthProvider` initialization

### API client (`src/services/api.js`)

- `uploadResume(file)` — `POST /profile/resume` (multipart); returns `{ analysis_id, status }`
- `getResumeAnalysis()` — `GET /profile/resume/analysis`
- `getAnalysisStatus(id)` — `GET /resume/analysis/{id}/status`; used for polling
- `respondToSuggestion(id, action)` — `POST /profile/resume/suggestions/{id}` with `{ action }`
- `undoSuggestion(id)` — `POST /profile/resume/suggestions/{id}/undo`
- `startInterview(resumeFile, jdFile, config)` — multipart upload
- `submitAnswer(sessionId, answer)` — returns next question + interim scores
- `getInterviewReport(sessionId)` — returns `{ report_id, content, session_id }`

### ResumeAnalyzer UX & state

- On mount: loads existing analysis from `GET /profile/resume/analysis`; if `status == "processing"`, resumes polling via `onAnalysisStarted` callback in `Index.tsx`
- Suggestions state is a flat merged array of `overall.suggestions` + all `sections[].suggestions`, deduped by `id`
- Card borders: yellow (pending), green (accepted), red (rejected)
- Accepted cards show "Undo"; pending cards show "Accept" + "Reject"; buttons are disabled once actioned
- All suggestion actions use optimistic updates; failures roll back with an error toast

---

## Vector Store & RAG

- FAISS index lives under `vector_stores/interview_faiss_index/`
- Used for context retrieval when forming interview questions
- Rebuilt from uploaded documents at interview start; persisted via Docker volume mount

---

## Deployment & Operations

### Docker

- Backend built from `backend-microservice/Dockerfile`
- Frontend dev image from `frontend/Dockerfile.dev` (Vite dev server on port 8080)
- `docker-compose.yml` at repo root orchestrates both services
- Common issue: `Bind for 0.0.0.0:8000 failed` — run `lsof -i :8000` to find and kill occupying process

### Environment variables

Backend `.env` at `backend-microservice/.env`:
```
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.aimlapi.com/v1
FIREBASE_PROJECT_ID=interviewer-ea164
FIREBASE_API_KEY=
FIREBASE_SERVICE_ACCOUNT_PATH=./firebase-service-account.json
ENVIRONMENT=development
DEBUG=false
```

### Security

- `firebase-service-account.json` must never be committed
- COOP header `same-origin-allow-popups` set on all responses to support Google OAuth popup
- `ENVIRONMENT=development` + `dummy-token` bypasses Firebase token verification for local dev

---

## API Contracts (current)

### Upload Resume
```
POST /profile/resume  (multipart, field: resume)
```
Response: `{ "analysis_id": "uuid", "status": "processing", "message": "..." }`

### Get Analysis Status
```
GET /resume/analysis/{analysis_id}/status
```
Response: `{ "analysis_id": "uuid", "status": "processing|completed|failed", "current_step": "..." }`

### Respond to Suggestion
```
POST /profile/resume/suggestions/{suggestion_id}
Body: { "action": "accept" | "reject" }
```
Accept response: `{ "suggestion_id": "...", "status": "accepted", "applied_changes": { "section": "...", "suggestion_applied": "..." } }`
Reject response: `{ "suggestion_id": "...", "status": "rejected" }`

### Undo Suggestion
```
POST /profile/resume/suggestions/{suggestion_id}/undo
```
Response: `{ "message": "Suggestion undone. Resume restored to previous state.", "suggestion_id": "..." }`

### Start Interview
```
POST /interview/start  (multipart: resume, job_description, max_questions, model_name, temperature)
```
Response: `{ "session_id": "uuid", "first_question": "...", "total_questions": 5 }`

### Submit Answer
```
POST /interview/answer
Body: { "session_id": "uuid", "answer": "..." }
```
Response: `{ "session_id": "uuid", "next_question": "...|null", "score": 0, "analysis": "...", "is_complete": false }`

### Get Report
```
GET /interview/sessions/{session_id}/report
```
Response: `{ "report_id": "uuid", "session_id": "uuid", "content": "markdown report text" }`

---

## Notable Implementation Decisions

- **Live resume JSON**: `edited_resume_data` in `profiles/{uid}` is the authoritative editable resume state; starts from `parsed_sections`, accumulates changes from accepted suggestions
- **One-shot undo per suggestion**: snapshot deleted after use; re-accepting creates a new one
- **Reject is no-op on resume**: only status flag in analysis; `edited_resume_data` unchanged
- **Synchronous report finalization**: inline at interview completion for Cloud Functions compatibility
- **COOP header**: set globally to allow Firebase OAuth popup cross-origin communication

---

## Known Gaps & Next Steps

- Multi-level undo not supported — re-accepting overwrites snapshot
- No bulk accept/reject of suggestions
- `edited_resume_data` diffs not yet shown in UI
- Route prefix standardization (`/api/v1`) not applied globally
- Pagination on sessions endpoint for large histories
- Task execution reliability for long AI jobs (consider Celery/RQ + Redis)
- Expand integration test coverage (`backend-microservice/tests/`)

---

## File Map (primary)

- Backend
  - `backend-microservice/app/server.py` — FastAPI app, all routes, `_apply_suggestion_to_resume`, `_undo_suggestion_on_resume`
  - `backend-microservice/app/services/resume_analyzer_service.py` — `ResumeAnalyzerService` (3-step AI pipeline)
  - `backend-microservice/app/database/firebase_db.py` — `FirebaseManager`: all Firestore + Auth operations
  - `backend-microservice/app/core/config.py` — Pydantic settings from `.env`
  - `backend-microservice/app/services/interview_system.py` — Orchestrates interview AI components
- Frontend
  - `frontend/src/components/ResumeAnalyzer.tsx` — Resume upload, analysis display, suggestions UI
  - `frontend/src/components/AuthForm.tsx` — Auth UI (email/password + Google)
  - `frontend/src/components/Dashboard.tsx` — Sessions list with View Report
  - `frontend/src/components/FullReportViewer.tsx` — Report modal
  - `frontend/src/services/api.js` — API client singleton
  - `frontend/src/lib/firebase.ts` — Firebase initialization
- Firestore collections
  - `profiles/{uid}` — user profile + live resume (`edited_resume_data`)
  - `resume_analyses/{id}` — analysis results and suggestion statuses
  - `resume_parsed_sections/{id}` — raw parsed resume JSON
  - `suggestion_snapshots/{uid}:{suggestion_id}` — undo snapshots
  - `interview_sessions/{id}`, `interview_reports/{id}` — interview data

---

## Changelog (recent highlights)

- **2026-04-05**: Added COOP header middleware (`same-origin-allow-popups`) to fix Google OAuth popup; also patched Vite dev config and nginx.conf
- Added `_apply_suggestion_to_resume`: LLM-powered resume editing on suggestion accept with snapshot-based undo
- Added `_undo_suggestion_on_resume`: restores `edited_resume_data` from `suggestion_snapshots`
- Resume analysis migrated to async `BackgroundTask` with `current_step` polling
- Data store migrated from Supabase to Firebase Auth + Firestore
- Report generation changed from async to synchronous for Cloud Functions compatibility
- Google Sign-In added to `AuthForm.tsx` via Firebase `signInWithPopup`
