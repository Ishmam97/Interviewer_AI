---
type: codebase-note
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - codebase
  - frontend
  - react
---
# Frontend Subsystem

Stack: React 18 + Vite + TypeScript, shadcn/ui component library, Tailwind CSS, React Router v6, Vitest for tests.

Location: `frontend/` (git submodule tracked from the parent repo).

## Routing — state-based, not URL-based

#gotcha ALL navigation is driven by `activeSection` state in `frontend/src/pages/Index.tsx`. React Router only registers two routes: root `/` and a 404 catch-all. There are no URL-based routes for features like interview, dashboard, profile, etc. Deep-linking is not possible. This is intentional to keep the app simple, but it means browser back/forward doesn't work for feature navigation.

## Key components

| File | Role |
|---|---|
| `pages/Index.tsx` | Root page. Manages auth state (Firebase onAuthStateChanged), `activeSection` routing, interview setup flow |
| `App.tsx` | React Router setup — only root + 404 |
| `services/api.js` | `ApiService` singleton — all backend REST calls with Firebase ID token attached |
| `lib/firebase.ts` | Firebase client SDK config |
| `components/AuthForm.tsx` | Email/password + Google OAuth sign-in/sign-up |
| `components/Dashboard.tsx` | Session history list + "View Report" action |
| `components/InterviewInterface.tsx` | Live Q&A: question display, answer input, score feedback |
| `components/ClassicInterviewInterface.tsx` | Alternative interview UI (simpler, no streaming) |
| `components/ResumeAnalyzer.tsx` | 3-step resume analysis UI with polling |
| `components/ResumeManager.tsx` | Multi-resume list: upload, set-active, delete |
| `components/ResumeSelector.tsx` | Picker for Dream Job: shows completed analyses, auto-selects active |
| `components/DreamJobLanding.tsx` | Dream Job state machine controller: setup → loading → results/error |
| `components/DreamJobSetup.tsx` | Step 1: paste job link or enter manually; company autocomplete via Google favicon API |
| `components/DreamJobDashboard.tsx` | Fit analysis results: score circle, 4 tabs (Strengths, Improve, Projects, ATS) |
| `components/FullReportViewer.tsx` | Modal showing full interview report |
| `components/AppSidebar.tsx` | Navigation sidebar |
| `hooks/useApi.js` | React hook wrapping `ApiService` with loading/error state |

## API client

`frontend/src/services/api.js` — `ApiService` class (exported as singleton `apiService`). Attaches `Authorization: Bearer <token>` to every authenticated request. Token comes from Firebase `getIdToken()` refreshed on each call.

Methods are grouped by domain: auth, profile, resume, interview, settings, dreamJob. Six Dream Job methods added as of May 2026.

## State management

No Redux or Zustand — all state is local React state in `Index.tsx` or individual components. For complex async flows (resume analysis, Dream Job) components poll the backend directly with `setInterval`.

## Build / test

```bash
cd frontend
npm run dev        # Vite dev server on :8080
npm run build      # Production build to dist/
npm test           # Vitest
npm run lint       # ESLint
```

Tests live in `frontend/src/__tests__/`. Current coverage: `api.test.ts` (ApiService), `DreamJobDashboard.test.tsx`, `ResumeSelector.test.tsx`.

## Known weaknesses

- No URL-based routing makes deep-linking impossible and browser history unusable.
- `api.js` is plain JavaScript (not TypeScript) — no type safety on API responses.
- Polling intervals (2s for Dream Job, resume analysis) are hardcoded — no exponential backoff.
- No global error boundary (ErrorBoundary component exists but not wired to App-level).
- Test coverage is thin — mostly the Dream Job addition.

[[Codebase Map]] · [[Backend]] · [[Dream Job]]
