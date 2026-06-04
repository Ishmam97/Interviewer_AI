---
type: feature-note
status: shipped
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - feature
  - dream-job
  - web-scraping
  - security
---
# Job Link Parser

`services/job_link_parser.py` — scrapes job posting URLs and returns structured metadata for the Dream Job feature. Called by `POST /dream-job/from-link`.

## Supported sources

| Source | Detection | Method |
|---|---|---|
| **Greenhouse** | `greenhouse.io` in hostname | Calls the public JSON API at `boards-api.greenhouse.io/v1/boards/{company}/jobs/{id}` — clean, reliable |
| **Ashby** | `ashbyhq.com` in hostname | Extracts JSON-LD `JobPosting` schema or `__NEXT_DATA__` Next.js SSR payload; falls back to og:* meta |
| **LinkedIn** | `linkedin.com` in hostname | Best-effort og:* meta tags; LinkedIn aggressively blocks bots (403/429/999) → returns graceful `{ error: "linkedin_blocked" }` — frontend should prompt user to paste JD manually |
| **Generic** | all other URLs | og:* meta + visible body text (strips scripts/styles/nav) |

## Return shape

```json
{
  "company": "string | null",
  "role_title": "string | null",
  "location": "string | null",
  "jd_text": "string",
  "source": "greenhouse | ashby | linkedin | generic",
  "source_url": "string",
  "error": "string | null"
}
```

Error values: `"linkedin_blocked"` (graceful), `"url_rejected"` (SSRF guard), `"parse_failed"` (unhandled exception), `"partial_parse"` (Ashby fallback).

## SSRF guard

#gotcha The parser has an explicit SSRF guard: `_is_safe_url()` resolves every hostname via DNS, then rejects private, loopback, link-local, reserved, and multicast IPs. This prevents server-side request forgery attacks where an attacker passes an internal URL (e.g. `http://169.254.169.254/` AWS metadata). Redirect chains are also validated hop-by-hop in `_safe_get()`.

## HTTP config

- Timeout: 20s per request
- Max redirects: 5 (manually followed, SSRF-checked at each hop)
- User-Agent: `Mozilla/5.0 (compatible; DreamJobBot/1.0; +https://example.com/bot)`

## API contract (HTTP 200 on partial failures)

The endpoint `POST /dream-job/from-link` returns HTTP 200 even for partial failures like `"linkedin_blocked"` — the error field in the JSON body tells the frontend what happened. Only `"url_rejected"` returns HTTP 400. `"parse_failed"` returns HTTP 422.

[[Features MOC]] · [[Dream Job]]
