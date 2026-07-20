---
type: codebase-note
status: active
created: '2026-06-02'
updated: '2026-07-19'
tags:
  - codebase
  - backend
  - fastapi
  - security
---
# Backend Subsystem

Entrypoint: `backend-microservice/app/server.py` (~1900 lines, ~42 routes). A single FastAPI file containing ALL route definitions, auth middleware, session management, rate limiting, and background-task wiring. No separate router modules — everything lives here. See [[Single server.py]] for the decision rationale.

## How it starts

```
uvicorn app.server:app --host 0.0.0.0 --port 8000 --reload
```

Docker runs the same command via `backend-microservice/Dockerfile`, as a **non-root user** (`appuser`) since 2026-07 — see [[Security Hardening]].

## Route groups

All routes use bare paths — **no `/api/v1` prefix**. No auth-free `/test/*` routes exist server-side (see [[Auth Flow]]).

| Group | Prefix | Notes |
|---|---|---|
| Auth | `/auth/*` | signup (auto-logs-in via token exchange), signin, signout, Google OAuth, password |
| Profile | `/profile/*` | profile CRUD, multi-resume management, suggestions accept/undo/bulk |
| Resume analysis | `/profile/resume/*`, `/resume/analysis/*` | async pipeline, status polling |
| Interview (classic REST) | `/interview/start`, `/interview/answer`, `/interview/sessions*` | LangGraph-backed Q&A loop |
| Live interview (WS) | `/interview/prepare`, `WS /ws/interview/{id}` | Gemini streaming agent — see [[Live Interview]] |
| Dream Job | `/dream-job/*`, `/dream-jobs` | Kimi fit analysis |
| Reports/Dashboard | `/reports`, `/dashboard/stats`, `/interview/{id}/report` | added 2026-07-06 — frontend called these before they existed server-side |
| Settings | `/settings` | per-user model/API config |
| Health | `/health`, `/admin/health` | `/admin/health` (added 2026-07-06) probes Firestore connectivity too |

## Auth system

`get_current_user` dependency does real Firebase ID token verification on every call — see [[Auth Flow]]. No dev bypass exists.

## Rate limiting (added 2026-07)

`slowapi` `Limiter`, keyed by **raw bearer token** when present (one bucket per authenticated session regardless of shared IP) or remote IP for pre-auth routes. Disabled when `ENVIRONMENT=test` so the test suite isn't flaky against real limits. Applied to every LLM-cost or auth-abuse route: `/auth/signup`, `/auth/signin` (10/min IP), `/interview/start`, `/interview/prepare`, `/profile/resume`, `/dream-job`, `/dream-job/from-link` (10/min token), `/interview/answer` (20/min token — happens more often per session). See [[Rate limiting via slowapi]].

## Session management (in-memory, NOT durable)

- Active sessions: in-memory `_active_sessions` (classic REST) and `_live_sessions` (WS) dicts in `server.py`
- **There is no `_reconstruct_session()`.** A grep for it returns zero hits. If a session isn't in the in-memory dict — because the process restarted, or the request landed on a different Cloud Run instance — `/interview/answer` returns a clean 404 ("Interview session not found or expired. Please start a new interview.") rather than crashing. This is a deliberate UX improvement, not session recovery: **the interview itself is genuinely lost**, not silently degraded.
- #gotcha This is why `deploy.yml` should pin `--max-instances 1 --min-instances 1` until a session-persistence architecture (Redis vs Firestore-backed) is decided — see the production roadmap §5 and the open ADR question.

## Startup: stale-analysis sweeper (added 2026-07-06)

`BackgroundTasks` (resume analysis, Dream Job) are still in-process/non-durable, but a sweeper now fails-out anything stuck in `processing`/`normalizing` past 10 minutes: runs once at boot (fire-and-forget via `asyncio.to_thread` — **must never block startup**, see gotcha below) and every 5 minutes after. See [[BackgroundTasks over Celery]] (updated) for the full rationale.

#gotcha **A blocking Firestore call in the FastAPI `lifespan` startup hook delays `/health` becoming reachable** — caught via an actual `docker build && docker run` test, not by unit tests. `asyncio.create_task(...)` alone does NOT fix this: it still runs synchronous code on the same event loop. The fix is `asyncio.to_thread(_sweep_stale_analyses_sync)` — genuinely offloads the blocking Firestore call to a worker thread so `/health` responds instantly regardless of Firestore reachability at boot. Cloud Run's startup probe depends on this.

## Environment config

`backend-microservice/app/core/config.py` — Pydantic `Settings`. Model IDs are now **config-driven env vars** (added 2026-07-06), not hardcoded:

```
OPENAI_API_KEY=                          # currently DISABLED — see production roadmap risk #3
OPENAI_BASE_URL / AIML_BASE_URL=https://api.aimlapi.com/v1
RESUME_PARSE_MODEL / RESUME_SECTION_MODEL / RESUME_HOLISTIC_MODEL
DREAM_JOB_NORMALIZE_MODEL / DREAM_JOB_FIT_MODEL / SUGGESTION_APPLY_MODEL
FIREBASE_PROJECT_ID=interviewer-ea164
ENVIRONMENT=development|production|test   # "production" strips localhost CORS + disables /docs
```
See [[Config-driven fail-loud LLM calls]].

## Dead code

`app/database/supabase.py` — unused, leftover from an earlier design. Still present as of 2026-07-19 (pre-existing dead code, deliberately not removed per "don't delete unless asked").

## Known weaknesses (still open — see production roadmap Phase D)

- `BackgroundTasks` still non-durable at the queue level (sweeper mitigates the "stuck forever" symptom, not the underlying architecture) — Cloud Tasks/Celery is the real fix.
- No pagination on `/interview/sessions`, `/reports`, `/profile/resumes`, `/dream-jobs`.
- `(user_id, session_id)` unique constraint missing in `interview_reports` — should use `session_id` as the doc ID.
- `get_report_by_session` linearly scans the 50 most-recent reports — 404s for anything older.
- Single-instance-implied design (`--max-instances 1` recommended) — FAISS index and both session dicts aren't shared/reconstructable across instances.
- Live-interview post-report step (`server.py` ~1622) swallows exceptions silently — user can be stuck on "generating your report…" forever. Flagged as a Phase A blocker in the roadmap, not yet fixed in code.

[[Codebase Map]] · [[AI Pipeline]] · [[Auth Flow]] · [[Security Hardening]] · [[Dream Job]] · [[Live Interview]]
