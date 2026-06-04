---
type: codebase-note
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - codebase
  - langgraph
  - interview
---
# LangGraph Workflow

`services/workflow_manager.py` — `InterviewWorkflowManager` class. Builds and runs the LangGraph `StateGraph` for the interview.

## Graph

```
[document_processor] → [planner] → [question_generator] → [rag_retriever]
                                          ↑                       ↓
                                          │                [response_analyzer]
                                          │                       ↓
                                          │                 [note_taker]
                                          │                /            \
                                       "continue"      "complete"
                                          │                       ↓
                                          └─────────      [report_generator] → END
```

## Nodes

| Node | Method | What it does |
|---|---|---|
| `document_processor` | `_process_documents` | Initialises state lists; sets `next_action = "plan"` |
| `planner` | `_create_interview_plan` | Calls `InterviewPlanner.create_interview_plan()` → `interview_plan[]` |
| `question_generator` | `_generate_next_question` | Reads `interview_plan[current_question_idx]`, sets `current_question` |
| `rag_retriever` | `_retrieve_context` | FAISS similarity search on `question + answer`; populates `rag_context`; empty string on error |
| `response_analyzer` | `_analyze_response` | `ResponseAnalyzer.analyze_response()` → `current_analysis` string |
| `note_taker` | `_take_notes` | Creates `InterviewNote`, appends to `interview_notes`, updates `conversation_history`, increments `current_question_idx` |
| `report_generator` | `_generate_report` | `ReportGenerator.generate_report()` → `interview_report` |

## Conditional edge: `_should_continue_interview`

```python
if state['current_question_idx'] >= len(state['interview_plan']):
    return "complete"
return "continue"
```

## Important: The graph is not actually invoked end-to-end in production

`InterviewWorkflowManager.execute_workflow()` exists but is NOT called from `server.py`. The REST API drives the workflow **step by step** by calling individual methods directly:

- At session start: `_process_documents` → `_create_interview_plan`
- At each `/interview/answer`: `_retrieve_context` → `_analyze_response` → `_take_notes` → (if done) `_generate_report`

The LangGraph graph is built but used more as a structural blueprint — the actual execution is imperative, not graph-driven, in the REST handlers.

#gotcha This means LangGraph's state-machine guarantees (checkpointing, replay) are NOT being used. If the graph were invoked via `execute_workflow()`, it would try to run the full interview synchronously in one call, which breaks the REST Q&A model.

## InterviewState TypedDict (full shape)

```python
class InterviewState(TypedDict):
    resume_content: str
    job_description: str
    interview_plan: List[Dict]      # [{ question, category, priority, expected_skills, follow_up_prompts }]
    current_question_idx: int
    current_question: str
    candidate_response: str
    interview_notes: List[Dict]     # [{ question, response, timestamp, score, analysis, question_category }]
    conversation_history: List[Dict]  # [{ role, content }]
    interview_report: str
    rag_context: str
    next_action: str
    is_complete: bool
```

[[Codebase Map]] · [[Interview System]] · [[RAG System]]
