---
type: feature-note
status: active
created: '2026-07-19'
updated: '2026-07-19'
tags:
  - feature
  - planning
  - roadmap
---
# Production Roadmap

The authoritative plan from here to a live, paying product. Full artifact: `../../docs/roadmap/production-roadmap.md` (also rendered as a color-coded HTML dashboard: `../../docs/roadmap/production-roadmap.html`, published as a Claude artifact).

Produced 2026-07-07 by a 5-agent team (market research with live web access + production-gap analyst + deploy-path engineer + UX/monetization auditor, all feeding a synthesizer), then reviewer-verified against the actual repo — 3 of the reported Phase A blockers were independently confirmed true by reading the code directly (see below). The reusable orchestration pattern is saved as a portable template: `../../templates/agent-team-roadmap.tmpl.md`.

## The four phases

- **A — Launchable** (~3-5 solo-dev days): blocking fixes + the deploy runbook. Owner-only actions (re-provision the disabled AIML key, GCP console/IAM work, the `main` merge) are explicitly separated from Claude-doable code/config fixes.
- **B — Presentable** (~1-1.5 weeks): unify the three clashing UI color palettes onto teal-400/slate-950, kill leftover Lovable-scaffold branding, basic a11y.
- **C — Sellable** (~2-2.5 weeks): no-card freemium (Free 3-5 mocks/mo + always-free BYOK, Pro ~$12-15/mo annual, $49 one-time Job Search Pass), usage-counter gating on 4 named LLM-cost routes, Stripe.
- **D — Growable** (ongoing): observability (no push signal exists today), the session-persistence ADR, the live-interview quadratic-token-cost fix, and the ranked feature list below.

## Positioning / wedge

Resume+JD hyper-specific questions and scoring (FAISS RAG + Dream Job ATS/gap analysis) directly counters the #1 cited incumbent complaint — "generic, irrelevant, or hallucinated answers" (Final Round AI, LockedIn AI). Nobody in the delivery-coaching tier (Yoodli) owns resume-anchored relevance. Win on honesty and specificity, not stealth — see the anti-recommendations below.

## Anti-recommendations (researched, deliberate — do not build)

Facial/body-language/video scoring (pseudoscience — HireVue itself dropped it), real-time live-interview copilots (detection-plagued arms race), auto-apply/mass-application bots, card-upfront trial/auto-charge dark patterns, a pure Yoodli-clone delivery-only coach.

## Verified Phase A blockers (confirmed against the repo, not just claimed by the agent team)

- `frontend/firebase.json` does not exist → Hosting deploy fails on first run
- `deploy.yml` never sets `OPENAI_API_KEY`/`OPENAI_BASE_URL` → resume/dream-job LLM calls dead in prod
- `deploy.yml` builds the frontend against a fabricated Cloud Run URL shape
- `server.py`'s live-interview post-report step swallows exceptions silently (see [[Live Interview]])
- `firestore.rules` exists at repo root but nothing in the pipeline deploys it
- `frontend/index.html` still ships Lovable-scaffold branding (title, OG image, `@lovable_dev`) — literally what renders in shared links

## Feature roadmap (ranked, evidence-cited in the full doc)

1. Resume+JD provenance surfaced in the UI ("why this question") — Phase C, strong signal, small build
2. Generous no-card free tier + BYOK, positioned as the honest replacement for the retired Google Interview Warmup — Phase C
3. Voice answers + delivery scoring (pacing, filler words, rambling) — Phase D, biggest researched gap (the product is text-only today)
4. STAR-structure content coaching + model-answer diff — Phase D
5. Company/role-specific question sets auto-built from the Dream Job scraper — Phase D
6. "Practice for your AI/HireVue screen" mode (timed, one-way, simulates employer-side AI interviewers) — Phase D

[[Features MOC]] · [[Home]] · [[Backend]] · [[Live Interview]] · [[Security Hardening]]
