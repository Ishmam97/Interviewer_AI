---
type: moc
status: active
created: '2026-05-26'
updated: '2026-06-02'
tags:
  - home
---
# Home

Dashboard for this project's memory vault. The durable, cross-task knowledge base that complements the per-task artifacts in `docs/`.

**Project:** Interviewer AI — AI-driven mock interview app. Full-stack (React + FastAPI + Firebase + LangGraph + FAISS). Dream Job feature shipped 2026-05-04.

## Maps of content

- [[Codebase Map]] — how the codebase works (subsystems, gotchas)
- [[Features MOC]] — all features: shipped, in-progress, backlog
- [[Decisions Log]] — architecture decisions, each in its own note
- [[Concepts MOC]] — domain and technical concepts

## Codebase subsystems

- [[Backend]] · [[Frontend]] · [[Auth Flow]] · [[Data Model]]
- [[AI Pipeline]] · [[LangGraph Workflow]] · [[RAG System]] · [[Interview Planner]] · [[Response Analyzer]]

## Features

- [[Interview System]] · [[Resume Analysis]] · [[Dream Job]] · [[Job Link Parser]]

## Decisions

- [[Single server.py]] · [[Firebase over SQL]] · [[State-based frontend routing]]
- [[LangGraph for interview workflow]] · [[AIML API proxy]] · [[BackgroundTasks over Celery]]

## Concepts

- [[RAG]] · [[LangGraph]] · [[AIML API]]

## Top gotchas (quick reference)

1. No `dummy-token` auth bypass in current code — old docs were wrong
2. Frontend: all navigation is `activeSection` state, no URL routes
3. FAISS is lost on pod restart + session reconstruction
4. `ResponseAnalyzer` score extraction parses free text — defaults to 5 silently
5. LangGraph graph is defined but invoked imperatively, not end-to-end
6. `supabase.py` is dead code
7. All routes are bare-path, not `/api/v1/...`

---

See also: `REPOMAP.md` (structural index) · `CLAUDE.md` (operating contract)
