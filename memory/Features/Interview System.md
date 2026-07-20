---
type: feature-note
status: shipped
created: '2026-06-02'
updated: '2026-07-19'
tags:
  - feature
  - interview
  - langgraph
---
# Interview System (classic REST mode)

The original product feature. Users upload a resume + job description, start an interview, answer AI-generated questions one at a time over REST, and receive a final report with scores. A separate, newer WebSocket-based mode exists alongside this one — see [[Live Interview]]; the two are independent, not a v1/v2 relationship.

## Start flow

`POST /interview/start` (rate-limited 10/min, `max_questions` bounded 1–20 since 2026-07). Backend:

1. Creates `InterviewSystem` with user's LLM settings (`api_provider`, `model`, `temperature`, custom key if set)
2. Saves uploaded files to temp paths
3. **Generates `session_id` up front** (changed 2026-07) so the FAISS index gets a session-scoped path before `InterviewConfig` is built — see [[RAG System]] for why this matters (was a cross-user data leak)
4. Calls `interview_system.start_interactive_interview()` off the event loop via `asyncio.to_thread` (changed 2026-07 — this does synchronous file I/O + embedding + LLM calls and used to block every other in-flight request for its duration)
5. Saves session to Firestore, adds to in-memory `_active_sessions`, returns the first question

## Answer flow

`POST /interview/answer` (rate-limited 20/min — happens more often per session than `/start`). If the session isn't in `_active_sessions`, returns a clean 404 ("expired, please start a new interview") — there is **no session reconstruction** (see [[Backend]]). Otherwise: retrieve RAG context → analyze response → take notes → advance or generate the report. The blocking LLM/FAISS calls here are also offloaded via `asyncio.to_thread` since 2026-07.

## LangGraph state machine

See [[LangGraph Workflow]] for the full graph, nodes, and the "graph is defined but invoked imperatively, not end-to-end" caveat (still true — unchanged since 2026-06).

## InterviewConfig defaults

```python
max_questions: int = 5    # bounded 1-20 at the route level since 2026-07
chunk_size: int = 800
chunk_overlap: int = 150
rag_k_results: int = 3
temperature: float = 0.3
model_name: str = "gemini-2.5-flash"
index_path: str            # session-scoped since 2026-07, was a shared default
```

Overridden by `user_settings` Firestore doc.

## LLM providers

`interview_system._build_llm_and_embeddings()` supports `"openai"` (AIML API, default), `"gemini"`, `"anthropic"` — unchanged.

## Session persistence — no reconstruction (corrected 2026-07-19)

**Correction to earlier vault state:** this note used to describe a `_reconstruct_session()` that rebuilds `InterviewState` from Firestore (minus FAISS). That function **does not exist** — verified via grep, zero hits. If the process restarts or the request lands on a different instance, the session is simply gone; `/interview/answer` returns a 404, not a degraded-but-working reconstruction. This is tracked as an open ADR question in the production roadmap (Redis vs Firestore-backed persistence vs "accept single-instance").

## Report generation

`ReportGenerator.generate_report()` — unchanged. Inputs truncated: `resume_content[:2048]`, `job_description[:1024]`.

#gotcha Score extraction from `ResponseAnalyzer.analyze_response()` is still regex-based: parses `SCORE: N` from the LLM's text response, defaults to 5 if not found. Not yet fixed.

## Dashboard / history

`GET /interview/sessions` (no pagination — tech debt), `GET /interview/sessions/{id}`, `GET /interview/sessions/{id}/report`. Also `GET /reports`, `GET /dashboard/stats`, `GET /interview/{id}/report` were **added 2026-07-06** — the frontend called these endpoints before they existed server-side (a real, shipped-but-broken bug fixed during the hardening sprint).

[[Features MOC]] · [[LangGraph Workflow]] · [[RAG System]] · [[Response Analyzer]] · [[Interview Planner]] · [[Live Interview]]
