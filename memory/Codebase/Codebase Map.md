---
type: moc
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - codebase
  - moc
---
# Codebase Map

How the codebase actually works — subsystem behavior, where things live, and gotchas. Companion to `REPOMAP.md` (structural index); this is the hard-won understanding.

## Subsystems

- [[Backend]] — FastAPI server, all routes, session management, auth, background tasks
- [[Frontend]] — React SPA, state-based routing, ApiService, component map
- [[Auth Flow]] — Firebase Auth tokens, sign-up/sign-in flows; no dummy-token bypass in current code
- [[Data Model]] — all Firestore collections with schemas and gotchas

## AI pipeline components

- [[AI Pipeline]] — overview: LangGraph interview flow, resume analysis, FAISS RAG, Dream Job pipeline
- [[LangGraph Workflow]] — exact graph definition, nodes, edges, state machine; why graph is not invoked end-to-end
- [[RAG System]] — FAISS index lifecycle, embeddings, context retrieval, dangerous deserialization flag
- [[Interview Planner]] — question plan generation, fallback questions, JSON cleaning
- [[Response Analyzer]] — answer scoring, score extraction gotcha, conversation history window
- _(report generation is in `utils/prompts.py` REPORT_PROMPT → ReportGenerator; truncates resume to 2048 chars)_

## Top gotchas (read before touching anything)

1. **No `dummy-token` bypass in current code** — old docs described it; current `server.py` does real Firebase verification. Use test endpoints for auth-free dev. ([[Auth Flow]])
2. **State-based routing** — ALL frontend navigation is `activeSection` state in `Index.tsx`. No URL routing for features. ([[Frontend]])
3. **FAISS not reconstructable** — session rebuilt from Firestore after pod restart loses RAG context entirely. ([[RAG System]])
4. **Score extraction is line-parsing, not JSON** — `ResponseAnalyzer.extract_score()` looks for `SCORE: N` in free text; defaults to 5 silently. ([[Response Analyzer]])
5. **LangGraph graph not invoked end-to-end** — `execute_workflow()` exists but REST handlers call nodes directly. ([[LangGraph Workflow]])
6. **`supabase.py` is dead code** — exists, unused, should be deleted.
7. **All routes are bare-path** — `/interview/start` not `/api/v1/interview/start`. Some docs are wrong.

[[Home]]
