"""
Job Link Parser — scrape a job posting URL and return structured metadata.

Supported sources (in order of specificity):
- Greenhouse  (boards.greenhouse.io / boards-api.greenhouse.io) — clean JSON API
- Ashby       (jobs.ashbyhq.com)                                — JSON-LD / __NEXT_DATA__
- LinkedIn    (linkedin.com/jobs/view/…)                        — best-effort meta tags;
              LinkedIn aggressively blocks bots, so failures are swallowed and callers
              receive {error: "linkedin_blocked"} and should fall back to manual paste.
- Generic fallback — og:* meta tags + visible text

Return shape:
{
    "company": str | None,
    "role_title": str | None,
    "location": str | None,
    "jd_text": str,
    "source": "greenhouse" | "ashby" | "linkedin" | "generic",
    "source_url": str,
    "error": str | None,   # present only on partial / full failures
}
"""

import ipaddress
import json
import logging
import re
import socket
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 20.0
_MAX_REDIRECTS = 5
# Caps the scraped JD text before it's later embedded in an LLM prompt
# (dream_job_analyzer_service). A hostile/oversized page shouldn't translate
# into unbounded token cost downstream.
_MAX_JD_TEXT_CHARS = 15000
_USER_AGENT = (
    "Mozilla/5.0 (compatible; DreamJobBot/1.0; +https://example.com/bot)"
)
_ALLOWED_SCHEMES = {"http", "https"}
# Reject responses that honestly declare an oversized body before we buffer
# them into memory. Doesn't stop a server that lies about Content-Length, but
# guards the common case of a careless huge page cheaply.
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024

# ── SSRF guard ────────────────────────────────────────────────────────────────


def _is_safe_url(url: str) -> tuple[bool, str]:
    """Validate URL scheme + resolve hostname + reject private/loopback/link-local IPs.

    Returns (True, "") when safe, (False, reason) otherwise.
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False, f"scheme '{parsed.scheme}' not allowed"
    host = parsed.hostname
    if not host:
        return False, "missing hostname"
    try:
        infos = socket.getaddrinfo(host, None)
        for _family, _type, _proto, _canonname, sockaddr in infos:
            ip = ipaddress.ip_address(sockaddr[0])
            # Unwrap IPv4-mapped IPv6 (e.g. ::ffff:169.254.169.254) so the
            # checks below see the real embedded IPv4 instead of classifying
            # the wrapper address, which is not itself private/link-local.
            mapped = ip.ipv4_mapped if isinstance(ip, ipaddress.IPv6Address) else None
            check_ip = mapped or ip
            if (
                check_ip.is_private
                or check_ip.is_loopback
                or check_ip.is_link_local
                or check_ip.is_reserved
                or check_ip.is_multicast
                or check_ip.is_unspecified
            ):
                return False, f"resolves to non-public IP {ip}"
    except (socket.gaierror, ValueError) as exc:
        return False, f"DNS resolution failed: {exc}"
    return True, ""


async def _safe_get(
    client: httpx.AsyncClient, url: str, headers: dict | None = None, **kwargs
) -> httpx.Response:
    """GET with manual redirect following that re-validates every hop for SSRF."""
    headers = headers or {}
    for _ in range(_MAX_REDIRECTS + 1):
        ok, reason = _is_safe_url(url)
        if not ok:
            raise ValueError(f"SSRF guard blocked redirect to {url}: {reason}")
        resp = await client.get(url, headers=headers, follow_redirects=False, **kwargs)
        content_length = resp.headers.get("content-length")
        if content_length and int(content_length) > _MAX_RESPONSE_BYTES:
            raise ValueError(f"Response too large ({content_length} bytes) from {url}")
        if resp.is_redirect:
            location = resp.headers.get("location", "")
            if not location:
                break
            # Resolve relative redirects
            if not urlparse(location).scheme:
                parsed = urlparse(url)
                location = f"{parsed.scheme}://{parsed.netloc}{location}"
            url = location
            continue
        return resp
    return resp  # type: ignore[return-value]  # last response after max hops


# ── Helpers ───────────────────────────────────────────────────────────────────


def _hostname(url: str) -> str:
    return urlparse(url).hostname or ""


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def _og(soup: BeautifulSoup, prop: str) -> str | None:
    tag = soup.find("meta", property=f"og:{prop}")
    if tag:
        return (tag.get("content") or "").strip() or None
    return None


def _meta_name(soup: BeautifulSoup, name: str) -> str | None:
    tag = soup.find("meta", attrs={"name": name})
    if tag:
        return (tag.get("content") or "").strip() or None
    return None


def _visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())
    return text[:_MAX_JD_TEXT_CHARS]


# ── Source-specific parsers ────────────────────────────────────────────────────


async def _parse_greenhouse(url: str, client: httpx.AsyncClient) -> dict:
    """
    Greenhouse exposes a public JSON API at boards-api.greenhouse.io.
    We convert the board URL to an API URL automatically.
    """
    # Normalise: boards.greenhouse.io/company/jobs/12345 →
    #            boards-api.greenhouse.io/v1/boards/company/jobs/12345
    path = urlparse(url).path.lstrip("/")
    # path looks like: <company>/jobs/<job_id>
    match = re.match(r"([^/]+)/jobs/(\d+)", path)
    if not match:
        raise ValueError(f"Unrecognised Greenhouse URL pattern: {url}")
    company_slug, job_id = match.group(1), match.group(2)
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs/{job_id}"

    resp = await _safe_get(client, api_url, timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    # Strip HTML from the content field
    content_html = data.get("content", "")
    jd_text = _soup(content_html).get_text(separator="\n").strip() if content_html else ""
    if not jd_text:
        jd_text = data.get("absolute_url", "")

    return {
        "company": (data.get("departments") or [{}])[0].get("name") or None,
        "role_title": data.get("title"),
        "location": (data.get("offices") or [{}])[0].get("name") or None,
        "jd_text": jd_text,
        "source": "greenhouse",
        "source_url": url,
        "error": None,
    }


async def _parse_ashby(url: str, client: httpx.AsyncClient) -> dict:
    """
    Ashby embeds job data in either JSON-LD (<script type="application/ld+json">)
    or __NEXT_DATA__ (Next.js SSR payload).
    """
    resp = await _safe_get(client, url, headers={"User-Agent": _USER_AGENT}, timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    soup = _soup(resp.text)

    # Try JSON-LD first
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = data[0]
            if data.get("@type") == "JobPosting":
                description_html = data.get("description", "")
                jd_text = (
                    _soup(description_html).get_text(separator="\n").strip()
                    if description_html
                    else _visible_text(soup)
                )
                return {
                    "company": (data.get("hiringOrganization") or {}).get("name"),
                    "role_title": data.get("title"),
                    "location": (data.get("jobLocation") or {})
                    .get("address", {})
                    .get("addressLocality"),
                    "jd_text": jd_text,
                    "source": "ashby",
                    "source_url": url,
                    "error": None,
                }
        except (json.JSONDecodeError, AttributeError):
            continue

    # Fallback: __NEXT_DATA__
    next_data_tag = soup.find("script", id="__NEXT_DATA__")
    if next_data_tag:
        try:
            next_data = json.loads(next_data_tag.string or "")
            job = (
                next_data.get("props", {})
                .get("pageProps", {})
                .get("jobPosting")
                or next_data.get("props", {}).get("pageProps", {}).get("job")
                or {}
            )
            desc_html = job.get("descriptionHtml") or job.get("description") or ""
            jd_text = (
                _soup(desc_html).get_text(separator="\n").strip()
                if desc_html
                else _visible_text(soup)
            )
            return {
                "company": job.get("companyName"),
                "role_title": job.get("title"),
                "location": job.get("locationName"),
                "jd_text": jd_text,
                "source": "ashby",
                "source_url": url,
                "error": None,
            }
        except (json.JSONDecodeError, AttributeError):
            pass

    # Last resort: og tags + visible text
    return {
        "company": _og(soup, "site_name"),
        "role_title": _og(soup, "title"),
        "location": None,
        "jd_text": _visible_text(soup),
        "source": "ashby",
        "source_url": url,
        "error": "partial_parse",
    }


async def _parse_linkedin(url: str, client: httpx.AsyncClient) -> dict:
    """
    LinkedIn aggressively blocks bots; we try og:* meta tags and return a
    graceful error so the frontend can fall back to manual paste.
    """
    try:
        resp = await _safe_get(
            client,
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=_HTTP_TIMEOUT,
        )
        if resp.status_code in (403, 429, 999):
            raise httpx.HTTPStatusError(
                f"LinkedIn blocked (HTTP {resp.status_code})", request=resp.request, response=resp
            )
        resp.raise_for_status()
        soup = _soup(resp.text)
        return {
            "company": _og(soup, "site_name") or _meta_name(soup, "author"),
            "role_title": _og(soup, "title") or _meta_name(soup, "title"),
            "location": None,
            "jd_text": _og(soup, "description") or _visible_text(soup),
            "source": "linkedin",
            "source_url": url,
            "error": None,
        }
    except Exception as exc:
        logger.warning(f"[job_link_parser] LinkedIn parse failed (expected): {exc}")
        return {
            "company": None,
            "role_title": None,
            "location": None,
            "jd_text": "",
            "source": "linkedin",
            "source_url": url,
            "error": "linkedin_blocked",
        }


async def _parse_generic(url: str, client: httpx.AsyncClient) -> dict:
    """
    Generic fallback: og:* meta + visible body text.
    """
    resp = await _safe_get(
        client,
        url,
        headers={"User-Agent": _USER_AGENT},
        timeout=_HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    soup = _soup(resp.text)

    return {
        "company": _og(soup, "site_name") or _meta_name(soup, "author"),
        "role_title": _og(soup, "title") or _meta_name(soup, "title"),
        "location": None,
        "jd_text": _og(soup, "description") or _visible_text(soup),
        "source": "generic",
        "source_url": url,
        "error": None,
    }


# ── Public entry-point ─────────────────────────────────────────────────────────


async def parse_job_url(url: str) -> dict:
    """
    Dispatch to the appropriate source-specific parser and return a
    normalised job dict.

    Rejects private/loopback/link-local targets (SSRF guard) before any
    network call is made.

    On any unhandled exception (network error, parse error for non-LinkedIn
    sources) we return a partial result with error="parse_failed" so callers
    can decide what to do rather than crashing.
    """
    # ── SSRF guard ─────────────────────────────────────────────────────────────
    ok, reason = _is_safe_url(url)
    if not ok:
        logger.warning(f"[job_link_parser] Rejected URL {url!r}: {reason}")
        return {
            "company": None,
            "role_title": None,
            "location": None,
            "jd_text": "",
            "source": "generic",
            "source_url": url,
            "error": "url_rejected",
        }

    host = _hostname(url)

    async with httpx.AsyncClient() as client:
        try:
            if "greenhouse.io" in host:
                return await _parse_greenhouse(url, client)
            elif "ashbyhq.com" in host:
                return await _parse_ashby(url, client)
            elif "linkedin.com" in host:
                return await _parse_linkedin(url, client)
            else:
                return await _parse_generic(url, client)
        except Exception as exc:
            logger.error(f"[job_link_parser] Failed to parse {url}: {exc}")
            return {
                "company": None,
                "role_title": None,
                "location": None,
                "jd_text": "",
                "source": "generic",
                "source_url": url,
                "error": "parse_failed",
            }
