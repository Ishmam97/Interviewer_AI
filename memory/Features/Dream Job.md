---
type: feature-note
status: shipped
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - feature
  - dream-job
---
# Dream Job Feature

**Status:** Shipped (2026-05-04)

Users paste a job-posting URL or enter target details manually, pick one of their analyzed resumes, and get a Kimi-powered fit analysis with score, gaps, tailoring plan, and ATS coverage.

Docs: `docs/architecture/dream-job.md` · Progress: `docs/stories/dream-job-progress.md`

## What it does

Returns:
- `fit_score` (0–100) and `interview_chance` estimate
- `matching_strengths` — where the resume aligns with the JD
- `gaps` — skills/experience the JD requires that are absent
- `points_to_improve` — specific resume improvements
- `resume_tailoring_plan` — section-by-section rewrite guidance
- `suggested_projects` — portfolio additions to close gaps
- `ats_keyword_coverage` — which keywords the resume hits/misses

## Backend pipeline

2-pass async pipeline in `services/dream_job_analyzer_service.py`:

1. **Pass 1 — normalize** (`openai/gpt-5-nano-2025-08-07` via AIML API): parses raw JD text into structured fields
2. **Pass 2 — analyze** (`moonshot/kimi-k2-0905-preview`): compares normalized JD against resume, produces fit analysis

Status stored in `dream_jobs` Firestore collection. Frontend polls `GET /dream-job/{id}/status` every 2 seconds.

## API routes

| Method | Path | Notes |
|---|---|---|
| POST | `/dream-job/from-link` | Scrape JD from URL (LinkedIn returns graceful error, not failure) |
| POST | `/dream-job` | Create analysis (verifies resume ownership + completed status) |
| GET | `/dream-job/{id}/status` | Lightweight poll endpoint |
| GET | `/dream-job/{id}` | Full result (ownership verified) |
| GET | `/dream-jobs` | List user's analyses (excludes jd_text/result for performance) |
| DELETE | `/dream-job/{id}` | Ownership verified |

## Frontend components

| Component | File | Role |
|---|---|---|
| `DreamJobLanding` | `components/DreamJobLanding.tsx` | State machine: setup → loading → done/error |
| `DreamJobSetup` | `components/DreamJobSetup.tsx` | Two tabs: paste link vs manual entry |
| `ResumeSelector` | `components/ResumeSelector.tsx` | Pick from completed analyses; auto-selects active |
| `DreamJobDashboard` | `components/DreamJobDashboard.tsx` | Results: animated score circle + 4 tabs |

## Open / future work

- "Tailor My Resume" button exists in `DreamJobDashboard` but is disabled ("Coming soon") — next feature iteration
- LinkedIn URL parsing is blocked (graceful error returned, not failure)
- No caching of JD parses — same URL parsed fresh every time

[[Features MOC]] · [[AI Pipeline]] · [[Codebase Map]]
