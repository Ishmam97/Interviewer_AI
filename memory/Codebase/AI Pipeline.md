---
type: codebase-note
status: active
created: '2026-06-02'
updated: '2026-07-19'
tags:
  - codebase
  - ai
  - langgraph
  - rag
---
# AI Pipeline

The core intelligence of the app. All LLM calls go through an OpenAI-compatible API (AIML API by default, configurable via `OPENAI_BASE_URL`/`AIML_BASE_URL`) or Gemini directly (live interview).

## LLM configuration — now config-driven (2026-07)

#gotcha **Fixed bug, keep for context:** model IDs used to be hardcoded string literals scattered across `resume_analyzer_service.py`, `dream_job_analyzer_service.py`, and `server.py`. Now every model ID is a `Settings` field in `core/config.py`, overridable via env var without a code change:

| Setting | Default | Used by |
|---|---|---|
| `AIML_BASE_URL` | `https://api.aimlapi.com/v1` | all AIML-routed calls |
| `RESUME_PARSE_MODEL` / `RESUME_SECTION_MODEL` | `openai/gpt-5-nano-2025-08-07` | resume analyzer steps 1–2 |
| `RESUME_HOLISTIC_MODEL` | `moonshot/kimi-k2-0905-preview` | resume analyzer step 3 |
| `DREAM_JOB_NORMALIZE_MODEL` | `openai/gpt-5-nano-2025-08-07` | Dream Job pass 1 |
| `DREAM_JOB_FIT_MODEL` | `moonshot/kimi-k2-0905-preview` | Dream Job pass 2 |
| `SUGGESTION_APPLY_MODEL` | `openai/gpt-4.1-mini-2025-04-14` | suggestion accept + bulk-apply |
| `GEMINI_MODEL` | `gemini-2.5-flash` | live interview |
| `DEFAULT_MODEL` | `gpt-4.1-nano-2025-04-14` | classic LangGraph interview (user-overridable via `user_settings`) |

See [[Config-driven fail-loud LLM calls]] for why this changed.

## Fail-loud, not silent-default (fixed 2026-07-06 — was CRITICAL)

#gotcha **Fixed bug, keep for context:** every LLM step in `resume_analyzer_service.py` and `dream_job_analyzer_service.py` used to wrap its call in `try/except Exception` and return a **zero-filled default dict** on any failure (bad JSON, provider 404, expired key). Since the AIML key was disabled at one point during testing, this meant `status: "completed"` reports full of `score: 0` and empty lists — the user saw an empty report with **no error indication at all**. All three resume-analysis steps and both Dream Job passes now **re-raise** on failure instead of swallowing it, so the existing background-task `except` handler correctly flips the Firestore doc to `status: "failed"` with the real error. Regression tests (`test_analyzer_fail_loud.py`) assert a provider error or malformed JSON raises, not returns zeros.

## Interview pipeline (LangGraph, classic REST mode)

`services/workflow_manager.py` defines a LangGraph state machine (see [[LangGraph Workflow]] for the full graph). Report generation is synchronous at interview completion.

## Live interview pipeline (WebSocket, Gemini) — shipped, not backlog

**Correction to earlier vault state:** this was previously listed as backlog/unclear. It is a real, shipped feature: `POST /interview/prepare` (uploads resume+JD to Gemini File API, generates a question plan) → `WS /ws/interview/{session_id}` (streaming conversational Q&A via `LiveInterviewAgent`). See [[Live Interview]].

## FAISS vector store

Now **per-session**, not a single shared path — see [[RAG System]] for the cross-user-leak fix.

## Resume analysis pipeline

3-step async, launched as `BackgroundTask` on resume upload — see [[Resume Analysis]] for the full step-by-step and the suggestion-persistence model.

## Dream Job pipeline

2-pass async pipeline — see [[Dream Job]]. Both passes now cap embedded user text (~12-15K chars) and set `max_tokens` explicitly (added 2026-07, cost hardening).

## Cost/timeout hardening (added 2026-07)

Per-call timeouts tightened 320s→60s (they were pathologically long, and the SDK's own retry logic could multiply the wait); overall analysis timeouts tightened 480s→240s (resume) / 180s (Dream Job); `max_retries=2` explicit on every `AsyncOpenAI` client; `max_tokens` set on every completion call (previously unbounded); each analyzer service's `httpx.AsyncClient` is now explicitly closed via `aclose()` in the background-task `finally` block (was leaking a connection per analysis run). `max_questions` bounded 1–20 on both interview-creation routes.

## Prompts

All LLM prompts live in `backend-microservice/app/utils/prompts.py`. Centralised — change one file to adjust behaviour across the pipeline.

[[Codebase Map]] · [[Backend]] · [[Dream Job]] · [[Live Interview]] · [[Resume Analysis]]
