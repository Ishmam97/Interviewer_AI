---
type: codebase-note
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - codebase
  - interview
  - planning
---
# Interview Planner

`services/interview_planner.py` — `InterviewPlanner` class. Generates the interview question plan from resume + JD.

## What it does

Called once at session start in `_create_interview_plan`. Uses `PLANNING_PROMPT` from `utils/prompts.py` with `ChatPromptTemplate`. LLM returns a JSON array; the planner parses and validates it.

## Question plan item shape

```json
{
  "question": "string",
  "category": "experience | technical | behavioral | problem_solving | ...",
  "priority": 1-5,
  "expected_skills": ["string"],
  "follow_up_prompts": ["string"]
}
```

## Question count

Taken from `InterviewConfig.max_questions` (default 5, set from `user_settings`). If the LLM returns more than `max_questions + 2`, the list is trimmed.

## Fallback questions

If the LLM response fails to parse (bad JSON, empty list, API error), `_get_fallback_questions()` returns hardcoded questions:
1. Tell me about your background (experience)
2. Technical skills matching (technical)
3. Challenging problem you solved (problem_solving)
4. Why are you interested in this role (behavioral)
5. Where do you see yourself in 3-5 years (behavioral)

#gotcha The fallback questions are completely generic — they don't reference the actual resume or JD. If the LLM fails at plan generation, users get a generic interview instead of a targeted one, with no visible error.

## JSON cleaning

LLM responses sometimes wrap JSON in ` ```json ... ``` ` fences. `_clean_json_response()` strips them before `json.loads()`.

[[Codebase Map]] · [[Interview System]] · [[LangGraph Workflow]]
