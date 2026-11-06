# Product and UX audit — 2026-11-06

## Scope and confidence

Source review of the React frontend, its API client, and existing tests. This is a static audit, not a claim that the live application, every backend integration, screen reader, or browser was exercised. File references are repository-relative. The landing page is being redesigned separately; recommendations below concentrate on the authenticated experience and on keeping that integration intact. Severity reflects user impact and confidence in the code path, not measured incident frequency.

## Current product journey

- **Entry and account:** The root route validates the stored token, shows a loading state, then renders the landing page or the authenticated workspace. Email/password and Google sign-in feed the same callback; new users may enter an optional, multi-step profile setup. Sources: `frontend/src/App.tsx`, `frontend/src/pages/Index.tsx:22`, `frontend/src/components/AuthForm.tsx`, `frontend/src/components/ProfileSetup.tsx`.
- **Interview:** The initial workspace asks for interview type, 3–10 questions, a resume and job description. Both documents can be uploaded or pasted. Classic uses REST and shows per-answer feedback; Live prepares a session and streams a text conversation over WebSocket. Completion links to a new interview or dashboard. Sources: `frontend/src/pages/Index.tsx:261`, `frontend/src/components/FileUpload.tsx`, `frontend/src/components/ClassicInterviewInterface.tsx`, `frontend/src/components/InterviewInterface.tsx`, `frontend/src/components/InterviewCompletion.tsx`.
- **Resume:** Users can upload a resume for asynchronous analysis, review section feedback, edit parsed sections, apply suggestions, undo and re-analyze. Resume versions are exposed in account settings. Sources: `frontend/src/components/ResumeAnalyzer.tsx`, `frontend/src/components/ResumeManager.tsx`, `frontend/src/pages/Index.tsx:82`.
- **Dream Job:** Users select a resume, supply a job link or manual description, then receive a fit analysis and action plan. Link parsing provides a manual fallback for LinkedIn. The tailoring action is explicitly disabled as coming soon. Sources: `frontend/src/components/DreamJobSetup.tsx:66`, `frontend/src/components/DreamJobLanding.tsx:26`, `frontend/src/components/DreamJobDashboard.tsx:284`.
- **Progress and account:** Dashboard fetches sessions and reports, shows metrics and charts, filters sessions, opens reports and deletes sessions; profile exposes editable information and resume sections; settings covers AI provider, password and resume versions. Sources: `frontend/src/components/Dashboard.tsx`, `frontend/src/components/ProfilePage.tsx`, `frontend/src/components/AccountSettings.tsx`.

## Prioritized findings

### P0 — prevent private document leakage on shared browsers

`FileUpload` persists complete resume and job-description content under global localStorage keys and restores it on mount (`frontend/src/components/FileUpload.tsx:12`, `:64`). `ProfileSetup` writes the same resume key (`frontend/src/components/ProfileSetup.tsx:14`, `:91`). Sign-out clears React state but does not clear either key (`frontend/src/pages/Index.tsx:139`). A subsequent user on the same browser can therefore see and submit a previous user's documents. The success toast also says the file was saved locally even when a storage quota exception is swallowed (`FileUpload.tsx:15`, `:89`).

**Implement:** Clear user document caches on sign-out and account changes, and decide explicitly whether durable client-side storage is needed. If it is, namespace by authenticated identity, disclose local retention, and handle quota/read errors visibly. Do not rely on key namespacing as encryption. **Acceptance:** Two accounts signing in sequentially in one browser never see each other's documents; sign-out removes sensitive local drafts according to the chosen retention policy; quota failure does not claim successful persistence. Include browser tests with account switching and storage failure.

### P1 — interview preparation can become unrecoverable

The Live preparation catch shows a toast but never transitions from `preparing` to `errored` (`frontend/src/components/InterviewInterface.tsx:87`). The preparation view therefore keeps spinning without the error screen's Try Again action (`:287`). Classic does transition to `errored` on startup failure (`frontend/src/components/ClassicInterviewInterface.tsx:57`).

**Implement:** Set an error phase with an actionable inline message and retry/back controls, preserving inputs. **Acceptance:** Simulated rejected preparation, timeout and offline responses each leave a clear retryable state; retry can succeed without re-entering files; no duplicate session is created by repeated clicks.

### P1 — selected type is not sent for Classic

The setup requires an interview type and the classic screen displays it, but `startInterview` receives only question count, model and temperature (`frontend/src/components/ClassicInterviewInterface.tsx:34`, `:62`); the API client sends no interview type in that request (`frontend/src/services/api.js:128`). The Live path does send it (`api.js:432`). Consequently, the Classic UI promises a selection that is not transmitted by this client.

**Implement:** Align the Classic request and backend contract, or clearly restrict the selector to supported modes. **Acceptance:** Selecting two distinct types in both modes produces requests containing the selected type and a correctly labeled session; add contract tests for each mode.

### P1 — navigation and submission risk losing work

Sections are conditional components driven by in-memory `activeSection` (`frontend/src/pages/Index.tsx:25`, `:118`, `:260`); changing sections unmounts the interview or Dream Job flow. Live cleanup closes the socket (`frontend/src/components/InterviewInterface.tsx:145`); Dream Job stops polling on unmount (`frontend/src/components/DreamJobLanding.tsx:35`). On Classic answer submission, the answer is cleared before the request succeeds; failure only raises a toast (`frontend/src/components/ClassicInterviewInterface.tsx:89`, `:125`). A network failure can therefore lose the typed answer and leave an apparently submitted candidate message. Refresh also resets the selected section because only `/` is routed (`frontend/src/App.tsx:19`).

**Implement:** Confirm leaving an active interview or preserve and restore it; retain failed answers and provide an explicit retry that does not duplicate submissions; persist resumable analysis IDs and restore their status where supported by the backend; use routes for major sections. **Acceptance:** Sidebar navigation, refresh and transient network failure never silently discard an answer; user can return to a running analysis or is given an accurate recovery path; browser Back and deep links reach the intended section.

### P1 — primary resume upload is inaccessible by keyboard

The empty analyzer upload target is a clickable `div` without a keyboard handler, button role or tab stop (`frontend/src/components/ResumeAnalyzer.tsx:880`). Setup also uses a click-driven upload area (`frontend/src/components/ProfileSetup.tsx:288`). The interview-type label targets `interview-type` but its `SelectTrigger` has no matching ID (`frontend/src/pages/Index.tsx:269`). Placeholder-only interview answer fields need explicit accessible names (`frontend/src/components/InterviewInterface.tsx:355`, `frontend/src/components/ClassicInterviewInterface.tsx:232`).

**Implement:** Use native buttons/associated file inputs and properly associated labels; ensure focus, state announcements and visible errors for every flow. **Acceptance:** Keyboard-only users can upload, select a type, answer, navigate and recover from errors; screen readers announce field names, validation and async state; verify with keyboard and an automated accessibility scan, then manually test at least one screen reader.

### P2 — failure and empty states are conflated in the dashboard

Dashboard fetches sessions and reports with `Promise.all`; either failure results in a toast, ends loading and leaves both arrays empty (`frontend/src/components/Dashboard.tsx:48`). A temporary failure can look like no history, and one failed endpoint hides the other's successful data. Missing scores are coerced to zero in summary/chart calculations (`:62`, `:98`), potentially implying a measured score of zero.

**Implement:** Load independently, retain successful data, show a persistent retry state per failed section, and exclude unknown scores from averages. **Acceptance:** Simulated partial and total failures remain distinguishable from genuinely empty data; retries recover without reload; missing scores render as unavailable and do not distort averages.

### P2 — onboarding, analysis, and privacy copy need a coherent promise

Resume inputs are present in profile setup, interview upload and analyzer, with distinct storage paths and differing language about being saved (`frontend/src/components/ProfileSetup.tsx:80`, `frontend/src/components/FileUpload.tsx:64`, `frontend/src/components/ResumeAnalyzer.tsx:905`). Users cannot infer whether a document is local, associated with their account, or shared across features. The account deletion button directs the user to contact support, but supplies no contact information (`frontend/src/components/AccountSettings.tsx:165`).

**Implement:** Explain where documents are stored and reused, expose current resume and change/remove actions consistently, and provide an actionable deletion/support route. **Acceptance:** A new user can identify which resume will be used, replace/remove it, understand retention and reach a working deletion request without guessing.

### P2 — async status and results need durable recovery

Resume analysis polling handles repeated connection failures, but has no total attempt limit when requests succeed indefinitely with a nonterminal status (`frontend/src/pages/Index.tsx:82`). Dream Job adds a five-minute cap and error view, but its current analysis ID is component state and unmounting clears polling (`frontend/src/components/DreamJobLanding.tsx:32`, `:46`).

**Implement:** Use bounded, non-overlapping polling, expose timeouts separately from actual job failure, and reconnect to a known job after navigation/reload. **Acceptance:** A stalled job never spins forever; leaving and returning restores a running or completed job without starting a duplicate; temporary connectivity loss offers a status retry.

### P2 — mobile layout and motion require broader verification

The workspace wraps its contents in fixed `p-8` and the interview setup uses `w-[70vw]` (`frontend/src/pages/Index.tsx:260`, `:264`), reducing usable width on small screens. Chat auto-scroll requests smooth motion on each message (`frontend/src/components/ClassicInterviewInterface.tsx:52`; `frontend/src/components/InterviewInterface.tsx:82`), and loading views animate. Current small-viewport smoke tests cover the public page, not authenticated screens (`frontend/e2e/smoke.spec.ts`).

**Implement:** Use responsive container widths and padding, test long content and dialogs at 320–375 px, and honor reduced motion. **Acceptance:** All major authenticated flows fit at 320 px without page-level horizontal scrolling, controls remain usable at 200% zoom, and reduced-motion preference removes nonessential animation and smooth scrolling.

## Roadmap

1. **Trust and recovery:** Address shared-browser document isolation, Live preparation failures, Classic type contract, answer preservation, and keyboard access. Define explicit ownership and retention of each document.
2. **Connected journeys:** Route main sections, restore long-running jobs and sessions, make dashboard errors actionable, and unify resume selection across interview and Dream Job. Instrument funnel steps and failure/retry outcomes without logging document or answer contents.
3. **Product clarity:** Refine first-run guidance, provide example input and clear duration/requirements for Classic versus Live, clarify score meaning and limitations, and expose support/deletion paths. Validate language with users.
4. **Future capability:** Consider resume tailoring only after the existing disabled action has an implemented, reviewable workflow; then test suggestion provenance, user approval, undo and export. Consider longitudinal practice plans and more report comparisons after score definitions and missing-data handling are reliable. These are proposals, not current features.

## Validation plan and coverage gaps

Frontend unit tests exist for the API client, Live interview, Dream Job and resume selection; hermetic Playwright smoke tests cover the public landing page and a narrow set of accessible names, branding and 375 px layout (`frontend/src/__tests__`, `frontend/e2e/smoke.spec.ts`). Live-stack Playwright tests are opt-in (`frontend/playwright.config.ts`, `frontend/e2e/live/README.md`). There is no evidence in these tests of full authenticated keyboard journeys, account-switch storage isolation, failed Classic answer retry, or section-navigation recovery. Add deterministic mocked browser journeys for sign-in/setup, both interview modes, resume analysis and Dream Job, dashboard partial failures, account switching, and small screens; complement with targeted component tests and opt-in live contract coverage. Run accessibility automation against authenticated states as well as the public page, and perform manual keyboard/screen-reader checks.

## Landing integration notes

The public page must continue to invoke `onSignIn` with the user object expected by `Index`, including `needs_setup`, so onboarding and token-based auto-login continue to work (`frontend/src/pages/Index.tsx:124`, `:215`). Current smoke tests assert specific landing heading and CTA text (`frontend/e2e/smoke.spec.ts`); revise those assertions to test the new design's actual accessible content and working entry points rather than retaining obsolete copy. Avoid claiming unsupported voice interviews, automatic tailoring or live results beyond what current flows implement.
