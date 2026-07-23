---
type: codebase-note
status: active
created: '2026-06-02'
updated: '2026-07-19'
tags:
  - codebase
  - auth
  - firebase
  - security
---
# Auth Flow

Firebase Auth is the identity provider. The backend verifies Firebase ID tokens on every protected route — there is no dev bypass.

## Sign-up flow

1. Frontend posts `{ email, password, full_name }` to `POST /auth/signup`
2. Backend creates a Firebase Auth user via `firebase_admin.auth.create_user()`
3. Backend creates a custom token via `auth.create_custom_token()`, then exchanges it for a real ID token via the Firebase Identity Toolkit REST API (`exchange_custom_token`)
4. ID token returned in `session.access_token` — **the user is logged in immediately after signup**, no separate sign-in round-trip

#gotcha (fixed 2026-07-06) Signup used to return the custom token without exchanging it, so `session.access_token` was empty and the frontend silently failed to log the user in post-signup. Fixed by calling `exchange_custom_token` inline in the `/auth/signup` handler.

## Sign-in flow

1. Frontend posts credentials to `POST /auth/signin`
2. Backend calls the Firebase Identity Toolkit REST API with email/password
3. Returns ID token + refresh token

## Google OAuth flow

1. Firebase Google Sign-In popup in browser → Google ID token
2. Frontend posts the ID token to `POST /auth/google`
3. Backend verifies with `firebase_admin.auth.verify_id_token()`, creates a profile if new user

## Token verification

Every protected route uses the `get_current_user` FastAPI dependency:
- Reads `Authorization: Bearer <token>`
- Calls `FirebaseManager.verify_id_token(token)` → wraps `firebase_admin.auth.verify_id_token()`
- Returns decoded token dict; `uid` is extracted via `_get_user_id(current_user)`

**There is no `dummy-token` bypass and no auth-free `/test/*` route in the backend.** Older docs (and an earlier version of this vault) described one — verified false by grepping `server.py` for "dummy"/"test/interview": zero hits. `frontend/src/services/api.js` still has two **dead** client methods (`startTestInterview`, `submitTestAnswer`) pointing at `/test/interview/start`/`/answer` — nothing calls them, and the routes don't exist server-side. Harmless dead code, not a live bypass. See [[Codebase Map]] gotcha list.

## Rate limiting (added 2026-07)

`/auth/signup` and `/auth/signin` are rate-limited via slowapi at **10/minute per IP** — the two pre-auth endpoints are the brute-force/signup-abuse surface. See [[Security Hardening]] and [[Rate limiting via slowapi]].

## 401 handling (frontend, added 2026-07)

`api.js`'s `handleResponse` now clears the stored token and dispatches a `window` `auth:unauthorized` CustomEvent on any 401, so an expired/revoked token bounces the user to sign-in immediately instead of silently retrying a dead token until manual reload. `Index.tsx` listens for the event.

## Firebase project

- Project ID: `interviewer-ea164`
- authDomain: `interviewer-ea164.firebaseapp.com`
- storageBucket: `interviewer-ea164.firebasestorage.app`
- appId: `1:452095792083:web:3337139b726fa56164d526`

## Service account

`backend-microservice/firebase-service-account.json` must be present for the Firebase Admin SDK to initialize. Never committed (confirmed via `git log --all -- '*service-account*'` — zero history). Falls back to Application Default Credentials if missing, which works in GCP but requires the runtime service account to have `firebaseauth.admin` **and `iam.serviceAccountTokenCreator` on itself** (custom-token signing via IAM signBlob) — easy to miss; `/auth/signup` throws at runtime without it. See the production roadmap's Phase A owner checklist.

[[Codebase Map]] · [[Backend]] · [[Security Hardening]]
