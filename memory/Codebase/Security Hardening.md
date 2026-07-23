---
type: codebase-note
status: active
created: '2026-07-19'
updated: '2026-07-19'
tags:
  - codebase
  - security
  - gotcha
---
# Security Hardening (2026-07 sprint)

Consolidated record of the security work done in the production-readiness sprint. Most of these were found by a parallel audit (backend-routes, AI-pipeline, security, deploy-infra, frontend, tests) and then fixed and regression-tested.

## Rate limiting

No rate limiting existed at all before 2026-07. Added `slowapi`, keyed by raw bearer token (one bucket per authenticated session) or remote IP for pre-auth routes — see [[Rate limiting via slowapi]].

## Upload validation — magic-byte sniffing (was extension-only)

`_validate_upload` in `server.py` used to trust the filename extension alone (`.pdf`/`.txt`). A renamed binary could ride a spoofed extension straight into the PDF loader or the LLM pipeline. Now sniffs actual content: PDFs must start with `%PDF-`; non-PDF files must decode as UTF-8 and contain no null bytes. Also rejects empty files (previously accepted silently).

## SSRF guard hardening (`services/job_link_parser.py`)

The guard already resolved DNS and rejected private/loopback/link-local/reserved/multicast IPs before scraping a job-posting URL. Two gaps fixed:
- **`is_unspecified`** (0.0.0.0 / ::) was not checked.
- **IPv4-mapped IPv6** (e.g. `::ffff:169.254.169.254`, wrapping the cloud metadata IP in an IPv6 literal) was not unwrapped before classification — a bare IPv6-looking address could sail through the private/link-local checks that only ever looked at the wrapper, not the embedded IPv4.

Both fixed via `ip.ipv4_mapped` unwrap before the private/loopback/link-local/reserved/multicast/unspecified checks. Also added a `Content-Length` pre-check (5MB cap) to reject a response that *honestly* declares itself oversized before buffering it into memory — doesn't stop a server that lies about the header, but a cheap guard against the common case.

## Dependency CVEs

- `python-multipart==0.0.6` (CVE-2024-24762, ReDoS on multipart parsing — on the request path for every file upload) → bumped to `0.0.9`.
- `python-jose[cryptography]==3.3.0` (known CVEs) → **removed entirely** — verified via grep it was never actually imported anywhere in the app; it was auth-adjacent dead weight left over from before the Firebase-only auth model.

## Docker hardening

- `Dockerfile` now runs as a non-root `appuser` (was root) — verified via an actual `docker build && docker run`: confirmed `whoami` returns `appuser` and the runtime-writable dirs (`logs/`, `vector_stores/`) are correctly owned and writable.
- Added `backend-microservice/.dockerignore` — protects against a future `COPY .` accidentally baking `.env`/`*service-account*.json` into the image, and stops local per-session FAISS dirs (see [[RAG System]]) from leaking into the build context.
- Removed the risky import-time `pip install faiss-cpu` fallback (see [[RAG System]]).

## Prod-only hardening in `core/config.py` / `server.py`

- `/docs` and `/redoc` disabled when `ENVIRONMENT=production` (previously exposed unconditionally).
- Localhost CORS origins stripped when `ENVIRONMENT=production` (previously always included, even in prod).
- `SECRET_KEY`/`ALGORITHM` in `config.py` are dead/unused fields (no live code path signs anything with them) — deliberately left alone rather than forcing a fail-fast check for a currently-inert value; flagged, not fixed (see [[Backend]] known weaknesses).

## What was verified but NOT fixed (accepted risk / deferred)

- **DNS-rebind TOCTOU** on the SSRF guard: resolve-then-connect leaves a theoretical window where DNS could rebind between validation and the actual `httpx` connection. A fully robust fix needs a custom transport pinning the resolved IP — judged disproportionate effort for a MEDIUM-severity, sophisticated, timing-dependent attack vs. the per-redirect-hop re-validation that already exists. Documented as a residual risk, not silently ignored.

[[Codebase Map]] · [[Backend]] · [[Rate limiting via slowapi]] · [[Job Link Parser]]
