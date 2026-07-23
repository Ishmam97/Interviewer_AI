---
type: moc
status: active
created: '2026-06-02'
updated: '2026-07-19'
tags:
  - codebase
  - moc
---
# Codebase Map

How the codebase actually works — subsystem behavior, where things live, and gotchas. Companion to `REPOMAP.md` (structural index); this is the hard-won understanding. Last comprehensively re-verified against the repo: **2026-07-19** (a large hardening sprint landed 2026-07-06/07 — this map reflects the current, not the original, state).

## Subsystems

- [[Backend]] — FastAPI server, all routes, session management, rate limiting, background tasks
- [[Frontend]] — React SPA, state-based routing, ApiService, component map
- [[Auth Flow]] — Firebase Auth tokens, sign-up/sign-in flows; no dev bypass, no auth-free `/test/*` routes server-side
- [[Data Model]] — all Firestore collections with schemas and gotchas
- [[Security Hardening]] — rate limiting, SSRF, upload sniffing, dependency CVEs, non-root Docker — the full 2026-07 hardening record

## AI pipeline components

- [[AI Pipeline]] — overview: config-driven model IDs, fail-loud error handling, classic + live interview modes, FAISS RAG, Dream Job
- [[Live Interview]] — WebSocket/Gemini streaming mode; shipped, previously mis-tracked as backlog
- [[LangGraph Workflow]] — classic mode's exact graph definition, nodes, edges; why the graph is not invoked end-to-end (still true, unchanged)
- [[RAG System]] — FAISS index lifecycle, now **per-session** (was a shared path → cross-user data leak, fixed)
- [[Interview Planner]] — question plan generation, fallback questions, JSON cleaning
- [[Response Analyzer]] — answer scoring, score extraction gotcha (still regex-based, not fixed), conversation history window
- _(report generation is in `utils/prompts.py` REPORT_PROMPT → ReportGenerator; truncates resume to 2048 chars)_

## Top gotchas (read before touching anything)

1. **No dev-auth bypass, no real `/test/*` routes** — verified via grep, zero hits server-side. Frontend has two dead client methods pointing at nonexistent routes; harmless, not a live bypass. ([[Auth Flow]])
2. **State-based routing** — ALL frontend navigation is `activeSection` state in `Index.tsx`. No URL routing for features. ([[Frontend]])
3. **No session reconstruction exists** — there is no `_reconstruct_session()`. A restart or a request landing on a different instance loses the session entirely; the API now returns a clean 404 rather than crashing, but the interview itself is genuinely gone. ([[Backend]])
4. **Score extraction is line-parsing, not JSON** — `ResponseAnalyzer.extract_score()` looks for `SCORE: N` in free text; defaults to 5 silently. Still unfixed. ([[Response Analyzer]])
5. **LangGraph graph not invoked end-to-end** — `execute_workflow()` exists but REST handlers call nodes directly. Still true. ([[LangGraph Workflow]])
6. **`supabase.py` is dead code** — exists, unused, still not removed as of 2026-07-19.
7. **All routes are bare-path** — `/interview/start` not `/api/v1/interview/start`. Unchanged.
8. **FAISS is now session-scoped** — was a cross-user data leak via a shared default path; fixed 2026-07-06. ([[RAG System]], [[Session-scoped FAISS index]])
9. **LLM calls now fail loud** — used to silently return zero-filled "completed" reports on any provider/parse error; fixed 2026-07-06. ([[AI Pipeline]], [[Config-driven fail-loud LLM calls]])
10. **Rate limiting exists now** — slowapi, keyed by bearer token for authed routes / IP for pre-auth routes. Didn't exist before 2026-07-06. ([[Security Hardening]], [[Rate limiting via slowapi]])
11. **The live-interview post-report step can silently strand a user** — swallows exceptions with no WS error sent. Known, flagged in the production roadmap as a launch blocker, not yet fixed. ([[Live Interview]])
12. **Resume-edit persistence standardized on `working_parsed_sections`** — a 3-way split (`profile.edited_resume_data` vs `resume_parsed_sections.working_parsed_sections` vs an unused dedicated method) resolved 2026-07-19. ([[Standardize on working_parsed_sections]])

[[Home]] · [[Production Roadmap]]
