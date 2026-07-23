---
type: decision
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - decision
  - ai
  - llm
  - aiml-api
---
# Decision: AIML API as the LLM Proxy

LLM calls go through AIML API (`https://api.aimlapi.com/v1`) rather than directly to OpenAI or individual providers.

**Why:** AIML API is an OpenAI-compatible proxy that aggregates multiple model providers. A single API key and base URL gives access to OpenAI models, Kimi/Moonshot, and others. This lets the app use `moonshot/kimi-k2-0905-preview` for holistic analysis (better for long-context synthesis) while using `openai/gpt-5-nano` for cheap fast parsing — all from the same `AsyncOpenAI` client.

**Trade-off:**
- Adds a dependency on a third-party proxy — if AIML API has downtime, the entire AI pipeline fails
- Model names use provider-prefixed strings (`openai/gpt-5-nano-2025-08-07`) — different from vanilla OpenAI naming
- Pricing and rate limits are AIML's, not the model provider's directly
- Switching away requires changing `OPENAI_BASE_URL` and potentially model name strings

**How to apply:** Always use `OPENAI_BASE_URL`/`AIML_BASE_URL` from config when constructing `AsyncOpenAI` or LangChain clients. Don't hardcode `api.openai.com`. When adding a new LLM call, pick the right model tier: `gpt-5-nano` for cheap structured extraction, Kimi for long-context synthesis — and add the model ID as a new `Settings` field, never a hardcoded string (see [[Config-driven fail-loud LLM calls]]).

**Update 2026-07:** the key-was-disabled failure mode this trade-off warned about actually happened — see [[Config-driven fail-loud LLM calls]] for how the resulting silent-zero-score bug was fixed, and [[AIML API]] for the current config-driven model list and tightened timeouts.

[[Decisions Log]] · [[AIML API]] · [[AI Pipeline]]
