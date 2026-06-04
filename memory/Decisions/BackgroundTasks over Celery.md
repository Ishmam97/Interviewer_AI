---
type: decision
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - decision
  - architecture
  - async
  - background-tasks
---
# Decision: FastAPI BackgroundTasks (not Celery/Redis)

Async analysis jobs (resume analysis, Dream Job analysis) are launched via FastAPI's built-in `BackgroundTasks` mechanism, not a dedicated job queue like Celery + Redis.

**Why:** `BackgroundTasks` requires zero extra infrastructure — no Redis, no Celery worker process, no broker config. For a demo/personal project where simplicity beats resilience, this is the right call.

**Trade-off:**
- **Not durable.** If the FastAPI process restarts while a job is running, the job is silently lost. The Firestore record stays at `status: "processing"` forever with no retry.
- **No retry on failure.** If an LLM call fails mid-analysis, the whole analysis fails and the status transitions to `"failed"`. There's no automatic retry.
- **No monitoring.** No Flower, no queue depth visibility, no job history.
- **Single-process.** `BackgroundTasks` runs in the same process as the web server. A flood of long-running Kimi calls can starve the event loop.

**How to apply:** Keep using `BackgroundTasks` for new async features at this stage. If the app moves to production with real users, replace with Celery + Redis (or a managed queue like Cloud Tasks). The interface is: launch job → write `status: "pending"` → update to `"failed"` or `"completed"` in Firestore → frontend polls status endpoint.

[[Decisions Log]] · [[Backend]] · [[Resume Analysis]] · [[Dream Job]]
