---
type: feature-note
status: shipped
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - feature
  - interview
  - langgraph
---
# Interview System

The core product feature. Users upload a resume + job description, start an interview, answer AI-generated questions, and receive a final report with scores.

## Start flow

`POST /interview/start` — multipart form with resume file + JD text (or text fields). Backend:

1. Creates `InterviewSystem` with user's LLM settings (`api_provider`, `model`, `temperature`, custom key if set)
2. Saves uploaded files to temp paths
3. Calls `interview_system.start_interactive_interview()`:
   - `setup_rag_system()` — builds FAISS index from resume + JD chunks (or loads existing)
   - `_process_documents()` — initialises `InterviewState`
   - `_create_interview_plan()` — calls `InterviewPlanner.create_interview_plan()` → LLM generates JSON plan
4. Saves session to Firestore (`interview_sessions` collection)
5. Adds to in-memory `_active_sessions` dict
6. Returns first question

## Answer flow

`POST /interview/answer` — `{ session_id, answer }`. Backend:

1. Retrieves session from `_active_sessions` (or reconstructs from Firestore)
2. `workflow_manager._retrieve_context(state)` — FAISS similarity search on `question + answer` → `rag_context`
3. `workflow_manager._analyze_response(state)` — `ResponseAnalyzer.analyze_response()` → LLM scores the answer (see [[Response Analyzer]])
4. `workflow_manager._take_notes(state)` — appends `InterviewNote` to `interview_notes[]`, advances `current_question_idx`
5. `workflow_manager._should_continue_interview()` — if `current_question_idx >= len(interview_plan)` → complete
6. If continuing: generate next question and return it
7. If complete: `workflow_manager._generate_report()` → `ReportGenerator.generate_report()` → save to Firestore and return report

## LangGraph state machine

Nodes and edges in `services/workflow_manager.py`:

```
document_processor → planner → question_generator → rag_retriever
                                        ↑                    ↓
                                        │            response_analyzer
                                        │                    ↓
                                        │              note_taker
                                        │             /         \
                                   continue        complete
                                        │                    ↓
                                        └──────────   report_generator → END
```

`_should_continue_interview` is the conditional edge on `note_taker`.

## InterviewState (TypedDict)

```python
resume_content: str
job_description: str
interview_plan: List[Dict]     # [{ question, category, priority, expected_skills, follow_up_prompts }]
current_question_idx: int
current_question: str
candidate_response: str
interview_notes: List[Dict]    # [{ question, response, timestamp, score, analysis, question_category }]
conversation_history: List[Dict]  # [{ role: "interviewer"|"candidate", content }]
interview_report: str
rag_context: str
next_action: str
is_complete: bool
```

## InterviewConfig defaults

```python
max_questions: int = 5
chunk_size: int = 800
chunk_overlap: int = 150
rag_k_results: int = 3
temperature: float = 0.3
model_name: str = "gemini-2.5-flash"
```

Overridden by `user_settings` Firestore doc.

## LLM providers

`interview_system._build_llm_and_embeddings()` supports three providers:

| `api_provider` | LLM class | Embeddings |
|---|---|---|
| `"openai"` (default) | `ChatOpenAI` (+ `OPENAI_BASE_URL`) | `OpenAIEmbeddings` `text-embedding-3-small` |
| `"gemini"` | `ChatGoogleGenerativeAI` | `GoogleGenerativeAIEmbeddings` `gemini-embedding-2-preview` |
| `"anthropic"` | `ChatAnthropic` | Falls back to `OpenAIEmbeddings` via system AIML key |

## Session persistence

Sessions are written to Firestore **before** being cached in `_active_sessions`. If a request arrives for a session not in the in-memory cache, `_reconstruct_session()` rebuilds `InterviewState` from Firestore data — but **without the FAISS index** (it was in-memory/volume, not in Firestore). RAG is unavailable for reconstructed sessions.

## Report generation

`ReportGenerator.generate_report()` uses `REPORT_PROMPT` from `utils/prompts.py`. Inputs are truncated: `resume_content[:2048]`, `job_description[:1024]`. Returns a markdown string.

#gotcha Score extraction from `ResponseAnalyzer.analyze_response()` is regex-based: parses `SCORE: N` from the LLM's text response. If the LLM doesn't include that exact line, score defaults to 5.

## Test endpoints (no auth)

- `POST /test/interview/start` — starts a session without any authentication
- `POST /test/interview/answer` — submits an answer without authentication

## Dashboard / history

- `GET /interview/sessions` — list user's sessions (no pagination — tech debt)
- `GET /interview/sessions/{id}` — single session detail
- `GET /interview/sessions/{id}/report` — fetch saved report (or generate if session still active)

[[Features MOC]] · [[LangGraph Workflow]] · [[RAG System]] · [[Response Analyzer]] · [[Interview Planner]]
