---
type: moc
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - decision
  - moc
---
# Decisions Log

Each decision lives in its own note. This index links them all.

## Architecture decisions

- [[Single server.py]] — all routes in one file; split when it hurts
- [[Firebase over SQL]] — Firestore for auth + persistence; no SQL/Redis
- [[State-based frontend routing]] — `activeSection` in Index.tsx, no URL routes
- [[LangGraph for interview workflow]] — graph defined but invoked imperatively, not end-to-end
- [[AIML API proxy]] — single OpenAI-compatible proxy for multi-provider LLM access
- [[BackgroundTasks over Celery]] — simple async jobs, not durable; upgrade path to Celery when needed

## Pending decisions (no ADR yet)

- Route prefix: bare paths vs `/api/v1/...` — needs a call before any public API exposure
- Multi-instance session caching: FAISS not shareable; Redis cache + S3 index storage if scaling beyond single pod
- `supabase.py` cleanup: dead code, should be removed

[[Home]]
