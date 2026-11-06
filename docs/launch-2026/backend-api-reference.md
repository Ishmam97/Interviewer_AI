# Backend API reference

**Source inspected:** `backend-microservice/app/server.py`, `app/models/`, and `app/database/firebase_db.py` in this checkout on 2026-11-06. This is a static route inventory, not a live API contract test. Request and response summaries below are taken from handler signatures and return statements; details can vary with Firestore document contents and Pydantic response models. All endpoints are mounted at the service root; no global `/api/v1` prefix is applied in this file.

## Conventions and authentication

- Most HTTP routes authenticate with `Depends(get_current_user)`, which extracts a bearer credential and validates its Firebase ID token. “Bearer” below means this dependency. The WebSocket route authenticates separately using a token in its first JSON message.
- Public routes in this inventory: `POST /beta-signups`, `GET /health`, `GET /admin/health`, `POST /auth/signup`, `POST /auth/signin`. `POST /auth/google` takes Firebase ID token as the HTTP Bearer credential itself.
- Rate limits are attached where shown below using SlowAPI. This is source configuration, not proof of a shared/distributed limiter in deployment.
- Firestore is accessed through `FirebaseManager` in `app/database/firebase_db.py`, with some resume routes also directly accessing collections. Async resume and Dream Job jobs use FastAPI `BackgroundTasks` in the current process; they are not durable queue workers.
- `HTTPException` responses use FastAPI's standard `{"detail": ...}` shape. Successful response fields below reflect code, not a generated OpenAPI snapshot.

## Health, signup, and authentication

| Method and path | Auth / limit | Request | Success response | Behavior and storage |
|---|---|---|---|---|
| `POST /beta-signups` | Public; 5/minute per remote IP | JSON `{email, consent: true, website?: string}` (`BetaSignupRequest` lowercases/validates email; strict consent true; honeypot optional) | `{message: "Thanks for your interest."}` | Filled `website` honeypot returns generic success without saving. Otherwise `FirebaseManager.create_beta_signup(email)` stores in `beta_signups`; storage error → 503. See [beta operations](beta-operations.md). |
| `GET /health` | Public | none | `{status: "healthy", timestamp}` | Process-level health only; no dependency check. |
| `GET /admin/health` | Public in source | none | `{api_status, database_status, timestamp}` | Probes Firestore but returns HTTP 200 even if database is unhealthy. |
| `POST /auth/signup` | Public; 10/minute | JSON `{email, password, full_name?}` | `{message, user, session, needs_setup: true}` | Firebase signup; exchanges custom token when needed. Existing account → 409; other signup error → 400. |
| `POST /auth/signin` | Public; 10/minute | JSON `{email, password}` | `{message, user, session, needs_setup}` | Firebase sign in; checks profile completeness. Invalid credentials → 401. |
| `POST /auth/signout` | Bearer | none | `{message: "Signed out"}` | Response only; client clears token. |
| `POST /auth/google` | Firebase ID token as HTTP Bearer | `Authorization: Bearer <Firebase ID token>` | `{user: {id,email,name}, needs_setup}` | Verifies token and gets/creates profile; no JSON body. Missing/invalid credential → 401. |
| `GET /auth/me` | Bearer | none | `{user: {id,email,name,providers,has_password}}` | Reads Firebase provider metadata. |
| `POST /auth/password` | Bearer | JSON `{new_password}` | See handler's success message | Updates password for authenticated user; password policy/provider errors come from handler/Firebase. |

## Profile and settings

| Method and path | Auth / limit | Request | Success response | Behavior and storage |
|---|---|---|---|---|
| `GET /profile` | Bearer | none | User profile document/shape | Reads `profiles/{uid}`. |
| `PUT /profile` | Bearer | JSON optional fields `full_name`, `job_title`, `years_experience`, `bio`, `location`, `target_roles`, `profile_complete` | `{message: ...}` | Updates user profile; request model is `ProfileUpdateRequest`. |
| `GET /settings` | Bearer | none | `{settings: {..., user_api_key_set: boolean}}` | Reads `user_settings/{uid}`; removes raw `user_api_key` before response. |
| `PUT /settings` | Bearer | JSON optional `max_questions`, `model_name`, `temperature`, `api_provider`, `user_api_key`, `base_url` | `{message: "Settings updated successfully"}` | Writes supplied non-`None` settings to `user_settings/{uid}`. This handler accepts arbitrary `base_url`; see backend audit SSRF finding. |

## Resume analysis and editing

| Method and path | Auth / limit | Request | Success response | Behavior / storage |
|---|---|---|---|---|
| `POST /profile/resume` | Bearer; 10/minute | multipart `resume` file | `{analysis_id, status: "processing", message}` | Validates and extracts file; creates `resume_analyses/{id}`, enforces resume quota, then schedules `_run_resume_analysis_bg`. Temp file is deleted in `finally`. |
| `GET /profile/resume/analysis` | Bearer | none | User's resume data/current analysis document | Reads latest/current resume data for UID; missing current analysis → 404. |
| `GET /resume/analysis/{analysis_id}/status` | Bearer | path ID | `{analysis_id,status,current_step,filename}`; includes nested analysis fields when completed | Reads analysis by ID then compares stored `user_id` with caller UID; 404 absent, 403 wrong owner. |
| `POST /profile/resume/suggestions/{suggestion_id}` | Bearer | JSON `{action: "accept"|"reject"}` | Status and, on accept, applied changes (see handler) | Operates on user's current completed analysis. Accept enforces quota and invokes resume-edit operation; reject changes status only. Invalid action → 400. |
| `POST /profile/resume/suggestions/{suggestion_id}/undo` | Bearer | no body required | `{message,suggestion_id}` | Restores one accepted suggestion from one-shot snapshot and returns status to pending. Missing suggestion/snapshot → 404; not accepted → 400. |
| `POST /profile/resumes/{analysis_id}/suggestions/bulk` | Bearer | JSON `{suggestion_ids: string[], section: string}` | `{message,applied_count,not_found_ids,updated_section,section_key,previous_section}` | Checks owner and completed status; reserves suggestion quota; applies selected suggestions with one section-oriented model call; snapshots prior section. |
| `POST /profile/resumes/{analysis_id}/suggestions/undo-section` | Bearer | JSON `{section: string}` | `{message,reverted_ids,restored_section,section_key}` | Restores last bulk section snapshot, resets affected accepted statuses, removes snapshot. |
| `GET /profile/resumes` | Bearer; query `limit=50`, `cursor?` | none | `{resumes: [...], next_cursor}` | Lists resume analysis summaries for UID, active marker and parsed-section availability. |
| `GET /profile/resumes/{analysis_id}` | Bearer | path ID | `{analysis_id,filename,created_at,status,resume_analysis:{overall,sections,ats,lackings,quality_score,parsed_sections,usage}}` | Fetches analysis and parsed sections; explicit owner check; 404/403. |
| `DELETE /profile/resumes/{analysis_id}` | Bearer | path ID | `{message,analysis_id}` | Calls owner-scoped repository delete; failure/missing → 404. |
| `POST /profile/resumes/{analysis_id}/set-active` | Bearer | path ID | `{message,analysis_id}` | Sets active resume for caller; failure/missing → 404. |
| `POST /analyze/resume` | Bearer; 10/minute | multipart `resume` file | `{analysis: ...}` | Legacy synchronous analysis helper. Unlike `/profile/resume`, this route does not call `_enforce_quota` in the inspected handler. |

**Background lifecycle:** `upload_resume` creates the Firestore analysis record before scheduling the task. `_run_resume_analysis_bg` updates status/steps and persists analysis/parsed content. The task uses FastAPI in-process background execution; a process restart can interrupt it. Client poll route is `GET /resume/analysis/{id}/status`.

## Classic interview, history, and reports

| Method and path | Auth / limit | Request | Success response | Behavior / storage |
|---|---|---|---|---|
| `POST /interview/start` | Bearer; 10/minute | multipart `resume`, `job_description`; `max_questions` (default 3, 1–20), `model_name`, `temperature` | `InterviewResponse`: `session_id`, `current_question`, `is_complete`, current index, total question count | Loads provider settings, checks quota, extracts docs, creates per-session FAISS path, initializes interview system and puts state in `_active_sessions`. It does not persist the active runtime state for reconstruction. |
| `POST /interview/answer` | Bearer; 20/minute | JSON `{session_id, answer}` | `AnalysisResponse`: `session_id, score, analysis, is_complete, next_question` | Looks up `_active_sessions`, processes answer and next question. The inspected handler does not compare stored session `user_id` with caller, and does not write updated active state to Firestore in this route. Missing process-local session → 404. |
| `GET /interview/sessions` | Bearer; query `limit=50`, `cursor?` | none | `{sessions, next_cursor}` | Lists sessions belonging to caller. Repository errors are caught and converted to an empty list. |
| `GET /interview/sessions/{session_id}` | Bearer | path ID | Session document | Calls `get_interview_session(session_id)` without a UID argument; handler does not verify ownership in current source. Missing → 404. |
| `GET /interview/{session_id}/report` | Bearer | path ID | `{content, report_id, session_id}` | Queries saved report by `(uid, session_id)`; missing → 404. This is the client `getInterviewReport` path. |
| `GET /interview/sessions/{session_id}/report` | Bearer | path ID | Current handler returns session document | Despite the path name, inspected handler calls `get_interview_session(session_id)` and returns the session; it does not generate/fetch report content or check owner. |
| `GET /reports` | Bearer; query `limit=50`, `cursor?` | none | `{reports, next_cursor}` | Lists current user's reports. Repository exceptions become empty list. |
| `GET /dashboard/stats` | Bearer | none | Stats dictionary | Calls aggregate repository function; exceptions return `{}`. |

**No DELETE interview-session route is registered in `server.py`**, although the current frontend API client has `deleteInterviewSession()` targeting `DELETE /interview/{id}`. Static source mismatch; see frontend reference.

## Live interview

| Method and path | Auth / limit | Request | Success response | Behavior / storage |
|---|---|---|---|---|
| `POST /interview/prepare` | Bearer; 10/minute | multipart `resume`, `job_description`, optional `interview_type` (default `Job Interview`), `max_questions` (default 5, 1–20) | `{session_id,question_count,interview_type,questions_preview}` | Validates docs, enforces interview quota, uploads files to Gemini and generates a question plan. Session metadata is stored in process-local `_live_sessions`. |
| `WS /ws/interview/{session_id}` | First JSON message `{type:"auth",token}` | After auth: server sends `authenticated`, then `ready`; client sends answer/end; server emits streaming text/events | Event protocol includes `ai_text`, `complete`, `report_ready`, `error`; exact fields vary by event | Verifies Firebase token and compares session owner UID. Uses Gemini live agent. On transcript completion generates report and writes interview session/report data; cleans `_live_sessions` in `finally`. Provider uploaded-file deletion is not called in this route according to audit. |

## Dream Job

| Method and path | Auth / limit | Request | Success response | Behavior / storage |
|---|---|---|---|---|
| `POST /dream-job/from-link` | Bearer; 10/minute | JSON `{url}` | `{company,role_title,location,jd_text,source_url,source,error?}` | Calls `job_link_parser.parse_job_url`. Unsafe URL → 400; parser failure → 422; platform warning such as LinkedIn blocked can be returned in `error`. |
| `POST /dream-job` | Bearer; 10/minute | JSON `{company,role_title,jd_text,source,source_url?,resume_analysis_id}` | `{dream_job_id,status:"pending"}` | Verifies selected resume belongs to user and is completed, enforces quota, creates job record, schedules `_run_dream_job_analysis_bg`. |
| `GET /dream-job/{dream_job_id}/status` | Bearer | path ID | `{dream_job_id,status,current_step,error?}` | Reads and owner-checks `dream_jobs` record. |
| `GET /dream-job/{dream_job_id}` | Bearer | path ID | Full Dream Job document | Reads and owner-checks record. |
| `GET /dream-jobs` | Bearer; query `limit=50`, `cursor?` | none | `{dream_jobs,next_cursor}` | Lists caller's job analyses. |
| `DELETE /dream-job/{dream_job_id}` | Bearer | path ID | `{message,dream_job_id}` | Owner-scoped deletion; missing/forbidden → 404. |

Background task statuses include pending/normalizing/analyzing/completed/failed as written by task/service. The task reconstructs resume text from parsed resume sections and persists final normalized JD, fit result and usage to the Dream Job record.

## Request models and error handling

Important Pydantic models in `app/server.py` include `UserCredentials`, `ProfileUpdateRequest`, `SettingsUpdateRequest`, `AnswerRequest`, `PasswordUpdateRequest`, `SuggestionActionRequest`, `BulkSuggestionRequest`, `SectionUndoRequest`, `DreamJobFromLinkRequest`, and `DreamJobCreateRequest`. Interview start response models are in `app/services/models.py` (imported by server), not `app/models/interview_models.py`.

Common errors observed in handlers:

- 400: validation/business precondition or rejected URL/action.
- 401: missing/invalid credentials or sign-in rejection.
- 402: quota exhausted (`_enforce_quota`).
- 403: ownership mismatch on routes with an explicit check.
- 404: missing object/session/snapshot or unavailable in-process interview state.
- 409: duplicate signup.
- 422: parser could not extract job posting (and normal FastAPI validation errors).
- 429: route limiter; separate meaning from quota 402.
- 500/503: operation or storage failure paths.

## Source-versus-runtime status and known limitations

The inventory above is **source-verified only**. No request was sent to a running FastAPI server, Firebase, Gemini, OpenAI-compatible provider, job board, or deployment. Thus route reachability, actual auth middleware, field compatibility with current external clients, and production Firestore rules are unverified.

Important source-level limits documented in the backend audit: several interview endpoints fetch globally keyed IDs without owner checks; sessions and async tasks are process-local; the quota store failure path can fail open; legacy `/analyze/resume` is not metered in its handler; settings permit a user-controlled provider base URL; and the live endpoint stores provider file references without visible cleanup. See [backend audit](../audits/2026-11-06-backend.md) for full findings and acceptance criteria.
