---
type: feature-note
status: shipped
created: '2026-06-02'
updated: '2026-07-19'
tags:
  - feature
  - dream-job
---
# Dream Job Feature

**Status:** Shipped (2026-05-04), hardened 2026-07.

Users paste a job-posting URL or enter target details manually, pick one of their analyzed resumes, and get a Kimi-powered fit analysis with score, gaps, tailoring plan, and ATS coverage.

Docs: `docs/architecture/dream-job.md` · Progress: `docs/stories/dream-job-progress.md`

## What it does

Returns `fit_score`, `interview_chance`, `matching_strengths`, `gaps`, `points_to_improve`, `resume_tailoring_plan`, `suggested_projects`, `ats_keyword_coverage`.

## Backend pipeline (models now config-driven — see [[AI Pipeline]])

2-pass async pipeline in `services/dream_job_analyzer_service.py`:

1. **Pass 1 — normalize** (`DREAM_JOB_NORMALIZE_MODEL`, `gpt-5-nano`): parses raw JD text into structured fields
2. **Pass 2 — analyze** (`DREAM_JOB_FIT_MODEL`, Kimi): compares normalized JD against resume, produces fit analysis

Both passes **re-raise on failure** (2026-07-06 fix) — no more silent zero-score reports. Per-call timeout 60s (was 320s), overall 180s (was 480s). All embedded text (resume parsed sections, raw resume text, normalized JD, raw JD) capped ~12,000 chars before the prompt — the biggest single risk here before the fix was the *redundant* full-resume text being embedded twice (once as parsed JSON, once "raw," which server.py actually reconstructs as `json.dumps(parsed_sections)` — i.e. the same content twice under two labels) plus an unbounded scraped-JD length; both capped now, the duplication itself untouched (low priority, documented not fixed).

Status stored in `dream_jobs` Firestore collection. Frontend polls `GET /dream-job/{id}/status` every 2 seconds.

#gotcha (fixed 2026-07-19) **The status poll used to never terminate on error** — `DreamJobLanding.tsx`'s `catch` block just `console.warn`'d and kept the `setInterval` running forever, hammering the backend every 2s indefinitely with the user stuck on the loading spinner with no way out but closing the tab. Fixed: bounded on two axes — 5 consecutive errors, or 150 total attempts (5 min) — either trips a visible "Analysis failed" error state with a retry button.

## API routes

| Method | Path | Notes |
|---|---|---|
| POST | `/dream-job/from-link` | Rate-limited 10/min. Scrape JD from URL — see [[Job Link Parser]] |
| POST | `/dream-job` | Rate-limited 10/min. Verifies resume ownership + completed status |
| GET | `/dream-job/{id}/status` | Lightweight poll endpoint |
| GET | `/dream-job/{id}` | Full result (ownership verified) |
| GET | `/dream-jobs` | List user's analyses |
| DELETE | `/dream-job/{id}` | Ownership verified |

## Frontend components

`DreamJobLanding` (state machine: setup → loading → done/error, now with bounded polling) · `DreamJobSetup` · `ResumeSelector` · `DreamJobDashboard`.

## Open / future work

- "Tailor My Resume" button still disabled ("Coming soon") in `DreamJobDashboard` — the next Dream Job iteration, and the natural home for a freemium paywall surface (see the production roadmap Phase C).
- LinkedIn URL parsing still blocked (graceful error, not failure).
- No caching of JD parses.

[[Features MOC]] · [[AI Pipeline]] · [[Codebase Map]] · [[Security Hardening]]
