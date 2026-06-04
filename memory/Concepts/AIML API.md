---
type: concept
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - concept
  - ai
  - llm
  - api
---
# AIML API

AIML API (`https://api.aimlapi.com/v1`) is an OpenAI-compatible proxy that provides access to multiple LLM providers through a single OpenAI-format interface.

## Why it's used here

Instead of calling OpenAI directly, the app routes through AIML API to access:
- OpenAI models (`gpt-4.1-nano`, `gpt-5-nano-2025-08-07`)
- Kimi/Moonshot (`moonshot/kimi-k2-0905-preview`) — used for holistic resume review and Dream Job fit analysis
- Other models as needed

Single API key, single base URL. Configured via `OPENAI_BASE_URL=https://api.aimlapi.com/v1` in `.env`.

## Model names on AIML API

Models are referenced with their provider prefix: `openai/gpt-5-nano-2025-08-07`, `moonshot/kimi-k2-0905-preview`. The client is an `AsyncOpenAI` instance pointed at the AIML base URL.

## Where it's used

| Service | Models |
|---|---|
| `resume_analyzer_service.py` | `openai/gpt-5-nano` (parse + sections), `moonshot/kimi-k2` (holistic) |
| `dream_job_analyzer_service.py` | `openai/gpt-5-nano` (normalize), `moonshot/kimi-k2` (fit analysis) |
| `interview_system.py` (via langchain) | `gpt-4.1-nano` default, user-configurable |

## Timeouts

Both analyzer services use:
- Per-call: 320s (httpx timeout on the `AsyncOpenAI` client)
- Overall analysis: 480s (`asyncio.wait_for`)

These are very long — Kimi calls for complex analyses can take 1-3 minutes.

[[Concepts MOC]] · [[AI Pipeline]] · [[Resume Analysis]] · [[Dream Job]]
