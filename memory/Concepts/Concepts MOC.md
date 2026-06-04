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

- [[RAG]] — Retrieval-Augmented Generation; how vector search grounds LLM responses in the resume/JD
- [[LangGraph]] — graph-based AI workflow library; used as structural blueprint (not invoked end-to-end)
- [[AIML API]] — OpenAI-compatible LLM proxy aggregating OpenAI, Kimi, and others via a single key/URL

## Infrastructure / patterns

- [[BackgroundTasks over Celery]] _(Decisions)_ — async job pattern; not durable; upgrade path documented

## Data

- [[Data Model]] _(Codebase)_ — all Firestore collections and schemas

## Auth

- [[Auth Flow]] _(Codebase)_ — Firebase Auth token verification, sign-up/sign-in flows, no dummy-token bypass in current code

[[Home]]
