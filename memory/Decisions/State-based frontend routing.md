---
type: decision
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - decision
  - frontend
  - routing
---
# Decision: State-Based Frontend Routing

All navigation in the frontend is driven by `activeSection` state in `frontend/src/pages/Index.tsx`. React Router only registers two routes: root `/` and a 404 catch-all.

**Why:** Simplest possible routing for a single-page app with no need for deep-linking at MVP time. Avoids auth-aware route guards, protected routes, and redirect logic in React Router.

**Trade-off:**
- Browser back/forward buttons don't work for feature navigation
- Deep-linking is impossible — you can't share a URL to the dashboard or a specific interview
- Refreshing the page always goes back to the landing/auth screen
- Testing specific views requires navigating through the UI each time

**How to apply:** When adding a new feature "page", add a new value to the `activeSection` type and a conditional render in `Index.tsx`. Do NOT add a React Router route unless the user has explicitly asked to migrate to URL-based routing — that's a larger refactor that touches auth guards, redirects, and the entire Index component structure.

[[Decisions Log]] · [[Frontend]]
