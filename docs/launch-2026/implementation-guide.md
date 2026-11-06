# Implementation guide: launch 2026

**Repository snapshot:** 2026-11-06. This guide maps the implementation currently present in the repository to the three audits in `docs/audits/`. It is an engineering map, not a production deployment attestation. Route and service names below reflect source inspection; deployment state, provider behavior, rules deployment, telemetry, and legal posture require separate evidence.

## 1. System map

```text
Browser (React/Vite, frontend/src)
  App.tsx → pages/Index.tsx → feature components
  services/api.js (Bearer token; REST + WebSocket)
       │ HTTP / WebSocket
       ▼
FastAPI (backend-microservice/app/server.py)
  auth + request validation + quota checks + orchestration
       ├── services/ (resume, interview, Dream Job, parsing, usage)
       ├── database/firebase_db.py (Firebase Auth + Firestore)
       └── external AI / job-page providers
```

The frontend's `Index` owns the authenticated workspace and selects feature sections. `api.js` centralizes base URLs, token headers and request methods. The FastAPI module currently owns route definitions and much of the orchestration; service modules contain specialized AI and parsing work. `FirebaseManager` is the Firestore access layer. Interview runtime state also lives in process dictionaries, and FastAPI background jobs are in-process, so Firestore persistence does not make those execution paths durable.

### Key entry points

| Layer | Entry point | Responsibility |
|---|---|---|
| Frontend bootstrap | `frontend/src/App.tsx` | Root route, auth/loading shell, public landing versus workspace. |
| Workspace controller | `frontend/src/pages/Index.tsx` | Auth callback, section selection, interview setup, resume state and feature composition. |
| HTTP/WebSocket client | `frontend/src/services/api.js` | API base URL, bearer auth, response handling and feature endpoint methods. |
| Backend app | `backend-microservice/app/server.py` | FastAPI middleware, auth dependency, endpoints, quota calls, background task orchestration. |
| Persistence | `backend-microservice/app/database/firebase_db.py` | Firebase Auth and Firestore operations. |
| Runtime configuration | `backend-microservice/app/core/config.py` | Pydantic settings; inspect names/defaults without copying environment values into docs. |

## 2. User journeys and component ownership

### Entry, identity, and navigation

- `LandingPage.tsx` is the public entry and invokes its `onSignIn` callback. Its integration contract is consumed by `Index`: preserve the expected user object, including `needs_setup`, so token-based automatic sign-in and optional setup remain connected.
- `AuthForm.tsx` handles email/password and Google sign-in UI; `Index` receives the result and chooses setup or the workspace.
- `ProfileSetup.tsx` gathers optional profile and resume information for new users.
- `AppSidebar.tsx` changes `activeSection` in `Index`. The current top-level sections are conditionally mounted rather than URL-routed, so navigation can unmount active feature state.
- `AccountSettings.tsx` handles account preferences, provider configuration, password and resume versions. Do not treat these settings or the current usage counters as proof of a payment subscription.

### Interview practice

- `FileUpload.tsx` accepts document uploads and pasted text for the initial interview. It currently uses browser storage for drafts; see UX finding P0.
- `ClassicInterviewInterface.tsx` calls `apiService.startInterview` then `submitAnswer`, presents per-answer feedback and opens completion/report UI. Audit finding: selected interview type is displayed but omitted from the classic request payload. Failed submission currently risks clearing a user's answer.
- `InterviewInterface.tsx` calls `prepareInterview`, opens a WebSocket from `getInterviewWebSocketUrl`, and streams interview text/state. Preparation errors currently leave the UI in a preparing state per the UX audit.
- `InterviewCompletion.tsx` presents the completed state and next actions. `FullReportViewer.tsx` / `DashboardReportViewer.tsx` display report content.
- Backend classic route sequence: `POST /interview/start` → `POST /interview/answer` → `GET /interview/{session_id}/report` or `GET /interview/sessions/{session_id}/report`. Session listing and dashboard use `GET /interview/sessions`, `/reports`, and `/dashboard/stats`.
- Backend live sequence: `POST /interview/prepare` creates/prepares a session; `WS /ws/interview/{session_id}` exchanges live events. Inspect its authentication behavior separately from HTTP auth: WebSocket code has its own connection path.
- `interview_system.py`, `interview_planner.py`, `response_analyzer.py`, `report_generator.py`, `live_interview_agent.py`, and `rag_system.py` implement interview orchestration and generation. Review model configuration, retrieval isolation, prompt boundaries, timeouts and cost limits when changing this flow.

### Resume analysis and editing

- `ResumeAnalyzer.tsx` uploads a resume, polls analysis status, renders overview/section/suggestion/ATS views, and offers suggestion actions.
- `ResumeManager.tsx` and `ResumeSelector.tsx` cover saved resume versions and selection; `ProfilePage.tsx` edits profile/resume data; `ResumePreview.tsx` renders resume content.
- API methods in `api.js`: `uploadResume`, `getResumeAnalysis`, `getAnalysisStatus`, suggestion accept/reject/undo, working-resume patch, bulk suggestion, section undo, re-analysis, list/get/delete/set-active resume.
- Backend sequence: `POST /profile/resume` validates and stores the upload, creates an analysis record, then schedules `_run_resume_analysis_bg`; the client polls `GET /resume/analysis/{analysis_id}/status`. `ResumeAnalyzerService` parses and analyzes sections. `FirebaseManager` writes analysis/status and parsed data. Suggestions update analysis state and, on accept, apply changes to editable resume data; undo restores a snapshot.
- Storage areas include `profiles/{uid}`, `resume_analyses/{analysis_id}`, `resume_parsed_sections/{analysis_id}`, and `suggestion_snapshots/{uid}:{suggestion_id}`. Confirm owner checks at every identifier-based access and deletion semantics across related records before changing the schema.
- A separate legacy `POST /analyze/resume` path exists in `server.py`; audit it independently for quota and expected UI usage.

### Dream Job targeting

- `DreamJobSetup.tsx` collects company, role, resume and job description or link.
- `DreamJobLanding.tsx` submits/polls asynchronous analysis; its result handoff is rendered by `DreamJobDashboard.tsx`.
- API methods: `parseDreamJobLink`, `createDreamJob`, status/result/list/delete methods.
- Backend routes: `POST /dream-job/from-link` parses a URL; `POST /dream-job` creates the analysis; `/dream-job/{id}/status`, `/dream-job/{id}`, `/dream-jobs`, and `DELETE /dream-job/{id}` manage results. `job_link_parser.py` handles supported and generic pages; `dream_job_analyzer_service.py` generates analysis; `FirebaseManager` persists `dream_jobs` data.
- Keep manual job-description entry as a fallback. Treat link parsing as fallible and subject to SSRF, redirect and response-size controls. Resume tailoring remains explicitly unavailable in the inspected UI; don't describe it as shipped.

### Dashboard, profile, and account

- `Dashboard.tsx` loads sessions/reports and presents stats, filters, history and deletion. Audit finding: combined request failure is presented as empty history; missing scores can be counted as zero.
- `DashboardEmptyState.tsx` renders a genuine first-run state. Preserve the distinction between no data and failed loading.
- `ProfilePage.tsx` edits profile and resume sections. `AccountSettings.tsx` manages settings and resume versions.
- `FirebaseManager` methods for sessions, reports, profile, resumes and usage are in `firebase_db.py`. For every read/mutation keyed by session, report, analysis or job ID, enforce the authenticated owner in the repository query or immediately before access.

## 3. API and data flow index

The full current contract is implemented in `frontend/src/services/api.js` and FastAPI handlers in `backend-microservice/app/server.py`. This compact map is for navigation; confirm request/response models in source before editing.

| Concern | Frontend methods | Backend routes / data store |
|---|---|---|
| Auth | `signUp`, `signIn`, `signOut`, `googleSignIn`, `validateToken`, `setPassword` | `/auth/signup`, `/auth/signin`, `/auth/signout`, `/auth/google`, `/auth/me`, `/auth/password`; Firebase Auth. |
| Profile/settings | `getProfile`, `updateProfile`, `getSettings`, `updateSettings` | `/profile`, `/settings`; `profiles/{uid}`, `user_settings/{uid}`. |
| Classic interview | `startInterview`, `submitAnswer`, `getInterviewSessions`, `deleteInterviewSession`, `getInterviewReport` | `/interview/start`, `/interview/answer`, `/interview/sessions[/{id}]`, report routes; `interview_sessions`, `interview_reports`, plus in-memory active session state. |
| Live interview | `prepareInterview`, `getInterviewWebSocketUrl` | `/interview/prepare`, `/ws/interview/{id}`; in-memory live-session state and Firestore records. |
| Resume | `uploadResume`, status/get, suggestion, working-data, version methods | `/profile/resume`, `/resume/analysis/{id}/status`, `/profile/resume/*`, `/profile/resumes/*`; `resume_analyses`, `resume_parsed_sections`, `profiles`, snapshots. |
| Dream Job | parse/create/status/get/list/delete methods | `/dream-job/from-link`, `/dream-job`, `/dream-job/{id}[ /status]`, `/dream-jobs`; `dream_jobs`. |
| Dashboard | session/report/stats methods | `/reports`, `/dashboard/stats`, session/report routes. |

### Persistence model (as implemented)

- `profiles/{uid}`: profile fields and current editable resume state/metadata.
- `user_settings/{uid}`: user-configurable settings and usage/plan fields used by quota logic. Audit: do not trust client-writable entitlement data if repository Firestore rules are deployed.
- `interview_sessions/{session_id}` and `interview_reports/{report_id}`: interview history and generated reports. Audit notes globally keyed session access in several paths and transient in-memory runtime sessions.
- `resume_analyses/{analysis_id}` and `resume_parsed_sections/{analysis_id}`: status, analysis output and parsed data.
- `suggestion_snapshots/{uid}:{suggestion_id}`: pre-apply data for one-step undo.
- `dream_jobs/{dream_job_id}`: job-specific analysis and status.
- Token-usage records are written by `FirebaseManager.save_token_usage`; verify the event coverage and pricing model before treating them as a complete cost ledger.

## 4. Implementation recipes

These recipes turn recurring audit patterns into concrete change sequences. They are not a claim that work has already been completed.

### A. Add or change an authenticated API feature

1. Define/adjust the Pydantic request and response contract in `app/models/` (or adjacent server models if that route currently defines them locally).
2. Add the route in `server.py`; resolve identity through `get_current_user`, derive UID with `_get_user_id`, validate limits before expensive work, and return explicit typed failures.
3. Add a `FirebaseManager` operation when persistence is needed. Query/update by both object ID and owner UID; don't fetch globally and check only in a later UI layer.
4. Add an `api.js` method that uses the common auth/response helpers. Avoid duplicating base URL, token, error or multipart handling.
5. Connect the method to the owning component with loading, success, empty, retry and terminal-error states. Keep user-entered content on a failed request.
6. Add/update API contract, owner-isolation, failure and UI tests. For launch-critical work, include the audit's two-user or failure-injection acceptance case.

### B. Add an asynchronous analysis/job

1. Create an owner-bound record with a stable identifier and explicit initial status before work begins.
2. Reserve quota/cost budget atomically before queueing; avoid charging for invalid requests. Return the ID and current state.
3. Execute through a durable queue/worker before relying on multi-instance production. Current FastAPI `BackgroundTasks` are in-process and are not durable.
4. Persist checkpoints and result payloads; publish `completed` only after all required results have been stored. Make retries idempotent and define how failed work settles or releases the reservation.
5. Expose owner-scoped status/result routes and bounded polling with backoff, an overall deadline, reconnect after navigation/reload, and distinct `failed`, `timed out`, and `still processing` UI states.
6. Verify worker restart, duplicate delivery, provider timeout and partial-write cases. Track status transitions and costs without logging resume/interview text.

### C. Change quota, plans, or cost controls

1. Inventory every system-funded provider call, including legacy endpoints, interview modes, retries and background steps.
2. Define server-owned entitlement data and a transactional reservation keyed by user, action, period and idempotency key. Handle concurrent requests and month rollover atomically.
3. Permit BYOK exemptions only when the specific call actually uses a validated user credential; a nonempty string must not exempt system-funded requests.
4. Enforce independent per-user and global spend/concurrency ceilings. Return a clear service-unavailable response if the accounting store is unavailable.
5. Test limits, races, reset, provider failure, retries, BYOK mismatch and deployment configuration. A plan label or billing webhook alone is not enforcement evidence.

### D. Modify public landing/auth integration

1. Keep the public landing callback compatible with `Index`'s expected user object and `needs_setup` onboarding behavior.
2. Keep CTA controls connected to the existing sign-in callback; maintain keyboard semantics and useful accessible names.
3. Update smoke assertions to the new actual accessible copy and working entry points; do not assert obsolete marketing text.
4. Consult [verification.md](verification.md) for current evidence: landing build, browser tests and frontend unit checks pass; deployed beta persistence remains an open gate. Check validation, spam/rate limits, persistence, privacy consent/copy, error states and email delivery expectations for the endpoint. Don't imply signups are captured until storage behavior is confirmed.

## 5. Audit finding traceability

Use the dated audit as the authoritative detailed finding and acceptance record. This table provides the first code locations to inspect.

| Audit finding | Primary implementation locations | Acceptance evidence to collect |
|---|---|---|
| Backend P0: cross-user interview access/mutation | `server.py` session, answer and report routes; `firebase_db.py` session/report queries | Two-user own/other/missing/malformed ID tests for each ID route; denial causes no provider call or write. |
| Backend P0: client-writable entitlements, BYOK bypass, unmetered endpoint | `firestore.rules`; `server.py` `_enforce_quota`, `/settings`, `/analyze/resume`; `usage_service.py`; `firebase_db.py` settings/usage | Emulator rejects entitlement tampering; dummy BYOK key does not bypass system-funded calls; route inventory proves every funded operation metered. Verify deployed rules/revision separately. |
| Backend P1: filename/path and upload memory handling | `server.py` `_validate_upload`, `/interview/prepare`; ingress/proxy configuration | Traversal and absolute filenames stay within temp storage; oversized chunked body rejected before full buffering; malformed PDF time/resource limits. |
| Backend P1: outbound/SSRF boundaries | `job_link_parser.py`; `/settings` and custom `base_url` flow into `interview_system.py` | Controlled DNS/redirect/IP/oversize tests plus infrastructure egress proof. |
| Backend P1: quota races/failure-open | `server.py` quota call sites; `usage_service.py`; `firebase_db.py` increment/reset | Concurrent limit and rollover tests; failed accounting store blocks paid work; retries don't double charge; rejected work leaves no processing record. |
| Backend P1: volatile sessions/jobs and partial writes | `server.py` in-memory dictionaries, `BackgroundTasks`, completion paths; `firebase_db.py` writes | Worker kill/retry/restart/multi-instance evidence; completed status has full results; duplicate delivery is idempotent. |
| Backend P1: sensitive data and provider key lifecycle | `firebase_db.py` settings/profile/resume/report methods; `gemini_file_service.py`; live prepare route | Deletion inventory/test across primary data, backups and provider files; credential rotation/removal evidence; retention and provider policy documented. |
| Backend P2: health/observability/blocking calls | `server.py` health routes, middleware, synchronous Firebase call sites | Dependency outage yields typed 5xx; liveness responsive; dependency/job/cost metrics and alert test; latency/event-loop measurements. |
| Backend P2: AI quality and costs | `resume_analyzer_service.py`, `dream_job_analyzer_service.py`, prompts, interview services | Versioned schemas/prompts; representative consented evals for groundedness, injection, schema, latency, cost; failures explicit. |
| Backend P2: rate limits and supply chain | `server.py` limiter; `.github/workflows/ci.yml`, `deploy.yml`; Dockerfile and requirements | Shared UID/IP limit tests; deploy gated on CI; short-lived identity, pinned artifacts and rehearsed rollback. |
| UX P0: shared-browser document exposure | `FileUpload.tsx`, `ProfileSetup.tsx`, `Index.tsx` signout/account transition | Sequential account-switch browser test; signout cleanup; storage-quota error does not claim success. |
| UX P1: live preparation retry state | `InterviewInterface.tsx` prepare catch/phase UI | Rejected, timeout, offline, retry success and duplicate-click tests. |
| UX P1: Classic interview type mismatch | `ClassicInterviewInterface.tsx`, `api.js` `startInterview`, backend start request model | Contract tests for distinct types in classic and live mode. |
| UX P1: lost work/navigation and inaccessible upload | `Index.tsx`, `ClassicInterviewInterface.tsx`, `InterviewInterface.tsx`, `ResumeAnalyzer.tsx`, `ProfileSetup.tsx` | Navigation/refresh/transient failure recovery; keyboard upload and screen-reader announced states. |
| UX P2: dashboard errors, unknown scores, unbounded polling | `Dashboard.tsx`, `Index.tsx` analysis polling, `DreamJobLanding.tsx` | Independent partial-failure states; unknown score excluded; stalled job deadline and reconnect tests. |
| Business: validate paid pack, funnel, cost, and launch gates | Backend usage/provider paths, product analytics, support/deletion operations | Qualified cohort denominators; completed report and repeat measures; observed costs/refunds; payment event reconciliation before paid pilot. |

## 6. Launch verification checklist

These checks group existing audit acceptance criteria into a launch sequence. They do not supersede the more specific audit checklists.

### Trust and containment

- [ ] Verify deployed Cloud Run revision, ingress, IAM and Firestore rules; compare with this repository snapshot.
- [ ] Owner-check every ID-bearing route, including WebSocket and delete/update paths; prove cross-user denial has no side effect.
- [ ] Close every unmetered system-funded route; test entitlement tampering and BYOK mismatch; establish a hard global spend/concurrency ceiling.
- [ ] Bound upload bytes before buffering, use server-generated filenames, and constrain document extraction.
- [ ] Constrain outbound destinations, redirects, resolved IPs and streamed response bytes; prove network egress restrictions.

### Reliability and recovery

- [ ] Quota reservations are transactional, idempotent, and fail closed when the spend-control store is unavailable.
- [ ] Durable jobs and sessions survive worker/process restart and duplicate delivery; completion means all result data exists.
- [ ] Every long job has bounded retries/polling, explicit failure, and a way to return after navigation/reload.
- [ ] Provider files, account data and backups have a tested retention/deletion path; credentials can be rotated and removed.
- [ ] Dependency failures, job failures, latency, usage and costs have useful metrics and tested alerts/runbooks.

### User journey and product evidence

- [ ] Shared-browser account switching cannot reveal prior resume/JD content.
- [ ] Both interview modes preserve selected type and answers; errors are actionable; keyboard and screen-reader journeys work.
- [ ] Dashboard distinguishes empty state, partial failure and unknown measurements.
- [ ] Landing callback and onboarding contract work; landing and beta-signup work remain **pending** until relevant checks are reviewed.
- [ ] Internal rehearsal completes upload → mock → report → return → delete, including recovery and support paths.
- [ ] Private beta and paid-pilot decisions use observed funnel denominators, repeat behavior, usefulness, costs and refunds. Payment/entitlement reconciliation must exist before taking money.

## 7. Pending versus verified

**Pending at the time this guide was written:** landing-page modernization and beta-signup endpoint. Their completion requires review of the resulting changes plus verification that the landing CTA still reaches the expected auth/setup flow and that the signup endpoint has explicit input, abuse, storage, consent, error, and delivery behavior. Neither is to be marked shipped or verified by this guide.

**Not established by static audit:** actual deployed code/rules/IAM, provider account settings, live customer behavior or volumes, privacy/legal compliance, real AI quality, payment capability, deletion from backups/vendors, or production spend. Maintain a dated evidence record for each such item rather than inferring it from source.
