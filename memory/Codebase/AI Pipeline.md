---
type: codebase-note
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - codebase
  - ai
  - langgraph
  - rag
---
# AI Pipeline

The core intelligence of the app. All LLM calls go through an OpenAI-compatible API (AIML API by default, configurable via `OPENAI_BASE_URL`).

## LLM configuration

| Setting | Default | Override |
|---|---|---|
| Model | `gpt-4.1-nano-2025-04-14` (interview flow) | `user_settings` Firestore doc |
| Base URL | `https://api.aimlapi.com/v1` | `OPENAI_BASE_URL` env var |
| Embeddings | `text-embedding-3-small` | `use_ollama` flag → `granite-embedding:30m` |
| Dream Job LLM | Kimi (2nd pass) | hardcoded in `dream_job_analyzer_service.py` |

## Interview pipeline (LangGraph)

`services/workflow_manager.py` defines a LangGraph state machine:

```
document_processing → interview_planning → question_generation → answer_analysis → (loop) → report_generation
```

- **document_processing** (`services/document_processor.py`): parse PDF/TXT resume + JD; extract text
- **interview_planning** (`services/interview_planner.py`): generate question plan (topics, count, difficulty) via LLM
- **RAG** (`services/rag_system.py`): FAISS index built from resume + JD at session start; top-k chunks retrieved per question for context
- **question_generation** (`services/interview_system.py`): uses plan + RAG context to generate each question
- **answer_analysis** (`services/response_analyzer.py`): scores answer 0–10, identifies strengths/weaknesses, suggests improvements
- **report_generation** (`services/report_generator.py`): synthesizes all Q&A, scores, and analysis into a final report

Report generation is synchronous at interview completion (by design — Cloud Functions compatibility).

## FAISS vector store

- Index built at interview start from uploaded documents
- Persisted to `./vector_stores/interview_faiss_index` (Docker volume)
- Survives container restarts via volume mount
- #gotcha If the session is reconstructed from Firestore (e.g. after pod restart), FAISS is NOT available — RAG falls back to no-context mode silently

## Resume analysis pipeline

3-step async, launched as BackgroundTask on resume upload:

1. **parsing_document** — gpt-5-nano extracts structured JSON (name, contact, summary, experience, education, skills, certs, projects)
2. **analyzing_sections** — 7 parallel LLM calls, one per section; each returns `score`, `strengths`, `weaknesses`, `tips`, `suggestions[]`
3. **holistic_review** — cross-section assessment, overall score, top 3 improvements

Each suggestion: `{ id: unique_string, text: string, status: "pending" }`. User accepts/rejects; accepted suggestions trigger an AI resume edit (diff applied to stored resume text).

## Dream Job pipeline

2-pass async pipeline in `services/dream_job_analyzer_service.py`:

1. **normalizing** — `gpt-5-nano` parses JD into structured fields (role, company, required skills, nice-to-haves, etc.)
2. **analyzing** — Kimi LLM performs fit analysis against resume, returns fit_score, interview_chance, matching_strengths, gaps, points_to_improve, resume_tailoring_plan, suggested_projects, ats_keyword_coverage

Frontend polls `GET /dream-job/{id}/status` every 2s during analysis.

## Prompts

All LLM prompts live in `backend-microservice/app/utils/prompts.py`. Centralised — change one file to adjust behaviour across the pipeline.

[[Codebase Map]] · [[Backend]] · [[Dream Job]]
