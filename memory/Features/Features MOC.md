---
type: moc
status: active
created: '2026-06-02'
updated: '2026-07-19'
tags:
  - feature
  - moc
---
# Features MOC

One note per feature. Each links to its `docs/` artifacts and accumulates cross-task context.

## Shipped features

- [[Interview System]] — classic REST interview mode: upload resume + JD, answer AI questions turn-by-turn, get a scored report. LangGraph pipeline, per-session FAISS RAG, configurable LLM.
- [[Live Interview]] — **corrected 2026-07-19: this is shipped, not backlog.** Conversational WebSocket mode built on Gemini streaming (`/interview/prepare` + `WS /ws/interview/{id}`). Independent code path from the classic mode, not a replacement for it.
- [[Resume Analysis]] — 3-step async pipeline (parse → 7 parallel section analyses → holistic review), now fail-loud (no more silent zero-score reports on error). Suggestions system accept/reject/undo, persistence standardized on `working_parsed_sections` (2026-07-19).
- [[Dream Job]] — Kimi-powered job fit analysis. Paste URL or enter manually, pick a resume, get fit score + gap analysis + tailoring plan. Shipped 2026-05-04; hardened 2026-07 (fail-loud, cost caps, bounded polling).
- [[Job Link Parser]] — Scrapes job posting URLs (Greenhouse/Ashby/LinkedIn/generic) with a hardened SSRF guard. Called by Dream Job's from-link endpoint.

## Active planning artifact

- [[Production Roadmap]] — the authoritative path-to-production plan (Phases A-D, pricing, feature ranking, anti-recommendations), produced by a 5-agent research team and reviewer-verified 2026-07-07.

## In progress

_Nothing currently in flight._

## Planned / backlog

- **Resume Tailor** — "Tailor My Resume" button in `DreamJobDashboard` still disabled ("Coming soon"). Flagged in [[Production Roadmap]] as a natural home for a freemium paywall surface.
- **Live-interview fixes** — the post-report silent-stuck-forever bug and the quadratic-token-history cost issue are both known, both unfixed as of 2026-07-19. See [[Live Interview]].
- **UI palette unification** — three clashing color systems ship today (new teal/slate landing page, old blue/purple everywhere else, purple/pink on Dream Job). Scoped in [[Production Roadmap]] Phase B, deferred by the project owner for a later session.
- **Freemium / monetization** — no plan concept, no usage gating, no Stripe integration exist yet. Fully scoped in [[Production Roadmap]] Phase C.

[[Home]]
