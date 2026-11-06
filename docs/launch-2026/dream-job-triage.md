# Dream Job runtime triage — 2026-11-06

Evidence: local backend process logs following the user's attempt; no user resume, tokens or raw provider response copied here.

## Confirmed failures

1. `POST /dream-job/from-link` failed at `server.py` importing `job_link_parser`: `ModuleNotFoundError: No module named bs4`. The temporary test environment used to launch the backend lacked `beautifulsoup4==4.13.4`, already present in requirements.txt. Installed the declared dependency in that runtime. Failed imports can be retried without restarting the service.
2. `POST /dream-job` successfully queued analysis. Pass 1 (`normalizing_jd`, configured model `openai/gpt-5-nano-2025-08-07`) received HTTP 200 from the configured AIML provider, then `json.loads(resp.choices[0].message.content)` at `dream_job_analyzer_service.py:203` raised `JSONDecodeError: Expecting value: line 1 column 1`. Background task marked the job failed; fit scoring never ran. HTTP success is not valid model output. Existing logs do not contain response content length, finish reason or refusal metadata, so empty, non-JSON and truncated response causes cannot yet be distinguished. The 1200-token budget is a hypothesis to investigate, not a proven root cause.
3. Separately, report listing failed with Firestore `FAILED_PRECONDITION` requiring a composite index for interview_reports: user_id ascending, created_at descending (implicit document-name ordering). The database wrapper masks this failure as an empty result, so the endpoint returns 200. This does not explain the Dream Job normalization failure.

## Next corrective work

- Add safe model-response diagnostics: model, stage, finish reason, content length and token counts only; never log raw resumes, job descriptions, keys or model output.
- Reject missing choices, refusal, empty content, truncation, malformed JSON and wrong schema explicitly. Preserve failed status and an actionable user message; do not substitute invented scores or an empty result.
- Use a synthetic non-personal JD to verify provider/model response-format behavior and token budget, then implement a bounded retry only where justified. Charge/account for all attempts.
- Add provider-shape regression cases; current mocks cannot establish real provider behavior.
- Commit the Firestore index definition and deploy through the reviewed project workflow; show report service failures as errors rather than empty dashboards.
- Build a complete reproducible application environment from requirements; the temporary beta-test venv is not verified for every feature.

No automatic rerun of the user's analysis or cloud index change was performed.

## Verification

Job-parser module now imports successfully. All 41 existing Dream Job service/endpoint tests pass with mocked providers/Firebase; this does not verify a successful live model response. No application source changes were made in this triage.
