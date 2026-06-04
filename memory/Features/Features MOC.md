---
type: moc
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - feature
  - moc
---
# Features MOC

One note per feature. Each links to its `docs/` artifacts and accumulates cross-task context.

## Shipped features

- [[Interview System]] — core product: upload resume + JD, answer AI questions, get scored report. LangGraph pipeline, FAISS RAG, configurable LLM.
- [[Resume Analysis]] — 3-step async pipeline (parse → 7 parallel section analyses → holistic review). Suggestions system with accept/reject/undo.
- [[Dream Job]] — Kimi-powered job fit analysis. Paste URL or enter manually, pick a resume, get fit score + gap analysis + tailoring plan. Shipped 2026-05-04.
- [[Job Link Parser]] — Scrapes job posting URLs (Greenhouse/Ashby/LinkedIn/generic) with SSRF guard. Called by Dream Job from-link endpoint.

## In progress

_Nothing currently in flight._

## Planned / backlog

- **Resume Tailor** — "Tailor My Resume" button in `DreamJobDashboard` is disabled ("Coming soon"). Next Dream Job iteration.
- **Live Interview agent** — WebSocket endpoint `/ws/interview/{id}` + `services/live_interview_agent.py` exist; UI incomplete.
- **Gemini interview prep** — `POST /interview/prepare` + `services/gemini_file_service.py` hook Gemini File API. Status unclear.

[[Home]]
