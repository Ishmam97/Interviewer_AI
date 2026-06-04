---
type: codebase-note
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - codebase
  - auth
  - firebase
---
# Auth Flow

Firebase Auth is the identity provider. The backend verifies Firebase ID tokens.

## Sign-up flow

1. Frontend posts `{ email, password }` to `POST /auth/signup`
2. Backend creates Firebase Auth user via `firebase_admin.auth.create_user()`
3. Backend creates a custom token, then calls Firebase Identity Toolkit REST API to exchange it for a real ID token
4. ID token returned in `session.access_token`
5. Frontend stores token via the Firebase client SDK

## Sign-in flow

1. Frontend posts credentials to `POST /auth/signin`
2. Backend calls Firebase Identity Toolkit REST API with email/password
3. Returns ID token + refresh token

## Google OAuth flow

1. Firebase Google Sign-In popup in browser → gets Google ID token
2. Frontend posts ID token to `POST /auth/google`
3. Backend verifies with `firebase_admin.auth.verify_id_token()`, creates profile if new user

## Token verification

Every protected route uses the `get_current_user` FastAPI dependency:
- Reads `Authorization: Bearer <token>`
- Calls `FirebaseManager.verify_id_token(token)` → wraps `firebase_admin.auth.verify_id_token()`
- Returns decoded token dict; `uid` is extracted from it

#gotcha Old documentation (old.CLAUDE.md, old.QWEN.md) described a `dummy-token` dev bypass (`ENVIRONMENT=development` + `Authorization: Bearer dummy-token` → mock user). **This bypass does NOT exist in current code** — grepping `server.py` for "dummy" returns nothing. Actual code does real Firebase ID token verification on every request. Do not rely on the bypass; set up a real Firebase dev project or use the test endpoints (`/test/interview/start`, `/test/interview/answer`) which explicitly skip auth.

## Test endpoints (no auth required)

- `POST /test/interview/start` — starts a session without authentication
- `POST /test/interview/answer` — submit answer without authentication

These exist for development use and must be removed or gated before production.

## Firebase project

- Project ID: `interviewer-ea164`
- authDomain: `interviewer-ea164.firebaseapp.com`
- storageBucket: `interviewer-ea164.firebasestorage.app`
- appId: `1:452095792083:web:3337139b726fa56164d526`

## Service account

`backend-microservice/firebase-service-account.json` must be present for Firebase Admin SDK to initialize. Never committed to git. In GCP environments, Application Default Credentials work as a fallback.

[[Codebase Map]] · [[Backend]]
