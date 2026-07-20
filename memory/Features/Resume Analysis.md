---
type: feature-note
status: shipped
created: '2026-06-02'
updated: '2026-07-19'
tags:
  - feature
  - resume
  - ai-pipeline
---
# Resume Analysis

Users upload a resume (PDF or TXT) and the backend runs a 3-step async AI analysis pipeline. Results drive an interactive suggestions system where users can accept/reject AI-proposed improvements, with each accepted suggestion triggering an AI-applied edit to the resume's **working copy**.

## Trigger

`POST /profile/resume` (rate-limited 10/min) — multipart file upload. Backend validates upload content (magic bytes, not just extension — see [[Security Hardening]]), creates an analysis record in Firestore (`status: "processing"`), then launches the pipeline as a `BackgroundTask` and returns `{ analysis_id, status: "processing" }`.

#gotcha (fixed 2026-07) `create_resume_analysis`'s success/failure return value used to be ignored — if the Firestore write failed, a background task was still enqueued against a doc that didn't exist, so the client would poll a 404 forever. The route now checks the return value and returns HTTP 500 immediately if doc creation fails, and never enqueues the task.

Frontend polls `GET /resume/analysis/{id}/status` until `status` is `"completed"` or `"failed"`. If the process crashes mid-analysis, a **startup + 5-minute sweeper** now fails the doc out after 10 minutes stuck in `processing` (see [[Backend]] and [[BackgroundTasks over Celery]]) — previously it stayed `processing` forever with no recovery.

## Pipeline — 3 steps (models now config-driven, see [[AI Pipeline]])

All LLM calls use AIML API. Per-call timeout 60s (was 320s), overall 240s (was 480s). Every step **re-raises on failure** — no more silent zero-score defaults (see [[Config-driven fail-loud LLM calls]]).

### Step 1 — `parsing_document` (`RESUME_PARSE_MODEL`)
Extracts structured JSON: `name, contact{email,phone,linkedin,location}, summary, experience[], education[], skills[], certifications[], projects[]`. Resume text capped ~12,000 chars before embedding in the prompt (cost hardening, added 2026-07).

### Step 2 — `analyzing_sections` (`RESUME_SECTION_MODEL`)
7 **parallel** LLM calls, one per section. Each returns `{ name, found, score 0-100, content_snippet, strengths[], weaknesses[], tips[], suggestions[] }`.

### Step 3 — `holistic_review` (`RESUME_HOLISTIC_MODEL`, Kimi)
Whole-resume assessment: `overall_score, quality_score, summary, strengths[], weaknesses[], top_tips[], lackings[], ats{score,keywords_found[],keywords_missing[],formatting_issues[]}, suggestions[]`.

## Suggestions system — persistence model migrated (2026-07-19)

Every suggestion: `{ id, text, status: "pending"|"accepted"|"rejected" }`.

#gotcha **Migrated bug, keep for context:** the accept/undo flow used to write the LLM-edited resume to `profile.edited_resume_data` (a field on the user's profile doc), while the *bulk*-apply flow and Dream Job's resume input both read from a **different** store — `resume_parsed_sections/{analysis_id}.working_parsed_sections`. Two competing sources of truth for "the current edited resume," and a `set_working_parsed_sections` FirebaseManager method existed but was never called by the single-suggestion path. **Standardized on `working_parsed_sections` everywhere** (user's explicit direction): `_apply_suggestion_to_resume` and `_restore_suggestion_snapshot` now both read/write via `fb.get_resume_parsed_doc`/`fb.set_working_parsed_sections(analysis_id, user_id, data)`, and `profile.edited_resume_data` is no longer written or read anywhere in the codebase (verified via grep — zero references left, frontend included). Undo snapshots are now keyed `{user_id}:{analysis_id}:{suggestion_id}` (was `{user_id}:{suggestion_id}` — the old 2-part key couldn't disambiguate across re-analyses of the same resume).

- `POST /profile/resume/suggestions/{suggestion_id}` — accept or reject (accept triggers the LLM-applied edit above)
- `POST /profile/resume/suggestions/{suggestion_id}/undo` — restores from the session-scoped snapshot
- `POST /profile/resumes/{id}/suggestions/bulk` — apply multiple suggestions to one section in a single focused LLM call (uses the same `working_parsed_sections` store; not yet migrated to call `set_working_parsed_sections` directly — still does a raw Firestore `.update()`, a known minor inconsistency, untested, low priority)
- `POST /profile/resumes/{id}/suggestions/undo-section` — undo a whole section's bulk changes

This resolved the last 5 failing backend tests in the suite (backend now 147/147 green).

## Multi-resume

Users can have multiple analyses. One is flagged `active` — what Dream Job uses by default. `POST /profile/resumes/{id}/set-active` switches it.

## Frontend

`components/ResumeAnalyzer.tsx` — polling now distinguishes a genuine 404 ("no resume yet," expected empty state) from any other error status via `error.status` (added on `api.js`'s thrown errors, 2026-07) — previously any load failure looked identical to "no resume uploaded," hiding real backend problems from the user.
`components/ResumeManager.tsx` — its own status-poll now tolerates a run of transient errors (was: any single failed poll silently stopped forever with the "processing" badge stuck).

## Known weaknesses (open — see production roadmap)

- `BackgroundTasks` still non-durable at the architecture level (the sweeper mitigates the symptom).
- No retry on individual step failure.
- 7 parallel section calls can hit AIML API rate limits under load.
- Bulk-apply's raw Firestore write bypasses `set_working_parsed_sections`'s ownership check (minor, untested).

[[Features MOC]] · [[AI Pipeline]] · [[Dream Job]] · [[Config-driven fail-loud LLM calls]]
