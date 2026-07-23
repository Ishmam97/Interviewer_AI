---
type: feature-note
status: shipped
created: '2026-06-02'
updated: '2026-07-19'
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
| **Greenhouse** | `greenhouse.io` in hostname | Public JSON API at `boards-api.greenhouse.io/v1/boards/{company}/jobs/{id}` |
| **Ashby** | `ashbyhq.com` in hostname | JSON-LD `JobPosting` schema or `__NEXT_DATA__`; falls back to og:* meta |
| **LinkedIn** | `linkedin.com` in hostname | Best-effort og:* meta tags; LinkedIn blocks bots (403/429/999) → graceful `{ error: "linkedin_blocked" }` |
| **Generic** | all other URLs | og:* meta + visible body text (capped ~15,000 chars — see below) |

## Return shape

```json
{ "company": "string|null", "role_title": "string|null", "location": "string|null",
  "jd_text": "string", "source": "greenhouse|ashby|linkedin|generic",
  "source_url": "string", "error": "string|null" }
```

Error values: `"linkedin_blocked"` (graceful), `"url_rejected"` (SSRF guard), `"parse_failed"`, `"partial_parse"`.

## SSRF guard — hardened 2026-07

`_is_safe_url()` resolves every hostname via DNS, rejects private/loopback/link-local/reserved/multicast **and now also unspecified (0.0.0.0/::) and IPv4-mapped-IPv6-wrapped private IPs** (e.g. `::ffff:169.254.169.254` — the cloud metadata endpoint, wrapped). Redirect chains are validated hop-by-hop in `_safe_get()`. Full detail in [[Security Hardening]].

## Cost/memory hardening — added 2026-07

- `_visible_text()` output capped at ~15,000 chars before it's ever embedded in a Dream Job LLM prompt — previously a hostile or just very large page could translate into unbounded downstream token cost.
- `_safe_get` now checks `Content-Length` and rejects anything declaring itself over 5MB before buffering into memory (doesn't stop a server that lies about the header, but catches the honest case cheaply).

## HTTP config

Timeout 20s per request; max 5 redirects (manually followed, SSRF-checked at each hop); custom User-Agent.

## API contract

`POST /dream-job/from-link` returns HTTP 200 even for partial failures like `"linkedin_blocked"` (error surfaced in the body). Only `"url_rejected"` returns 400; `"parse_failed"` returns 422. Rate-limited 10/min per token since 2026-07.

[[Features MOC]] · [[Dream Job]] · [[Security Hardening]]
