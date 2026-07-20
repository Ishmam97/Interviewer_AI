---
type: codebase-note
status: active
created: '2026-07-19'
updated: '2026-07-19'
tags:
  - codebase
  - interview
  - websocket
  - gemini
---
# Live Interview (WebSocket)

**Correction to earlier vault state:** this was previously listed in Features MOC as "in progress / unclear." It is fully shipped — a conversational, streaming alternative to the classic REST/LangGraph interview mode, built on Gemini rather than the AIML API.

## Flow

1. `POST /interview/prepare` (rate-limited 10/min, `max_questions` bounded 1–20): uploads resume + JD to the Gemini File API via `services/gemini_file_service.py`, generates a question plan, stores it in the in-memory `_live_sessions` dict keyed by a new `session_id`.
2. Client opens `WS /ws/interview/{session_id}`.
3. `services/live_interview_agent.py`'s `LiveInterviewAgent` streams the conversation turn-by-turn using Gemini (`GEMINI_MODEL`, default `gemini-2.5-flash`), sending partial tokens over the socket as they're generated.
4. On completion, a post-interview step (`server.py` ~1588–1626) analyzes the full transcript and saves an `interview_sessions` Firestore record with `report_data`.

## Hardening (added 2026-07)

- **Wall-clock timeout on streaming turns.** A single Gemini generation used to have no timeout at all — the 300s WS-level receive timeout only covered waiting for the *candidate's next answer*, not generation itself. A hung upstream stream could block the whole socket indefinitely. Fixed with an explicit `asyncio.wait_for` around each streamed turn; on timeout, falls back to a graceful "having trouble responding" message rather than hanging.
- `max_questions` bounded 1–20 (previously unbounded — a careless or malicious request could drive unbounded Gemini File API + generation cost).

## Known open issue — quadratic token cost (flagged in production roadmap, not yet fixed)

#gotcha The live interview resends the **entire growing conversation history** to Gemini on every turn (not just the new turn) — token cost scales roughly quadratically with interview length. Flagged in the production roadmap as "the single biggest cost-scaling risk — fix before 1000 MAU." No fix implemented yet as of 2026-07-19.

## Known open issue — silent stuck-forever on report failure (Phase A blocker, not yet fixed)

The post-interview analysis step (`server.py` ~1622) wraps its work in a bare `except Exception as exc: logger.error(...)` with **no WS message sent to the client**. If `analyze_transcript` throws, the user is left staring at "generating your report…" forever with no error, no timeout, no retry. This is called out as a Phase A ("Launchable") blocker in `docs/roadmap/production-roadmap.md` — the fix (send a WS `error` message + add a client-side timeout) is scoped but not yet implemented.

## Relationship to the classic interview mode

Entirely separate code paths — different session dict (`_live_sessions` vs `_active_sessions`), different LLM provider (Gemini vs whatever the classic mode's `api_provider` resolves to), different transport (WebSocket vs REST polling). Both modes are shipped and user-facing; neither supersedes the other.

[[Codebase Map]] · [[Backend]] · [[Interview System]] · [[AI Pipeline]]
