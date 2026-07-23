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

## Update 2026-07-06: the "stuck in processing forever" symptom is now mitigated (not the architecture)

The "no durability, job silently lost" trade-off above was accepted risk until it manifested as its predicted symptom: a killed/restarted process leaves the Firestore doc at `status: "processing"` forever with no recovery path. A **stale-analysis sweeper** was added — not a replacement for Celery, a symptom mitigation:

- Runs once at FastAPI startup (fire-and-forget, **not awaited** — see the critical gotcha below) and every 5 minutes after
- Fails out any `resume_analyses`/`dream_jobs` doc stuck in a non-terminal status for >10 minutes (comfortably above both services' own internal timeouts)
- `create_resume_analysis`'s return value is now checked before enqueuing the background task at all — previously ignored, meaning a failed doc-creation still queued a task that would poll a document that never existed

#gotcha **A subtle, only-caught-by-live-testing bug during this fix:** the sweeper's first version awaited its work inside the FastAPI `lifespan` startup hook. Since `FirebaseManager`'s Firestore calls are synchronous, this **blocked the event loop** — including `/health` — until the sweep finished or errored, which could take 20-30+ seconds if Firestore/ADC was slow or unreachable at boot. This would delay or fail Cloud Run's startup health probe. `asyncio.create_task(...)` alone did NOT fix it (still runs synchronous code on the same event loop when its turn comes). The actual fix: `asyncio.to_thread(_sweep_stale_analyses_sync)` — genuinely offloads the blocking call to a worker thread. Caught by an actual `docker build && docker run` test, not by any unit test; a good example of why this project verifies deploy-critical behavior by literally running the container, not just asserting on it.

[[Decisions Log]] · [[Backend]] · [[Resume Analysis]] · [[Dream Job]]
