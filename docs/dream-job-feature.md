# Dream Job Feature

## Overview

Dream Job lets a user paste a job-posting URL or enter target details manually, picks one of their analyzed resumes, and runs a Kimi-powered fit analysis. The dashboard returns a fit score, interview-callback estimate, matching strengths, skill gaps, points to improve, a section-by-section resume tailoring plan, suggested portfolio projects, and ATS keyword coverage.

## Architecture

```
┌─────────────┐
│   Frontend  │
│  (React)    │
└──────┬──────┘
       │
       │ REST /dream-job/*
       ↓
┌─────────────────────────────┐
│   FastAPI Backend           │
│  (DreamJobAnalyzerService)  │
└──────┬──────────────────────┘
       │
       │ Firestore + Kimi API
       ↓
┌─────────────────────┐
│  Firebase/Firestore │
│  Kimi (LLM)         │
└─────────────────────┘
```

## API Contract

| Method | Path | Auth | Request | Response | Notes |
|--------|------|------|---------|----------|-------|
| POST | `/dream-job/from-link` | yes | `{url}` | `{company, role_title, location, jd_text, source_url, source, error?}` | 400=url_rejected, 422=parse_failed, 200+error="linkedin_blocked" graceful |
| POST | `/dream-job` | yes | `{company, role_title, jd_text, source, source_url?, resume_analysis_id}` | `{dream_job_id, status: "pending"}` | Verifies resume ownership + completed status |
| GET | `/dream-job/{id}/status` | yes | — | `{dream_job_id, status, current_step, error?}` | Lightweight; for polling |
| GET | `/dream-job/{id}` | yes | — | full dream_jobs doc | Ownership-verified |
| GET | `/dream-jobs` | yes | — | `{dream_jobs: [summary]}` | Excludes jd_text/result |
| DELETE | `/dream-job/{id}` | yes | — | `{message, dream_job_id}` | Ownership-verified |

## Frontend Component Map

| Component | File | Step | Notes |
|-----------|------|------|-------|
| `DreamJobLanding` | `frontend/src/components/DreamJobLanding.tsx` | Controller | State machine: setup → loading → done/error. Polls `/dream-job/{id}/status` every 2s. |
| `DreamJobSetup` | `frontend/src/components/DreamJobSetup.tsx` | Step 1 — Entry | Two tabs: "Paste link" (calls `/dream-job/from-link`) vs "Enter manually". Company autocomplete uses Google favicon API. |
| `ResumeSelector` | `frontend/src/components/ResumeSelector.tsx` | Step 1.5 — Resume choice | Lists user's completed resume analyses; auto-selects active resume. Empty state links to `/analyzer`. |
| `DreamJobDashboard` | `frontend/src/components/DreamJobDashboard.tsx` | Step 3 — Results | Hero (animated SVG score circle) + 4 tabs: Strengths & Gaps, Improve Resume, Suggested Projects, ATS Keywords. "Tailor My Resume" button is disabled with "Coming soon" tooltip. |
| `apiService.parseDreamJobLink` etc. | `frontend/src/services/api.js` | API layer | 6 methods added: parseDreamJobLink, createDreamJob, getDreamJobStatus, getDreamJob, listDreamJobs, deleteDreamJob. |

## Firestore `dream_jobs` Schema

```
{
  uid, dream_job_id, company, role_title, jd_text, jd_normalized,
  source: "manual"|"link", source_url,
  resume_analysis_id,
  status: "pending"|"normalizing"|"analyzing"|"completed"|"failed",
  current_step, error,
  result: { fit_score, interview_chance, fit_summary, matching_strengths,
            gaps, points_to_improve, resume_tailoring_plan,
            suggested_projects, ats_keyword_coverage },
  usage: {prompt_tokens, completion_tokens, total_tokens},
  created_at, updated_at
}
```

## Status Flow

`pending` (created) → `normalizing` (Pass 1, gpt-5-nano JD parse) → `analyzing` (Pass 2, Kimi fit) → `completed`. On any error/timeout: → `failed` with `error` populated.

## Open Questions

- TBD
