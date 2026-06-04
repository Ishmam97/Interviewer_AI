---
type: decision
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - decision
  - architecture
  - fastapi
---
# Decision: Single server.py for All Routes

All ~36 FastAPI routes live in one file: `backend-microservice/app/server.py` (~1700 lines).

**Why:** Chosen for MVP speed — no need to wire up APIRouter modules, dependency injection across files, or shared state between routers. All route handlers share direct access to `_active_sessions` dict and `_firebase_manager` singleton without passing them around.

**Trade-off:** The file is already large and will become harder to navigate as features grow. The next natural split would be domain-based routers: `auth_router`, `profile_router`, `interview_router`, `dream_job_router`.

**How to apply:** When adding a new route, add it to `server.py` in the appropriate section (grouped by domain with comment headers). If a new feature adds more than ~5 routes, consider creating a proper APIRouter module and including it — but don't do this as a refactor unless the feature itself is being touched.

[[Decisions Log]] · [[Backend]]
