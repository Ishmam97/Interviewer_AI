---
type: moc
status: active
created: '2026-05-26'
updated: '2026-07-19'
tags:
  - home
---
# Home

Dashboard for this project's memory vault. The durable, cross-task knowledge base that complements the per-task artifacts in `docs/`.

**Project:** Interviewer AI — AI-driven mock interview app. Full-stack (React + FastAPI + Firebase + LangGraph + FAISS + Gemini). Dream Job feature shipped 2026-05-04. A production-readiness hardening sprint (2026-07-06/07) took the backend test suite from 79/33 to **147/147 passing** and fixed several CRITICAL bugs (silent zero-score AI reports, a cross-user FAISS data leak, missing rate limiting). A 5-agent research team then produced a full production roadmap (2026-07-07), reviewer-verified against the repo. This vault was last fully reconciled against the live codebase **2026-07-19** — read the notes below, not the older assumption that nothing changed since June.

## Maps of content

- [[Codebase Map]] — how the codebase works (subsystems, gotchas) — **most current summary of what changed**
- [[Features MOC]] — all features: shipped, in-progress, backlog
- [[Decisions Log]] — architecture decisions, each in its own note
- [[Concepts MOC]] — domain and technical concepts

## Codebase subsystems

- [[Backend]] · [[Frontend]] · [[Auth Flow]] · [[Data Model]] · [[Security Hardening]]
- [[AI Pipeline]] · [[LangGraph Workflow]] · [[RAG System]] · [[Interview Planner]] · [[Response Analyzer]] · [[Live Interview]]

## Features

- [[Interview System]] · [[Live Interview]] · [[Resume Analysis]] · [[Dream Job]] · [[Job Link Parser]] · [[Production Roadmap]]

## Decisions

**Foundational (2026-06):** [[Single server.py]] · [[Firebase over SQL]] · [[State-based frontend routing]] · [[LangGraph for interview workflow]] · [[AIML API proxy]] · [[BackgroundTasks over Celery]]

**Hardening sprint (2026-07):** [[Config-driven fail-loud LLM calls]] · [[Session-scoped FAISS index]] · [[Rate limiting via slowapi]] · [[Standardize on working_parsed_sections]]

## Concepts

- [[RAG]] · [[LangGraph]] · [[AIML API]]

## Top gotchas (quick reference — see [[Codebase Map]] for the full, current list)

1. No dev-auth bypass and no auth-free `/test/*` routes exist server-side — a June-era claim to the contrary was itself wrong and has been corrected
2. Frontend: all navigation is `activeSection` state, no URL routes
3. **No session reconstruction exists at all** (no `_reconstruct_session()`) — a restart loses the interview entirely; the API returns a clean 404, it does not silently degrade
4. `ResponseAnalyzer` score extraction parses free text — defaults to 5 silently (still unfixed)
5. LangGraph graph is defined but invoked imperatively, not end-to-end (still true)
6. `supabase.py` is dead code (still present)
7. All routes are bare-path, not `/api/v1/...`
8. **FAISS is now per-session** — was a shared-path cross-user data leak until 2026-07-06
9. **LLM calls now fail loud** — used to silently return zero-filled "completed" reports on error until 2026-07-06
10. **Rate limiting exists now** (slowapi, bearer-token-keyed) — didn't exist until 2026-07-06
11. Live-interview post-report step can still silently strand a user (known, unfixed, flagged as a launch blocker)
12. Three clashing UI color palettes ship today — unification scoped in [[Production Roadmap]], deferred by owner request

## Where to look for what's next

[[Production Roadmap]] is the single source of truth for prioritized work: Phase A (launch blockers, ~3-5 days) → B (UI unification) → C (freemium + Stripe) → D (ops + differentiating features). Owner-only actions (GCP console, secrets, the disabled AIML key, the `main` merge) are explicitly separated from Claude-doable work throughout.

---

See also: `REPOMAP.md` (structural index) · `CLAUDE.md` (operating contract) · `docs/roadmap/production-roadmap.md` (the full roadmap artifact) · `docs/architecture/production-readiness-assessment.md` (the original hardening-sprint audit)
