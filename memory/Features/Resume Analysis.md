---
type: feature-note
status: shipped
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - feature
  - resume
  - ai-pipeline
---
# Resume Analysis

Users upload a resume (PDF or TXT) and the backend runs a 3-step async AI analysis pipeline. The results drive an interactive suggestions system where users can accept or reject AI-proposed improvements, with each accepted suggestion triggering an AI resume edit.

## Trigger

`POST /profile/resume` — multipart file upload. Backend saves the file, creates an analysis record in Firestore (`status: "processing"`), then launches the pipeline as a `BackgroundTask` and immediately returns `{ analysis_id, status: "processing" }`.

Frontend polls `GET /resume/analysis/{id}/status` until `status` is `"completed"` or `"failed"`.

## Pipeline — 3 steps

All LLM calls use AIML API (`https://api.aimlapi.com/v1`). Timeouts: per-call 320s, overall 480s.

### Step 1 — `parsing_document`
**Model:** `openai/gpt-5-nano-2025-08-07`

Extracts structured JSON from raw resume text:
```json
{
  "name": "string",
  "contact": { "email", "phone", "linkedin", "location" },
  "summary": "string | null",
  "experience": [{ "title", "company", "duration", "bullets": [] }],
  "education": [{ "degree", "institution", "year" }],
  "skills": [],
  "certifications": [],
  "projects": [{ "name", "description" }]
}
```

### Step 2 — `analyzing_sections`
**Model:** `openai/gpt-5-nano-2025-08-07`

7 **parallel** LLM calls, one per section: `contact`, `summary`, `experience`, `education`, `skills`, `certifications`, `projects`.

Each section returns:
```json
{
  "name": "Experience",
  "found": true,
  "score": 0-100,
  "content_snippet": "first 100 chars",
  "strengths": [],
  "weaknesses": [],
  "tips": [],
  "suggestions": [{ "id": "unique_string", "text": "...", "status": "pending" }]
}
```

### Step 3 — `holistic_review`
**Model:** `moonshot/kimi-k2-0905-preview` (Kimi)

Whole-resume assessment returning:
```json
{
  "overall_score": 0-100,
  "quality_score": 0-100,
  "summary": "2-3 sentence narrative",
  "strengths": [],
  "weaknesses": [],
  "top_tips": [],
  "lackings": [],
  "ats": {
    "score": 0-100,
    "keywords_found": [],
    "keywords_missing": [],
    "formatting_issues": []
  },
  "suggestions": [{ "id", "text", "section": "overall", "status": "pending" }]
}
```

## Suggestions system

Every suggestion has shape: `{ id: unique_string, text: string, status: "pending" | "accepted" | "rejected" }`.

- `POST /profile/resume/suggestions/{suggestion_id}` — accept or reject
- **On accept:** AI rewrites the resume to incorporate the suggestion; the new text replaces `resume_text` in Firestore; old version appended to `resume_history[]` (for undo)
- `POST /profile/resume/suggestions/{suggestion_id}/undo` — restores previous `resume_text` from history
- `POST /profile/resumes/{id}/suggestions/bulk` — accept/reject multiple at once
- `POST /profile/resumes/{id}/suggestions/undo-section` — undo all changes in a section

## Multi-resume

Users can have multiple analyses (uploaded at different times). One is flagged `active`. The active resume is what Dream Job uses by default. `POST /profile/resumes/{id}/set-active` switches the flag.

## Frontend

`components/ResumeAnalyzer.tsx` — multi-step analysis UI with polling. Shows progress through `current_step`, then reveals section scores and suggestions for review.
`components/ResumeManager.tsx` — lists all resumes, allows upload/delete/set-active.

## Known weaknesses

- `BackgroundTasks` not durable — if the process restarts mid-step, the job is silently lost with `status: "processing"` forever
- No retry on individual step failure — if step 2 times out, the whole analysis fails
- 7 parallel section calls can hit AIML API rate limits under load

[[Features MOC]] · [[AI Pipeline]] · [[Dream Job]]
