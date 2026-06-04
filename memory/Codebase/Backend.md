---
type: codebase-note
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - codebase
  - backend
  - fastapi
---
# Backend Subsystem

Entrypoint: `backend-microservice/app/server.py` (~1700 lines). A single FastAPI file containing ALL route definitions, auth middleware, session management, and background task wiring. No separate router modules — everything lives here.

## How it starts

```
uvicorn app.server:app --host 0.0.0.0 --port 8000 --reload
```

Docker runs it the same way via `backend-microservice/Dockerfile`.

## Route groups

All routes use bare paths — **no `/api/v1` prefix** despite some docs suggesting otherwise. Code wins.

| Group | Prefix | Notes |
|---|---|---|
| Auth | `/auth/*` | signup, signin, signout, google OAuth, password reset |
| Profile | `/profile/*` | profile CRUD, multi-resume management |
| Resume analysis | `/profile/resume/*`, `/resume/analysis/*` | async pipeline, suggestions, undo |
| Interview | `/interview/*` | start, answer, sessions list/detail, report |
| Dream Job | `/dream-job/*`, `/dream-jobs` | fit analysis (new feature) |
| Settings | `/settings` | per-user model/API config |
| Live interview | `WS /ws/interview/{id}` | WebSocket agent |
| Misc | `/health`, `/analyze/resume`, `/interview/prepare` | |

## Auth system

- `get_current_user` dependency reads `Authorization: Bearer <token>`
- In **production**: `firebase_admin.auth.verify_id_token()` validates the token
- In **development** (`ENVIRONMENT=development`): token `dummy-token` returns a hardcoded mock user — no Firebase call
- `uid` comes from the decoded token's `uid` claim
- Google OAuth: frontend gets Google ID token → POST `/auth/google` → backend creates profile if new

#gotcha Firebase service account must exist at `backend-microservice/firebase-service-account.json`. Never committed. Falls back to Application Default Credentials if missing, which silently works in GCP but fails locally without ADC setup.

## Session management

- Active sessions: in-memory `_active_sessions` dict in `server.py`
- Sessions are written to **Firestore before** being added to the in-memory cache
- If a request arrives for a session not in cache: `_reconstruct_session()` rebuilds from Firestore
- #gotcha Reconstruction from Firestore **cannot restore the FAISS index** — RAG is unavailable for reconstructed sessions. This is a known limitation in multi-instance deployments.

## Resume analysis pipeline

3-step async pipeline in `services/resume_analyzer_service.py`, launched as `BackgroundTask`:

1. `parsing_document` — gpt-5-nano extracts structured JSON (name, contact, experience, education, skills, etc.)
2. `analyzing_sections` — 7 parallel LLM calls, one per resume section; each returns score + suggestions
3. `holistic_review` — overall assessment and cross-section feedback

Status is stored in Firestore so the frontend can poll `GET /resume/analysis/{id}/status`.

## Environment config

`backend-microservice/app/core/config.py` — Pydantic `Settings` loaded from `.env`:

```
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.aimlapi.com/v1   # AIML API proxy, OpenAI-compatible
FIREBASE_PROJECT_ID=interviewer-ea164
FIREBASE_API_KEY=...
FIREBASE_SERVICE_ACCOUNT_PATH=./firebase-service-account.json
ENVIRONMENT=development   # "production" enforces Firebase token verification
DEBUG=false
```

## Dead code

`app/database/supabase.py` exists but is **unused** — leftover from an earlier design. Remove it.

## Known weaknesses

- `BackgroundTasks` are not durable — if the process restarts mid-analysis, the job is lost. Celery + Redis needed for production.
- No pagination on `/interview/sessions` — will be slow for prolific users.
- `(user_id, session_id)` unique constraint missing in `interview_reports` Firestore collection.
- Single-instance design — FAISS volume isn't shared; pod restarts lose session FAISS context.

[[Codebase Map]] · [[AI Pipeline]] · [[Auth Flow]] · [[Dream Job]]
