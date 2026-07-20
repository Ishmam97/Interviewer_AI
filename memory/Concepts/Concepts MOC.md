---
type: moc
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - concept
  - moc
---
# Concepts MOC

Domain and technical concepts used in this project.

## AI / ML

- [[RAG]] — Retrieval-Augmented Generation; how vector search grounds LLM responses in the resume/JD. Now per-session — see [[Session-scoped FAISS index]]
- [[LangGraph]] — graph-based AI workflow library; used as structural blueprint (not invoked end-to-end)
- [[AIML API]] — OpenAI-compatible LLM proxy aggregating OpenAI, Kimi, and others via a single key/URL. Model IDs are now config-driven, not hardcoded — see [[Config-driven fail-loud LLM calls]]

## Infrastructure / patterns

- [[BackgroundTasks over Celery]] _(Decisions)_ — async job pattern; not durable, mitigated (not fixed) by a stale-analysis sweeper as of 2026-07-06
- [[Security Hardening]] _(Codebase)_ — rate limiting, SSRF guard, upload sniffing, dependency CVEs, non-root Docker — the full 2026-07 record
- [[Rate limiting via slowapi]] _(Decisions)_ — the bearer-token-keyed limiter design and why

## Data

- [[Data Model]] _(Codebase)_ — all Firestore collections and schemas
- [[Standardize on working_parsed_sections]] _(Decisions)_ — resolved a 3-way split in resume-edit persistence

## Auth

- [[Auth Flow]] _(Codebase)_ — Firebase Auth token verification, sign-up/sign-in flows, no dev bypass or `/test/*` routes exist server-side

[[Home]]
