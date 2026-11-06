# Frontend feature reference

**Source inspected:** `frontend/src/` as present in this checkout on 2026-11-06. This is a static source map. It describes component code and client-side API calls; it does not claim that a live backend, browser behavior, or provider integration was exercised. Endpoint existence is cross-checked against [the backend API reference](backend-api-reference.md).

## Application shell and section flow

### `App.tsx`

Bootstraps the React app and root route (`/`). The authenticated/public decision is made in `pages/Index.tsx`. `pages/NotFound.tsx` is the fallback page.

### `pages/Index.tsx`

The workspace controller owns `user`, `needsSetup`, `activeSection`, interview mode/setup, uploaded files, question count, and resume-analysis status/selection.

- On mount, calls `apiService.validateToken()` and restores the authenticated user if `/auth/me` succeeds.
- Listens for the API client's `auth:unauthorized` event; clears the signed-in user and resets the interview state.
- Public state renders `LandingPage`; setup state renders `ProfileSetup`; authenticated state renders `AppSidebar` and one feature section.
- `handleSignIn` consumes the user object including `needs_setup`; setup completion merges the updated profile into local user state.
- Section selection conditionally mounts feature components. An active interview or Dream Job flow can therefore be unmounted by changing sections.
- When resume analysis is processing, polls every 2.5 seconds. Five consecutive request errors change UI state to failed/connection lost. Completed and failed states stop polling.
- Interview start requires both resume and job description plus an interview type, then chooses Classic or Live. Completion clears the file selection.
- Sign-out calls `apiService.signOut()` then clears React state and files; source audit notes that document draft keys used by `FileUpload` are not removed there.

### `AppSidebar.tsx`

Receives `activeSection`, `onSectionChange`, `user`, `onSignOut`, and `analysisReady`. Buttons navigate among interview, analyzer, Dream Job, dashboard, profile and settings. It displays the user's name/email and resume-analysis readiness. Navigation is callback-based, not URL-based.

## Feature component inventory

### Public entry and account

| Component | Props / main state | User actions and client calls | Errors and boundaries |
|---|---|---|---|
| `LandingPage.tsx` | `onSignIn(userData)`; signup `busy` and `status` state | Anchor navigation to process, experience, FAQ, beta and sign-in. POSTs email, consent and honeypot to `/beta-signups`; 15-second request timeout. IntersectionObserver reveals sections, honoring reduced motion. Embeds `AuthForm` with callback preserved. | Pending disables submission; storage/rate-limit/network failures retain form fields and allow retry. Success is announced only after API success. UI preview/feedback are explicitly illustrative. Auth errors remain in `AuthForm`. |
| `AuthForm.tsx` | `onSignIn`; mode (`idle`, sign-in, sign-up), email/name/password, loading | Email sign-in → `signIn`; email signup → `signUp`, then `signIn`; Google popup → `googleSignIn`; development dummy-account path also exists in source. Successful response calls `onSignIn` with user and `needs_setup`. | Toasts/displayed errors; loading state prevents duplicate form submission. Google popup failure is caught. API 401 clears token and emits app event centrally. |
| `ProfileSetup.tsx` | `user`, `onComplete`, optional `onAnalysisStarted`; step, profile/career form, target-role list, resume upload state | Multi-step profile collects name/location/bio, job title/experience/target roles; saves with `updateProfile`; optional resume upload calls `uploadResume` and reports analysis ID through callback. | Toast on save/upload failure; loading flags. Upload target is click-driven in the inspected code (keyboard concern is in UX audit). |
| `AccountSettings.tsx` | `user`, analysis status callbacks; settings, key visibility, password and provider states | Loads `getSettings` and `validateToken`; saves provider/model/base URL/key/question count/temperature via `updateSettings`; changes password via `setPassword`; embeds `ResumeManager`. Delete-account control currently directs user to contact support. | Loading/saving flags and toast errors; raw key is not returned by backend settings GET, only a boolean indicator. |
| `ProfilePage.tsx` | `user`; profile, parsed resume sections, active analysis ID, edit/snapshot state | Loads profile and latest resume analysis; edits personal fields via `updateProfile`, patches working resume using `patchWorkingResume`. | Loading/error feedback; local snapshots support cancel/revert editing. See audit for concerns about accessible state and document lifecycle. |

### Interview flow

| Component | Props / phases | Actions and client calls | UI behavior/error handling |
|---|---|---|---|
| `FileUpload.tsx` | Controlled `uploadedFiles` and setter; file/text selection state | Select/drop resume and job description or enter pasted text; converts inputs to component-level file descriptors. | Validation and toast feedback. Persists resume/JD content in browser localStorage and restores on mount; shared-browser exposure and quota-message mismatch are documented in the UX audit. |
| `ClassicInterviewInterface.tsx` | `uploadedFiles`, `user`, `maxQuestions`, `interviewType`, `onComplete`, `onViewDashboard`; phase, session, messages, answer, submit state, conversation history | Mount calls `startInterview` with files and config; submit calls `submitAnswer`; End moves to completion; completion offers new interview/dashboard. | Start failure changes phase to `errored`; submit failure displays toast. In inspected code answer is optimistically appended and cleared before request completion; on failure it is not restored. Client request currently omits `interviewType`. |
| `InterviewInterface.tsx` (Live) | Same high-level interview props; phases `preparing`, `connecting`, `ready`, `live`, `analyzing`, `complete`, `errored`; messages, stream state, report | Mount calls `prepareInterview`; WebSocket opens at `getInterviewWebSocketUrl`; sends token auth, answer/end messages; receives `authenticated`, `ready`, `ai_text`, `complete`, `report_ready`, `error`; fetches report with `getInterviewReport`. | Network errors set error phase; report wait has 75-second client timeout. Preparation catch displays toast but source currently does not set `errored`, leaving the spinner path (UX audit). WebSocket closes on unmount. |
| `InterviewCompletion.tsx` | conversation history, average score, optional report data, callbacks | Displays session wrap-up/report details and invokes new-interview/dashboard callbacks. | Presentation component; actual persistence/report generation belongs to backend. |

**Client contract note:** Classic submits `max_questions`, model and temperature but no `interview_type`; Live sends `interview_type`. The setup selector therefore doesn't currently affect the classic backend request. See [UX audit](../audits/2026-11-06-product-ux.md#prioritized-findings).

### Resume analysis, resume versions, and editing

| Component | Props / state | Actions and client calls | UI behavior/error handling |
|---|---|---|---|
| `ResumeAnalyzer.tsx` | `user`, shared `analysisStatus`, callbacks, optional `analysisId` and `onBack`; selected tab, upload/analysis state, suggestion state | Upload via `uploadResume`; reads analysis/status; accept/reject via `respondToSuggestion`; undo via `undoSuggestion`; edits parsed sections and supports bulk apply/section undo through API service. Tabs show overview, section analysis, suggestions and ATS-like output. | Loading and toast/error states; analysis polling is partly owned by `Index`. Empty upload target is not a keyboard-operable button in inspected source (UX audit). |
| `ResumeManager.tsx` | shared analysis status, callbacks to start analysis/view a version; versions, upload/delete/preview selection | Lists via `getResumes`; upload via `uploadResume`; activate/delete with corresponding methods; preview via `getResumeById`; polls status while an analysis is running. | Separate loading/upload/delete/preview flags and confirmation UI; API failures toast. |
| `ResumeSelector.tsx` | controlled selected resume ID / callback (used by Dream Job setup) | Loads selectable resume versions and reports chosen `analysis_id`; routes to resume upload through optional parent callback when none exist. | Loading/empty state. It selects completed resume versions; analysis lifecycle is owned by parent. |
| `ResumePreview.tsx` | parsed resume data, filename and close/display props | Renders parsed sections for review; no direct API calls. | Presentation-only component. |

### Dream Job

| Component | Props / state | Actions and client calls | UI behavior/error handling |
|---|---|---|---|
| `DreamJobSetup.tsx` | `onSubmit(values)`, optional `onGoUpload`; link parse state, company/role/JD/source, selected resume, submission state | Link tab calls `parseDreamJobLink`; manual tab accepts company, role and JD; `ResumeSelector` chooses a completed resume; submits `{company, role_title, jd_text, source, source_url, resume_analysis_id}`. | Inline link parse errors (including LinkedIn-blocked fallback), toast on missing fields; autocomplete suggestions are local/static. |
| `DreamJobLanding.tsx` | `user`, optional upload navigation; flow (`setup`, `loading`, `done`, `error`), job ID, progress, result | On submit calls `createDreamJob`; polls `getDreamJobStatus` every 2 seconds; once complete fetches `getDreamJob`; can reset to analyze another. | Bounded poll attempts and consecutive errors; failed job and timeout paths offer retry. Polling stops on component unmount, and job ID is component state, so navigation/reload does not restore progress. |
| `DreamJobDashboard.tsx` | `result`, `onAnalyzeAnother` | Renders fit result, gaps and action plan; no direct API calls. Tailoring action is marked unavailable/coming soon. | Presentation state; retry/new analysis delegates to parent. |

### History and reports

| Component | Props / state | Actions and client calls | UI behavior/error handling |
|---|---|---|---|
| `Dashboard.tsx` | `user`, optional `onStartInterview`; sessions, reports, stats, filter, selected report, delete state | Mount loads `getInterviewSessions()` and `getReports()` in one `Promise.all`; stats are calculated from sessions. Can filter, delete with `deleteInterviewSession`, load report via `getInterviewReport`; shows report viewer. | A single catch displays a toast, then loading ends; audit notes failure can look like empty history and a failed half hides successful half. Missing score values are treated as 0 in some calculations. |
| `DashboardEmptyState.tsx` | kind (`sessions`/`reports`) and start callback | CTA returns to interview setup. | Distinguishes empty presentation only when parent decides no records exist; dashboard load errors are not separately represented. |
| `DashboardReportViewer.tsx` | report/session and close callback | Displays report content selected from dashboard. | Presentation component; no API requests. |
| `FullReportViewer.tsx` | report object and modal state | Renders full report content. | Presentation component used by interview completion paths. |

### Shared UI and error behavior

- API client `ApiService.handleResponse` parses JSON, throws an `Error` containing backend `detail`/`message` and status for non-2xx responses. A 401 clears the saved bearer token and dispatches `auth:unauthorized`.
- Auth JSON requests use `Authorization: Bearer <token>` and JSON content type. Multipart helpers intentionally omit content type so the browser sets boundaries.
- Many feature components use toast notifications for request failures; async feature state is component-local unless explicitly lifted to `Index`.
- User-facing feature names and claims should match actual flows: Live mode streams text over WebSocket; source does not establish general voice input/output. Resume tailoring remains unavailable.

## API client methods and route mapping

`frontend/src/services/api.js` defaults to `http://localhost:8000`; WebSocket defaults to `ws://localhost:8000`. Both are environment configurable. The default `ApiService` stores the token in `localStorage` under `auth_token`.

| Client methods | Registered backend route(s) | Notes |
|---|---|---|
| `signUp`, `signIn`, `signOut`, `googleSignIn`, `validateToken`, `setPassword` | `/auth/signup`, `/auth/signin`, `/auth/signout`, `/auth/google`, `/auth/me`, `/auth/password` | Email signup UI calls signup then signin; OAuth obtains Firebase ID token, passes it to `/auth/google`, then saves returned session token where provided. |
| `getProfile`, `updateProfile` | `GET/PUT /profile` | Profile fields. |
| `getSettings`, `updateSettings` | `GET/PUT /settings` | Backend masks raw API key on read. |
| `startInterview`, `submitAnswer`, `getInterviewSessions`, `deleteInterviewSession`, `getInterviewReport`, `getReports`, `getDashboardStats` | `/interview/start`, `/interview/answer`, `/interview/sessions`, `/interview/{id}` (DELETE client path), `/interview/{id}/report`, `/reports`, `/dashboard/stats` | `getInterviewSessions` and `getReports` unwrap response arrays. The DELETE client path has no matching backend route (see mismatch below). |
| `uploadResume`, `getResumeAnalysis`, `getAnalysisStatus`, suggestion and working-data methods | `/profile/resume`, `/profile/resume/analysis`, `/resume/analysis/{id}/status`, `/profile/resume/suggestions/*`, `/profile/resumes/{id}/*` | Some API helper paths don't match registered routes; compare the mismatch list below. |
| `getResumes`, `deleteResume`, `setActiveResume`, `getResumeById` | `/profile/resumes`, `/profile/resumes/{id}`, `/profile/resumes/{id}/set-active` | These methods correspond to registered routes. |
| `prepareInterview`, `getInterviewWebSocketUrl` | `/interview/prepare`, `/ws/interview/{id}` | Live path; websocket sends auth token in first JSON message. |
| `parseDreamJobLink`, `createDreamJob`, `getDreamJobStatus`, `getDreamJob`, `listDreamJobs`, `deleteDreamJob` | `/dream-job/from-link`, `/dream-job`, `/dream-job/{id}/status`, `/dream-job/{id}`, `/dream-jobs`, `DELETE /dream-job/{id}` | Authenticated. |

### Client/backend route mismatches to keep visible

Static source comparison found the following API client calls without a matching backend decorator in `server.py` as inspected:

- `deleteInterviewSession` calls `DELETE /interview/{id}`; no DELETE handler is registered. Dashboard delete therefore needs route reconciliation.
- `respondToSuggestion` can call `POST /profile/resumes/{analysis_id}/suggestions/{suggestion_id}`; backend has the legacy current-resume path (`/profile/resume/suggestions/{suggestion_id}`) and bulk path, but no per-analysis accept/reject decorator.
- `undoSuggestion` can call `POST /profile/resumes/{analysis_id}/suggestions/{suggestion_id}/undo`; backend registers only `/profile/resume/suggestions/{suggestion_id}/undo`.
- `patchWorkingResume` calls `PATCH /profile/resumes/{analysis_id}/working`; no PATCH route is registered in `server.py`.
- `reAnalyzeResume` calls `POST /profile/resumes/{analysis_id}/re-analyze`; no matching route is registered.
- `startTestInterview` is labeled as a development test method but its current implementation posts to `/settings`, not a test interview route. No test interview routes are registered.
- `getInterviewReport` calls `GET /interview/{id}/report`; this route returns report content. A similarly named `/interview/sessions/{id}/report` route is also registered but returns the session object in current code.

These are source contract observations, not runtime 404 results; they should be checked against the intended product contract and any mounted routers before being treated as live failures.

## Evidence status

Everything in this document is **source-verified** by reading frontend modules and matching client URLs to route decorators. No browser, backend server, Firebase project, model provider, or user session was exercised for this reference. UX audit findings remain in [the product/UX audit](../audits/2026-11-06-product-ux.md), including shared browser storage, keyboard access, answer preservation, and navigation recovery.
