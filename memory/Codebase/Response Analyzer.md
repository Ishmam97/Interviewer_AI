---
type: codebase-note
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - codebase
  - interview
  - scoring
---
# Response Analyzer

`services/response_analyzer.py` — `ResponseAnalyzer` class. Scores and analyses candidate answers during interviews.

## What it does

Called per answer in the LangGraph `response_analyzer` node. Receives:
- `question` — the interview question asked
- `response` — the candidate's answer
- `rag_context` — top-3 FAISS chunks from the resume/JD (may be empty string on FAISS miss)
- `conversation_history` — last 6 exchanges (rolling window)

Returns a freeform text string via `ANALYSIS_PROMPT` from `utils/prompts.py`.

## Score extraction

#gotcha Score extraction is **regex/line-based**, not structured JSON. `extract_score()` scans the LLM response line by line for `SCORE: N`. If the LLM omits that exact prefix or formats it differently, the score defaults to **5**. Silently. This means scores can be wrong without any error surfacing.

```python
def extract_score(self, analysis: str) -> int:
    score = 5  # default
    for line in analysis.split('\n'):
        if line.startswith('SCORE:'):
            try:
                score = int(line.split(':')[1].strip().split()[0])
            except:
                score = 5
            break
    return score
```

## InterviewNote shape

Created by `create_interview_note()` after each answer:
```python
{
    "question": str,
    "response": str,
    "timestamp": datetime.now().isoformat(),
    "score": int,           # 0-10 extracted from analysis text
    "analysis": str,        # full LLM response
    "question_category": str  # from interview_plan[idx].category
}
```

## Conversation history window

Only the last 6 exchanges are passed to the LLM for context. This keeps token usage bounded but means the LLM has no memory of questions >6 turns ago.

[[Codebase Map]] · [[Interview System]] · [[LangGraph Workflow]]
