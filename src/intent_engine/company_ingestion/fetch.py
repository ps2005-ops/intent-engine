"""V1.1 safe HTTP retrieval — bounded, redirect-revalidated, honest.

Manual redirect loop (never auto-follow): every hop is re-validated
against the SSRF wall and the same-domain redirect policy. Size, time,
MIME, and redirect-count limits enforced. No cookies, no auth headers,
no JavaScript, descriptive User-Agent. Transport is injectable so the
test suite never touches the network.
"""
from __future__ import annotations

import urllib.error
import urllib.request
from urllib.parse import urlparse

from intent_engine.company_ingestion.records import (
    ACCEPTED_MIME_PREFIXES, CONNECT_TIMEOUT_S, MAX_REDIRECTS,
    MAX_RESPONSE_BYTES, USER_AGENT,
)
from intent_engine.company_ingestion.validation import (
    UnsafeURLRejected, redirect_allowed, resolve_public_addresses,
    validate_candidate_url,
)


class FetchResult(dict):
    """{ok, status_code, mime_type, body, final_url, failure_type,
    safe_message, retryable, redirects}"""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None                       # surface 3xx as HTTPError


def _default_transport(url: str, timeout: float):
    """Returns (status_code, headers_dict, body_bytes_capped, exceeded)."""
    opener = urllib.request.build_opener(_NoRedirect())
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "text/html,text/plain"})
    response = opener.open(request, timeout=timeout)
    body = response.read(MAX_RESPONSE_BYTES + 1)
    headers = {k.lower(): v for k, v in response.headers.items()}
    return (response.status, headers, body[:MAX_RESPONSE_BYTES],
            len(body) > MAX_RESPONSE_BYTES)


def safe_fetch(url: str, *, transport=None, resolver=None,
               timeout: float = CONNECT_TIMEOUT_S,
               extra_mime_prefixes=(), binary: bool = False,
               accept_truncated: bool = False) -> FetchResult:
    """``extra_mime_prefixes`` narrowly widens the accepted content types for a
    single call — used only by sitemap discovery, which must read XML. The
    default retrieval path is unchanged (HTML/text only), so no analysed
    evidence document can arrive as an unexpected content type.

    ``accept_truncated`` keeps the first ``MAX_RESPONSE_BYTES`` of an
    over-cap response instead of discarding it, and marks the result
    ``truncated=True``. Off by default and used only for annual filings.

    The reason it is worth having is specific and measured. A 10-K's primary
    document routinely runs past 2MB, so the whole response was thrown away —
    and with it Item 1. Business, which is where the Competition section
    lives. But an annual report is an ORDERED document: Item 1 sits at the
    front, and truncation removes the end. Measured 2026-08-05, the first 2MB
    of the latest 10-K reaches the Competition text for Palantir (char 65k of
    555k), Shopify (38k of 411k), Caterpillar (154k of 351k) and Nvidia
    (35k of 373k, which fits whole).

    The truncation flag is not decoration. Nothing downstream may present a
    truncated filing as a complete one, and a break proof drives exactly that.
    """
    transport = transport or _default_transport
    redirects = []
    current = url
    try:
        current = validate_candidate_url(current)
        if resolver is not False:        # False disables DNS check in tests
            resolve_public_addresses(urlparse(current).hostname,
                                     resolver=resolver)
    except UnsafeURLRejected as exc:
        return FetchResult(ok=False, failure_type="blocked",
                           safe_message=str(exc), retryable=False,
                           final_url=current, redirects=redirects)

    for _hop in range(MAX_REDIRECTS + 1):
        try:
            status, headers, body, exceeded = transport(current, timeout)
        except urllib.error.HTTPError as exc:
            location = exc.headers.get("Location") if exc.headers else None
            if exc.code in (301, 302, 303, 307, 308) and location:
                from urllib.parse import urljoin
                target = urljoin(current, location)
                if not redirect_allowed(current, target):
                    return FetchResult(
                        ok=False, failure_type="unsafe_redirect",
                        safe_message=f"redirect to {urlparse(target).hostname}"
                                     " leaves the approved domain policy",
                        retryable=False, final_url=current,
                        redirects=redirects)
                try:
                    if resolver is not False:
                        resolve_public_addresses(urlparse(target).hostname,
                                                 resolver=resolver)
                except UnsafeURLRejected as unsafe:
                    return FetchResult(ok=False, failure_type="unsafe_redirect",
                                       safe_message=str(unsafe),
                                       retryable=False, final_url=current,
                                       redirects=redirects)
                redirects.append({"from": current, "to": target,
                                  "status": exc.code})
                current = target
                continue
            retryable = exc.code in (429, 500, 502, 503, 504)
            return FetchResult(ok=False, failure_type="http_status",
                               safe_message=f"HTTP {exc.code}",
                               status_code=exc.code, retryable=retryable,
                               final_url=current, redirects=redirects)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return FetchResult(ok=False, failure_type="timeout"
                               if "timed out" in str(exc).lower()
                               else "connection",
                               safe_message=str(exc)[:200], retryable=True,
                               final_url=current, redirects=redirects)

        if exceeded and not accept_truncated:
            return FetchResult(ok=False, failure_type="too_large",
                               safe_message=f"response exceeded "
                                            f"{MAX_RESPONSE_BYTES} bytes",
                               retryable=False, final_url=current,
                               redirects=redirects)
        truncated = bool(exceeded)
        mime = (headers.get("content-type") or "").split(";")[0].strip()
        accepted = tuple(ACCEPTED_MIME_PREFIXES) + tuple(extra_mime_prefixes)
        if mime and not any(mime.startswith(p) for p in accepted):
            return FetchResult(ok=False, failure_type="bad_mime",
                               safe_message=f"unsupported content type "
                                            f"{mime!r}",
                               retryable=False, final_url=current,
                               redirects=redirects)
        if binary:
            # Raw bytes for binary evidence (PDF). Decoding would destroy it.
            return FetchResult(ok=True, status_code=status, mime_type=mime,
                               body=body, final_url=current,
                               redirects=redirects, failure_type=None,
                               safe_message="", retryable=False,
                               truncated=truncated)
        try:
            text = body.decode("utf-8", errors="replace")
        except Exception:                                  # noqa: BLE001
            return FetchResult(ok=False, failure_type="parse_error",
                               safe_message="body could not be decoded",
                               retryable=False, final_url=current,
                               redirects=redirects)
        return FetchResult(ok=True, status_code=status, mime_type=mime,
                           body=text, final_url=current,
                           redirects=redirects, failure_type=None,
                           safe_message="", retryable=False,
                           truncated=truncated)

    return FetchResult(ok=False, failure_type="unsafe_redirect",
                       safe_message=f"more than {MAX_REDIRECTS} redirects",
                       retryable=False, final_url=current,
                       redirects=redirects)
