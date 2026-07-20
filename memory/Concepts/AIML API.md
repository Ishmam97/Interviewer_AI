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

## Where it's used — now config-driven (2026-07, see [[Config-driven fail-loud LLM calls]])

Model IDs used to be hardcoded per-service; every one is now a `Settings` field in `core/config.py`, overridable by env var without a code change:

| Setting | Default | Used by |
|---|---|---|
| `RESUME_PARSE_MODEL` / `RESUME_SECTION_MODEL` | `openai/gpt-5-nano-2025-08-07` | resume analyzer steps 1-2 |
| `RESUME_HOLISTIC_MODEL` | `moonshot/kimi-k2-0905-preview` | resume analyzer step 3 |
| `DREAM_JOB_NORMALIZE_MODEL` | `openai/gpt-5-nano-2025-08-07` | Dream Job pass 1 |
| `DREAM_JOB_FIT_MODEL` | `moonshot/kimi-k2-0905-preview` | Dream Job pass 2 |
| `SUGGESTION_APPLY_MODEL` | `openai/gpt-4.1-mini-2025-04-14` | suggestion accept + bulk-apply |

`interview_system.py` (via langchain) still defaults to `DEFAULT_MODEL` = `gpt-4.1-nano-2025-04-14`, user-configurable via `user_settings`.

#gotcha The AIML API key has been disabled at least once in production use (confirmed directly by the project owner). This is exactly the failure mode [[Config-driven fail-loud LLM calls]] was fixed for — a disabled/invalid key must now surface as `status: "failed"`, not a silent zero-score "completed" report. See the production roadmap's risk list — re-provisioning the key is a Phase A owner action.

## Timeouts — tightened 2026-07

Both analyzer services now use:
- Per-call: **60s** (was 320s — the SDK's own retry logic could multiply an already-long wait)
- Overall analysis: **240s resume / 180s Dream Job** (was 480s for both)
- `max_retries=2` explicit; `max_tokens` set on every completion call (previously unbounded)

[[Concepts MOC]] · [[AI Pipeline]] · [[Resume Analysis]] · [[Dream Job]] · [[Config-driven fail-loud LLM calls]]
