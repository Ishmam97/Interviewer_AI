# Dashboard and workspace modernization — 2026-11-06

## Rollback checkpoints

Before redesign, committed backend/docs in `8d9eb561` and the separate frontend repository in `83e159f`. These commits preserve the landing, beta signup, audits and launch plans. The redesign follows those checkpoints; changes in the two repositories must be managed separately. Neither checkpoint was pushed by this task.

## Changes

- Overview is the initial signed-in destination, with a welcome, prominent practice action, statistics and existing charts/insights.
- Compact grouped sidebar preserves Interview practice, Resume Analyzer, Dream Job, Profile, Account Settings and sign-out. Active destination is announced; collapsed icons retain accessible names. Mobile navigation closes after selection.
- Ivory/sage/forest workspace theme, calmer cards, breadcrumbs, clearer spacing and responsive interview setup. Both interview modes, all nine interview types, question count and uploads remain available.
- Dashboard sessions/reports load independently. Successful data remains available when the other request fails; the error offers retry.
- Score averages exclude missing scores; history is explicitly ordered by date. Statistics recompute after deletion. Reports now has a visible tab for its existing content.
- Removed an unused prop passed to AccountSettings; full TypeScript check now passes.
- Added frontend Docker build exclusions for local environment files and node_modules.

## Runtime

Stopped the host Vite and Uvicorn processes launched earlier. Both application services now run via Docker Compose from `/home/ishmam/github/Interviewer_AI`:

```sh
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 backend
docker compose down
```

Frontend: http://localhost:8080/. Backend: http://localhost:8000/health. Do not run standalone npm dev or uvicorn for this workspace going forward. Compose uses existing local runtime configuration; don't commit credentials or dump resolved Compose secrets into logs. `down` should be used without `-v` to retain volumes.

## Verification

- Both Docker endpoints return HTTP 200; backend reports healthy.
- Production frontend build and TypeScript checks pass inside frontend container.
- All 48 frontend unit tests pass inside Docker, including dashboard action/data/error cases.
- 26 focused backend tests pass inside Docker with Firebase mocked.
- Two Playwright workspace tests pass against the Docker-hosted frontend: navigation destinations, both interview modes, nine types, account/profile access, collapsed sign-out, mobile drawer behavior and 375 px overflow. API responses are intercepted; no real user data is used.
- Desktop dashboard screenshot reviewed. Existing large-bundle and Browserslist warnings remain.

Existing backend limitations (Dream Job provider JSON failure, missing reports Firestore index, and previously audited route issues) are not resolved by visual modernization. Retaining UI actions and passing mocked tests does not establish every live provider/database flow is functional. No public deployment was performed.
