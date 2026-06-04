---
type: codebase-note
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - codebase
  - firestore
  - data-model
---
# Data Model

Firestore is the only persistent store (no SQL, no Redis). All collections confirmed by reading `firebase_db.py` and `server.py` directly.

## Collections

### `profiles` (doc ID = Firebase UID)
User profile: display name, email, professional background, goals, preferences.

### `user_settings` (doc ID = Firebase UID)
Per-user AI configuration: `api_provider`, `model`, `temperature`, `custom_api_key`.

### `resume_analyses` (sub-collection or top-level, scoped by UID)
Full resume analysis state per upload:
- `status`, `current_step`
- `resume_text` — current resume text (mutated by accepted suggestions)
- `resume_history[]` — previous versions for undo

### `resume_parsed_sections` (doc ID = analysis_id)
Step 1 output: structured JSON of parsed sections (name, contact, experience, education, skills, certs, projects).

### `section_snapshots` 
Per-section analysis results (step 2 output): `score`, `strengths`, `weaknesses`, `tips`, `suggestions[]`.

### `suggestion_snapshots`
Individual suggestion state: `{ id, text, status: "pending"|"accepted"|"rejected" }`.

### `interview_sessions` (auto ID)
Full session lifecycle:
```
uid, session_id, status, conversation_history[], scores[], final_report,
resume_text, jd_text, question_plan, current_question_index,
created_at, updated_at
```

### `interview_reports` (auto ID)
Completed report records: `uid`, `session_id`, `report_text`, `overall_score`, `created_at`.
#gotcha Missing unique constraint on `(uid, session_id)` — `save_interview_report` prevents duplicates in code logic but Firestore has no enforcement; bugs can create duplicate records.

### `dream_jobs` (auto ID)
Dream Job fit analysis documents:
```
uid, dream_job_id, company, role_title, jd_text, jd_normalized,
source: "manual"|"link", source_url,
resume_analysis_id,
status: "pending"|"normalizing"|"analyzing"|"completed"|"failed",
current_step, error,
result: {
  fit_score, interview_chance, fit_summary,
  matching_strengths[], gaps[], points_to_improve[],
  resume_tailoring_plan, suggested_projects[], ats_keyword_coverage
},
usage: { prompt_tokens, completion_tokens, total_tokens },
created_at, updated_at
```

### `token_usage` (auto ID)
Tracks LLM token consumption per request for cost monitoring.

[[Codebase Map]] · [[Backend]] · [[Dream Job]]
