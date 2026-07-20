---
type: moc
status: active
created: '2026-06-02'
updated: '2026-07-19'
tags:
  - decision
  - moc
---
# Decisions Log

Each decision lives in its own note. This index links them all.

## Architecture decisions (2026-06, foundational)

- [[Single server.py]] — all routes in one file; split when it hurts
- [[Firebase over SQL]] — Firestore for auth + persistence; no SQL/Redis
- [[State-based frontend routing]] — `activeSection` in Index.tsx, no URL routes
- [[LangGraph for interview workflow]] — graph defined but invoked imperatively, not end-to-end
- [[AIML API proxy]] — single OpenAI-compatible proxy for multi-provider LLM access
- [[BackgroundTasks over Celery]] — simple async jobs; **update 2026-07-06:** the predicted "job silently lost" failure mode happened, now mitigated by a stale-analysis sweeper (not a Celery migration)

## Hardening-sprint decisions (2026-07-06/07)

- [[Config-driven fail-loud LLM calls]] — CRITICAL fix: model IDs moved to env-configurable settings; every analyzer step now re-raises instead of silently returning zero-filled "completed" reports
- [[Session-scoped FAISS index]] — fixed a real cross-user data leak: the classic interview mode's FAISS index used to default to one shared path across all sessions
- [[Rate limiting via slowapi]] — keyed by raw bearer token (not IP) for authenticated routes, so shared-IP users don't share a bucket
- [[Standardize on working_parsed_sections]] — resolved a 3-way split in resume-edit persistence; last 5 failing backend tests now pass, suite is 147/147 green

## Resolved / superseded pending items (were listed here as of 2026-06-02)

- ~~Route prefix: bare paths vs `/api/v1/...`~~ — still bare paths; not resolved, but no longer "pending a call," it's the accepted convention (see [[Backend]])
- ~~Multi-instance session caching~~ — formalized as an explicit open ADR question in [[Production Roadmap]] §5 (Redis vs Firestore-backed vs "accept single-instance, non-resumable"); recommended interim answer is `--max-instances 1` until real concurrency data justifies the investment
- ~~`supabase.py` cleanup~~ — still dead code as of 2026-07-19, still not removed (low priority, no user request to do so)

## Open decisions awaiting the project owner (see [[Production Roadmap]] §5 for full detail + recommendations)

- CORS / Hosting-domain identity mismatch (config.py vs deploy.yml vs the real Firebase Hosting domain) — **blocks Phase A**, must be reconciled before first deploy
- `deploy.yml`/`ci.yml` CI/CD edits (Python 3.11→3.12, `--set-env-vars`→`--set-secrets`, URL/timeout/max-instances fixes) — deliberately not made without owner confirmation per this project's CI/CD-edit caution rule
- UI palette winner (recommendation: teal-400/slate-950, the newest deliberate design) — deferred by owner request, see [[Production Roadmap]]
- Dark mode: keep or drop the currently-dead `next-themes` infra — recommendation: drop now, build a real toggle later if wanted
- Product name in-UI: "AI Interview Assistant" vs "Interviewer AI" (the repo/brand identity) — recommendation: standardize on "Interviewer AI"

[[Home]]
