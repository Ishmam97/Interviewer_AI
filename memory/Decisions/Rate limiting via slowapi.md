---
type: decision
status: active
created: '2026-07-19'
updated: '2026-07-19'
tags:
  - decision
  - security
  - architecture
---
# Decision: slowapi for rate limiting, keyed by bearer token

Added 2026-07-06. No rate limiting existed before this — every LLM-cost route and the pre-auth signup/signin routes were fully open to abuse.

**Why slowapi:** lightweight, in-process, no new infrastructure (matches the project's existing "no Redis/Celery unless needed" posture — see [[BackgroundTasks over Celery]]). In-memory storage is fine at this project's current scale (single instance recommended anyway, see the session-persistence ADR).

**Key function — the interesting part:** most routes require auth, so per-user limiting is more meaningful than per-IP (a shared office/NAT IP shouldn't share one bucket across unrelated users). But `slowapi`'s `key_func` only receives the `Request` object, not FastAPI's already-resolved `current_user` dependency. Rather than re-decoding the JWT inside the key function (extra work, and a forged-but-unverified token would just fail downstream anyway), the key function **uses the raw bearer token string itself** as the rate-limit key: one bucket per distinct valid session, with no JWT parsing needed. Falls back to `get_remote_address` (IP) for the two pre-auth routes (`/auth/signup`, `/auth/signin`) where there's no token yet.

**Naming collision found while wiring this up:** `slowapi`'s `@limiter.limit(...)` decorator requires a parameter literally named `request: Request` on the decorated function. Three routes (`submit_answer`, `dream_job_from_link`, `create_dream_job`) already used `request` as the name of their Pydantic body parameter. Fixed by renaming those body parameters to `payload` — a pure internal rename (Pydantic binds by type annotation, not name), zero API contract change.

**Rate limits chosen:**
- Auth (signup/signin): 10/min per IP
- LLM-cost routes (`/interview/start`, `/interview/prepare`, `/profile/resume`, `/dream-job`, `/dream-job/from-link`): 10/min per token
- `/interview/answer`: 20/min per token (happens far more often per session than session-start)

**Disabled under test** (`enabled=(settings.ENVIRONMENT != "test")`) — some parametrized test files hit the same endpoint with the same hardcoded dummy token a dozen-plus times within one process; without this, the suite would be flaky against its own real limits.

**Trade-off:** in-memory limiter state doesn't survive a restart and isn't shared across instances — acceptable at `--max-instances 1`, would need a shared backend (Redis) if the app scales horizontally before the session-persistence question is resolved anyway.

Regression tests: `test_rate_limiting.py` (auth 429 after threshold), `test_bg_task_cleanup.py` (max_questions bound tests).

[[Decisions Log]] · [[Security Hardening]] · [[Backend]]
